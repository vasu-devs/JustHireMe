from __future__ import annotations

from gateway.clients.base import BaseServiceClient


class GraphHttpClient(BaseServiceClient):
    service_name = "graph"
    timeout = 90.0

    async def stats(self, *, repair: bool = False) -> dict:
        return await self._request("POST", "/internal/v1/graph/stats", json={"repair": repair}, timeout=90.0)
