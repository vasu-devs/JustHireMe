from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from api.dependencies import get_repository
from data.repository import Repository

router = APIRouter(prefix="/api/v1", tags=["events"])


@router.get("/events")
async def get_events_endpoint(
    limit: int = 100,
    job_id: str | None = None,
    repo: Repository = Depends(get_repository),
):
    # Clamp: an unbounded/negative limit reaches SQLite as LIMIT -1 (= unlimited)
    # and would dump the whole events table.
    limit = max(1, min(limit, 1000))
    return await asyncio.to_thread(repo.events.get_events, limit=limit, job_id=job_id)
