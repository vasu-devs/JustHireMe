from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from api.auth import LOCAL_ORIGIN_RE, check_http_token
from api.dependencies import get_event_bus
from api.routers import automation, dashboard, diagnostics, discovery, events, generation, graph, health, ingestion, leads, learning, opportunities, profile, runtime, settings, templates
from api.routers import help as help_router
from api.websocket import register_websocket
from core.errors import JustHireMeError, http_status_for
from core.telemetry import record_exception
from core.version import APP_VERSION


class TokenAuthMiddleware:
    """Bearer-token gate as a plain ASGI middleware.

    Deliberately NOT ``@app.middleware("http")`` (Starlette's
    ``BaseHTTPMiddleware``): that wraps every request/response through an
    async queue so user code can inspect a ``Response`` object, which means
    the ENTIRE body -- however large -- gets buffered and re-chunked through
    it. Fine for small JSON, but for GET /api/v1/leads' ~48MB payload that
    re-chunking alone measured at 10-15s of pure middleware overhead on top
    of the ~1s the query + serialization actually took. This forwards the
    ASGI ``send`` callable straight through untouched (only intercepting the
    "http.response.start" event, to stamp x-request-id) so a large body
    never passes through anything but the network.
    """

    def __init__(self, app: ASGIApp, token_getter: Callable[[], str]) -> None:
        self.app = app
        self.token_getter = token_getter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request = Request(scope, receive=receive)
        request_id = request.headers.get("x-request-id", "")

        async def send_with_request_id(message) -> None:
            if request_id and message["type"] == "http.response.start":
                MutableHeaders(scope=message)["x-request-id"] = request_id
            await send(message)

        try:
            rejection = await check_http_token(request, self.token_getter)
            if rejection is not None:
                if request_id:
                    rejection.headers["x-request-id"] = request_id
                return await rejection(scope, receive, send)
            return await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            record_exception(exc, domain="api", request_id=request_id, path=request.url.path)
            raise


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
) -> FastAPI:
    app = FastAPI(
        title="JustHireMe",
        version=APP_VERSION,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=LOCAL_ORIGIN_RE,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Defense-in-depth against DNS rebinding: the sidecar only ever serves the
    # local Tauri webview, so reject requests whose Host header isn't loopback.
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "[::1]", "::1"],
    )
    app.state.connection_manager = connection_manager
    app.state.token_getter = token_getter

    app.add_middleware(TokenAuthMiddleware, token_getter=token_getter)

    @app.exception_handler(JustHireMeError)
    async def _domain_error(request: Request, exc: JustHireMeError):
        # THE transport boundary. The business layer raises domain errors and
        # knows nothing about HTTP; this is the only place they become statuses.
        return JSONResponse(status_code=http_status_for(exc), content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def _unhandled_exception(request: Request, exc: Exception):
        # Never leak internal exception text to the client; the middleware above
        # already recorded the detail server-side. Return a generic 500 + the
        # request id so a user-reported failure can be correlated to the log.
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request.headers.get("x-request-id", "")},
        )

    app.include_router(health.create_router(started_at))
    app.include_router(diagnostics.create_router(started_at))
    app.include_router(events.router)
    app.include_router(graph.router)
    app.include_router(help_router.router)
    app.include_router(runtime.router)
    app.include_router(profile.router)
    app.include_router(learning.router)
    app.include_router(opportunities.router)
    app.include_router(dashboard.router)
    if connection_manager is not None:
        _wire_event_bus(connection_manager)
        app.include_router(leads.create_router(connection_manager))
    if scheduler is not None and ghost_tick is not None:
        app.include_router(settings.create_router(scheduler, ghost_tick))
    if connection_manager is not None and logger is not None:
        app.include_router(ingestion.create_router(connection_manager, logger))
    app.include_router(templates.create_router(logger))
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
