from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone

from api.dependencies import get_discovery_service, get_job_runner, get_ranking_service, get_repository
from api.rate_limit import RateLimiter, require_rate_limit
from core.logging import get_logger
from core.telemetry import record_error
from data.repository import Repository
from gateway.discovery_config import (
    free_sources_enabled,
    has_explicit_discovery_targets,
    has_profile_discovery_signal,
    has_x_token,
    int_cfg,
    job_targets,
    profile_for_discovery,
    truthy,
)


_scan_limiter = RateLimiter(3, 60)
_log = get_logger(__name__)

REEVALUATION_STATUS_LOCKS = {"approved", "applied", "interviewing", "rejected", "accepted", "discarded"}


class TaskRegistry:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task] = {}
        self._stops: dict[str, asyncio.Event] = {}

    async def start(self, name: str, coro_factory, *, mutex_with: list[str] | None = None) -> bool:
        async with self._lock:
            for check_name in [name, *(mutex_with or [])]:
                task = self._tasks.get(check_name)
                if task and not task.done():
                    return False

            stop = asyncio.Event()
            self._stops[name] = stop

            async def _wrapper() -> None:
                try:
                    await coro_factory(stop)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    _log.error("background task %s failed: %s", name, exc)
                finally:
                    async with self._lock:
                        if self._tasks.get(name) is task:
                            self._tasks.pop(name, None)
                            self._stops.pop(name, None)

            task = asyncio.create_task(_wrapper())
            self._tasks[name] = task
            return True

    async def stop(self, name: str) -> bool:
        async with self._lock:
            task = self._tasks.get(name)
            stop = self._stops.get(name)
            if not task or task.done() or stop is None:
                return False
            stop.set()
            return True

    async def is_running(self, name: str) -> bool:
        async with self._lock:
            task = self._tasks.get(name)
            return bool(task and not task.done())

    async def status(self) -> dict[str, bool]:
        return {
            "scanning": await self.is_running("scan"),
            "reevaluating": await self.is_running("reevaluate"),
        }


TASKS = TaskRegistry()


def _merge_scan_usage(total: dict, incoming: dict, target_count: int) -> None:
    total["configured"] = total.get("configured", 0) + target_count
    for key in ("executed", "candidates", "saved", "duplicates", "filtered", "missing_url", "errors"):
        total[key] = total.get(key, 0) + int(incoming.get(key, 0) or 0)
    for key, value in (incoming.get("by_source") or {}).items():
        total.setdefault("by_source", {})[key] = value


def _record_scan_telemetry(summary: dict) -> None:
    """Persist a completed scan as lifetime counters + a last-scan snapshot.

    Best-effort and fail-silent: telemetry must never break or slow a scan, so
    the underlying helpers swallow their own errors. This answers "how many leads
    did the last scan yield, and why were the rest dropped?" from /diagnostics.
    """
    from core.telemetry import incr_metrics, set_metric_state

    incr_metrics({
        "scans_run": 1,
        "leads_found": int(summary.get("candidates", 0) or 0),
        "leads_saved": int(summary.get("saved", 0) or 0),
        "leads_duplicate": int(summary.get("duplicates", 0) or 0),
        "leads_filtered": int(summary.get("filtered", 0) or 0),
        "leads_scored": int(summary.get("scored", 0) or 0),
        "eval_fallback": int(summary.get("fallback", 0) or 0),
        "eval_prefiltered": int(summary.get("prefiltered", 0) or 0),
    })
    set_metric_state("last_scan", summary)


def _target_batches(urls: list[str], size: int) -> list[list[str]]:
    size = max(1, size)
    return [urls[index:index + size] for index in range(0, len(urls), size)]


def should_preserve_job_status(status: str) -> bool:
    return status in REEVALUATION_STATUS_LOCKS


async def broadcast_x_source_errors(manager, errors: list[str]) -> None:
    if not errors:
        return
    for msg in errors[:3]:
        await manager.broadcast({"type": "agent", "event": "x_source_error", "msg": f"X source skipped: {msg}"})
    if len(errors) > 3:
        await manager.broadcast({"type": "agent", "event": "x_source_error", "msg": f"{len(errors) - 3} more X queries were skipped"})


