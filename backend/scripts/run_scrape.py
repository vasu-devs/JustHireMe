#!/usr/bin/env python
"""Run the full job scrape locally and build the job dataset.

One command, no backend server, no API keys — every source it touches is a
keyless public JSON/RSS endpoint. Leads land in the same SQLite database the
desktop app reads, so anything collected here shows up in the UI.

    python scripts/run_scrape.py --profile me.json     # scrape for a profile
    python scripts/run_scrape.py --query ".NET AWS"    # scrape for a keyword
    python scripts/run_scrape.py --stats               # what's already stored

``--profile`` takes a JSON file of the shape ``{"title": "...", "skills": [...]}``.
Without one, ``--query`` is used to drive the search-first boards directly.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.company_seeds import ats_seed_targets, workday_seed_targets  # noqa: E402
from core.config import DEFAULT_JOB_TARGETS  # noqa: E402
from data.sqlite.leads import DEFAULT_DB_PATH, get_connection, save_lead  # noqa: E402
from discovery.lead_intel import canonical_lead_id  # noqa: E402
from discovery.sources.aggregator import _fetch_arbeitnow  # noqa: E402
from discovery.sources.ats import is_ats_target, scrape_target as scrape_ats_target  # noqa: E402
from discovery.sources.hackernews import scrape_hn_hiring  # noqa: E402
from discovery.sources.rss import (  # noqa: E402
    is_rss_target,
    scrape_jobicy_api,
    scrape_remoteok,
    scrape_remotive,
    scrape_rss,
    scrape_working_nomads,
)

CONCURRENCY = 6


async def dispatch_target(target: str) -> list[dict]:
    """Route one target to the scraper that actually understands it.

    This used to be a single call to ``ats.scrape_target`` for every target,
    including the plain feeds in ``DEFAULT_JOB_TARGETS``. That function only
    recognizes ``ats:``-prefixed targets and direct ATS-host URLs -- every
    other target (hn-hiring, remoteok, remotive, jobicy, weworkremotely,
    arbeitnow) fell through its unmatched branch and returned ``[]`` with no
    exception raised, so the "+"/"!" logging in ``_scrape_all`` never printed
    a line for them either. Net effect: those 6-7 sources contributed zero
    leads on *every* run, silently. Mirrors the routing table in
    ``automation/scout.py``'s ``run()``.
    """
    lower = target.lower()
    if "hn-hiring" in lower or "news.ycombinator.com" in lower:
        return await scrape_hn_hiring()
    if "remoteok.com/api" in lower:
        return await scrape_remoteok()
    if "remotive.com/api" in lower:
        return await scrape_remotive(target)
    if "jobicy.com/api" in lower:
        return await scrape_jobicy_api(target)
    if "workingnomads.com/api" in lower:
        return await scrape_working_nomads()
    if "arbeitnow.com/api" in lower:
        # Same endpoint discovery.sources.aggregator queries; empty role_terms
        # means _matches_role keeps everything, i.e. the unfiltered board.
        return await _fetch_arbeitnow([])
    if is_rss_target(target):
        return await scrape_rss(target)
    if is_ats_target(target):
        return await scrape_ats_target(target)
    return []


def _board_targets(boards_file: Path) -> list[str]:
    """Read a ``[{"provider": ..., "slug": ..., "jobs": ...}, ...]`` file
    written by ``probe_ai_boards.py`` / ``probe_new_boards.py`` into
    ``ats:<provider>:<slug>`` targets. Missing/unreadable is not fatal -- the
    rest of the target pool still runs."""
    if not boards_file.exists():
        return []
    try:
        boards = json.loads(boards_file.read_text(encoding="utf-8"))
        return [f"ats:{board['provider']}:{board['slug']}" for board in boards]
    except (ValueError, KeyError, TypeError) as exc:
        print(f"  ! {boards_file.name} unreadable ({type(exc).__name__}), skipping")
        return []

# The desktop app stores its database under its Tauri bundle id, while the
# backend resolves to %LOCALAPPDATA%/JustHireMe. Scraping into the latter fills a
# database the installed app never opens, so prefer the app's own file when it
# exists — one dataset, whichever way it was collected.
TAURI_DB = Path.home() / "AppData" / "Roaming" / "com.vasudev-siddh.justhireme" / "crm.db"


def resolve_db(explicit: str | None) -> str:
    if explicit:
        return explicit
    if TAURI_DB.exists():
        return str(TAURI_DB)
    return DEFAULT_DB_PATH


def _stats(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        scored = conn.execute("SELECT COUNT(*) FROM leads WHERE signal_score > 0").fetchone()[0]
        print(f"\n  {total:,} leads stored, {scored:,} scored\n")
        rows = conn.execute(
            "SELECT platform, COUNT(*) c FROM leads GROUP BY platform ORDER BY c DESC"
        ).fetchall()
        for platform, count in rows:
            print(f"    {platform or 'unknown'!s:22} {count:6,}")
        print()
    finally:
        conn.close()


async def _scrape_all(targets: list[str]) -> list[dict]:
    """Fan out across targets, tolerating individual board failures.

    A dead board is normal — slugs drift and employers migrate ATS — so one
    failure must never abort a scan that other sources are still filling.
    """
    sem = asyncio.Semaphore(CONCURRENCY)
    done = 0

    async def one(target: str) -> list[dict]:
        nonlocal done
        async with sem:
            try:
                leads = await dispatch_target(target)
            except Exception as exc:
                leads = []
                print(f"    ! {target[:52]:52} {type(exc).__name__}")
            done += 1
            if leads:
                print(f"    + {target[:52]:52} {len(leads):4} jobs   [{done}/{len(targets)}]")
            return leads

    batches = await asyncio.gather(*(one(t) for t in targets))
    return [lead for batch in batches for lead in batch]


def _ingest(leads: list[dict], db_path: str) -> tuple[int, int]:
    """Write leads, giving each a stable id derived from its URL.

    Raw scraper dicts carry no ``job_id`` and ``save_lead`` is INSERT OR IGNORE
    keyed on it — without this every scrape collapses into a single row while
    still reporting success.
    """
    conn = get_connection(db_path)
    try:
        before = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    finally:
        conn.close()

    written = 0
    for lead in leads:
        url = str(lead.get("url") or "").strip()
        if not url:
            continue
        lead = dict(lead)
        lead.setdefault("job_id", canonical_lead_id(url))
        meta = lead.get("source_meta")
        if isinstance(meta, dict):
            lead["source_meta"] = json.dumps(meta)
        try:
            save_lead(lead, db_path)
            written += 1
        except Exception as exc:
            print(f"    ! save failed for {url[:48]}: {type(exc).__name__}")

    conn = get_connection(db_path)
    try:
        after = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    finally:
        conn.close()
    return written, after - before


def build_targets(profile: dict) -> list[str]:
    """Full target pool for one profile: generic feeds + auto-derived ATS/Workday
    boards + probed AI/new boards + Himalayas + NoDesk RSS.

    Extracted out of ``main()`` so ``scripts/watch_jobs.py`` scrapes the exact
    same source pool on a schedule instead of re-deriving it.
    """
    targets = [t for t in DEFAULT_JOB_TARGETS if t.startswith("http")]
    targets += ats_seed_targets(profile)
    targets += workday_seed_targets(profile)

    # Boards discovered by scripts/probe_ai_boards.py (greenhouse/lever/ashby,
    # AI-sector) and scripts/probe_new_boards.py (teamtailor/rippling/breezy/
    # pinpoint/bamboohr). Both files are the same {provider, slug, jobs} shape,
    # so one loader covers them; they run alongside the generic pool rather
    # than replacing it.
    core_dir = Path(__file__).resolve().parents[1] / "core"
    for boards_file in (core_dir / "ai_boards.json", core_dir / "new_boards.json"):
        targets += _board_targets(boards_file)

    # Himalayas is one flat global-remote feed, not a per-company board -- no
    # slug to loop over. NoDesk is a plain RSS feed (main + engineering, the
    # category actually relevant to this profile); dispatch_target already
    # routes any *.xml/*.rss target through the generic RSS scraper.
    targets.append("ats:himalayas")
    targets += [
        "https://nodesk.co/remote-jobs/index.xml",
        "https://nodesk.co/remote-jobs/engineering/index.xml",
        # Working Nomads' full feed -- verified live keyless API (its own
        # ?category= param is a confirmed no-op, see scrape_working_nomads).
        "https://www.workingnomads.com/api/exposed_jobs/",
        # Jobicy's geo=apac IS a real, verified filter (confirmed against
        # geo=usa/asia/india returning genuinely different -- or, for the
        # latter two, zero -- results) and surfaces APAC/India-eligible roles
        # the default recency-sorted count=50 pull otherwise crowds out.
        "https://jobicy.com/api/v2/remote-jobs?count=50&geo=apac",
        # WeWorkRemotely category feeds -- verified genuinely distinct content
        # per category (not the Remotive/Working Nomads no-op trap), and each
        # item carries a <region> tag (captured by scrape_rss) that a flat
        # /remote-jobs.rss pull alone would still see, just diluted across
        # every non-engineering category competing for the same 100-item cap.
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    ]
    return targets


async def run_once(profile: dict, db_path: str, *, announce: bool = True) -> dict:
    """Scrape + ingest one cycle for ``profile`` into ``db_path``.

    Returns ``{"targets", "scraped", "written", "added"}``. Shared by ``main()``
    (one-shot CLI run) and ``scripts/watch_jobs.py`` (the recurring loop) so the
    scrape+ingest glue exists exactly once.
    """
    targets = build_targets(profile)
    if announce:
        print(f"\n  scraping {len(targets)} sources for: {profile.get('title') or profile.get('s') or 'profile'}\n")
    leads = await _scrape_all(targets)
    if announce:
        print(f"\n  {len(leads)} jobs scraped")
    written, added = _ingest(leads, db_path)
    if announce:
        print(f"  {written} written, {added} new (rest already known)")
    return {"targets": len(targets), "scraped": len(leads), "written": written, "added": added}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", help="path to a profile JSON file")
    parser.add_argument("--query", default="", help="keyword for search-first boards")
    parser.add_argument("--db", default=None, help="database file (defaults to the app's)")
    parser.add_argument("--stats", action="store_true", help="show stored counts and exit")
    args = parser.parse_args()
    args.db = resolve_db(args.db)

    if args.stats:
        _stats(args.db)
        return 0

    profile: dict = {}
    if args.profile:
        profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    if args.query:
        profile.setdefault("title", args.query)
    if not profile:
        print("  need --profile or --query (see --help)")
        return 2

    await run_once(profile, args.db)
    _stats(args.db)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
