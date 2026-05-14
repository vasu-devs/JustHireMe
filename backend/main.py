# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs

from __future__ import annotations

import argparse
import secrets
import socket
import sys
import time

from fastapi import WebSocket

from api.app import create_app
from api.auth import create_api_token, require_ws_token
from api.scheduler import create_ghost_tick, create_lifespan, create_scheduler
from api.websocket import ConnectionManager, agent_event_action as _agent_event_action
from core.logging import get_logger
from gateway.supervisor import LocalServiceSupervisor
from services.apps import create_service_app

_log = get_logger(__name__)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_UP = time.monotonic()
_sched = create_scheduler()
_API_TOKEN: str = create_api_token()
cm = ConnectionManager()


async def _require_ws_token(ws: WebSocket) -> bool:
    return await require_ws_token(ws, lambda: _API_TOKEN)


def build_gateway_app(*, enable_services: bool = False):
    ghost_tick = create_ghost_tick(cm)
    supervisor = LocalServiceSupervisor(enabled=True) if enable_services else None
    internal_token = supervisor.internal_token if supervisor is not None else secrets.token_urlsafe(32)
    lifespan = create_lifespan(_sched, ghost_tick, _log, service_supervisor=supervisor)
    return create_app(
        lifespan=lifespan,
        token_getter=lambda: _API_TOKEN,
        started_at=_UP,
        scheduler=_sched,
        ghost_tick=ghost_tick,
        connection_manager=cm,
        logger=_log,
        websocket_token_guard=_require_ws_token,
        internal_token=internal_token,
    )


app = build_gateway_app(enable_services=False)


def _parse_args():
    parser = argparse.ArgumentParser(description="JustHireMe backend gateway/service runner")
    parser.add_argument("--service", choices=("profile", "discovery", "ranking", "generation", "automation", "graph"))
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--token", default="")
    parser.add_argument("--no-services", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    import uvicorn

    args = _parse_args()
    port = args.port or _free_port()
    if args.service:
        internal_token = args.token or secrets.token_urlsafe(32)
        service_app = create_service_app(args.service, internal_token=internal_token)
        uvicorn.run(service_app, host="127.0.0.1", port=port, log_level="warning")
    else:
        gateway_app = build_gateway_app(enable_services=not args.no_services)
        sys.stdout.write(f"JHM_TOKEN={_API_TOKEN}\n")
        sys.stdout.write(f"PORT:{port}\n")
        sys.stdout.flush()
        uvicorn.run(gateway_app, host="127.0.0.1", port=port, log_level="warning")