async def run_x_signal_scan(
    manager,
    cfg: dict,
    kind_filter: str | None = None,
    profile: dict | None = None,
    discovery_service=None,
) -> list[dict]:
    if not has_x_token(cfg):
        return []

    discovery_service = discovery_service or get_discovery_service()
    kind_filter = "job"
    label = "job leads"
    await manager.broadcast({"type": "agent", "event": "x_scout_start", "msg": f"Scanning X for {label}..."})
    result = await discovery_service.scan_x(cfg, kind_filter=kind_filter, profile=profile)
    leads = result.leads
    usage = result.usage
    await manager.broadcast({"type": "agent", "event": "x_scout_done", "msg": f"X scout - {len(leads)} {label} found"})
    if usage.get("executed_queries"):
        await manager.broadcast({
            "type": "agent",
            "event": "x_scout_usage",
            "msg": f"X usage - {usage.get('executed_queries', 0)} requests, {usage.get('tweets_seen', 0)} posts checked, {usage.get('filtered', 0)} filtered",
        })
    if not leads:
        await broadcast_x_source_errors(manager, result.errors)
    hot_threshold = int_cfg(cfg, "x_hot_lead_threshold", 80, 1, 100)
    notify_hot = truthy(cfg.get("x_enable_notifications"))
    for lead in leads:
        await manager.broadcast({"type": "LEAD_UPDATED", "data": lead})
        if (lead.get("signal_score") or 0) >= hot_threshold:
            await manager.broadcast({"type": "HOT_X_LEAD", "data": lead})
            if notify_hot:
                await manager.broadcast({"type": "agent", "event": "x_hot_lead", "msg": f"Hot X lead: {lead.get('title','?')} @ {lead.get('company','?')}"})
    return leads


async def run_free_source_scan(
    manager,
    cfg: dict,
    kind_filter: str | None = None,
    profile: dict | None = None,
    force: bool = False,
    discovery_service=None,
) -> tuple[list[dict], dict, list[str]]:
    if not force and not free_sources_enabled(cfg):
        return [], {}, []

    discovery_service = discovery_service or get_discovery_service()
    kind_filter = "job"
    label = "job leads"
    await manager.broadcast({"type": "agent", "event": "free_scout_start", "msg": f"Scanning free sources for {label}..."})
    try:
        result = await discovery_service.scan_free_sources(cfg, kind_filter=kind_filter, profile=profile, force=force)
    except Exception as exc:
        # Close the websocket activity entry before propagating, so listeners
        # don't sit on "Scanning free sources..." with no terminal event.
        await manager.broadcast({"type": "agent", "event": "free_scout_done", "msg": f"Free scout failed: {exc}"})
        raise
    leads = result.leads
    usage = result.usage
    await manager.broadcast({
        "type": "agent",
        "event": "free_scout_done",
        "msg": (
            f"Free scout - {len(leads)} new {label} "
            f"({usage.get('candidates', 0)} candidates, {usage.get('duplicates', 0)} duplicates, "
            f"{usage.get('filtered', 0)} filtered, {usage.get('executed', 0)} sources checked)"
        ),
    })
    for msg in result.errors[:4]:
        record_error("free_source_fetch_failed", msg, "api.discovery")
        await manager.broadcast({"type": "agent", "event": "free_source_error", "msg": f"Free source detail: {msg}"})
    for lead in leads:
        await manager.broadcast({"type": "LEAD_UPDATED", "data": lead})
    return leads, usage, result.errors


def _finalize_job(job_store, job_id: str, *, status: str, error: str = "") -> None:
    """Mark a persisted job terminal unless the run already did so.

    Without this, a failed or stopped scan leaves its job row at
    "running, progress 5" forever (job rows survive restarts).
    """
    try:
        record = job_store.get(job_id)
        if record and record.status in ("succeeded", "failed", "cancelled"):
            return
        job_store.update(job_id, status=status, progress=100, error=error or None)
    except Exception as log_exc:
        _log.warning('suppressed exception in backend/api/routers/discovery.py:_finalize_job: %s', log_exc)


