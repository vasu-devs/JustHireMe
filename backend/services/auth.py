from __future__ import annotations

from fastapi import HTTPException, Request


def require_internal_token(request: Request) -> None:
    expected = request.app.state.internal_token
    auth = request.headers.get("authorization", "")
    if not expected or auth != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid internal service token")
