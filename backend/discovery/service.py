from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from discovery.targets import (
    free_sources_enabled,
    has_profile_discovery_signal,
    has_x_token,
    int_cfg,
    profile_free_source_targets,
    profile_x_queries,
    truthy,
)


@dataclass
class DiscoveryRunResult:
    leads: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class DiscoveryService:
    async def plan_board_targets(self, profile: dict, raw_urls: list[str], market_focus: str = "global") -> list[str]:
        from discovery.query_gen import generate

        return await asyncio.to_thread(generate, profile, raw_urls, market_focus)

    async def scan_job_boards(
        self,
        urls: list[str],
        cfg: dict,
        should_stop: Callable[[], bool] | None = None,
    ) -> DiscoveryRunResult:
        from discovery.sources.apify import run_board_scan

        result = await asyncio.to_thread(run_board_scan, urls, cfg, should_stop)
        return DiscoveryRunResult(leads=result.leads, usage=result.usage, errors=result.errors)

    async def scan_free_sources(
        self,
        cfg: dict,
        *,
        kind_filter: str | None = None,
        profile: dict | None = None,
        force: bool = False,
        should_stop: Callable[[], bool] | None = None,
    ) -> DiscoveryRunResult:
        if not force and not free_sources_enabled(cfg):
            return DiscoveryRunResult()

        from automation.source_adapters import run_free_scout

        raw_targets = cfg.get("free_source_targets", "") or profile_free_source_targets(profile or {})
        has_watchlist = bool(str(cfg.get("company_watchlist", "") or "").strip())
        has_connectors = truthy(cfg.get("custom_connectors_enabled", "false")) and bool(str(cfg.get("custom_connectors", "") or "").strip())
        if not str(raw_targets or "").strip() and not has_watchlist and not has_connectors:
            if has_profile_discovery_signal(profile):
                message = "Free-source scan skipped: no runnable source targets were derived from this profile."
            else:
                message = "Free-source scan skipped: add a target role, profile skills, source targets, or a company watchlist."
            return DiscoveryRunResult(errors=[message])

        result = await asyncio.to_thread(
            run_free_scout,
            raw_targets=raw_targets,
            raw_watchlist=cfg.get("company_watchlist", ""),
            raw_custom_connectors=cfg.get("custom_connectors", ""),
            raw_custom_headers=cfg.get("custom_connector_headers", ""),
            custom_connectors_enabled=truthy(cfg.get("custom_connectors_enabled", "false")),
            kind_filter=kind_filter or "job",
            max_requests=int_cfg(cfg, "free_source_max_requests", 20, 1, 80),
            min_signal_score=int_cfg(cfg, "free_source_min_signal_score", 60, 0, 100),
            should_stop=should_stop,
        )
        return DiscoveryRunResult(
            leads=result.leads,
            usage=result.usage,
            errors=result.errors,
        )

    async def scan_x(
        self,
        cfg: dict,
        *,
        kind_filter: str = "job",
        profile: dict | None = None,
        should_stop=None,
    ) -> DiscoveryRunResult:
        if not has_x_token(cfg):
            return DiscoveryRunResult()

        from discovery.sources.x_twitter import run_x_scan

        result = await asyncio.to_thread(
            run_x_scan,
            should_stop=should_stop,
            bearer_token=cfg.get("x_bearer_token") or None,
            raw_queries=cfg.get("x_search_queries", "") or profile_x_queries(profile or {}, cfg.get("job_market_focus", "global")),
            raw_watchlist=cfg.get("x_watchlist", ""),
            kind_filter=kind_filter,
            max_requests=int_cfg(cfg, "x_max_requests_per_scan", 5, 1, 50),
            max_results=int_cfg(cfg, "x_max_results_per_query", 50, 10, 100),
            min_signal_score=int_cfg(cfg, "x_min_signal_score", 55, 0, 100),
        )
        return DiscoveryRunResult(
            leads=result.leads,
            usage=result.usage,
            errors=result.errors,
        )


def create_discovery_service() -> DiscoveryService:
    return DiscoveryService()