async def run_scan(
    manager,
    *,
    repo: Repository | None = None,
    discovery_service=None,
    ranking_service=None,
    stop_event: asyncio.Event | None = None,
) -> None:
    stop_event = stop_event or asyncio.Event()
    job_store = get_job_runner()
    job = job_store.create("scan", {})
    job_store.update(job.job_id, status="running", progress=5)
    try:
        await _run_scan_inner(
            manager,
            repo=repo,
            discovery_service=discovery_service,
            ranking_service=ranking_service,
            stop_event=stop_event,
            job_store=job_store,
            job=job,
        )
    except Exception as exc:
        _finalize_job(job_store, job.job_id, status="failed", error=str(exc))
        raise
    else:
        _finalize_job(job_store, job.job_id, status="cancelled" if stop_event.is_set() else "succeeded")


async def _run_scan_inner(
    manager,
    *,
    repo: Repository | None,
    discovery_service,
    ranking_service,
    stop_event: asyncio.Event,
    job_store,
    job,
) -> None:
    repo = repo or get_repository()
    discovery_service = discovery_service or get_discovery_service()
    ranking_service = ranking_service or get_ranking_service()
    # H4: these are synchronous SQLite reads; run them off the event loop so a
    # slow/locked DB doesn't block all other coroutines.
    cfg = await asyncio.to_thread(repo.settings.get_settings)
    profile = profile_for_discovery(await asyncio.to_thread(repo.profile.get_profile), cfg)
    if not has_profile_discovery_signal(profile) and not has_explicit_discovery_targets(cfg):
        msg = "Scan skipped: add a target role, profile skills, work history, or explicit job source first."
        await manager.broadcast({"type": "agent", "event": "scan_skipped", "msg": msg})
        job_store.update(job.job_id, status="cancelled", progress=100, error=msg)
        return

    market_focus = cfg.get("job_market_focus", "global")
    raw_urls = job_targets(cfg.get("job_boards", ""), market_focus)
    await run_x_signal_scan(manager, cfg, "job", profile, discovery_service=discovery_service)
    await run_free_source_scan(manager, cfg, "job", profile, discovery_service=discovery_service)

    await manager.broadcast({"type": "agent", "event": "query_gen_start", "msg": "Generating profile-tailored search queries..."})
    try:
        urls = await discovery_service.plan_board_targets(profile, raw_urls, market_focus)
        await manager.broadcast({"type": "agent", "event": "query_gen_done", "msg": f"Search plan ready - {len(urls)} targets"})
        for url in urls:
            await manager.broadcast({"type": "agent", "event": "query_gen_target", "msg": url})
    except Exception as exc:
        urls = raw_urls
        await manager.broadcast({"type": "agent", "event": "query_gen_error", "msg": f"Query generation failed ({exc}), using raw URLs"})

    await manager.broadcast({"type": "agent", "event": "scout_start", "msg": f"Launching scan for {len(urls)} targets..."})
    leads: list[dict] = []
    scout_usage: dict = {"configured": 0, "executed": 0, "candidates": 0, "saved": 0, "duplicates": 0, "filtered": 0, "missing_url": 0, "errors": 0, "by_source": {}}
    scout_errors: list[str] = []
    batch_size = int_cfg(cfg, "board_scan_batch_size", 4, 1, 12)
    batches = _target_batches(urls, batch_size)
    for batch_index, batch in enumerate(batches, start=1):
        if stop_event.is_set():
            break
        try:
            scout_result = await discovery_service.scan_job_boards(batch, cfg)
            leads.extend(scout_result.leads)
            _merge_scan_usage(scout_usage, scout_result.usage or {}, len(batch))
            scout_errors.extend(scout_result.errors or [])
        except Exception as exc:
            scout_usage["configured"] += len(batch)
            scout_usage["errors"] += len(batch)
            detail = str(exc).strip() or type(exc).__name__
            scout_errors.append(f"board batch {batch_index}/{len(batches)} skipped ({len(batch)} targets): {detail}")
            record_error("source_fetch_failed", detail, "api.discovery")

    await manager.broadcast({
        "type": "agent",
        "event": "scout_done",
        "msg": (
            f"Scout finished - {len(leads)} new leads found "
            f"({scout_usage.get('candidates', 0)} candidates, {scout_usage.get('duplicates', 0)} duplicates, "
            f"{scout_usage.get('filtered', 0)} filtered, {scout_usage.get('errors', 0)} source errors)"
        ),
    })
    for msg in scout_errors[:5]:
        record_error("source_fetch_failed", msg, "api.discovery")
        await manager.broadcast({"type": "agent", "event": "scout_source_detail", "msg": f"Scout source detail: {msg}"})

    if stop_event.is_set():
        await manager.broadcast({"type": "agent", "event": "eval_done", "msg": "Scan stopped after scouting."})
        return

    discovered = await asyncio.to_thread(repo.leads.get_discovered_leads)
    # Only score leads that haven't been scored yet (status 'discovered'). Leads
    # already scored ('matched'/'discarded') are re-ranked via the explicit
    # re-evaluate action — re-scoring the whole backlog on every scan is an O(N)
    # LLM cost that grows unboundedly as matched leads accumulate.
    to_score = [lead for lead in discovered if (lead.get("status") or "discovered") == "discovered"]
    await manager.broadcast({"type": "agent", "event": "eval_start", "msg": f"Evaluating {len(to_score)} new leads via {cfg.get('llm_provider', 'ollama')}"})

    # Token gate: LLM-evaluate only the top-K new leads by the cheap deterministic
    # score; the rest keep the deterministic score. Caps per-scan LLM cost at O(K).
    max_llm = int_cfg(cfg, "max_llm_evaluations", 25, 0, 500)
    llm_ids = await ranking_service.select_llm_eval_ids(to_score, profile, max_llm=max_llm)

    fallback_count = 0
    prefiltered_count = 0
    for lead in to_score:
        if stop_event.is_set():
            await manager.broadcast({"type": "agent", "event": "eval_done", "msg": "Scan stopped during evaluation."})
            return
        try:
            result = await ranking_service.evaluate_lead(lead, profile, cfg, use_llm=lead["job_id"] in llm_ids)
            await asyncio.to_thread(
                repo.leads.update_lead_score,
                lead["job_id"], result["score"], result["reason"],
                result.get("match_points", []), result.get("gaps", []),
                False, result.get("scored_by", ""),
            )
            if result.get("scored_by") == "deterministic_fallback":
                fallback_count += 1
            if result.get("scored_by") == "prefiltered_off_field":
                prefiltered_count += 1
            await manager.broadcast({"type": "LEAD_UPDATED", "data": {**lead, **result}})
            await manager.broadcast({"type": "agent", "event": "eval_scored", "msg": f"Scored {lead.get('title','')} = {result['score']}/100"})
        except Exception as exc:
            await manager.broadcast({"type": "agent", "event": "eval_error", "msg": f"Eval failed for {lead.get('title','')}: {exc}"})

    if prefiltered_count > 0:
        await manager.broadcast({
            "type": "agent",
            "event": "eval_prefilter_summary",
            "msg": f"{prefiltered_count}/{len(to_score)} leads skipped as off-field (no LLM tokens spent)",
        })
    if fallback_count > 0:
        await manager.broadcast({
            "type": "agent",
            "event": "eval_fallback_summary",
            "msg": f"{fallback_count}/{len(to_score)} leads scored by fallback (LLM unavailable)",
        })
    await manager.broadcast({"type": "agent", "event": "eval_done", "msg": "Evaluation cycle complete"})
    await asyncio.to_thread(repo.settings.save_settings, {"last_scan_finished_at": datetime.now(timezone.utc).isoformat()})
    await asyncio.to_thread(_record_scan_telemetry, {
        "at": datetime.now(timezone.utc).isoformat(),
        "new_leads": len(leads),
        "scored": len(to_score),
        "fallback": fallback_count,
        "prefiltered": prefiltered_count,
        **{k: scout_usage.get(k, 0) for k in ("configured", "executed", "candidates", "saved", "duplicates", "filtered", "missing_url", "errors")},
        "by_source": scout_usage.get("by_source", {}),
    })
    job_store.update(job.job_id, status="succeeded", progress=100)


