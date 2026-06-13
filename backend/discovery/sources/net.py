"""SSRF-guarded HTTP client for discovery source fetchers.

Source adapters fetch user/config-supplied URLs (custom connectors, RSS feeds,
job-board APIs). Without a guard a crafted feed URL — or a redirect from a
legitimate-looking host — could drive the backend into internal services
(``127.0.0.1``, cloud metadata at ``169.254.169.254``, private LAN hosts).

``guarded_async_client`` installs an httpx request event-hook that runs on the
initial request *and on every redirect*, so auto-redirect following cannot reach
an internal host. The same public-host policy as the portfolio crawler is reused
(see ``profile.url_guard``).
"""

from __future__ import annotations

import httpx

from core.url_guard import assert_public_url


async def _guard_request(request: httpx.Request) -> None:
    # getaddrinfo here is a brief blocking call; acceptable for the scout path
    # and far cheaper than the network fetch it gates.
    assert_public_url(str(request.url))


def guarded_async_client(**kwargs) -> httpx.AsyncClient:
    """An httpx.AsyncClient that refuses non-public hosts, including on redirect."""
    hooks = kwargs.pop("event_hooks", {}) or {}
    request_hooks = list(hooks.get("request", []))
    request_hooks.append(_guard_request)
    hooks["request"] = request_hooks
    return httpx.AsyncClient(event_hooks=hooks, **kwargs)
