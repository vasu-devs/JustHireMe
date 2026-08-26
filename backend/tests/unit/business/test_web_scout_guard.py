"""The web scout must fail loudly (not silently return []) with no usable LLM.

The Google-dork -> browser -> LLM web path extracts leads via an LLM. Without a
reachable LLM it used to contribute zero leads with no signal, which reads as
"no jobs found". These lock in the loud-fail: the scan then records a real source
error the user can act on, and no browser is launched for a doomed extraction.
"""

from __future__ import annotations

import pytest

import discovery.sources.web as web


def test_scrape_raises_loud_when_no_llm(monkeypatch):
    launched = {"crawl": False}

    def no_llm(step=None):
        raise RuntimeError("no LLM configured")

    async def fake_crawl(u, headed=False):  # pragma: no cover - must never run
        launched["crawl"] = True
        return ""

    monkeypatch.setattr("llm.client.assert_llm_configured", no_llm)
    monkeypatch.setattr("discovery.sources.web.crawl", fake_crawl)

    with pytest.raises(RuntimeError):
        web.scrape("site:example.com nurse")
    assert launched["crawl"] is False, "guard must run before any browser launch"


def test_wellfound_scrape_raises_loud_when_no_llm(monkeypatch):
    def no_llm(step=None):
        raise RuntimeError("no LLM configured")

    monkeypatch.setattr("llm.client.assert_llm_configured", no_llm)
    with pytest.raises(RuntimeError):
        web.scrape_wellfound_target("site:wellfound.com designer")


def test_scrape_proceeds_when_llm_ok(monkeypatch):
    monkeypatch.setattr("llm.client.assert_llm_configured", lambda step=None: None)

    async def fake_crawl(u, headed=False):
        return "# scraped page markdown"

    monkeypatch.setattr("discovery.sources.web.crawl", fake_crawl)
    monkeypatch.setattr(
        "discovery.sources.web.parse",
        lambda md, src: [{"title": "Nurse", "company": "Mercy", "url": "https://x/y"}],
    )

    out = web.scrape("site:example.com nurse")
    assert out == [{"title": "Nurse", "company": "Mercy", "url": "https://x/y"}]