async def run_scan_task(
    manager,
    logger,
    *,
    repo: Repository | None = None,
    discovery_service=None,
    ranking_service=None,
    stop_event: asyncio.Event | None = None,
) -> None:
    try:
        await run_scan(
            manager,
            repo=repo,
            discovery_service=discovery_service,
            ranking_service=ranking_service,
            stop_event=stop_event,
        )
    except Exception as exc:
        logger.error("scan failed: %s", exc)
        await manager.broadcast({"type": "agent", "event": "eval_done", "msg": f"Scan failed: {exc}"})


async def run_reevaluate_jobs(
    manager,
    *,
    repo: Repository | None = None,
    ranking_service=None,
    stop_event: asyncio.Event | None = None,
) -> None:
    stop_event = stop_event or asyncio.Event()
    job_store = get_job_runner()
    job = job_store.create("reevaluate", {})
    job_store.update(job.job_id, status="running", progress=5)
    try:
        await _run_reevaluate_jobs_inner(
            manager,
            repo=repo,
            ranking_service=ranking_service,
            stop_event=stop_event,
            job_store=job_store,
            job=job,
        )
    except Exception as exc:
        _finalize_job(job_store, job.job_id, status="failed", error=str(exc))
        raise
    else:
        _finalize_job(job_store, job.job_id, status="cancelled" if stop_event.is_set() else "succeeded")


