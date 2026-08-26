#!/usr/bin/env python
"""Closed-loop job-search orchestrator -- one command, the full cycle, on a
schedule:

    scrape (run_scrape) -> score (deterministic CGFE) -> shortlist_global
    -> verify_shortlist (live fetch, deterministic, free) -> draft generation
    for newly-CONFIRMED roles -> write review queue -> sleep -> repeat.

The loop ends at ``draft_ready``: a human reviews and approves via
``scripts/review.py``, then applies themselves on the employer's own site.
Nothing here ever submits an application anywhere -- that boundary is
deliberate, not a TODO.

Supersedes watch_jobs.py as the recommended entry point: this is a strict
superset (same scrape+score cycle, reused via ``watch_jobs.run_cycle``'s
building blocks -- not reimplemented -- plus shortlist/verify/draft/review
stages watch_jobs.py never had). watch_jobs.py is kept working standalone
(e.g. for install_watcher.ps1 / a lighter scrape+score-only cadence) rather
than deleted, since job_loop.py imports and reuses its cycle pieces directly;
they are not two independent implementations of the same loop.

Crash-tolerant per STAGE (not just per cycle): a dead board, a verify-fetch
timeout, or one bad draft can never take down the rest of that cycle, let
alone tomorrow's. Each stage logs its own stable error code via
core.telemetry.record_error and the cycle carries on with whatever the
earlier stages produced.

    python scripts/job_loop.py                 # loop forever, 6h interval
    python scripts/job_loop.py --once           # single cycle, then exit
    python scripts/job_loop.py --interval 4 --draft-cap 10
    python scripts/job_loop.py --profile candidate_profile.json --db path\\to\\crm.db

Stop with Ctrl-C (or SIGTERM) -- the current cycle finishes, then the loop
exits.
"""
from __future__ import annotations

import os
from pathlib import Path

# llm.client (used by generate_drafts' LLM draft calls) builds its Settings
# repository ONCE, at import time, from core.paths.app_data_dir() -- which
# resolves to a DIFFERENT default directory than the installed desktop app
# uses (see run_scrape.py's TAURI_DB / resolve_db comment). This must run
# BEFORE any backend module is imported below (generate_drafts.py has the
# same requirement and the same fix -- see its module docstring), or a draft
# LLM call would silently read llm_provider from an empty/unrelated database
# and fall back to ollama instead of the user's configured provider.
_TAURI_APP_DATA = Path.home() / "AppData" / "Roaming" / "com.vasudev-siddh.justhireme"
if _TAURI_APP_DATA.exists() and "JHM_APP_DATA_DIR" not in os.environ:
    os.environ["JHM_APP_DATA_DIR"] = str(_TAURI_APP_DATA)

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generate_drafts  # noqa: E402  sibling script
import run_scrape  # noqa: E402  sibling script
import shortlist_global  # noqa: E402  sibling script
import verify_shortlist  # noqa: E402  sibling script
import watch_jobs  # noqa: E402  sibling script -- reused for _Stop/signals/sleep/score_unscored_leads
from core.logging import get_logger  # noqa: E402
from core.telemetry import record_error  # noqa: E402
from data.sqlite.events import record_event  # noqa: E402
from data.sqlite.leads import get_all_leads, update_lead_status  # noqa: E402

_log = get_logger("scripts.job_loop")

DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent / "candidate_profile.json"
DEFAULT_DRAFTS_DIR = Path(__file__).resolve().parent / "drafts"

