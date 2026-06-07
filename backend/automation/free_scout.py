import logging
import asyncio
import re
import threading
from contextvars import ContextVar
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from discovery.lead_intel import canonical_lead_id
from discovery.normalizer import (
    budget_from_text,
    fit_bullets,
    followup_sequence,
    location_from_text,
    outreach_drafts,
    proof_snippet,
    signal_quality,
    tech_stack_from_text,
    urgency_from_text,
    classify_job_seniority,
)
from discovery.sources.ats import scrape_ashby as _source_scrape_ashby
from discovery.sources.ats import scrape_direct_ats_url as _source_scrape_direct_ats_url
from discovery.sources.ats import scrape_greenhouse as _source_scrape_greenhouse
from discovery.sources.ats import scrape_lever as _source_scrape_lever
from discovery.sources.ats import scrape_workable as _source_scrape_workable
from discovery.sources.custom import connector_headers as _source_connector_headers
from discovery.sources.custom import dot_get as _source_dot_get
from discovery.sources.custom import parse_json_setting as _source_parse_json_setting
from discovery.sources.custom import scrape_custom_connector as _source_scrape_custom_connector
from discovery.sources.github_jobs import github_query as _source_github_query
from discovery.sources.github_jobs import scrape_github as _source_scrape_github
from discovery.sources.hackernews import scrape_hn as _source_scrape_hn
from discovery.sources.reddit import scrape_reddit as _source_scrape_reddit
from discovery.quality_gate import MIN_DEFAULT_QUALITY, attach_quality_metadata, evaluate_lead_quality
from core.logging import get_logger

_log = get_logger(__name__)

LAST_ERRORS: list[str] = []
LAST_USAGE: dict[str, Any] = {}
# STABILITY: thread-safe scout diagnostics snapshot
_STATE_LOCK = threading.RLock()
_ERROR_SINK: ContextVar[list[str] | None] = ContextVar("free_scout_error_sink", default=None)

DEFAULT_TARGETS: list[str] = []

_CONNECTOR_MAX_ITEMS = 60


def _publish_state(errors: list[str], usage: dict[str, Any]) -> None:
    global LAST_ERRORS, LAST_USAGE
    snapshot = dict(usage)
    if isinstance(snapshot.get("by_source"), dict):
        snapshot["by_source"] = dict(snapshot["by_source"])
    with _STATE_LOCK:
        LAST_ERRORS = list(errors)
        LAST_USAGE = snapshot


def _error_sink(errors: list[str] | None = None) -> list[str]:
    return errors if errors is not None else (_ERROR_SINK.get() or LAST_ERRORS)


def rank_lead_by_feedback(lead: dict) -> dict:
    from data.repository import create_repository

    return create_repository().feedback.rank_lead_by_feedback(lead)


def save_lead(*args, **kwargs):
    from automation.lead_store import save_lead_compat

    return save_lead_compat(*args, **kwargs)


def url_exists(job_id: str) -> bool:
    from data.repository import create_repository

    return create_repository().leads.url_exists(job_id)


def split_lines(raw: str | None) -> list[str]:
    out: list[str] = []
    for line in str(raw or "").splitlines():
        line = line.strip().rstrip(",")
        if line and not line.startswith("#"):
            out.append(line)
    return out


def targets_from_settings(raw_targets: str | None, raw_watchlist: str | None) -> list[str]:
    targets = split_lines(raw_targets)
    targets.extend(_ats_targets_from_watchlist(raw_watchlist))
    return targets or list(DEFAULT_TARGETS)


def _dot_get(value, path: str, default=""):
    return _source_dot_get(value, path, default)


def _parse_json_setting(raw: str | None, fallback, errors: list[str] | None = None):
    return _source_parse_json_setting(raw, fallback, _error_sink(errors))


def _connector_headers(raw_headers: str | None, name: str, errors: list[str] | None = None) -> dict:
    return _source_connector_headers(raw_headers, name, _error_sink(errors))


