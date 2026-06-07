"""Portfolio site crawling.

A Playwright (headless browser) crawler with an httpx HTTP fallback, plus page
snapshotting and same-origin link extraction/prioritization. Bounded by a soft
session deadline and a max page count. Produces PageSnapshot objects consumed by
the extraction layer.
"""

from __future__ import annotations

import asyncio
import base64
import html
import re
import time
from urllib.parse import urljoin, urlparse, urlunparse

from automation.browser_runtime import launch_chromium
from core.logging import get_logger
from profile.portfolio_models import PageSnapshot
from profile.url_guard import BlockedUrlError, is_public_host
from profile.portfolio_text import (
    _canonical_url,
    _dedupe_strings,
    _looks_like_asset,
    _normalize_block_text,
    _same_origin,
)

_log = get_logger(__name__)

MAX_PAGES = 100
MAX_TEXT_PER_PAGE = 200000
# M6: cap the whole multi-page crawl. The soft deadline stops queueing new pages
# and returns what was collected.
_CRAWL_SESSION_TIMEOUT = 300
LIKELY_INTERNAL_PATHS = (
    "",
    "about",
    "projects",
    "work",
    "works",
    "portfolio",
    "case-studies",
    "experience",
    "resume",
    "services",
    "contact",
)
LINK_KEYWORDS = (
    "about",
    "project",
    "projects",
    "work",
    "portfolio",
    "case",
    "case-study",
    "experience",
    "resume",
    "service",
    "contact",
)


async def _crawl_portfolio_browser(url: str) -> tuple[list[PageSnapshot], str]:
    from playwright.async_api import async_playwright

    pages: list[PageSnapshot] = []
    screenshot_b64 = ""
    # M6: a soft deadline stops queueing new pages and returns what was
    # collected so far, bounding the otherwise-unlimited multi-page crawl.
    deadline = time.monotonic() + _CRAWL_SESSION_TIMEOUT
    async with async_playwright() as pw:
        browser = await launch_chromium(pw, headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1100},
            user_agent="JustHireMe portfolio importer",
        )
        # SSRF guard: abort any document navigation (incl. HTTP redirects) that
        # resolves to a non-public host, so a redirect can't reach internal IPs.
        await context.route("**/*", _block_private_route)
        page = await context.new_page()
        queue = _seed_urls(url)
        seen: set[str] = set()
        while queue and len(pages) < MAX_PAGES:
            if time.monotonic() > deadline:
                _log.warning(
                    "portfolio crawl hit %ss session limit; returning %d page(s)",
                    _CRAWL_SESSION_TIMEOUT,
                    len(pages),
                )
                break
            current = queue.pop(0)
            normalized = _canonical_url(current)
            if normalized in seen or not _same_origin(url, normalized):
                continue
            if not is_public_host(urlparse(normalized).hostname or ""):
                _log.warning("portfolio crawl skipped non-public host: %s", normalized)
                continue
            seen.add(normalized)
            try:
                response = await page.goto(normalized, wait_until="domcontentloaded", timeout=18000)
                if response and response.status >= 400:
                    continue
                with contextlib_suppress():
                    await page.wait_for_load_state("networkidle", timeout=5000)
                await page.wait_for_timeout(600)
                snapshot = await _snapshot_playwright_page(page)
                pages.append(snapshot)
                if not screenshot_b64:
                    raw = await page.screenshot(type="png", full_page=False)
                    screenshot_b64 = base64.b64encode(raw).decode()
                for link in _prioritize_links(url, snapshot.links):
                    href = _canonical_url(link["href"])
                    if href not in seen and href not in queue and len(queue) < MAX_PAGES * 6:
                        queue.append(href)
            except Exception as exc:
                _log.warning("portfolio page fetch failed %s: %s", normalized, exc)
        await browser.close()
    return pages, screenshot_b64


async def _block_private_route(route):
    """Abort browser document navigations to non-public hosts (SSRF/redirect guard)."""
    try:
        req = route.request
        if req.resource_type == "document":
            host = urlparse(req.url).hostname or ""
            if not await asyncio.to_thread(is_public_host, host):
                _log.warning("portfolio crawl aborted non-public navigation: %s", req.url)
                await route.abort()
                return
        await route.continue_()
    except Exception:
        # Routing must never crash the crawl; let the request proceed normally.
        try:
            await route.continue_()
        except Exception:
            pass


class contextlib_suppress:
    def __enter__(self):
        return None

    def __exit__(self, _exc_type, _exc, _tb):
        return True


