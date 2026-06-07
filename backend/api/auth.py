from __future__ import annotations

import secrets
from collections.abc import Callable

from fastapi import Request, WebSocket, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer


LOCAL_ORIGIN_RE = r"^(tauri://localhost|https?://(localhost|127\.0\.0\.1|tauri\.localhost|\[::1\])(?::\d+)?)$"

_bearer = HTTPBearer(auto_error=False)


def create_api_token() -> str:
    return secrets.token_hex(32)


def valid_token(candidate: str, expected: str) -> bool:
    return bool(candidate) and bool(expected) and secrets.compare_digest(candidate, expected)


async def require_http_token(request: Request, call_next, token_getter: Callable[[], str]):
    if request.method == "OPTIONS" or request.url.path == "/health":
        return await call_next(request)

    creds = await _bearer(request)
    if creds is None or not valid_token(creds.credentials, token_getter()):
        return JSONResponse(
            {"detail": "invalid token"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return await call_next(request)


WS_TOKEN_SUBPROTOCOL = "jhm.bearer"


def ws_token_from_subprotocol(ws: WebSocket) -> str:
    """Extract the bearer token offered as the 2nd WebSocket subprotocol.

    Browsers can't set custom WS headers, but they can offer subprotocols, which
    travel in the ``Sec-WebSocket-Protocol`` *header* (not the URL). The client
    offers ``["jhm.bearer", "<token>"]``; we read the token from there.
    """
    raw = ws.headers.get("sec-websocket-protocol", "")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) >= 2 and parts[0] == WS_TOKEN_SUBPROTOCOL:
        return parts[1]
    return ""


async def require_ws_token(ws: WebSocket, token_getter: Callable[[], str]) -> bool:
    expected = token_getter()

    # Preferred (browser-safe): token in the Sec-WebSocket-Protocol header.
    if valid_token(ws_token_from_subprotocol(ws), expected):
        return True

    # Non-browser clients (tests/tools): Authorization header.
    auth = ws.headers.get("authorization", "")
    if auth.startswith("Bearer ") and valid_token(auth[7:], expected):
        return True

    await ws.close(code=4401, reason="invalid token")
    return False
