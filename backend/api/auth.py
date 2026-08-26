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


async def check_http_token(request: Request, token_getter: Callable[[], str]) -> JSONResponse | None:
    """Reject an absent/invalid bearer token; ``None`` means "let it through".

    Deliberately decoupled from ``call_next``/``BaseHTTPMiddleware``: that
    plumbing buffers the *entire* downstream response through an async queue
    to hand it back as an inspectable object, which is fine for small JSON
    bodies but adds seconds of pure middleware overhead for a large one (GET
    /api/v1/leads ships ~48MB -- measured turning a ~1s query into a 10-15s
    request). api.app wires this into a plain ASGI middleware instead, which
    never touches the response body.
    """
    if request.method == "OPTIONS" or request.url.path == "/health":
        return None

    creds = await _bearer(request)
    if creds is None or not valid_token(creds.credentials, token_getter()):
        return JSONResponse(
            {"detail": "invalid token"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return None


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
