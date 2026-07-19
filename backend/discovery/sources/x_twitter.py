from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class XScanResult:
    leads: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def run_x_scan(
    *,
    bearer_token: str | None = None,
    raw_queries: str | None = None,
    queries: list[str] | None = None,
    kind_filter: str | None = None,
    max_results: int = 50,
    raw_watchlist: str | None = None,
    max_requests: int = 5,
    min_signal_score: int = 55,
    should_stop=None,
) -> XScanResult:
    from automation.source_adapters import run_x_scout

    result = run_x_scout(
        bearer_token=bearer_token,
        raw_queries=raw_queries,
        queries=queries,
        kind_filter=kind_filter,
        max_results=max_results,
        raw_watchlist=raw_watchlist,
        max_requests=max_requests,
        min_signal_score=min_signal_score,
        should_stop=should_stop,
    )
    return XScanResult(
        leads=result.leads,
        usage=result.usage,
        errors=result.errors,
    )