async def _run_reevaluate_jobs_inner(
    manager,
    *,
    repo: Repository | None,
    ranking_service,
    stop_event: asyncio.Event,
    job_store,
    job,
) -> None:
    repo = repo or get_repository()
    ranking_service = ranking_service or get_ranking_service()
    cfg = await asyncio.to_thread(repo.settings.get_settings)
    # Enrich with the settings desired-position/target-role like the scan, ghost and
    # free-source paths do — otherwise re-evaluate scores each lead against a poorer
    # summary (missing the role signal) and can regress a matched lead to the
    # wrong-field cap, giving a different score than the identical scan produced.
    profile = profile_for_discovery(await asyncio.to_thread(repo.profile.get_profile), cfg)
    jobs = await asyncio.to_thread(repo.leads.get_job_leads_for_evaluation)
    total = len(jobs)
    scored = 0
    failed = 0
    fallback_count = 0

    # Token gate: LLM-evaluate only the top-K leads by the cheap deterministic score;
    # the rest keep the (calibrated) deterministic score. This caps the dominant
    # per-lead LLM cost from O(backlog) to O(K).
    max_llm = int_cfg(cfg, "max_llm_evaluations", 25, 0, 500)
    llm_ids = await ranking_service.select_llm_eval_ids(jobs, profile, max_llm=max_llm)

    await manager.broadcast({
        "type": "agent",
        "event": "reeval_start",
        "msg": f"Re-evaluating {total} job leads via {cfg.get('llm_provider', 'ollama')}",
    })

    for index, lead in enumerate(jobs, start=1):
        if stop_event.is_set():
            await manager.broadcast({
                "type": "agent",
                "event": "reeval_done",
                "msg": f"Re-evaluation stopped after {scored}/{total} jobs.",
            })
            return

        try:
            result = await ranking_service.evaluate_lead(
                lead, profile, cfg, use_llm=lead["job_id"] in llm_ids
            )
            preserve_status = should_preserve_job_status(lead.get("status", ""))
            await asyncio.to_thread(
                repo.leads.update_lead_score,
                lead["job_id"], result["score"], result["reason"],
                result.get("match_points", []), result.get("gaps", []),
                preserve_status, result.get("scored_by", ""),
            )
            if result.get("scored_by") == "deterministic_fallback":
                fallback_count += 1
            saved = await asyncio.to_thread(repo.leads.get_lead_by_id, lead["job_id"])
            await manager.broadcast({"type": "LEAD_UPDATED", "data": saved or {**lead, **result}})
            scored += 1
            await manager.broadcast({
                "type": "agent",
                "event": "reeval_scored",
                "msg": f"[{index}/{total}] Re-scored {lead.get('title','')} = {result['score']}/100",
            })
        except Exception as exc:
            failed += 1
            await manager.broadcast({
                "type": "agent",
                "event": "reeval_error",
                "msg": f"Re-eval failed for {lead.get('title','')}: {exc}",
            })

    summary = f"Re-evaluation complete - {scored}/{total} jobs scored"
    if failed:
        summary += f", {failed} failed"
    if fallback_count:
        summary += f", {fallback_count} fallback"
    await manager.broadcast({"type": "agent", "event": "reeval_done", "msg": summary})
    job_store.update(job.job_id, status="succeeded", progress=100, result={"scored": scored, "failed": failed, "total": total})


