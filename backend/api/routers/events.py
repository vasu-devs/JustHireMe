"""Activity log API — transport only."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_lead_service

router = APIRouter(prefix="/api/v1", tags=["events"])


@router.get("/events")
async def get_events_endpoint(
    limit: int = 100,
    job_id: str | None = None,
    service=Depends(get_lead_service),
):
    return await service.list_activity(limit=limit, job_id=job_id)
