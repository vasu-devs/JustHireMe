from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from api.auth import WS_TOKEN_SUBPROTOCOL
from core.logging import get_logger
from core.telemetry import record_error


_log = get_logger(__name__)


def agent_event_action(msg: dict) -> str:
    event = str(msg.get("event") or "agent").strip() or "agent"
    detail = str(msg.get("msg") or "").strip()
    return f"{event}: {detail}" if detail else event


class ConnectionManager:
    def __init__(self, max_connections: int = 50):
        self._ws: list[WebSocket] = []
        # STABILITY: synchronized websocket connection list and bounded fanout
        self._lock = asyncio.Lock()
        self._max_connections = max_connections
        self._tasks: set[asyncio.Task] = set()

    def _track_task(self, task: asyncio.Task) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def add(self, ws: WebSocket):
        async with self._lock:
            if len(self._ws) >= self._max_connections:
                await ws.close(code=1013, reason="too many websocket connections")
                return False
            self._ws.append(ws)
            return True

    async def remove(self, ws: WebSocket):
        async with self._lock:
            self._ws = [w for w in self._ws if w != ws]

    async def _record_event(self, msg: dict) -> None:
        try:
            from api.dependencies import get_repository

            repo = get_repository()
            await asyncio.to_thread(repo.events.record_event, msg.get("job_id") or "__system__", agent_event_action(msg))
        except Exception as exc:
            _log.debug("event recording failed during broadcast: %s", exc)
            record_error("websocket_event_record_failed", str(exc), "api.websocket")

    async def broadcast(self, msg: dict):
        if msg.get("type") == "agent":
            self._track_task(asyncio.create_task(self._record_event(msg)))

        dead = []
        text = json.dumps(msg)

        async def _send(ws: WebSocket) -> None:
            try:
                await asyncio.wait_for(ws.send_text(text), timeout=2.0)
            except Exception as exc:
                _log.debug("ws send failed (will remove dead connection): %s", exc)
                record_error("websocket_send_failed", str(exc), "api.websocket")
                dead.append(ws)

        async with self._lock:
            sockets = list(self._ws)
        await asyncio.gather(*(_send(ws) for ws in sockets))
        for ws in dead:
            await self.remove(ws)


async def websocket_loop(
    ws: WebSocket,
    *,
    manager: ConnectionManager,
    started_at: float,
    logger,
) -> None:
    # Echo the auth subprotocol the client offered so the browser handshake
    # completes (the token rode in as the 2nd offered subprotocol).
    offered = [p.strip() for p in ws.headers.get("sec-websocket-protocol", "").split(",") if p.strip()]
    subprotocol = WS_TOKEN_SUBPROTOCOL if offered and offered[0] == WS_TOKEN_SUBPROTOCOL else None
    await ws.accept(subprotocol=subprotocol)
    if not await manager.add(ws):
        return
    beat = 0
    try:
        while True:
            beat += 1
            await ws.send_text(json.dumps({
                "type": "heartbeat",
                "status": "alive",
                "beat": beat,
                "uptime_seconds": round(time.monotonic() - started_at, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=2.0)
                if msg == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
            except TimeoutError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("ws: %s", exc)
    finally:
        await manager.remove(ws)


def register_websocket(
    app: FastAPI,
    *,
    token_guard,
    manager: ConnectionManager,
    started_at: float,
    logger,
) -> None:
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        if not await token_guard(ws):
            return
        await websocket_loop(ws, manager=manager, started_at=started_at, logger=logger)
