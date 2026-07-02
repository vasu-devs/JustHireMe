from __future__ import annotations

import asyncio

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from discovery.sources.net import guarded_async_client

from discovery.normalizer import (
    budget_from_text,
    classify_job_seniority,
    fit_bullets,
    followup_sequence,
    location_from_text,
    outreach_drafts,
    proof_snippet,
    signal_quality,
    tech_stack_from_text,
    urgency_from_text,
)


def _is_retryable_source_error(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or 500 <= status < 600
    return False


def retry_after_seconds(value, default: int = 15) -> int:
    """Parse an HTTP ``Retry-After`` header. RFC 7231 allows either delay-seconds
    OR an HTTP-date; a bare ``int(value)`` raised ValueError on the date form, and
    since ValueError isn't retryable that aborted the 429 back-off entirely. Returns
    a sane seconds value clamped to [1, 300], falling back to ``default``."""
    text = str(value or "").strip()
    if not text:
        return default
    if text.isdigit():
        return max(1, min(int(text), 300))
    try:
        from datetime import datetime, timezone
        from email.utils import parsedate_to_datetime
        when = parsedate_to_datetime(text)
        if when is not None:
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            delta = int((when - datetime.now(timezone.utc)).total_seconds())
            return max(1, min(delta, 300))
    except Exception:
        pass
    return default


def text_lead(item: dict, default_kind: str = "job") -> dict:
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
    retry=retry_if_exception(_is_retryable_source_error),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
async def json_get(url: str, params: dict | None = None) -> dict | list:
    headers = {
        "User-Agent": "JustHireMe free-source scout",
        "Accept": "application/json",
    }
    async with guarded_async_client(timeout=30, headers=headers, follow_redirects=True) as cx:
        r = await cx.get(url, params=params)
        if r.status_code == 429:
            retry_after = retry_after_seconds(r.headers.get("Retry-After"))
            await asyncio.sleep(retry_after)
            r.raise_for_status()
        r.raise_for_status()
        return r.json()


@retry(
    retry=retry_if_exception(_is_retryable_source_error),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
async def xml_get(url: str, params: dict | None = None) -> str:
    """Fetch an XML source feed (e.g. Personio's recruiting feed) as raw text.

    Same SSRF-guarded client + retry policy as ``json_get``; the caller parses
    the returned text with ``defusedxml`` (never the stdlib XML parser).
    """
    headers = {
        "User-Agent": "JustHireMe free-source scout",
        "Accept": "application/xml, text/xml",
    }
    async with guarded_async_client(timeout=30, headers=headers, follow_redirects=True) as cx:
        r = await cx.get(url, params=params)
        if r.status_code == 429:
            retry_after = retry_after_seconds(r.headers.get("Retry-After"))
            await asyncio.sleep(retry_after)
            r.raise_for_status()
        r.raise_for_status()
        return r.text