async def _snapshot_playwright_page(page) -> PageSnapshot:
    data = await page.evaluate("""() => {
        const bad = ['script', 'style', 'noscript', 'svg', 'head', 'template'];
        bad.forEach(t => document.querySelectorAll(t).forEach(el => el.remove()));
        const links = Array.from(document.querySelectorAll('a[href]')).map(a => ({
            href: a.href || '',
            text: (a.innerText || a.getAttribute('aria-label') || '').trim()
        })).filter(l => l.href);
        return {
            title: document.title || '',
            text: document.body ? document.body.innerText : '',
            links
        };
    }""")
    return PageSnapshot(
        url=page.url,
        title=str(data.get("title") or ""),
        text=_normalize_block_text(str(data.get("text") or ""))[:MAX_TEXT_PER_PAGE],
        links=[{"href": str(link.get("href") or ""), "text": str(link.get("text") or "")} for link in data.get("links", []) if isinstance(link, dict)],
    )


def _crawl_portfolio_http(url: str) -> list[PageSnapshot]:
    import httpx

    def _block_private_request(request):
        # SSRF guard fires on every request incl. each redirect hop.
        if not is_public_host(request.url.host):
            raise BlockedUrlError(f"blocked non-public host during crawl: {request.url.host}")

    pages: list[PageSnapshot] = []
    queue = _seed_urls(url)
    seen: set[str] = set()
    with httpx.Client(
        timeout=16,
        follow_redirects=True,
        headers={"User-Agent": "JustHireMe portfolio importer"},
        event_hooks={"request": [_block_private_request]},
    ) as client:
        while queue and len(pages) < MAX_PAGES:
            current = _canonical_url(queue.pop(0))
            if current in seen or not _same_origin(url, current):
                continue
            if not is_public_host(urlparse(current).hostname or ""):
                _log.warning("portfolio HTTP crawl skipped non-public host: %s", current)
                continue
            seen.add(current)
            try:
                response = client.get(current)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type and "<html" not in response.text.lower():
                    continue
                snapshot = _snapshot_html(str(response.url), response.text)
                pages.append(snapshot)
                for link in _prioritize_links(url, snapshot.links):
                    href = _canonical_url(link["href"])
                    if href not in seen and href not in queue and len(queue) < MAX_PAGES * 6:
                        queue.append(href)
            except Exception as exc:
                _log.warning("portfolio HTTP page failed %s: %s", current, exc)
    return pages


def _snapshot_html(url: str, raw_html: str) -> PageSnapshot:
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw_html)
    links = _links_from_html(url, raw_html)
    text = re.sub(r"(?is)<(script|style|noscript|svg|head|template).*?</\1>", " ", raw_html)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>|</section>|</article>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return PageSnapshot(
        url=url,
        title=_normalize_block_text(html.unescape(title_match.group(1))) if title_match else "",
        text=_normalize_block_text(html.unescape(text))[:MAX_TEXT_PER_PAGE],
        links=links,
    )


def _links_from_html(base_url: str, raw_html: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for match in re.finditer(r"(?is)<a\b([^>]*)>(.*?)</a>", raw_html):
        attrs, body = match.groups()
        href_match = re.search(r"""href\s*=\s*['"]([^'"]+)['"]""", attrs)
        if not href_match:
            continue
        text = re.sub(r"<[^>]+>", " ", body)
        links.append({"href": urljoin(base_url, html.unescape(href_match.group(1))), "text": _normalize_block_text(html.unescape(text))})
    return links


def _seed_urls(url: str) -> list[str]:
    parsed = urlparse(url)
    root = urlunparse((parsed.scheme, parsed.netloc, "/", "", "", ""))
    seeds = [_canonical_url(url)]
    seeds.extend(_canonical_url(urljoin(root, path)) for path in LIKELY_INTERNAL_PATHS if path)
    return _dedupe_strings(seeds)


def _prioritize_links(root_url: str, links: list[dict[str, str]]) -> list[dict[str, str]]:
    candidates = []
    for link in links:
        href = _canonical_url(link.get("href") or "")
        if not href or not _same_origin(root_url, href) or _looks_like_asset(href):
            continue
        haystack = f"{urlparse(href).path} {link.get('text', '')}".lower()
        if any(keyword in haystack for keyword in LINK_KEYWORDS):
            candidates.append({"href": href, "text": link.get("text", "")})
    return sorted(candidates, key=lambda item: _link_score(item["href"], item.get("text", "")), reverse=True)


def _link_score(href: str, text: str) -> int:
    haystack = f"{urlparse(href).path} {text}".lower()
    score = 0
    for index, keyword in enumerate(LINK_KEYWORDS):
        if keyword in haystack:
            score += 30 - index
    return score - urlparse(href).path.count("/")
