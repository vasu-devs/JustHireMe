from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from api.dependencies import get_repository
from automation.ghost import create_ghost_tick  # noqa: F401  (re-exported: main.py builds the tick here)
from api.startup_validation import log_startup_warnings
from data.sqlite.connection import checkpoint_wal, close_all, init_sql, prune_history
from opportunities.orchestrator import OPPORTUNITY_SCANS
from opportunities.scheduled import create_scheduled_opportunity_tick

WAL_CHECKPOINT_INTERVAL_MINUTES = 5
OPPORTUNITY_REFRESH_INTERVAL_HOURS = 3


def create_scheduler() -> AsyncIOScheduler:
    return AsyncIOScheduler()


def ensure_ghost_job(scheduler: AsyncIOScheduler, ghost_tick) -> None:
    if not scheduler.get_job("ghost"):
        # max_instances=1 + coalesce: a ghost cycle (scan→eval→generate→apply)
        # can outlast the 6h interval; never let a second copy start on top of a
        # still-running one, and collapse any ticks missed while it ran into one.
        scheduler.add_job(
            ghost_tick, "interval", hours=6, id="ghost",
            max_instances=1, coalesce=True,
        )


def ensure_wal_checkpoint_job(scheduler: AsyncIOScheduler) -> None:
    # See checkpoint_wal()'s docstring: without a periodic PASSIVE checkpoint,
    # a long scan/rescore session leaves the WAL file growing unbounded (measured
    # at ~70MB, nearly the size of the main db) and every dashboard read has to
    # reconstruct pages across the whole thing -- 7x+ slower than a checkpointed
    # WAL. PASSIVE never blocks a concurrent reader/writer.
    if not scheduler.get_job("wal_checkpoint"):
        scheduler.add_job(
            checkpoint_wal, "interval", minutes=WAL_CHECKPOINT_INTERVAL_MINUTES,
            id="wal_checkpoint", max_instances=1, coalesce=True,
        )


def ensure_opportunity_refresh_job(scheduler: AsyncIOScheduler, opportunity_tick) -> None:
    if not scheduler.get_job("opportunity_refresh"):
        scheduler.add_job(
            opportunity_tick,
            "interval",
            hours=OPPORTUNITY_REFRESH_INTERVAL_HOURS,
            id="opportunity_refresh",
            max_instances=1,
            coalesce=True,
        )


def _run_lead_hygiene_migration(logger) -> None:
    """One-shot repair of stored lead rows (legacy HN comment-dump titles,
    RemoteOK spam blurbs/mojibake). Flag-gated so every install pays the cost
    exactly once; the repair itself is also idempotent as a second guard."""
    try:
        repo = get_repository()
        if (repo.settings.get_settings() or {}).get("lead_hygiene_v3") == "done":
            return
        # Dynamic import: the api layer reaches domain packages through
        # import_module by design (see api.dependencies._local_service).
        from importlib import import_module
        counts = import_module("discovery.maintenance").normalize_stored_leads()
        repo.settings.save_settings({"lead_hygiene_v3": "done"})
        logger.info(
            "lead hygiene migration: %s titles fixed, %s descriptions cleaned",
            counts.get("titles_fixed", 0), counts.get("descriptions_cleaned", 0),
        )
    except Exception as exc:
        logger.warning("lead hygiene migration skipped: %s", exc)


def create_lifespan(scheduler: AsyncIOScheduler, ghost_tick, logger):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_sql()
        prune_history()  # cap the append-only telemetry tables on startup
        checkpoint_wal()  # fold in any WAL left oversized by a prior session before the first request
        _run_lead_hygiene_migration(logger)
        ensure_ghost_job(scheduler, ghost_tick)
        ensure_wal_checkpoint_job(scheduler)
        opportunity_tick = create_scheduled_opportunity_tick(get_repository(), logger)
        ensure_opportunity_refresh_job(scheduler, opportunity_tick)
        log_startup_warnings(get_repository(), logger)
        scheduler.start()

        # Warm real semantic embeddings in the background: auto-download the ONNX model
        # if it's missing so ranking uses meaning-level fit (not the near-random hash
        # fallback) by default, with no manual setup. Non-blocking — the scan uses hash
        # until the model is ready, then upgrades automatically.
        async def _warm_embeddings() -> None:
            try:
                from data.vector.embeddings import ensure_onnx_model
                active = await asyncio.to_thread(ensure_onnx_model)
                logger.info("embedding warm-up done (onnx active=%s)", active)
            except Exception as exc:
                logger.warning("embedding warm-up skipped: %s", exc)

        warm_task = asyncio.create_task(_warm_embeddings())

        # Warm the OS/SQLite page cache for the leads table: a freshly-started
        # process's first GET /api/v1/leads pays a genuine cold-disk-read cost
        # for the ~80MB db file (measured 3-4s cold vs 0.5-0.7s once the pages
        # are cached -- confirmed by repeating the same query in-process, not
        # a code path difference). Runs the identical read list_leads() does
        # (classify_pending_seniority + get_all_leads) so a real UI load
        # shortly after startup hits a warm cache instead of being the one
        # that pays this cost. Best-effort background task, same shape as
        # _warm_embeddings above -- never blocks startup or user requests.
        async def _warm_leads_cache() -> None:
            try:
                from gateway.lead_adapters import classify_job_seniority

                repo = get_repository()
                await asyncio.to_thread(repo.leads.classify_pending_seniority, classify_job_seniority)
                await asyncio.to_thread(repo.leads.get_all_leads)
            except Exception as exc:
                logger.warning("leads cache warm-up skipped: %s", exc)

        leads_warm_task = asyncio.create_task(_warm_leads_cache())
        logger.info("FastAPI live.")
        try:
            yield
        finally:
            warm_task.cancel()
            leads_warm_task.cancel()
            await OPPORTUNITY_SCANS.shutdown()
            scheduler.shutdown(wait=False)
            close_all()
        logger.info("FastAPI shutdown.")

    return lifespan