async def run_reevaluate_jobs_task(
    manager,
    logger,
    *,
    repo: Repository | None = None,
    ranking_service=None,
    stop_event: asyncio.Event | None = None,
) -> None:
    try:
        await run_reevaluate_jobs(manager, repo=repo, ranking_service=ranking_service, stop_event=stop_event)
    except Exception as exc:
        logger.error("reevaluate failed: %s", exc)
        await manager.broadcast({"type": "agent", "event": "reeval_done", "msg": f"Re-evaluation failed: {exc}"})


def create_router(
    *,
    manager,
    logger,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["discovery"])

    @router.post("/scan")
    async def scan(
        repo: Repository = Depends(get_repository),
        discovery_service=Depends(get_discovery_service),
        ranking_service=Depends(get_ranking_service),
    ):
        require_rate_limit(_scan_limiter)
        started = await TASKS.start(
            "scan",
            lambda stop: run_scan_task(
                manager,
                logger,
                repo=repo,
                discovery_service=discovery_service,
                ranking_service=ranking_service,
                stop_event=stop,
            ),
            mutex_with=["reevaluate"],
        )
        if not started:
            status = await TASKS.status()
            detail = "Re-evaluation already running" if status["reevaluating"] else "Scan already running"
            raise HTTPException(status_code=409, detail=detail)
        return {"status": "scanning"}

    @router.get("/status")
    async def task_status():
        return await TASKS.status()

    @router.post("/scan/stop")
    async def stop_scan():
        if not await TASKS.stop("scan"):
            return {"status": "idle"}
        await manager.broadcast({"type": "agent", "event": "eval_done", "msg": "Scan stopped by user."})
        return {"status": "stopping"}

    @router.post("/leads/reevaluate")
    async def reevaluate_jobs(
        repo: Repository = Depends(get_repository),
        ranking_service=Depends(get_ranking_service),
    ):
        started = await TASKS.start(
            "reevaluate",
            lambda stop: run_reevaluate_jobs_task(
                manager,
                logger,
                repo=repo,
                ranking_service=ranking_service,
                stop_event=stop,
            ),
            mutex_with=["scan"],
        )
        if not started:
            status = await TASKS.status()
            detail = "Scan already running" if status["scanning"] else "Re-evaluation already running"
            raise HTTPException(status_code=409, detail=detail)
        return {"status": "reevaluating"}

    @router.post("/leads/reevaluate/stop")
    async def stop_reevaluate_jobs():
        if not await TASKS.stop("reevaluate"):
            return {"status": "idle"}
        await manager.broadcast({"type": "agent", "event": "reeval_done", "msg": "Re-evaluation stopped by user."})
        return {"status": "stopping"}

    @router.post("/leads/cleanup")
    async def cleanup_leads(
        dry_run: bool = False,
        limit: int = 1000,
        repo: Repository = Depends(get_repository),
    ):
        await manager.broadcast({
            "type": "agent",
            "event": "cleanup_start",
            "msg": f"Scanning up to {limit} leads for bad data...",
        })
        result = await asyncio.to_thread(repo.leads.cleanup_bad_leads, limit, dry_run)

        if not dry_run:
            for item in result.get("items", [])[:100]:
                lead = await asyncio.to_thread(repo.leads.get_lead_by_id, item["job_id"])
                if lead:
                    await manager.broadcast({"type": "LEAD_UPDATED", "data": lead})

        action = "would discard" if dry_run else "discarded"
        await manager.broadcast({
            "type": "agent",
            "event": "cleanup_done",
            "msg": f"Cleanup scanned {result['scanned']} leads and {action} {result['candidates']} bad rows.",
        })
        return result

    @router.post("/free-sources/scan")
    async def free_sources_scan(repo: Repository = Depends(get_repository)):
        cfg = await asyncio.to_thread(repo.settings.get_settings)  # H4: off event loop
        profile = profile_for_discovery(await asyncio.to_thread(repo.profile.get_profile), cfg)
        leads, usage, errors = await run_free_source_scan(manager, cfg, "job", profile, force=True)
        return {"status": "done", "leads": len(leads), "usage": usage, "errors": errors[:8]}

    return router
