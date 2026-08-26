"""Leads API — transport only.

Every handler parses the request, calls ``LeadService``, and serialises the
result. No storage access, no domain rules: those live in ``leads.service``.
Domain errors propagate and are turned into status codes by the single handler
in ``api.app``.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response, StreamingResponse

from api.dependencies import get_lead_service
from api.rate_limit import RateLimiter, require_rate_limit
from core.types import FeedbackBody, FollowupBody, ManualLeadBody, StatusBody

_background_tasks: set[asyncio.Task] = set()


def _track_background_task(task: asyncio.Task) -> None:
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# Coalesce feedback re-ranks: bulk/rapid feedback clicks would otherwise each spawn
# a full 500-lead recompute that duplicates work and contends on the SQLite write
# lock. At most one runs at a time; concurrent requests just mark it dirty so it
# loops once more, covering the whole burst in ~2 passes.
_relearn_state = {"running": False, "again": False}


async def _run_relearn(service, manager) -> None:
    if _relearn_state["running"]:
        _relearn_state["again"] = True
        return
    _relearn_state["running"] = True
    try:
        while True:
            _relearn_state["again"] = False
            changed = await service.recompute_feedback_signals()
            for updated in changed[:60]:
                await manager.broadcast({"type": "LEAD_UPDATED", "data": updated})
            if changed:
                await manager.broadcast({
                    "type": "agent",
                    "event": "feedback_relearn",
                    "msg": f"Re-ranked {len(changed)} lead(s) from your feedback",
                })
            if not _relearn_state["again"]:
                break
    except Exception as exc:
        logging.getLogger(__name__).warning(
            'suppressed exception in backend/api/routers/leads.py:_run_relearn: %s', exc
        )
    finally:
        _relearn_state["running"] = False


def create_router(manager) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["leads"])
    manual_limiter = RateLimiter(10, 60)

    @router.get("/leads")
    async def leads(
        page: int | None = None,
        limit: int = 200,
        beginner_only: bool = False,
        seniority: str | None = None,
        status: str | None = None,
        min_score: int | None = None,
        service=Depends(get_lead_service),
    ):
        result = await service.list_leads(
            page=page, limit=limit, beginner_only=beginner_only,
            seniority=seniority, status=status, min_score=min_score,
        )
        # Plain Response + json.dumps, not `return result` (FastAPI's default
        # jsonable_encoder + JSONResponse): every lead is already a plain
        # dict of JSON-safe primitives (see lead_row_dict), so jsonable_encoder's
        # per-field type introspection buys nothing here and measurably cost
        # several seconds on the full ~10,489-lead payload -- one more piece
        # of this endpoint's fix alongside the seniority_level cache above.
        # to_thread, not a plain call: this is a single-worker backend (see
        # leads.service's module docstring) -- serializing the full dataset is
        # CPU-bound and, run inline, blocks the event loop for the whole
        # duration, stalling every OTHER in-flight request (health, profile,
        # dashboard/overview) behind this one. Confirmed on the real UI: while
        # this request was in flight, unrelated small requests queued behind
        # it long enough for the screens they feed to render empty.
        body = await asyncio.to_thread(json.dumps, result)
        return Response(content=body.encode(), media_type="application/json")

    @router.get("/leads/export.csv")
    async def export_leads_csv(service=Depends(get_lead_service)):
        return StreamingResponse(
            iter([await service.export_csv()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=jhm_pipeline.csv"},
        )

    @router.get("/leads/{job_id}/versions")
    async def get_lead_versions(job_id: str, service=Depends(get_lead_service)):
        return await service.list_versions(job_id)

    @router.get("/leads/{job_id}")
    async def get_lead(job_id: str, service=Depends(get_lead_service)):
        return await service.get_lead(job_id)

    @router.delete("/leads/{job_id}")
    async def delete_lead_endpoint(job_id: str, service=Depends(get_lead_service)):
        await service.delete_lead(job_id)
        return {"ok": True}

    @router.put("/leads/{job_id}/status")
    async def update_status(job_id: str, body: StatusBody, service=Depends(get_lead_service)):
        result = await service.update_status(job_id, body.status)
        await manager.broadcast({"type": "LEAD_UPDATED", "data": result})
        return {"ok": True}

    @router.put("/leads/{job_id}/feedback")
    async def update_feedback(job_id: str, body: FeedbackBody, service=Depends(get_lead_service)):
        lead = await service.save_feedback(job_id, body.feedback, body.note)
        await manager.broadcast({"type": "LEAD_UPDATED", "data": lead})

        # Feedback should make the tool better with use: re-rank the other still-open
        # leads by what this thumbs-up/down just taught the model, and push the ones
        # whose signal changed so the UI reflects it live. Fire-and-forget so the
        # click returns instantly; failures are non-fatal.
        _track_background_task(asyncio.create_task(_run_relearn(service, manager)))
        return lead

    @router.put("/leads/{job_id}/followup")
    async def update_followup(job_id: str, body: FollowupBody, service=Depends(get_lead_service)):
        lead = await service.schedule_followup(job_id, body.days)
        await manager.broadcast({"type": "LEAD_UPDATED", "data": lead})
        return lead

    @router.post("/leads/manual")
    async def create_manual_lead(body: ManualLeadBody, service=Depends(get_lead_service)):
        require_rate_limit(manual_limiter)
        saved = await service.create_manual_lead(body.text, body.url)
        await manager.broadcast({"type": "LEAD_UPDATED", "data": saved})
        return saved

    @router.get("/followups/due")
    async def due_followups(limit: int = 25, service=Depends(get_lead_service)):
        return await service.due_followups(limit)

    @router.get("/leads/{job_id}/pdf")
    async def get_lead_pdf(
        job_id: str,
        kind: str = "resume",
        version: int | None = None,
        service=Depends(get_lead_service),
    ):
        path, filename = await service.resolve_pdf(job_id, kind, version)
        return FileResponse(path, media_type="application/pdf", filename=filename)

    return router
