from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_repository
from data.repository import Repository

router = APIRouter(prefix="/api/v1", tags=["notifications"])


@router.get("/notifications")
async def list_notifications(
    status: str = Query("all", regex="^(all|pending|sent|failed)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    repo: Repository = Depends(get_repository),
):
    items, total = repo.notifications.get_all_notifications(
        status=status, limit=limit, offset=offset
    )
    return {"items": items, "total": total}


@router.get("/notifications/stats")
async def notification_stats(repo: Repository = Depends(get_repository)):
    return repo.notifications.get_notification_stats()


@router.post("/notifications/{id}/retry")
async def retry_notification(id: int, repo: Repository = Depends(get_repository)):
    ok = repo.notifications.reset_notification(id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found or not in failed state")
    return {"ok": True}
