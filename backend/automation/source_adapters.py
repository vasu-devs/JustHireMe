from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceAdapterResult:
    leads: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def _drain(module, run, fallback_usage: dict | None = None) -> SourceAdapterResult:
    """Run a scout module's run() with a per-call result sink so the usage/errors we
    return belong to THIS call, not to a concurrent scan that raced on the module's
    LAST_USAGE/LAST_ERRORS globals. The sink is a plain dict scoped to this call; the
    scout's _publish_state fills it (in addition to the globals, kept for other
    readers). Falls back to the globals if the sink stayed empty (older run path)."""
    sink: dict = {}
    token = module._RESULT_SINK.set(sink)
    try:
        leads = run()
    finally:
        module._RESULT_SINK.reset(token)
    usage = sink.get("usage")
    if usage is None:
        usage = getattr(module, "LAST_USAGE", {}) or dict(fallback_usage or {})
    errors = sink.get("errors")
    if errors is None:
        errors = getattr(module, "LAST_ERRORS", []) or []
    return SourceAdapterResult(leads=leads, usage=usage or {}, errors=list(errors))


def run_free_scout(**kwargs) -> SourceAdapterResult:
    from automation import free_scout

    return _drain(free_scout, lambda: free_scout.run(**kwargs))


def run_apify_scout(*, urls: list[str], apify_token: str | None = None, apify_actor: str | None = None) -> SourceAdapterResult:
    from automation import scout

    return _drain(
        scout,
        lambda: scout.run(urls=urls, apify_token=apify_token, apify_actor=apify_actor),
        fallback_usage={"targets": len(urls)},
    )


def run_x_scout(**kwargs) -> SourceAdapterResult:
    from automation import x_scout

    return _drain(x_scout, lambda: x_scout.run(**kwargs))
