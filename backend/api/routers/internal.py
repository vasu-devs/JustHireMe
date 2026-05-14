from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from contracts.events import InternalEvent
from gateway.events import websocket_payload
from gateway.internal_auth import require_internal_token


router = APIRouter(prefix="/internal/v1", tags=["internal"], dependencies=[Depends(require_internal_token)])


@router.post("/events")
async def receive_internal_event(body: InternalEvent, request: Request):
    manager = getattr(request.app.state, "connection_manager", None)
    if manager is not None:
        await manager.broadcast(websocket_payload(body))
    return {"ok": True}
