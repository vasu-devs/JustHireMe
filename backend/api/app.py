from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.auth import LOCAL_ORIGIN_RE, require_http_token
from api.dependencies import get_event_bus
from api.routers import automation, discovery, events, generation, health, ingestion, internal, leads, misc, profile, settings
from api.websocket import register_websocket
from core.telemetry import record_exception


def _wire_event_bus(connection_manager) -> None:
    event_bus = get_event_bus()

    async def _forward_to_ws(_event_type: str, data: dict):
        await connection_manager.broadcast(data)

    event_bus.subscribe("*", _forward_to_ws)


def create_app(
    *,
    lifespan,
    token_getter: Callable[[], str],
    started_at: float,
    scheduler=None,
    ghost_tick=None,
    connection_manager=None,
    logger=None,
    websocket_token_guard=None,
    internal_token: str = "",
) -> FastAPI:
    app = FastAPI(
        title="JustHireMe",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=LOCAL_ORIGIN_RE,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.internal_token = internal_token
    app.state.connection_manager = connection_manager
    app.state.token_getter = token_getter

    @app.middleware("http")
    async def require_http_token_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id", "")
        try:
            response = await require_http_token(request, call_next, token_getter)
            if request_id:
                response.headers["x-request-id"] = request_id
            return response
        except Exception as exc:
            record_exception(exc, domain="api", request_id=request_id, path=request.url.path)
            raise

    app.include_router(health.create_router(started_at))
    app.include_router(internal.router)
    app.include_router(events.router)
    app.include_router(misc.router)
    app.include_router(profile.router)
    if connection_manager is not None:
        _wire_event_bus(connection_manager)
        app.include_router(leads.create_router(connection_manager))
    if scheduler is not None and ghost_tick is not None:
        app.include_router(settings.create_router(scheduler, ghost_tick))
    if connection_manager is not None and logger is not None:
        app.include_router(ingestion.create_router(connection_manager, logger))
    if connection_manager is not None:
        app.include_router(automation.create_router(connection_manager))
    if connection_manager is not None and logger is not None:
        app.include_router(discovery.create_router(manager=connection_manager, logger=logger))
    if connection_manager is not None:
        app.include_router(generation.create_router(manager=connection_manager))
    if connection_manager is not None and logger is not None and websocket_token_guard is not None:
        register_websocket(
            app,
            token_guard=websocket_token_guard,
            manager=connection_manager,
            started_at=started_at,
            logger=logger,
        )

    return app
