# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs

from __future__ import annotations

import argparse
import socket
import sys
import time

from fastapi import WebSocket

from api.app import create_app
from api.auth import create_api_token, require_ws_token
from api.scheduler import create_ghost_tick, create_lifespan, create_scheduler
from api.websocket import ConnectionManager, agent_event_action as _agent_event_action  # noqa: F401
from core.logging import get_logger

_log = get_logger(__name__)


def _reserve_socket(preferred: int = 0) -> socket.socket:
    """Bind and KEEP OPEN a listening socket so the port can't be stolen.

    The old flow picked a port (bind+close) then let uvicorn re-bind it later,
    leaving a window where another process could grab the port — after we'd
    already announced it to the UI. Holding the open socket and handing it to
    uvicorn eliminates that TOCTOU race: the port is ours from announce to serve.
    """
    # No SO_REUSEADDR: we hand this exact socket to uvicorn (never re-bind), and
    # on Windows SO_REUSEADDR would let another process bind the same port,
    # defeating the whole point of reserving it. Keep the bind exclusive.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", preferred))
    return s


_UP = time.monotonic()
_sched = create_scheduler()
_API_TOKEN: str = create_api_token()
cm = ConnectionManager()


async def _require_ws_token(ws: WebSocket) -> bool:
    return await require_ws_token(ws, lambda: _API_TOKEN)


def build_gateway_app():
    ghost_tick = create_ghost_tick(cm)
    lifespan = create_lifespan(_sched, ghost_tick, _log)
    return create_app(
        lifespan=lifespan,
        token_getter=lambda: _API_TOKEN,
        started_at=_UP,
        scheduler=_sched,
        ghost_tick=ghost_tick,
        connection_manager=cm,
        logger=_log,
        websocket_token_guard=_require_ws_token,
    )


_GATEWAY_APP_SINGLETON = None


def __getattr__(name: str):
    """Lazily build the gateway app on first attribute access (PEP 562).

    Building at module import time created a second app + scheduler that
    uvicorn never ran (it builds its own in ``__main__``), leaking resources
    and calling ``ensure_ghost_job``/``init_sql`` twice. Tests and tooling that
    do ``from main import app`` still work, but the app is only constructed
    once, on demand, and cached.
    """
    global _GATEWAY_APP_SINGLETON
    if name == "app":
        if _GATEWAY_APP_SINGLETON is None:
            _GATEWAY_APP_SINGLETON = build_gateway_app()
        return _GATEWAY_APP_SINGLETON
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _parse_args():
    parser = argparse.ArgumentParser(description="JustHireMe backend gateway runner")
    parser.add_argument("--port", type=int, default=0)
    # Accepted for backward compatibility: the desktop shell still passes it.
    # The app is always the in-process monolith now (no service subprocesses).
    parser.add_argument("--no-services", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    import uvicorn

    args = _parse_args()
    gateway_app = build_gateway_app()
    # Hold the bound socket, announce the port only after we own it, then hand
    # the same socket to uvicorn — no re-bind, no port-steal race.
    sock = _reserve_socket(args.port)
    port = sock.getsockname()[1]
    sys.stdout.write(f"JHM_TOKEN={_API_TOKEN}\n")
    sys.stdout.write(f"PORT:{port}\n")
    sys.stdout.flush()
    uvicorn.Server(uvicorn.Config(gateway_app, log_level="warning")).run(sockets=[sock])
