"""Round-9 audit fixes: ATS adapters survive a malformed entry; keyword coverage
scans the same extra vocabulary on the JD and profile sides."""

from __future__ import annotations

import asyncio
from unittest import mock

from discovery.sources import ats
from generation.generators.keywords import (
    _EXTRA_JD_TERMS,
    _job_keyword_terms,
    _profile_keyword_terms,
)


def _fake_json_get(return_value):
    async def _inner(url, params=None):
        return return_value
    return _inner


# --- ATS adapters: a single non-dict entry must not drop the whole board ----------

def test_greenhouse_skips_non_dict_entry_and_keeps_valid_jobs():
    data = {"jobs": ["junk-string", {"title": "Good Role", "absolute_url": "https://x/1", "content": "desc"}]}
    with mock.patch("discovery.sources.ats.json_get", new=_fake_json_get(data)):
        leads = asyncio.run(ats.scrape_greenhouse("acme"))
    assert [lead["title"] for lead in leads] == ["Good Role"], leads


def test_greenhouse_tolerates_list_valued_location():
    data = {"jobs": [{"title": "Role", "absolute_url": "https://x/1", "content": "d", "location": ["remote"]}]}
    with mock.patch("discovery.sources.ats.json_get", new=_fake_json_get(data)):
        leads = asyncio.run(ats.scrape_greenhouse("acme"))  # must not raise
    assert len(leads) == 1


def test_lever_skips_non_dict_entry_and_keeps_valid_jobs():
    data = ["junk-string", {"text": "Good Role", "hostedUrl": "https://x/1", "descriptionPlain": "desc"}]
    with mock.patch("discovery.sources.ats.json_get", new=_fake_json_get(data)):
        leads = asyncio.run(ats.scrape_lever("acme"))
    assert [lead["title"] for lead in leads] == ["Good Role"], leads


def test_ashby_skips_non_dict_entry_and_keeps_valid_jobs():
    data = {"jobs": ["junk-string", {"title": "Good Role", "jobUrl": "https://x/1", "descriptionHtml": "desc"}]}
    with mock.patch("discovery.sources.ats.json_get", new=_fake_json_get(data)):
        leads = asyncio.run(ats.scrape_ashby("acme"))
    assert [lead["title"] for lead in leads] == ["Good Role"], leads


# --- keyword coverage: extra JD terms must be coverable from the profile ----------

def test_profile_scans_same_extra_vocabulary_as_jd():
    jd = "We need Kafka, microservices, distributed systems, event-driven architecture, and system design."
    profile = {
        "skills": [{"n": "Kafka"}, {"n": "Microservices"}],
        "projects": [{
            "title": "Pipeline",
            "impact": "event-driven distributed system design at scale",
            "stack": "Kafka",
        }],
    }
    jd_terms = set(_job_keyword_terms(jd))
    profile_terms = _profile_keyword_terms(profile)
    for canonical in _EXTRA_JD_TERMS:
        assert canonical in jd_terms, (canonical, jd_terms)
        # Previously these 5 were structurally uncoverable (profile side only scanned
        # TECH_TAXONOMY), so a genuine skill was always reported as a gap.
        assert canonical in profile_terms, (canonical, profile_terms)


def test_extra_terms_absent_from_profile_are_not_falsely_covered():
    profile = {"skills": [{"n": "Python"}], "projects": [{"title": "Blog", "impact": "wrote a blog"}]}
    profile_terms = _profile_keyword_terms(profile)
    for canonical in _EXTRA_JD_TERMS:
        assert canonical not in profile_terms, (canonical, profile_terms)
