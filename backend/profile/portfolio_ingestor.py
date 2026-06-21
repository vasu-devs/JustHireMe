from __future__ import annotations

import asyncio
from urllib.parse import urlparse, urlunparse


from core.logging import get_logger
from profile.portfolio_text import _repo_title_from_url as _repo_title_from_url
from profile.portfolio_models import PageSnapshot
from profile.portfolio_crawl import (
    _CRAWL_SESSION_TIMEOUT,
    _crawl_portfolio_browser,
    _crawl_portfolio_http,
)
from profile.portfolio_crawl import _snapshot_html as _snapshot_html
from profile.portfolio_extract import (
    _collect_reference_links,
    _combined_text,
    _dedupe_pages,
    _extract_deterministic,
    _extract_with_llm,
    _merge_extract,
)

_log = get_logger(__name__)

_CRAWL_HARD_TIMEOUT = _CRAWL_SESSION_TIMEOUT + 30
async def ingest_portfolio_url(url: str) -> dict:
    """
    Crawl a real portfolio site, extract deterministic profile evidence, and
    optionally use the configured LLM to polish the structured profile.
    """
    start_url = _normalize_url(url)
    # SSRF protection is enforced at the network egress (the crawl loops skip
    # non-public hosts, the httpx hook blocks redirect hops, and a Playwright
    # route aborts internal navigations) — see profile/portfolio_crawl.py. An
    # internal URL simply yields no pages and a clean fetch-failure below.
    pages: list[PageSnapshot] = []
    screenshot_b64 = ""
    fetch_error: str | None = None

    try:
        # M6: hard backstop in case a single page await hangs past its own
        # timeout; the soft deadline inside the crawl handles the normal case
        # and returns partial pages via a normal return.
        pages, screenshot_b64 = await asyncio.wait_for(
            _crawl_portfolio_browser(start_url),
            timeout=_CRAWL_HARD_TIMEOUT,
        )
        if not pages:
            fetch_error = "Browser could not access the portfolio site."
            pages = await asyncio.to_thread(_crawl_portfolio_http, start_url)
    except TimeoutError:
        _log.warning(
            "portfolio crawl exceeded %ss hard limit for %s; falling back to HTTP",
            _CRAWL_HARD_TIMEOUT,
            start_url,
        )
        fetch_error = "Portfolio crawl timed out."
        pages = await asyncio.to_thread(_crawl_portfolio_http, start_url)
    except Exception as exc:
        _log.warning("portfolio browser crawl failed for %s: %s; trying HTTP fallback", start_url, exc)
        fetch_error = str(exc)
        pages = await asyncio.to_thread(_crawl_portfolio_http, start_url)

    pages = _dedupe_pages(pages)
    if not pages and fetch_error:
        return {"error": _portfolio_fetch_failure_message(fetch_error), "status_code": 502}
    if not pages:
        return {"error": "Could not fetch portfolio content", "status_code": 502}

    deterministic = _extract_deterministic(start_url, pages)
    llm_used = False
    extract = await _extract_with_llm(start_url, pages, deterministic)
    if extract:
        llm_used = True
        result = _merge_extract(deterministic, extract)
    else:
        result = deterministic
    result = _normalize_result_payload(result)
    references = _collect_reference_links(pages)

    result.update({
        "source": "portfolio_url",
        "url": start_url,
        "screenshot_b64": screenshot_b64,
        "raw_text": _combined_text(pages, max_chars=250000),
        "references": references,
        "evidence": {
            "pages": [{"url": page.url, "title": page.title, "text": page.text, "links": page.links} for page in pages],
        },
        "stats": {
            "pages_scanned": len(pages),
            "links_seen": sum(len(page.links) for page in pages),
            "references": len(references),
            "skills": len(result.get("skills") or []),
            "projects": len(result.get("projects") or []),
            "quality_filtered": result.pop("_quality_filtered", 0),
            "experience": len(result.get("experience") or []),
            "achievements": len(result.get("achievements") or []),
            "llm_used": llm_used,
        },
        "error": None if (result.get("candidate") or result.get("skills") or result.get("projects")) else "No structured portfolio data was extracted",
    })
    return result


def _normalize_result_payload(result: dict) -> dict:
    try:
        from profile.normalization import normalize_profile_payload

        cleaned = normalize_profile_payload(result)
        return {
            **result,
            "candidate": cleaned.get("candidate", result.get("candidate", {})),
            "identity": cleaned.get("identity", result.get("identity", {})),
            "skills": cleaned.get("skills", result.get("skills", [])),
            "projects": cleaned.get("projects", result.get("projects", [])),
            "education": cleaned.get("education", result.get("education", [])),
            "certifications": cleaned.get("certifications", result.get("certifications", [])),
            "achievements": cleaned.get("achievements", result.get("achievements", [])),
        }
    except Exception as exc:
        _log.warning("portfolio normalization skipped: %s", exc)
        return result


def _normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        parsed = urlparse(f"https://{url.strip()}")
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", parsed.query, ""))


def _portfolio_fetch_failure_message(fetch_error: str) -> str:
    if _is_missing_playwright_error(fetch_error):
        return (
            "This portfolio appears to require JavaScript rendering, but browser-based "
            "portfolio scanning is not available in this build. Update or rebuild "
            "JustHireMe with the browser feature enabled, then retry."
        )
    return f"{fetch_error} HTTP fallback also could not fetch portfolio content."


def _is_missing_playwright_error(fetch_error: str) -> bool:
    return "no module named" in fetch_error.lower() and "playwright" in fetch_error.lower()