# Per-stage wall-clock ceilings (seconds) -- every stage already has its own
# inner per-request timeouts (30s/HTTP call in run_scrape, 15s/fetch in
# verify_shortlist, 120s/attempt x2 in the codex_cli subprocess), but nothing
# previously capped the STAGE as a whole, so a pathological case (e.g. a huge
# shortlist growth, or a hang somewhere outside those inner timeouts) could
# still stall an entire cycle -- and everything after it -- indefinitely. One
# generous ceiling per stage, well above its observed real-world duration
# (a full 165-target scrape + 419-lead shortlist + 3 LLM drafts took ~2m40s
# end to end), turns "stalled forever" into "logged as a timeout, cycle moves
# on" without touching the inner timeouts that already do the real work.
_SCRAPE_TIMEOUT_S = 20 * 60
_SCORE_TIMEOUT_S = 10 * 60
_VERIFY_TIMEOUT_S = 15 * 60
_DRAFT_TIMEOUT_S = 5 * 60  # per lead: comfortably above codex_cli's own 240s worst case
# A cycle also needs a ceiling. Per-stage ceilings alone can add up to nearly
# an hour, which turns one stuck source into a pipeline-wide stall. The
# observed end-to-end run is ~2m40s, so four minutes leaves headroom while
# ensuring the recurring worker reaches its next cycle.
DEFAULT_CYCLE_TIMEOUT_S = 4 * 60

# A lead at any of these statuses has already been through review (or was
# dropped) -- never draft it again just because it's still CONFIRMED.
_ALREADY_ACTIONED = {
    "draft_ready", "approved", "applied", "interviewing",
    "offer", "accepted", "rejected", "discarded",
}


def _select_newly_confirmed(shortlist: list[dict], verify_cache: dict, cap: int) -> list[dict]:
    """CONFIRMED roles (per the live-fetch verifier) not already in review.
    ``shortlist`` is already score-sorted, so taking the first ``cap`` keeps
    the highest-scoring confirmed roles."""
    out = []
    for lead in shortlist:
        result = verify_cache.get(lead.get("job_id"), {})
        if result.get("verdict") != "CONFIRMED":
            continue
        if str(lead.get("status") or "") in _ALREADY_ACTIONED:
            continue
        out.append(lead)
        if len(out) >= cap:
            break
    return out


def _log_cycle_event(job_id: str | None, action: str, db_path: str) -> None:
    """Audit-trail write for the cycle itself. Never allowed to break the
    cycle it's describing -- same fail-open contract as every other telemetry
    call in this codebase (core.telemetry.record_error/record_metric)."""
    try:
        record_event(job_id, action, db_path)
    except Exception as exc:
        _log.debug("cycle event log failed: %s", exc)


def write_review_queue(db_path: str, drafts_dir: Path) -> Path:
    """Snapshot of everything sitting at draft_ready, for a quick look without
    running review.py / touching the DB directly. review.py's ``list``
    command remains the source of truth; this is a convenience export."""
    leads = [lead for lead in get_all_leads(db_path) if str(lead.get("status") or "") == "draft_ready"]
    leads.sort(key=lambda lead: -int(lead.get("score") or 0))
    queue = [
        {
            "job_id": lead.get("job_id"), "title": lead.get("title"), "company": lead.get("company"),
            "url": lead.get("url"), "score": int(lead.get("score") or 0),
        }
        for lead in leads
    ]
    drafts_dir.mkdir(parents=True, exist_ok=True)
    path = drafts_dir / "review_queue.json"
    path.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


