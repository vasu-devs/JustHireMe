"""Opt-in paid job API adapters with hard, local request governance.

Provider credentials never appear in SourceTarget, source health, logs, or API
responses. Every call first reserves allowance in SQLite; the reservation is
durable even if the process exits during network I/O.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from catalog.source_registry import SourceTarget
from core.config import int_cfg, truthy
from discovery.normalizer import strip_html_text
from discovery.sources.net import guarded_async_client
from opportunities.eligibility import CandidateConstraints


PAID_PROVIDERS = ("serpapi", "adzuna", "jooble")


_QUERY_SECRET = re.compile(r"(?i)([?&](?:api_key|app_key)=)[^&\s]+")
_JOOBLE_PATH_SECRET = re.compile(r"(?i)(https://(?:[a-z]{2}\.)?jooble\.org/api/)[^/?\s]+")


def _redact_provider_url(value: object) -> object:
    text = str(value)
    redacted = _QUERY_SECRET.sub(r"\1[REDACTED]", text)
    redacted = _JOOBLE_PATH_SECRET.sub(r"\1[REDACTED]", redacted)
    return redacted if redacted != text else value


class _PaidCredentialLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_provider_url(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: _redact_provider_url(value) for key, value in record.args.items()}
        return True


for _logger_name in ("httpx", "httpcore"):
    _network_logger = logging.getLogger(_logger_name)
    if not any(isinstance(value, _PaidCredentialLogFilter) for value in _network_logger.filters):
        _network_logger.addFilter(_PaidCredentialLogFilter())


class PaidProviderBudgetExceeded(RuntimeError):
    def __init__(self, provider: str, reason: str) -> None:
        self.provider = provider
        self.reason = reason
        super().__init__(f"{provider} request not sent: {reason}")


class PaidProviderRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class PaidProviderPolicy:
    provider: str
    enabled: bool
    configured: bool
    daily_request_cap: int
    monthly_request_cap: int
    daily_spend_cap_usd: float
    monthly_spend_cap_usd: float
    estimated_cost_per_request_usd: float


def _float_cfg(cfg: dict, key: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(str(cfg.get(key, "") or default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _credentials_configured(provider: str, cfg: dict) -> bool:
    if provider == "serpapi":
        return bool(str(cfg.get("serpapi_api_key") or "").strip())
    if provider == "adzuna":
        return bool(str(cfg.get("adzuna_app_id") or "").strip() and str(cfg.get("adzuna_app_key") or "").strip())
    if provider == "jooble":
        return bool(str(cfg.get("jooble_api_key") or "").strip())
    return False


def provider_policy(provider: str, cfg: dict) -> PaidProviderPolicy:
    provider = provider.strip().lower()
    master = truthy(cfg.get("paid_sources_enabled", "false"))
    return PaidProviderPolicy(
        provider=provider,
        enabled=master and truthy(cfg.get(f"{provider}_jobs_enabled", "false")),
        configured=_credentials_configured(provider, cfg),
        daily_request_cap=int_cfg(cfg, "paid_provider_daily_request_cap", 5, 1, 500),
        monthly_request_cap=int_cfg(cfg, "paid_provider_monthly_request_cap", 100, 1, 10_000),
        daily_spend_cap_usd=_float_cfg(cfg, "paid_provider_daily_spend_cap_usd", 0, 0, 10_000),
        monthly_spend_cap_usd=_float_cfg(cfg, "paid_provider_monthly_spend_cap_usd", 0, 0, 100_000),
        estimated_cost_per_request_usd=_float_cfg(
            cfg, f"{provider}_estimated_cost_per_request_usd", 0, 0, 1_000
        ),
    )


def _queries(candidate: CandidateConstraints) -> list[tuple[str, str]]:
    tracks = {track.value for track in candidate.preferred_technical_tracks}
    queries: list[tuple[str, str]] = []
    if not tracks or tracks & {"software", "backend", "frontend", "fullstack", "mobile", "qa_automation"}:
        queries.append(("software-engineering-intern-india", "software engineering intern"))
    if not tracks or tracks & {"ai_ml", "data"}:
        queries.extend([
            ("ai-ml-intern-india", "machine learning AI intern"),
            ("data-intern-india", "data science data engineering intern"),
        ])
    if tracks & {"cloud_devops", "security", "embedded_systems"}:
        label = " ".join(sorted(tracks & {"cloud_devops", "security", "embedded_systems"})).replace("_", " ")
        queries.append(("specialist-intern-india", f"{label} intern"))
    queries.extend([
        ("worldwide-remote-intern", "worldwide remote software engineering intern"),
        ("software-new-grad-india", "software engineer new grad"),
        ("entry-level-software-india", "entry level software engineer"),
    ])
    seen: set[str] = set()
    unique_queries: list[tuple[str, str]] = []
    for key, value in queries:
        if value in seen:
            continue
        seen.add(value)
        unique_queries.append((key, value))
    return unique_queries


def paid_provider_targets(
    cfg: dict,
    candidate: CandidateConstraints,
    usage_by_provider: dict[str, dict] | None = None,
) -> list[SourceTarget]:
    """Build only targets that are enabled, configured, and still affordable."""
    usage_by_provider = usage_by_provider or {}
    targets: list[SourceTarget] = []
    for provider in PAID_PROVIDERS:
        policy = provider_policy(provider, cfg)
        usage = usage_by_provider.get(provider) or {}
        remaining = min(
            policy.daily_request_cap - int(usage.get("requests_today") or 0),
            policy.monthly_request_cap - int(usage.get("requests_month") or 0),
        )
        if not policy.enabled or not policy.configured or remaining <= 0:
            continue
        queries = _queries(candidate)
        if provider in {"adzuna", "jooble"}:
            queries = [row for row in queries if row[0] != "worldwide-remote-intern"]
        for query_id, query in queries[:remaining]:
            # Adzuna and Jooble are regional APIs; their India endpoints cover
            # India onsite/hybrid plus remote-India. SerpApi also carries the
            # worldwide-remote query while originating the search from India.
            targets.append(SourceTarget(
                target_id=f"paid:{provider}:{query_id}",
                provider=provider,
                scan_target=f"paid:{provider}:{query}@@India",
                parser_version="1",
            ))
    return targets


def _target_parts(target: str) -> tuple[str, str, str]:
    prefix, provider, body = target.split(":", 2)
    if prefix != "paid" or provider not in PAID_PROVIDERS:
        raise ValueError("unknown paid provider target")
    query, _, location = body.partition("@@")
    if not query.strip():
        raise ValueError("paid provider query is required")
    return provider, query.strip(), location.strip() or "India"


def _serpapi_rows(data: dict) -> list[dict]:
    rows: list[dict] = []
    for job in data.get("jobs_results", []) if isinstance(data, dict) else []:
        if not isinstance(job, dict):
            continue
        apply_options = job.get("apply_options") if isinstance(job.get("apply_options"), list) else []
        apply_url = next(
            (str(option.get("link") or "").strip() for option in apply_options if isinstance(option, dict) and option.get("link")),
            "",
        )
        url = apply_url or str(job.get("share_link") or "").strip()
        title = str(job.get("title") or "").strip()
        if not title or not url:
            continue
        detected = job.get("detected_extensions") if isinstance(job.get("detected_extensions"), dict) else {}
        extensions = "\n".join(str(value) for value in (job.get("extensions") or []) if value)
        rows.append({
            "title": title,
            "company": str(job.get("company_name") or "").strip(),
            "url": url,
            "apply_url": apply_url,
            "platform": "serpapi",
            "location": str(job.get("location") or "").strip(),
            "description": "\n".join(filter(None, [strip_html_text(str(job.get("description") or "")), extensions])),
            "posted_date": str(detected.get("posted_at") or ""),
            "budget": str(detected.get("salary") or ""),
            "attribution": str(job.get("via") or "SerpApi Google Jobs"),
            "source_meta": {"id": str(job.get("job_id") or ""), "origin": str(job.get("via") or "")},
        })
    return rows


def _adzuna_rows(data: dict) -> list[dict]:
    rows: list[dict] = []
    for job in data.get("results", []) if isinstance(data, dict) else []:
        if not isinstance(job, dict):
            continue
        location = job.get("location") if isinstance(job.get("location"), dict) else {}
        company = job.get("company") if isinstance(job.get("company"), dict) else {}
        url = str(job.get("redirect_url") or "").strip()
        title = strip_html_text(str(job.get("title") or "")).strip()
        if not title or not url:
            continue
        salary_min, salary_max = job.get("salary_min"), job.get("salary_max")
        salary = ""
        if salary_min is not None or salary_max is not None:
            salary = f"Salary {salary_min or '?'} - {salary_max or '?'}"
        rows.append({
            "title": title,
            "company": str(company.get("display_name") or "").strip(),
            "url": url,
            "platform": "adzuna",
            "location": str(location.get("display_name") or "").strip(),
            "description": "\n".join(filter(None, [strip_html_text(str(job.get("description") or "")), salary])),
            "posted_date": str(job.get("created") or ""),
            "budget": salary,
            "attribution": "Adzuna",
            "source_meta": {"id": str(job.get("id") or ""), "category": str((job.get("category") or {}).get("label") or "") if isinstance(job.get("category"), dict) else ""},
        })
    return rows


def _jooble_rows(data: dict) -> list[dict]:
    rows: list[dict] = []
    for job in data.get("jobs", []) if isinstance(data, dict) else []:
        if not isinstance(job, dict):
            continue
        url = str(job.get("link") or "").strip()
        title = strip_html_text(str(job.get("title") or "")).strip()
        if not title or not url:
            continue
        rows.append({
            "title": title,
            "company": str(job.get("company") or "").strip(),
            "url": url,
            "platform": "jooble",
            "location": str(job.get("location") or "").strip(),
            "description": "\n".join(filter(None, [strip_html_text(str(job.get("snippet") or "")), str(job.get("type") or ""), str(job.get("salary") or "")])),
            "posted_date": str(job.get("updated") or ""),
            "budget": str(job.get("salary") or ""),
            "attribution": str(job.get("source") or "Jooble"),
            "source_meta": {"id": str(job.get("id") or ""), "origin": str(job.get("source") or "")},
        })
    return rows


async def _fetch(provider: str, query: str, location: str, cfg: dict) -> list[dict]:
    headers = {"User-Agent": "JustHireMe paid opportunity scout", "Accept": "application/json"}
    async with guarded_async_client(timeout=35, headers=headers, follow_redirects=True) as client:
        if provider == "serpapi":
            response = await client.get("https://serpapi.com/search.json", params={
                "engine": "google_jobs", "q": query, "location": location,
                "gl": "in", "hl": "en", "api_key": str(cfg.get("serpapi_api_key") or ""),
                "no_cache": "false",
            })
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get("error"):
                raise RuntimeError("provider returned an API error")
            return _serpapi_rows(payload if isinstance(payload, dict) else {})
        if provider == "adzuna":
            response = await client.get("https://api.adzuna.com/v1/api/jobs/in/search/1", params={
                "app_id": str(cfg.get("adzuna_app_id") or ""),
                "app_key": str(cfg.get("adzuna_app_key") or ""),
                "results_per_page": "50", "what": query, "where": location,
                "content-type": "application/json",
            })
            response.raise_for_status()
            payload = response.json()
            return _adzuna_rows(payload if isinstance(payload, dict) else {})
        domain = str(cfg.get("jooble_api_domain") or "in.jooble.org").strip().lower()
        parsed = urlsplit(f"https://{domain}")
        if not parsed.hostname or parsed.hostname != domain or not (domain == "jooble.org" or domain.endswith(".jooble.org")):
            raise ValueError("jooble_api_domain must be a jooble.org domain")
        response = await client.post(
            f"https://{domain}/api/{str(cfg.get('jooble_api_key') or '').strip()}",
            json={"keywords": query, "location": location, "page": "1", "ResultOnPage": "50", "companysearch": "false"},
        )
        response.raise_for_status()
        payload = response.json()
        return _jooble_rows(payload if isinstance(payload, dict) else {})


async def scrape_paid_target(target: str, *, cfg: dict, run_id: str, paid_store) -> list[dict]:
    provider, query, location = _target_parts(target)
    policy = provider_policy(provider, cfg)
    if not policy.enabled or not policy.configured:
        raise PaidProviderBudgetExceeded(provider, "provider_not_ready")
    target_id = f"paid:{provider}:{query[:120]}"
    reservation = await asyncio.to_thread(
        paid_store.reserve_request,
        provider,
        run_id=run_id,
        target_id=target_id,
        daily_request_cap=policy.daily_request_cap,
        monthly_request_cap=policy.monthly_request_cap,
        estimated_cost_usd=policy.estimated_cost_per_request_usd,
        daily_spend_cap_usd=policy.daily_spend_cap_usd,
        monthly_spend_cap_usd=policy.monthly_spend_cap_usd,
    )
    if not reservation.get("allowed"):
        raise PaidProviderBudgetExceeded(provider, str(reservation.get("reason") or "cap_exhausted"))
    request_id = str(reservation["request_id"])
    try:
        rows = await _fetch(provider, query, location, cfg)
    except Exception as exc:
        await asyncio.to_thread(
            paid_store.finish_request, request_id, status="failure", error_type=type(exc).__name__
        )
        # Deliberately omit URLs and provider response bodies: Jooble embeds its
        # credential in the path and HTTP exceptions would otherwise leak it.
        raise PaidProviderRequestError(f"{provider} request failed ({type(exc).__name__})") from exc
    await asyncio.to_thread(
        paid_store.finish_request, request_id, status="success", response_rows=len(rows)
    )
    return rows


def redacted_provider_status(provider: str, cfg: dict, usage: dict) -> dict:
    policy = provider_policy(provider, cfg)
    master = truthy(cfg.get("paid_sources_enabled", "false"))
    requests_today = int(usage.get("requests_today") or 0)
    requests_month = int(usage.get("requests_month") or 0)
    spend_today = float(usage.get("estimated_spend_today_usd") or 0)
    spend_month = float(usage.get("estimated_spend_month_usd") or 0)
    ratios = [
        requests_today / policy.daily_request_cap,
        requests_month / policy.monthly_request_cap,
    ]
    if policy.daily_spend_cap_usd > 0:
        ratios.append(spend_today / policy.daily_spend_cap_usd)
    if policy.monthly_spend_cap_usd > 0:
        ratios.append(spend_month / policy.monthly_spend_cap_usd)
    ratio = max(ratios, default=0)
    alert = "cap_reached" if ratio >= 1 else "warning_80" if ratio >= 0.8 else "notice_50" if ratio >= 0.5 else "normal"
    if not master:
        state = "master_disabled"
    elif not truthy(cfg.get(f"{provider}_jobs_enabled", "false")):
        state = "disabled"
    elif not policy.configured:
        state = "missing_credentials"
    elif ratio >= 1:
        state = "cap_reached"
    else:
        state = "ready"
    successful = int(usage.get("successful_requests") or 0)
    net_new_percent = float(usage.get("net_new_eligible_yield_percent") or 0)
    benchmark = "insufficient_data" if successful < 10 else "retain" if net_new_percent >= 10 else "pause_and_review"
    return {
        "provider": provider,
        "state": state,
        "enabled": policy.enabled,
        "configured": policy.configured,
        "alert": alert,
        "limits": {
            "daily_requests": policy.daily_request_cap,
            "monthly_requests": policy.monthly_request_cap,
            "daily_spend_usd": policy.daily_spend_cap_usd,
            "monthly_spend_usd": policy.monthly_spend_cap_usd,
            "estimated_cost_per_request_usd": policy.estimated_cost_per_request_usd,
        },
        "usage": usage,
        "remaining": {
            "daily_requests": max(0, policy.daily_request_cap - requests_today),
            "monthly_requests": max(0, policy.monthly_request_cap - requests_month),
        },
        "experiment": {
            "benchmark": benchmark,
            "minimum_successful_requests": 10,
            "retention_threshold_net_new_eligible_percent": 10,
        },
    }
