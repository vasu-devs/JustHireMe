"""Tests for the portfolio click-to-reveal + external-reference enhancements.

These cover the parts that make a portfolio crawl capture what a single static
scrape misses — the data behind a click (project modals) and the off-site links
those reveal (a demo video, a case-study writeup) — without needing a real
browser. The browser-driven click loop itself is best-effort glue; the units it
feeds (reveal-merge, reference classification/collection) are pure and tested
here, plus an end-to-end assertion that references reach the ingestor payload.
"""

from __future__ import annotations

import asyncio

from profile.portfolio_crawl import _apply_reveals
from profile.portfolio_extract import _collect_reference_links, _reference_block
from profile.portfolio_models import PageSnapshot
from profile.portfolio_text import _external_ref_kind


def test_external_ref_kind_classifies_resource_types():
    assert _external_ref_kind("https://www.youtube.com/watch?v=abc") == "video"
    assert _external_ref_kind("https://youtu.be/abc") == "video"
    assert _external_ref_kind("https://medium.com/@me/my-case-study") == "writeup"
    assert _external_ref_kind("https://my-project.vercel.app") == "demo"
    assert _external_ref_kind("https://github.com/me/project") == "code"
    assert _external_ref_kind("https://www.behance.net/me") == "design"
    assert _external_ref_kind("https://www.linkedin.com/in/me") == "social"
    # Not a recognized reference host -> empty.
    assert _external_ref_kind("https://example.com/page") == ""
    assert _external_ref_kind("") == ""


def test_apply_reveals_appends_modal_text_and_merges_external_links():
    snapshot = PageSnapshot(
        url="https://portfolio.test/",
        title="Asha",
        text="Asha Verma — Featured Projects\nVaani",
        links=[{"href": "https://portfolio.test/about", "text": "About"}],
    )
    reveals = [
        {
            "text": "Vaani — real-time multilingual voice assistant. Watch the demo and read the case study.",
            "links": [
                {"href": "https://youtu.be/demo123", "text": "Watch demo"},
                {"href": "https://medium.com/@asha/vaani", "text": "Case study"},
                # duplicate of an existing link must not be added twice
                {"href": "https://portfolio.test/about", "text": "About"},
            ],
        }
    ]
    merged = _apply_reveals(snapshot, reveals)

    assert "real-time multilingual voice assistant" in merged.text
    hrefs = [link["href"] for link in merged.links]
    assert "https://youtu.be/demo123" in hrefs
    assert "https://medium.com/@asha/vaani" in hrefs
    assert hrefs.count("https://portfolio.test/about") == 1  # deduped


def test_apply_reveals_noop_when_empty():
    snapshot = PageSnapshot(url="https://x.test/", title="x", text="hello", links=[])
    assert _apply_reveals(snapshot, []) is snapshot


def test_collect_reference_links_picks_offsite_refs_dedup_and_excludes_social():
    pages = [
        PageSnapshot(
            url="https://portfolio.test/",
            title="Asha",
            text="...",
            links=[
                {"href": "https://youtu.be/demo123", "text": "Watch demo"},
                {"href": "https://www.linkedin.com/in/asha", "text": "LinkedIn"},  # social -> excluded
                {"href": "https://portfolio.test/projects", "text": "Projects"},  # same-origin, not a ref host
            ],
        ),
        PageSnapshot(
            url="https://portfolio.test/projects",
            title="Projects",
            text="...",
            links=[
                {"href": "https://youtu.be/demo123", "text": "Watch demo again"},  # dup -> collapsed
                {"href": "https://github.com/asha/vaani", "text": "Source"},
                {"href": "https://vaani.vercel.app", "text": "Live"},
            ],
        ),
    ]
    refs = _collect_reference_links(pages)
    by_kind = {ref["kind"] for ref in refs}
    hrefs = [ref["href"] for ref in refs]

    assert "video" in by_kind and "code" in by_kind and "demo" in by_kind
    assert "social" not in by_kind  # linkedin excluded
    assert hrefs.count("https://youtu.be/demo123") == 1  # cross-page dedup
    assert not any("portfolio.test/projects" in h for h in hrefs)  # not a reference host


def test_reference_block_renders_attributable_lines():
    block = _reference_block([
        {"href": "https://youtu.be/x", "text": "Watch demo", "kind": "video"},
        {"href": "https://github.com/me/app", "text": "", "kind": "code"},
    ])
    assert "[video] Watch demo -> https://youtu.be/x" in block
    assert "[code] (link) -> https://github.com/me/app" in block


def test_references_reach_ingestor_payload(monkeypatch):
    """End to end: external links on the crawled pages surface as result['references']
    with their kinds, and the count appears in stats."""
    import profile.portfolio_ingestor as portfolio

    pages = [
        portfolio.PageSnapshot(
            url="https://portfolio.test/",
            title="Asha Verma | Engineer",
            text="""
            Asha Verma
            Backend engineer building React, FastAPI and PostgreSQL products.
            Featured Projects
            Vaani
            Real-time multilingual voice assistant built with Python and FastAPI.
            """,
            links=[
                {"href": "https://youtu.be/demo123", "text": "Watch Vaani demo"},
                {"href": "https://medium.com/@asha/vaani-case-study", "text": "Vaani case study"},
                {"href": "https://github.com/asha/vaani", "text": "GitHub"},
            ],
        )
    ]

    async def fake_browser(_url):
        return pages, ""

    async def fake_llm(_url, _pages, _draft):
        return None  # deterministic-only so the test never calls a provider

    monkeypatch.setattr(portfolio, "_crawl_portfolio_browser", fake_browser)
    monkeypatch.setattr(portfolio, "_extract_with_llm", fake_llm)

    result = asyncio.run(portfolio.ingest_portfolio_url("https://portfolio.test"))

    refs = result["references"]
    kinds = {ref["kind"] for ref in refs}
    hrefs = {ref["href"] for ref in refs}
    assert "video" in kinds and "writeup" in kinds and "code" in kinds
    assert "https://youtu.be/demo123" in hrefs
    assert "https://medium.com/@asha/vaani-case-study" in hrefs
    assert result["stats"]["references"] == len(refs) >= 3
