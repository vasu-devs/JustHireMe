"""Generation API — transport only.

Orchestration, persistence rules and failure classification live in
``generation.orchestrator``. This module maps HTTP to it and owns the
background-task handles plus the WebSocket fan-out callback.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_generation_orchestrator
from api.rate_limit import RateLimiter, require_rate_limit
from core.types import ManualLeadBody
from generation.orchestrator import GENERATION_RETRY_AFTER_SECONDS, is_transient_generation_error

_background_tasks: set[asyncio.Task] = set()


def _track_background_task(task: asyncio.Task) -> None:
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def create_router(*, manager) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["generation"])
    generate_limiter = RateLimiter(5, 60)
    manual_limiter = RateLimiter(10, 60)

    async def _notify(message: dict) -> None:
        await manager.broadcast(message)

    # MUST stay above /leads/{job_id}/generate/start: that pattern also matches
    # this path (with job_id="manual"), and FastAPI takes the first match.
    @router.post("/leads/manual/generate/start")
    async def create_manual_lead_and_start_generation(
        body: ManualLeadBody,
        orchestrator=Depends(get_generation_orchestrator),
    ):
        require_rate_limit(manual_limiter)
        queued = await orchestrator.create_manual_and_generate(body.text, body.url, _notify)
        _track_background_task(asyncio.create_task(queued["run"]()))
        await _notify({"type": "LEAD_UPDATED", "data": queued["lead"]})
        return {"status": "started", "job_id": queued["lead"]["job_id"], "lead": queued["lead"]}

    @router.post("/leads/{job_id}/generate")
    async def generate_for_lead(
        job_id: str,
        template_id: str = "",
        orchestrator=Depends(get_generation_orchestrator),
    ):
        require_rate_limit(generate_limiter)
        try:
            lead = await orchestrator.generate(job_id, _notify, template_id=template_id)
        except Exception as exc:
            raise _generation_http_error(exc) from exc
        return {
            "status": "ready",
            "job_id": job_id,
            "lead": lead,
            "generation_job_id": lead.get("generation_job_id", ""),
        }

    @router.post("/leads/{job_id}/generate/start")
    async def start_generate_for_lead(
        job_id: str,
        template_id: str = "",
        orchestrator=Depends(get_generation_orchestrator),
    ):
        require_rate_limit(generate_limiter)
        tailoring_lead = await orchestrator.start(job_id, _notify, template_id=template_id)
        _track_background_task(
            asyncio.create_task(orchestrator.generate_quietly(job_id, _notify, template_id=template_id))
        )
        return {"status": "started", "job_id": job_id, "lead": tailoring_lead}

    @router.post("/leads/{job_id}/pipeline/run")
    async def run_pipeline(job_id: str, orchestrator=Depends(get_generation_orchestrator)):
        require_rate_limit(generate_limiter)
        started = await orchestrator.run_pipeline(job_id, _notify)
        _track_background_task(asyncio.create_task(started["run"]()))
        return {"status": "started", "job_id": job_id, "pipeline_job_id": started["pipeline_job_id"]}

    return router


def _generation_http_error(exc: Exception) -> Exception:
    """Map an unexpected generation failure onto a retryable/permanent status.

    Domain errors (not found / blocked) are returned untouched so the shared
    handler in api.app maps them; only opaque failures need Retry-After.
    """
    from core.errors import JustHireMeError

    if isinstance(exc, JustHireMeError):
        return exc
    logging.getLogger(__name__).warning("generation failed: %s", exc)
    transient = is_transient_generation_error(exc)
    return HTTPException(
        status_code=503 if transient else 500,
        detail="Generation failed. See the activity log for details.",
        headers={"Retry-After": str(GENERATION_RETRY_AFTER_SECONDS)} if transient else None,
    )