async def run_cycle(
    profile: dict, db_path: str, *,
    draft_cap: int = 20, drafts_dir: Path | None = None, verify_concurrency: int = verify_shortlist.CONCURRENCY,
) -> dict:
    """One full scrape -> score -> shortlist -> verify -> draft -> review-queue
    cycle. Each stage is independently crash-tolerant: an exception in one is
    logged with a stable error code and the cycle continues with whatever the
    prior stages produced, rather than aborting."""
    drafts_dir = drafts_dir or DEFAULT_DRAFTS_DIR
    stats: dict = {"errors": []}
    cycle_started_at = time.monotonic()
    _log_cycle_event(None, "cycle_started", db_path)

    try:
        stats["scrape"] = await asyncio.wait_for(
            run_scrape.run_once(profile, db_path, announce=False), timeout=_SCRAPE_TIMEOUT_S,
        )
    except TimeoutError:
        _log.error("scrape stage timed out after %ds", _SCRAPE_TIMEOUT_S)
        record_error("job_loop_scrape_timeout", f"exceeded {_SCRAPE_TIMEOUT_S}s", "scripts.job_loop")
        stats["errors"].append("scrape")
        stats["scrape"] = {}
    except Exception as exc:
        _log.exception("scrape stage failed")
        record_error("job_loop_scrape_failed", str(exc), "scripts.job_loop")
        stats["errors"].append("scrape")
        stats["scrape"] = {}

    cfg = watch_jobs._load_cfg(db_path)
    try:
        stats["score"] = await asyncio.wait_for(
            watch_jobs.score_unscored_leads(profile, cfg, db_path), timeout=_SCORE_TIMEOUT_S,
        )
    except TimeoutError:
        _log.error("score stage timed out after %ds", _SCORE_TIMEOUT_S)
        record_error("job_loop_score_timeout", f"exceeded {_SCORE_TIMEOUT_S}s", "scripts.job_loop")
        stats["errors"].append("score")
        stats["score"] = {}
    except Exception as exc:
        _log.exception("score stage failed")
        record_error("job_loop_score_failed", str(exc), "scripts.job_loop")
        stats["errors"].append("score")
        stats["score"] = {}

    shortlist: list[dict] = []
    try:
        shortlist = shortlist_global.filtered_ranked_leads(get_all_leads(db_path))
    except Exception as exc:
        _log.exception("shortlist stage failed")
        record_error("job_loop_shortlist_failed", str(exc), "scripts.job_loop")
        stats["errors"].append("shortlist")
    stats["shortlist_size"] = len(shortlist)

    verify_cache: dict = {}
    if shortlist:
        try:
            verify_cache = await asyncio.wait_for(
                verify_shortlist.run(shortlist, db_path, fresh=False, concurrency=verify_concurrency),
                timeout=_VERIFY_TIMEOUT_S,
            )
        except TimeoutError:
            _log.error("verify stage timed out after %ds", _VERIFY_TIMEOUT_S)
            record_error("job_loop_verify_timeout", f"exceeded {_VERIFY_TIMEOUT_S}s", "scripts.job_loop")
            stats["errors"].append("verify")
        except Exception as exc:
            _log.exception("verify stage failed")
            record_error("job_loop_verify_failed", str(exc), "scripts.job_loop")
            stats["errors"].append("verify")
    verify_counts: dict[str, int] = {}
    for lead in shortlist:
        verdict = verify_cache.get(lead.get("job_id"), {}).get("verdict", "")
        verify_counts[verdict] = verify_counts.get(verdict, 0) + 1
    stats["verify"] = verify_counts

    drafted, draft_failed = 0, 0
    if verify_cache:
        pending = _select_newly_confirmed(shortlist, verify_cache, draft_cap)
        for lead in pending:
            try:
                # generate_draft is a blocking call (it shells out to codex_cli
                # synchronously) -- run it on a thread so a single stuck draft
                # can be timed out instead of blocking every draft after it
                # (and the whole cycle) for however long that one call hangs.
                await asyncio.wait_for(
                    asyncio.to_thread(generate_drafts.generate_draft, profile, lead, drafts_dir, db_path),
                    timeout=_DRAFT_TIMEOUT_S,
                )
                update_lead_status(lead["job_id"], "draft_ready", db_path)
                drafted += 1
            except TimeoutError:
                draft_failed += 1
                _log.warning("draft generation timed out (>%ds) for %s", _DRAFT_TIMEOUT_S, lead.get("job_id", "?"))
                record_error("job_loop_draft_timeout", f"exceeded {_DRAFT_TIMEOUT_S}s", "scripts.job_loop")
            except Exception as exc:
                draft_failed += 1
                _log.warning("draft generation failed for %s: %s", lead.get("job_id", "?"), exc)
                record_error("job_loop_draft_failed", str(exc), "scripts.job_loop")
    stats["drafted"] = drafted
    stats["draft_failed"] = draft_failed

    try:
        write_review_queue(db_path, drafts_dir)
    except Exception as exc:
        _log.warning("review-queue snapshot failed: %s", exc)
        stats["errors"].append("review_queue")

    duration_s = round(time.monotonic() - cycle_started_at, 1)
    stats["duration_s"] = duration_s
    _log_cycle_event(
        None,
        f"cycle_finished duration_s={duration_s} added={(stats.get('scrape') or {}).get('added', 0)} "
        f"shortlist={stats.get('shortlist_size', 0)} confirmed={(stats.get('verify') or {}).get('CONFIRMED', 0)} "
        f"drafted={stats.get('drafted', 0)} errors={len(stats.get('errors') or [])}",
        db_path,
    )
    return stats


