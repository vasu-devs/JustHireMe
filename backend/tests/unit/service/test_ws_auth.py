"""WebSocket auth: token via subprotocol header, not the URL (Tier-0 fix 0.3)."""
import asyncio

from api.auth import WS_TOKEN_SUBPROTOCOL, require_ws_token, ws_token_from_subprotocol

TOKEN = "s3cr3t-token"


class _FakeWS:
    def __init__(self, *, headers=None, query=None):
        # Starlette headers are accessed lowercase in our code.
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.query_params = query or {}
        self.closed_with = None

    async def close(self, code=1000, reason=""):
        self.closed_with = (code, reason)


def _check(ws):
    return asyncio.run(require_ws_token(ws, lambda: TOKEN))


def test_extract_token_from_subprotocol():
    ws = _FakeWS(headers={"sec-websocket-protocol": f"{WS_TOKEN_SUBPROTOCOL}, {TOKEN}"})
    assert ws_token_from_subprotocol(ws) == TOKEN


def test_subprotocol_token_accepted():
    ws = _FakeWS(headers={"sec-websocket-protocol": f"{WS_TOKEN_SUBPROTOCOL}, {TOKEN}"})
    assert _check(ws) is True
    assert ws.closed_with is None


def test_authorization_header_still_accepted():
    ws = _FakeWS(headers={"authorization": f"Bearer {TOKEN}"})
    assert _check(ws) is True


def test_query_token_no_longer_accepted():
    # The deprecated URL-query token path was removed — tokens must ride in the
    # subprotocol or Authorization header, never the URL.
    ws = _FakeWS(query={"token": TOKEN})
    assert _check(ws) is False
    assert ws.closed_with[0] == 4401


def test_invalid_token_closes_with_4401():
    ws = _FakeWS(headers={"sec-websocket-protocol": f"{WS_TOKEN_SUBPROTOCOL}, wrong"})
    assert _check(ws) is False
    assert ws.closed_with is not None and ws.closed_with[0] == 4401


def test_no_token_rejected():
    ws = _FakeWS()
    assert _check(ws) is False
    assert ws.closed_with[0] == 4401


def test_malformed_subprotocol_ignored():
    # Only the protocol name, no token after it.
    ws = _FakeWS(headers={"sec-websocket-protocol": WS_TOKEN_SUBPROTOCOL})
    assert ws_token_from_subprotocol(ws) == ""
    assert _check(ws) is False
