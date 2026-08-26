"""Diagnostics API — transport only: error reports in, metrics out."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_system_service
from api.rate_limit import RateLimiter, require_rate_limit

_errors_limiter = RateLimiter(30, 60)


def create_router(started_at: float) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["diagnostics"])

    @router.post("/errors")
    async def record_frontend_error(payload: dict, service=Depends(get_system_service)):
        require_rate_limit(_errors_limiter)
        await service.record_frontend_error(payload)
        return {"ok": True}

    @router.get("/diagnostics")
    async def diagnostics(service=Depends(get_system_service)):
        return await service.diagnostics(started_at)

    return router
