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


async def require_http_token(request: Request, call_next, token_getter: Callable[[], str]):
    if request.method == "OPTIONS" or request.url.path == "/health" or request.url.path.startswith("/internal/"):
        return await call_next(request)

    creds = await _bearer(request)
    if creds is None or creds.credentials != token_getter():
        return JSONResponse(
            {"detail": "invalid token"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return await call_next(request)


async def require_ws_token(ws: WebSocket, token_getter: Callable[[], str]) -> bool:
    token = ws.query_params.get("token", "")
    if token == token_getter():
        return True

    auth = ws.headers.get("authorization", "")
    if auth.startswith("Bearer ") and auth[7:] == token_getter():
        return True

    await ws.close(code=4401, reason="invalid token")
    return False