def _source_error_detail(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 403:
            return "HTTP 403 blocked by source"
        if status == 429:
            return "HTTP 429 rate limited by source"
        return f"HTTP {status}"
    if isinstance(exc, httpx.TimeoutException):
        return "request timed out"
    if isinstance(exc, httpx.ConnectError):
        return "connection failed"
    return str(exc).strip() or type(exc).__name__


async def _scrape_custom_connector(
    connector: dict,
    raw_headers: str | None = None,
) -> list[dict]:
    return await _source_scrape_custom_connector(connector, raw_headers, _error_sink())


def _ats_targets_from_watchlist(raw: str | None) -> list[str]:
    targets: list[str] = []
    for line in split_lines(raw):
        parts = [p.strip() for p in re.split(r"[,|]", line) if p.strip()]
        if len(parts) == 1 and parts[0].startswith(("http://", "https://")):
            targets.append(parts[0])
            continue
        if len(parts) < 2:
            continue
        provider = parts[0].lower()
        slug = parts[1]
        if provider in {"greenhouse", "gh"}:
            targets.append(f"ats:greenhouse:{slug}")
        elif provider == "lever":
            targets.append(f"ats:lever:{slug}")
        elif provider == "ashby":
            targets.append(f"ats:ashby:{slug}")
        elif provider == "workable":
            targets.append(f"ats:workable:{slug}")
    return targets


def _text_lead(item: dict, default_kind: str = "job") -> dict:
    text = "\n".join(str(item.get(k, "")) for k in ("title", "company", "description", "url"))
    quality = signal_quality(text, default_kind=default_kind)
    kind = item.get("kind") or quality["kind"]
    budget = item.get("budget") or budget_from_text(text)
    title = item.get("title", "")
    company = item.get("company", "")
    outreach = outreach_drafts(title, company, text, kind, budget)
    stack = item.get("tech_stack") or tech_stack_from_text(text)
    location = item.get("location") or location_from_text(text)
    urgency = item.get("urgency") or urgency_from_text(text)
    meta = dict(item.get("source_meta") or {})
    if stack:
        meta.setdefault("tech_stack", stack)
    if location:
        meta.setdefault("location", location)
    if urgency:
        meta.setdefault("urgency", urgency)
    candidate = {**item, "kind": kind, "description": item.get("description", "")}
    meta.setdefault("seniority_level", classify_job_seniority(candidate))
    return {
        **item,
        "kind": kind,
        "budget": budget,
        "signal_score": quality["score"],
        "signal_reason": quality["reason"],
        "signal_tags": quality["tags"],
        "outreach_reply": outreach["reply"],
        "outreach_dm": outreach["dm"],
        "outreach_email": outreach["email"],
        "proposal_draft": outreach["proposal"],
        "fit_bullets": fit_bullets(title, text),
        "followup_sequence": followup_sequence(company, kind),
        "proof_snippet": proof_snippet(title, text, kind),
        "tech_stack": stack,
        "location": location,
        "urgency": urgency,
        "source_meta": meta,
    }


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
async def _json_get(url: str, params: dict | None = None) -> dict | list:
    headers = {
        "User-Agent": "JustHireMe free-source scout",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as cx:
        r = await cx.get(url, params=params)
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", 15))
            await asyncio.sleep(retry_after)
            r.raise_for_status()
        r.raise_for_status()
        return r.json()


async def _scrape_greenhouse(slug: str) -> list[dict]:
    return await _source_scrape_greenhouse(slug)


async def _scrape_lever(slug: str) -> list[dict]:
    return await _source_scrape_lever(slug)


async def _scrape_ashby(slug: str) -> list[dict]:
    return await _source_scrape_ashby(slug)


async def _scrape_workable(slug: str) -> list[dict]:
    return await _source_scrape_workable(slug)


def _github_query(raw: str) -> str:
    return _source_github_query(raw)


async def _scrape_github(raw: str) -> list[dict]:
    return await _source_scrape_github(raw)


async def _scrape_hn(raw: str) -> list[dict]:
    return await _source_scrape_hn(raw)


async def _scrape_reddit(raw: str) -> list[dict]:
    return await _source_scrape_reddit(raw)


async def _scrape_direct_ats_url(url: str) -> list[dict]:
    return await _source_scrape_direct_ats_url(url)


async def _scrape_target(target: str) -> list[dict]:
    lower = target.lower()
    if lower.startswith("ats:greenhouse:"):
        return await _scrape_greenhouse(target.split(":", 2)[2].strip())
    if lower.startswith("ats:lever:"):
        return await _scrape_lever(target.split(":", 2)[2].strip())
    if lower.startswith("ats:ashby:"):
        return await _scrape_ashby(target.split(":", 2)[2].strip())
    if lower.startswith("ats:workable:"):
        return await _scrape_workable(target.split(":", 2)[2].strip())
    if lower.startswith(("http://", "https://")):
        return await _scrape_direct_ats_url(target)
    if lower.startswith("github:"):
        return await _scrape_github(target)
    if lower.startswith("hn:"):
        return await _scrape_hn(target)
    if lower.startswith("reddit:"):
        return await _scrape_reddit(target)
    if lower.startswith("site:github.com"):
        return await _scrape_github(target.replace("site:github.com", "github:", 1))
    return []


def run(
    raw_targets: str | None = None,
    raw_watchlist: str | None = None,
    raw_custom_connectors: str | None = None,
    raw_custom_headers: str | None = None,
    custom_connectors_enabled: bool = False,
    targets: list[str] | None = None,
    kind_filter: str | None = None,
    max_requests: int = 20,
    min_signal_score: int = MIN_DEFAULT_QUALITY,
) -> list[dict]:
    errors: list[str] = []
    error_token = _ERROR_SINK.set(errors)
    wanted = "job"
    all_targets = targets or targets_from_settings(raw_targets, raw_watchlist)
    custom_connectors = []
    if custom_connectors_enabled:
        parsed = _parse_json_setting(raw_custom_connectors, [], errors)
        custom_connectors = parsed if isinstance(parsed, list) else []
        if parsed and not isinstance(parsed, list):
            errors.append("custom connectors must be a JSON array")
    try:
        cap = max(1, min(int(max_requests or 20), 80))
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/automation/free_scout.py:run: %s', log_exc)
        cap = 20
    try:
        min_score = max(0, min(int(min_signal_score or 45), 100))
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/automation/free_scout.py:run: %s', log_exc)
        min_score = MIN_DEFAULT_QUALITY
    usage: dict[str, Any] = {
        "configured": len(all_targets) + len(custom_connectors),
        "executed": 0,
        "candidates": 0,
        "saved": 0,
        "duplicates": 0,
        "filtered": 0,
        "missing_url": 0,
        "errors": 0,
        "by_source": {},
    }
    if not all_targets and not custom_connectors:
        errors.append("No free-source targets configured. Add profile context, source targets, a company watchlist, or custom connectors.")
        _publish_state(errors, usage)
        _ERROR_SINK.reset(error_token)
        return []

    leads: list[dict] = []
    seen: set[str] = set()

    for target in all_targets[:cap]:
        try:
            batch = asyncio.run(_scrape_target(target))
            usage["executed"] += 1
            usage["candidates"] += len(batch)
            usage["by_source"][target] = len(batch)
        except Exception as exc:
            logging.getLogger(__name__).warning('suppressed exception in backend/automation/free_scout.py:run: %s', exc)
            usage["errors"] += 1
            errors.append(f"{target}: {_source_error_detail(exc)}")
            continue

        for item in batch:
            if wanted and item.get("kind") != wanted:
                usage["filtered"] += 1
                continue
            item = rank_lead_by_feedback(item)
            quality = evaluate_lead_quality(item, min_quality=min_score)
            item = attach_quality_metadata(item, quality)
            if not quality.get("accepted"):
                usage["filtered"] += 1
                errors.append(f"filtered {item.get('platform', 'free')}:{item.get('url', '')} - {quality.get('reason', 'quality gate')}")
                continue
            if (item.get("signal_score") or 0) < min_score:
                usage["filtered"] += 1
                continue
            url = item.get("url", "")
            if not url:
                usage["missing_url"] += 1
                continue
            jid = canonical_lead_id(url)
            if jid in seen or url_exists(jid):
                usage["duplicates"] += 1
                continue
            seen.add(jid)
            item["job_id"] = jid
            save_lead(
                jid,
                item.get("title", ""),
                item.get("company", ""),
                url,
                item.get("platform", "free"),
                item.get("description", ""),
                kind=item.get("kind", "job"),
                budget=item.get("budget", ""),
                signal_score=item.get("signal_score", 0),
                signal_reason=item.get("signal_reason", ""),
                signal_tags=item.get("signal_tags", []),
                outreach_reply=item.get("outreach_reply", ""),
                outreach_dm=item.get("outreach_dm", ""),
                outreach_email=item.get("outreach_email", ""),
                proposal_draft=item.get("proposal_draft", ""),
                fit_bullets=item.get("fit_bullets", []),
                followup_sequence=item.get("followup_sequence", []),
                proof_snippet=item.get("proof_snippet", ""),
                tech_stack=item.get("tech_stack", []),
                location=item.get("location", ""),
                urgency=item.get("urgency", ""),
                base_signal_score=item.get("base_signal_score"),
                learning_delta=item.get("learning_delta"),
                learning_reason=item.get("learning_reason", ""),
                source_meta=item.get("source_meta", {}),
            )
            usage["saved"] += 1
            leads.append(item)

    remaining = max(0, cap - usage["executed"])
    for connector in custom_connectors[:remaining]:
        if not isinstance(connector, dict):
            errors.append("custom connector skipped: each connector must be an object")
            continue
        try:
            batch = asyncio.run(_scrape_custom_connector(connector, raw_custom_headers))
            usage["executed"] += 1
            name = str(connector.get("name") or connector.get("url") or "custom")
            usage["candidates"] += len(batch)
            usage["by_source"][name] = len(batch)
        except Exception as exc:
            logging.getLogger(__name__).warning('suppressed exception in backend/automation/free_scout.py:run: %s', exc)
            usage["errors"] += 1
            name = str(connector.get("name") or "custom")
            errors.append(f"{name}: {_source_error_detail(exc)}")
            continue

        for item in batch:
            if wanted and item.get("kind") != wanted:
                usage["filtered"] += 1
                continue
            item = rank_lead_by_feedback(item)
            quality = evaluate_lead_quality(item, min_quality=min_score)
            item = attach_quality_metadata(item, quality)
            if not quality.get("accepted"):
                usage["filtered"] += 1
                errors.append(f"filtered {item.get('platform', 'connector')}:{item.get('url', '')} - {quality.get('reason', 'quality gate')}")
                continue
            if (item.get("signal_score") or 0) < min_score:
                usage["filtered"] += 1
                continue
            url = item.get("url", "")
            if not url:
                usage["missing_url"] += 1
                continue
            jid = canonical_lead_id(url)
            if jid in seen or url_exists(jid):
                usage["duplicates"] += 1
                continue
            seen.add(jid)
            item["job_id"] = jid
            save_lead(
                jid,
                item.get("title", ""),
                item.get("company", ""),
                url,
                item.get("platform", "connector"),
                item.get("description", ""),
                kind=item.get("kind", "job"),
                budget=item.get("budget", ""),
                signal_score=item.get("signal_score", 0),
                signal_reason=item.get("signal_reason", ""),
                signal_tags=item.get("signal_tags", []),
                outreach_reply=item.get("outreach_reply", ""),
                outreach_dm=item.get("outreach_dm", ""),
                outreach_email=item.get("outreach_email", ""),
                proposal_draft=item.get("proposal_draft", ""),
                fit_bullets=item.get("fit_bullets", []),
                followup_sequence=item.get("followup_sequence", []),
                proof_snippet=item.get("proof_snippet", ""),
                tech_stack=item.get("tech_stack", []),
                location=item.get("location", ""),
                urgency=item.get("urgency", ""),
                base_signal_score=item.get("base_signal_score"),
                learning_delta=item.get("learning_delta"),
                learning_reason=item.get("learning_reason", ""),
                source_meta=item.get("source_meta", {}),
            )
            usage["saved"] += 1
            leads.append(item)

    if len(all_targets) > cap:
        errors.append(f"Free-source cap hit: ran {cap} of {len(all_targets)} targets")
    if len(custom_connectors) > remaining:
        errors.append(f"Custom connector cap hit: ran {remaining} of {len(custom_connectors)} connectors")
    _publish_state(errors, usage)
    _ERROR_SINK.reset(error_token)
    return leads
