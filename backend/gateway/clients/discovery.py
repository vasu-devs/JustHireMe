from __future__ import annotations

from dataclasses import dataclass, field

from gateway.clients.base import BaseServiceClient


@dataclass
class DiscoveryRunResult:
    leads: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class DiscoveryHttpClient(BaseServiceClient):
    service_name = "discovery"
    timeout = 240.0

    async def plan_board_targets(self, profile: dict, raw_urls: list[str], market_focus: str = "global") -> list[str]:
        data = await self._request(
            "POST",
            "/internal/v1/discovery/plan",
            json={"profile": profile, "raw_urls": raw_urls, "market_focus": market_focus},
            timeout=90.0,
        )
        return list(data.get("urls") or [])

    async def scan_job_boards(self, urls: list[str], cfg: dict) -> DiscoveryRunResult:
        data = await self._request("POST", "/internal/v1/discovery/scan", json={"urls": urls, "cfg": cfg}, timeout=240.0)
        return DiscoveryRunResult(leads=data.get("leads") or [], usage=data.get("usage") or {}, errors=data.get("errors") or [])

    async def scan_free_sources(self, cfg: dict, *, kind_filter: str | None = None, profile: dict | None = None, force: bool = False) -> DiscoveryRunResult:
        data = await self._request(
            "POST",
            "/internal/v1/discovery/free-sources",
            json={"cfg": cfg, "profile": profile, "kind_filter": kind_filter, "force": force},
            timeout=240.0,
        )
        return DiscoveryRunResult(leads=data.get("leads") or [], usage=data.get("usage") or {}, errors=data.get("errors") or [])

    async def scan_x(self, cfg: dict, *, kind_filter: str = "job", profile: dict | None = None) -> DiscoveryRunResult:
        data = await self._request(
            "POST",
            "/internal/v1/discovery/x",
            json={"cfg": cfg, "profile": profile, "kind_filter": kind_filter},
            timeout=240.0,
        )
        return DiscoveryRunResult(leads=data.get("leads") or [], usage=data.get("usage") or {}, errors=data.get("errors") or [])
