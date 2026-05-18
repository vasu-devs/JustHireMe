from __future__ import annotations

import secrets

from fastapi import HTTPException, Request


def require_internal_token(request: Request) -> None:
    expected = request.app.state.internal_token
    auth = request.headers.get("authorization", "")
    candidate = auth[7:] if auth.startswith("Bearer ") else ""
    if not expected or not secrets.compare_digest(candidate, expected):
        raise HTTPException(status_code=401, detail="invalid internal service token")
