#!/usr/bin/env python
"""Continuously-running local job-discovery loop: scrape + score only.

For the FULL closed loop (this cycle, plus shortlist -> verify -> draft
generation -> review queue), use ``scripts/job_loop.py`` instead -- it imports
and reuses ``run_cycle``/``score_unscored_leads``/``_Stop``/``_sleep_interruptibly``
from THIS module rather than re-implementing them, so there is one scrape+score
implementation, not two. This script remains useful standalone for a lighter
scrape+score-only cadence (e.g. install_watcher.ps1 / Task Scheduler).

Each cycle: scrape (the same target pool as ``run_scrape.py``) -> ingest ->
score any still-unscored leads with the deterministic CGFE rubric (no LLM, no
API key, no cost) -> log a one-line summary. Crash-tolerant: an exception in
one cycle is logged with a stable error code and the loop keeps going -- a
dead board or a locked DB must never stop tomorrow's cycle from running.

    python scripts/watch_jobs.py                  # loop forever, 6h interval
    python scripts/watch_jobs.py --interval 2      # every 2 hours
    python scripts/watch_jobs.py --once            # single cycle, then exit
    python scripts/watch_jobs.py --profile candidate_profile.json --db path\\to\\crm.db

Stop with Ctrl-C (or SIGTERM) -- the current cycle finishes, then the loop
exits. See install_watcher.ps1 to run this persistently via Windows Task
Scheduler instead of a foreground terminal.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sqlite3
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_scrape  # noqa: E402  # sibling script -- scripts/ is on sys.path[0] when run directly
from core.logging import get_logger  # noqa: E402
from core.telemetry import record_error  # noqa: E402
from data.sqlite.leads import get_all_leads, update_lead_score  # noqa: E402
from ranking.service import create_ranking_service  # noqa: E402

_log = get_logger("scripts.watch_jobs")

DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent / "candidate_profile.json"


def _load_cfg(db_path: str) -> dict:
    """Read the settings table straight from the DB we were told to scan.

    Not the default repository singleton: that resolves its own app-data dir,
    which can differ from ``db_path`` (see ``run_scrape.resolve_db`` -- the
    installed desktop app and a bare backend checkout use different default
    locations). Settings (llm_provider, thresholds, ...) must come from the
    SAME database as the leads being scored.
    """
    conn = sqlite3.connect(db_path)
    try:
        return {k: v for k, v in conn.execute("SELECT key, val FROM settings")}
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


async def score_unscored_leads(profile: dict, cfg: dict, db_path: str) -> dict:
    """Deterministic-only CGFE scoring pass (``use_llm=False``) over every lead
    still at score=0. Same approach as ``scripts/rescore_unscored.py``, wrapped
    as a function so the watch loop can call it every cycle without spawning
    a subprocess."""
    svc = create_ranking_service()
    leads = [lead for lead in get_all_leads(db_path) if int(lead.get("score") or 0) == 0]
    scored = 0
    failed = 0
    sem = asyncio.Semaphore(12)

    async def _one(lead: dict) -> None:
        nonlocal scored, failed
        async with sem:
            try:
                result = await svc.evaluate_lead(lead, profile, cfg, use_llm=False)
                await asyncio.to_thread(
                    update_lead_score,
                    lead["job_id"], result["score"], result.get("reason", ""),
                    result.get("match_points", []), result.get("gaps", []),
                    preserve_status=True, scored_by=result.get("scored_by", ""), db_path=db_path,
                )
                scored += 1
            except Exception as exc:
                failed += 1
                _log.warning("score failed for %s: %s", lead.get("job_id", "?"), exc)

    await asyncio.gather(*(_one(lead) for lead in leads))
    return {"unscored": len(leads), "scored": scored, "failed": failed}


async def run_cycle(profile: dict, db_path: str) -> dict:
    """One full scrape -> ingest -> score cycle.

    Raises on failure -- crash-tolerance is the CALLER's job (the loop below),
    not this function's; keeping it exception-transparent is what makes it
    independently testable/mockable.
    """
    t0 = time.monotonic()
    before = len(get_all_leads(db_path))
    scrape_stats = await run_scrape.run_once(profile, db_path, announce=False)
    cfg = _load_cfg(db_path)
    score_stats = await score_unscored_leads(profile, cfg, db_path)
    after = len(get_all_leads(db_path))
    return {
        "duration_s": round(time.monotonic() - t0, 1),
        "leads_before": before,
        "leads_after": after,
        **scrape_stats,
        **score_stats,
    }


class _Stop:
    """Cooperative shutdown flag flipped by SIGINT/SIGTERM."""

    requested = False


def _install_signal_handlers(stop: _Stop) -> None:
    def _handle(signum, _frame):
        _log.info("shutdown requested (signal=%s) -- finishing current cycle", signum)
        stop.requested = True

    signal.signal(signal.SIGINT, _handle)
    # SIGTERM is registerable on Windows too (delivered when something signals
    # the process rather than hard-killing it); harmless to register even
    # where nothing ever sends it.
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle)


async def _sleep_interruptibly(seconds: float, stop: _Stop) -> None:
    """Sleep in short slices so a shutdown request is honored within ~30s
    instead of blocking for the full interval before the flag is checked."""
    remaining = seconds
    while remaining > 0 and not stop.requested:
        step = min(30.0, remaining)
        await asyncio.sleep(step)
        remaining -= step


async def watch(profile: dict, db_path: str, *, interval_hours: float, once: bool, stop: _Stop | None = None) -> int:
    """Run cycles until ``once`` is set, or ``stop.requested`` flips true.
    Returns the number of cycles run (tests pass a pre-armed ``stop``)."""
    stop = stop or _Stop()
    cycle = 0
    while True:
        cycle += 1
        _log.info("cycle %d starting", cycle)
        try:
            stats = await run_cycle(profile, db_path)
            _log.info(
                "cycle %d done: +%d new leads (%d total), %d scored, %d unscored-failed, %.1fs",
                cycle, stats["added"], stats["leads_after"], stats["scored"], stats["failed"], stats["duration_s"],
                extra={"domain": "watch_jobs", "duration_ms": round(stats["duration_s"] * 1000, 1)},
            )
        except Exception as exc:
            # THIS except is the one thing standing between "one flaky board /
            # locked DB / network blip" and a watcher that quietly stops running
            # overnight. Log with a stable error code and keep looping.
            _log.exception("cycle %d failed", cycle)
            record_error("watch_cycle_failed", str(exc), "scripts.watch_jobs")
        if once or stop.requested:
            break
        _log.info("sleeping %.1fh until next cycle", interval_hours)
        await _sleep_interruptibly(interval_hours * 3600, stop)
        if stop.requested:
            break
    _log.info("watcher stopped after %d cycle(s)", cycle)
    return cycle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interval", type=float, default=6.0, help="hours between cycles (default 6)")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE_PATH), help="candidate profile JSON path")
    parser.add_argument("--db", default=None, help="database file (defaults to the installed app's)")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit (testing / Task Scheduler)")
    args = parser.parse_args()

    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    db_path = run_scrape.resolve_db(args.db)
    stop = _Stop()
    _install_signal_handlers(stop)
    _log.info("watch_jobs starting: db=%s interval=%.1fh once=%s", db_path, args.interval, args.once)
    asyncio.run(watch(profile, db_path, interval_hours=args.interval, once=args.once, stop=stop))
    return 0


if __name__ == "__main__":
    sys.exit(main())
