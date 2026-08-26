"""App lifecycle API — transport only: liveness, subsystem health, shutdown.

The probes themselves live in ``system.health``.
"""

from __future__ import annotations

import asyncio
import secrets
import signal

from fastapi import APIRouter, Depends, Request

from api.dependencies import get_system_service
from core import env

_background_tasks: set[asyncio.Task] = set()


def _track_background_task(task: asyncio.Task) -> None:
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _details_authorized(request: Request) -> bool:
    """Only a token-bearing caller sees component detail; /health itself is open."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return False
    token_getter = getattr(request.app.state, "token_getter", None)
    if not callable(token_getter):
        return False
    try:
        expected = token_getter()
    except Exception:
        return False
    return bool(expected) and secrets.compare_digest(auth[7:], expected)


def create_router(started_at: float) -> APIRouter:
    router = APIRouter()

    @router.get("/health", dependencies=[])
    async def health(request: Request, service=Depends(get_system_service)):
        base = await service.liveness(started_at)
        base["details_available"] = _details_authorized(request)
        if not base["details_available"]:
            return base

        checks = await service.component_checks()
        status = "alive" if checks["sqlite"]["status"] == "ok" and checks["graph"]["status"] == "ok" else "degraded"
        return {
            **base,
            "status": status,
            "log_level": env.log_level(),
            "last_scan_finished_at": await service.last_scan_finished_at(),
            "components": checks,
            "checks": checks,
            "services": {},
        }

    @router.get("/api/v1/health/subsystems")
    async def health_subsystems(service=Depends(get_system_service)):
        return await service.subsystems()

    @router.post("/api/v1/shutdown")
    async def request_shutdown():
        # The other end of the lifecycle this router reports on: let the shell ask
        # the sidecar to exit cleanly. Deferred so the response is sent first.
        async def _shutdown_soon():
            await asyncio.sleep(0.1)
            signal.raise_signal(signal.SIGTERM)

        _track_background_task(asyncio.create_task(_shutdown_soon()))
        return {"ok": True}

    return router