async def watch(
    profile: dict, db_path: str, *, interval_hours: float, once: bool,
    draft_cap: int, drafts_dir: Path, verify_concurrency: int,
    cycle_timeout_s: float | None = DEFAULT_CYCLE_TIMEOUT_S,
    stop: watch_jobs._Stop | None = None,
) -> int:
    """Run cycles until ``once`` is set, or ``stop.requested`` flips true.
    Mirrors watch_jobs.watch()'s driver exactly (reuses its _Stop /
    _sleep_interruptibly rather than re-implementing them)."""
    stop = stop or watch_jobs._Stop()
    cycle = 0
    while True:
        cycle += 1
        _log.info("cycle %d starting", cycle)
        try:
            run = run_cycle(
                profile, db_path, draft_cap=draft_cap, drafts_dir=drafts_dir, verify_concurrency=verify_concurrency,
            )
            stats = await asyncio.wait_for(run, timeout=cycle_timeout_s) if cycle_timeout_s else await run
            _log.info(
                "cycle %d done: +%d leads, shortlist=%d, confirmed=%d, drafted=%d, errors=%s",
                cycle, (stats.get("scrape") or {}).get("added", 0), stats.get("shortlist_size", 0),
                (stats.get("verify") or {}).get("CONFIRMED", 0), stats.get("drafted", 0), stats.get("errors") or [],
                extra={"domain": "job_loop"},
            )
        except TimeoutError:
            _log.error("cycle %d timed out after %ss", cycle, cycle_timeout_s)
            record_error("job_loop_cycle_timeout", f"exceeded {cycle_timeout_s}s", "scripts.job_loop")
        except Exception as exc:
            # Should be unreachable -- every stage inside run_cycle already
            # catches its own exceptions. Kept as the same last-resort net
            # watch_jobs.py has, so a bug in the orchestration glue itself
            # still can't kill tomorrow's cycle.
            _log.exception("cycle %d failed", cycle)
            record_error("job_loop_cycle_failed", str(exc), "scripts.job_loop")
        if once or stop.requested:
            break
        _log.info("sleeping %.1fh until next cycle", interval_hours)
        await watch_jobs._sleep_interruptibly(interval_hours * 3600, stop)
        if stop.requested:
            break
    _log.info("job_loop stopped after %d cycle(s)", cycle)
    return cycle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interval", type=float, default=6.0, help="hours between cycles (default 6)")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE_PATH), help="candidate profile JSON path")
    parser.add_argument("--db", default=None, help="database file (defaults to the installed app's)")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit (testing / smoke run)")
    parser.add_argument("--draft-cap", type=int, default=20, help="max NEW drafts generated per cycle (default 20)")
    parser.add_argument("--out", default=str(DEFAULT_DRAFTS_DIR), help="drafts output directory")
    parser.add_argument("--verify-concurrency", type=int, default=verify_shortlist.CONCURRENCY)
    parser.add_argument(
        "--cycle-timeout-minutes", type=float, default=DEFAULT_CYCLE_TIMEOUT_S / 60,
        help="whole-cycle watchdog; 0 disables it (default 4 minutes)",
    )
    args = parser.parse_args()

    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    db_path = run_scrape.resolve_db(args.db)
    stop = watch_jobs._Stop()
    watch_jobs._install_signal_handlers(stop)
    _log.info(
        "job_loop starting: db=%s interval=%.1fh once=%s draft_cap=%d cycle_timeout=%.1fm",
        db_path, args.interval, args.once, args.draft_cap, args.cycle_timeout_minutes,
    )
    asyncio.run(watch(
        profile, db_path, interval_hours=args.interval, once=args.once,
        draft_cap=args.draft_cap, drafts_dir=Path(args.out),
        verify_concurrency=args.verify_concurrency,
        cycle_timeout_s=max(0.0, args.cycle_timeout_minutes * 60) or None,
        stop=stop,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
