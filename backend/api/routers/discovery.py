"""Discovery API — transport only.

Scan/re-evaluate orchestration lives in ``discovery.orchestrator``; this module
starts them, reports task state, and maps conflicts to 409.
"""

from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_discovery_context, get_lead_service
from api.rate_limit import RateLimiter, require_rate_limit
from discovery.orchestrator import (
    TASKS,
    free_sources_scan as run_free_sources_scan,
    run_reevaluate_jobs_task,
    run_scan_task,
)

_scan_limiter = RateLimiter(3, 60)


def create_router(
    *,
    manager,
    logger,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["discovery"])

    async def _notify(message: dict) -> None:
        await manager.broadcast(message)

    @router.post("/scan")
    async def scan(ctx=Depends(get_discovery_context)):
        require_rate_limit(_scan_limiter)
        started = await TASKS.start(
            "scan",
            lambda stop: run_scan_task(
                manager,
                logger,
                repo=ctx.repo,
                discovery_service=ctx.discovery_service,
                ranking_service=ctx.ranking_service,
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
    async def reevaluate_jobs(ctx=Depends(get_discovery_context)):
        started = await TASKS.start(
            "reevaluate",
            lambda stop: run_reevaluate_jobs_task(
                manager,
                logger,
                repo=ctx.repo,
                ranking_service=ctx.ranking_service,
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
        service=Depends(get_lead_service),
    ):
        return await service.cleanup(limit=limit, dry_run=dry_run, notify=_notify)

    @router.post("/free-sources/scan")
    async def free_sources_scan(ctx=Depends(get_discovery_context)):
        return await run_free_sources_scan(manager, ctx.repo)

    return router
