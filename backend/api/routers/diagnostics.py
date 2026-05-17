from __future__ import annotations

import time

from fastapi import APIRouter

from core.telemetry import get_error_count, get_top_errors


def create_router(started_at: float) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["diagnostics"])

    @router.get("/diagnostics")
    async def diagnostics():
        return {
            "top_errors": get_top_errors(limit=10),
            "error_count_24h": get_error_count(hours=24),
            "version": "1.0.0",
            "uptime_seconds": round(time.monotonic() - started_at, 2),
        }

    return router
