"""Regression tests for the audit-confirmed discovery correctness bugs.

Covers: location regex over-capture, seniority precedence (entry-level noun
collision), future-date freshness, Personio .de TLD, and the watchlist mapper
dropping the new keyless ATS providers.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from discovery import quality_gate
from discovery.lead_intel import location_from_text
from discovery.normalizer import classify_job_seniority
from discovery.sources import ats


# --- location_from_text -------------------------------------------------------

def test_location_ignores_lowercase_prose_after_keyword():
    # Previously re.I let [A-Z] match lowercase -> "onsite work required" captured
    # "work required" as a location.
    assert location_from_text("onsite work required") == ""
    assert location_from_text("hybrid schedule expected") == ""
    assert location_from_text("we offer onsite and hybrid options") == ""


def test_location_still_captures_real_locations():
    assert location_from_text("Location: Berlin") == "Berlin"
    # Capital-initial location is still captured (trailing prose over-capture is a
    # separate, pre-existing behavior; the fix here is only the lowercase anchor).
    assert location_from_text("Based in New York, hiring now").startswith("New York")
    assert location_from_text("Onsite Bengaluru role").lower().startswith("bengaluru")
    assert location_from_text("Fully remote team") == "Remote"


# --- classify_job_seniority (both copies) -------------------------------------

def _scout_classify(lead):
    from automation.scout import classify_job_seniority as scout_classify
    return scout_classify(lead)


def test_entry_level_with_senior_noun_is_not_senior():
    lead = {"title": "Account Manager - Entry Level (0-2 years)"}
    assert classify_job_seniority(lead) in {"fresher", "junior"}
    assert _scout_classify(lead) in {"fresher", "junior"}


def test_graduate_with_lead_noun_is_not_senior():
    lead = {"title": "Graduate Program - Team Lead track", "description": "for new grads"}
    assert classify_job_seniority(lead) == "fresher"
    assert _scout_classify(lead) == "fresher"


def test_genuine_senior_still_senior():
    assert classify_job_seniority({"title": "Senior Backend Engineer"}) == "senior"
    assert classify_job_seniority({"title": "Backend Engineer", "description": "5+ years required"}) == "senior"
    assert _scout_classify({"title": "Senior Backend Engineer"}) == "senior"


def test_bare_low_year_range_beats_incidental_senior_noun():
    # Round-6 regression: a bare "<=2 years" range with an incidental senior NOUN
    # (no junior WORD/range-term) must classify junior, not senior — otherwise these
    # genuinely entry-level postings get dropped from the beginner feed and hit the
    # quality-gate senior penalty. The <=2yr fallback must run BEFORE the senior test.
    for lead in (
        {"title": "Support Lead", "description": "requires 2 years experience"},
        {"title": "Marketing Manager", "description": "2 yoe"},
        {"title": "Solutions Architect", "description": "2 yrs"},
    ):
        assert classify_job_seniority(lead) == "junior", lead
        assert _scout_classify(lead) == "junior", lead


# --- quality_gate freshness (future date) -------------------------------------

def test_future_posting_date_is_not_fresh():
    future = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
    ok, reason = quality_gate._freshness({"posted_date": future})
    assert ok is False
    assert "future" in reason.lower()


def test_recent_posting_still_fresh():
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    ok, _reason = quality_gate._freshness({"posted_date": recent})
    assert ok is True


def test_sub_day_future_skew_is_still_fresh():
    # NTP/timezone skew: a posting a few hours ahead must stay fresh, not be
    # rejected by the future-date guard (timedelta.days floors to -1).
    soon = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    ok, _reason = quality_gate._freshness({"posted_date": soon})
    assert ok is True


def test_personio_auto_tld_tries_com_then_de(monkeypatch):
    # A bare slug (watchlist / ats: form carries no TLD) must try .com then .de.
    seen = []

    async def fake_xml_get(url, params=None):
        seen.append(url)
        return "<positions></positions>"  # empty -> triggers the .de retry

    monkeypatch.setattr(ats, "xml_get", fake_xml_get)
    asyncio.run(ats.scrape_personio("acme"))  # no explicit tld
    assert seen == ["https://acme.jobs.personio.com/xml", "https://acme.jobs.personio.de/xml"]


# --- Personio .de TLD ---------------------------------------------------------

def test_personio_uses_real_tld(monkeypatch):
    captured = {}

    async def fake_xml_get(url, params=None):
        captured["url"] = url
        return "<positions></positions>"

    monkeypatch.setattr(ats, "xml_get", fake_xml_get)
    asyncio.run(ats.scrape_personio("acme", "de"))
    assert captured["url"] == "https://acme.jobs.personio.de/xml"


def test_personio_direct_url_preserves_de_tld(monkeypatch):
    captured = {}

    async def fake(slug, tld="com"):
        captured["slug"] = slug
        captured["tld"] = tld
        return []

    monkeypatch.setattr(ats, "scrape_personio", fake)
    asyncio.run(ats.scrape_direct_ats_url("https://acme.jobs.personio.de/"))
    assert captured == {"slug": "acme", "tld": "de"}


# --- watchlist -> new keyless providers ---------------------------------------

def test_watchlist_maps_new_keyless_providers():
    from automation.free_scout import _ats_targets_from_watchlist

    out = _ats_targets_from_watchlist(
        "smartrecruiters,acme\nrecruitee,beta\npersonio,gamma\ngreenhouse,delta"
    )
    assert "ats:smartrecruiters:acme" in out
    assert "ats:recruitee:beta" in out
    assert "ats:personio:gamma" in out
    assert "ats:greenhouse:delta" in out  # legacy still works
