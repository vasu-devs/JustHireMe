"""Round-4 audit fixes: query_gen tenure, greenhouse slug, company regex, submit gate."""

from __future__ import annotations

import asyncio

import discovery.query_gen as qg
from automation.actuator import _submit_mode
from discovery.lead_intel import company_from_text
from discovery.sources import ats


def test_query_gen_present_role_not_600_months():
    # "Present" must resolve to today, not a 2099 sentinel (~600 months) that would
    # misclassify a junior with one current role as senior.
    months = qg._period_months("Jan 2024 - Present")
    assert 0 < months < 200, months


def test_greenhouse_direct_url_uses_company_slug(monkeypatch):
    seen = {}

    async def fake_gh(slug):
        seen["slug"] = slug
        return []

    monkeypatch.setattr(ats, "scrape_greenhouse", fake_gh)
    asyncio.run(ats.scrape_direct_ats_url("https://boards.greenhouse.io/acme/jobs/123"))
    assert seen["slug"] == "acme", "company slug is path[0], not the trailing job id"


def test_company_from_text_ignores_lowercase_prose():
    # "at the office" must not capture "the office" as a company (lowercase after 'at').
    assert company_from_text("we work at the office daily", fallback="X") == "X"
    # A real capitalized company is still captured.
    assert company_from_text("Engineer at Acme Corp | Remote", fallback="X") == "Acme Corp"


def test_submit_mode_safety_table():
    # The ONLY combination that submits: real button + DOM-ready + auto-apply on + not dry-run.
    assert _submit_mode(True, True, dry_run=True, auto_apply=True) == "dry_run"
    assert _submit_mode(True, True, dry_run=False, auto_apply=False) == "read_only"
    assert _submit_mode(True, False, dry_run=False, auto_apply=True) == "blocked"
    assert _submit_mode(False, True, dry_run=False, auto_apply=True) == "blocked"
    assert _submit_mode(True, True, dry_run=False, auto_apply=True) == "submit"
