"""The zero-config discovery backbone: field/region detection, auto ATS targets, the
keyless aggregator target, and their wiring into profile_free_source_targets."""

from __future__ import annotations

import asyncio
from unittest import mock

from core import company_seeds as cs
from core.config import profile_free_source_targets
from discovery.sources import aggregator as agg

_NURSE = {"s": "Registered Nurse, ICU", "exp": [{"role": "Staff Nurse"}], "skills": [{"n": "patient care"}]}
_SRE = {"s": "Senior SRE", "exp": [{"role": "Site Reliability Engineer"}], "skills": [{"n": "Kubernetes"}, {"n": "Python"}]}
_LAWYER = {"s": "Corporate Lawyer", "exp": [{"role": "Attorney"}], "skills": [{"n": "contracts"}]}


def test_detect_field_is_field_agnostic():
    assert cs.detect_field(_NURSE) == "healthcare"
    assert cs.detect_field(_SRE) == "tech"
    assert cs.detect_field(_LAWYER) == "legal"
    assert cs.detect_field({}) == "general"


def test_detect_region_from_location():
    assert cs.detect_region({"_discovery_location": "Berlin, Germany"}) == "europe"
    assert cs.detect_region({"_discovery_location": "New York, USA"}) == "us"
    assert cs.detect_region({"_discovery_location": "Bengaluru"}) == "india"
    assert cs.detect_region({}) == "global"


def test_ats_seeds_are_tech_strong_and_dont_guess_non_tech():
    tech_targets = cs.ats_seed_targets(_SRE)
    assert tech_targets and all(t.startswith("ats:") for t in tech_targets)
    assert "ats:greenhouse:stripe" in tech_targets
    # Non-tech fields get NO curated ATS slugs (would be unreliable) — the keyless
    # aggregator covers them instead.
    assert cs.ats_seed_targets(_NURSE) == []


def test_profile_free_source_targets_are_zero_config_and_adaptive():
    sre = dict(_SRE, _discovery_location="Berlin, Germany")
    lines = profile_free_source_targets(sre).splitlines()
    assert lines[0].startswith("aggregator:")          # keyless aggregator first
    assert "@@Berlin, Germany" in lines[0]             # carries detected location
    assert any(x.startswith("ats:greenhouse:") for x in lines)  # auto ATS backbone

    nurse_lines = profile_free_source_targets(_NURSE).splitlines()
    assert nurse_lines[0].startswith("aggregator:")    # nurse still gets the aggregator
    assert not any(x.startswith("ats:") for x in nurse_lines)   # but no tech ATS flood


def test_clean_role_query_strips_noise():
    from core.config import _clean_role_query
    # project-laden title + em-dash separator -> just the role phrase (internal hyphen kept)
    assert _clean_role_query(["Full-Stack Engineer — Internal Finance & P&L Platform"]) == "Full-Stack Engineer"
    # non-ASCII/mojibake acts as a separator, not deleted
    assert _clean_role_query(["Full-Stack Engineer � Internal Finance"]) == "Full-Stack Engineer"
    # summary filler dropped, sentence split on ". "
    assert _clean_role_query(["Applied AI Engineer. Engineer Summary"]) == "Applied AI Engineer"
    # falls through to the next usable term when the first is empty after cleaning
    assert _clean_role_query(["", "Registered Nurse"]) == "Registered Nurse"
    assert _clean_role_query([]) == "jobs"


def test_aggregator_target_parsing_and_category_mapping():
    assert agg._muse_category(agg._role_terms("registered nurse icu")) == "Healthcare"
    assert agg._muse_category(agg._role_terms("senior software engineer")) == "Software Engineering"
    assert agg._muse_category(agg._role_terms("corporate lawyer")) == "Legal Services"
    # trades have no valid Muse category -> skip Muse (aggregator falls back to Arbeitnow)
    assert agg._muse_category(agg._role_terms("welder fabricator")) == ""

    captured = {}

    async def fake(role, loc):
        captured["role"], captured["loc"] = role, loc
        return []

    with mock.patch.object(agg, "scrape_aggregator", new=fake):
        asyncio.run(agg.scrape_aggregator_target("aggregator:Registered Nurse@@London, UK"))
    assert captured == {"role": "Registered Nurse", "loc": "London, UK"}


def test_free_scout_dispatches_aggregator_target():
    from automation import free_scout

    async def fake_agg(target):
        return [{"title": "Nurse", "url": "https://x/1"}]

    with mock.patch.object(free_scout, "_source_scrape_aggregator", new=fake_agg):
        leads = asyncio.run(free_scout._scrape_target("aggregator:nurse@@London"))
    assert leads == [{"title": "Nurse", "url": "https://x/1"}]
