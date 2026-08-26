from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from opportunities.eligibility import CandidateConstraints
from opportunities.taxonomy import OpportunityType, TechnicalTrack
from opportunities import paid_sources


def _cfg(**overrides) -> dict:
    return {
        "paid_sources_enabled": "true",
        "serpapi_jobs_enabled": "true",
        "serpapi_api_key": "secret-serp",
        "adzuna_jobs_enabled": "false",
        "jooble_jobs_enabled": "false",
        "paid_provider_daily_request_cap": "5",
        "paid_provider_monthly_request_cap": "100",
        **overrides,
    }


def test_paid_targets_are_zero_cost_by_default() -> None:
    targets = paid_sources.paid_provider_targets({}, CandidateConstraints(candidate_id="friend-1"))
    assert targets == []


def test_paid_targets_require_both_switches_and_credentials_and_fit_remaining_cap() -> None:
    candidate = CandidateConstraints(candidate_id="friend-1")
    assert paid_sources.paid_provider_targets(
        _cfg(paid_sources_enabled="false"), candidate
    ) == []
    assert paid_sources.paid_provider_targets(
        _cfg(serpapi_api_key=""), candidate
    ) == []
    targets = paid_sources.paid_provider_targets(
        _cfg(), candidate, {"serpapi": {"requests_today": 4, "requests_month": 4}}
    )
    assert len(targets) == 1
    assert targets[0].provider == "serpapi"
    assert "secret-serp" not in targets[0].scan_target
    assert "secret-serp" not in targets[0].model_dump_json()

    full_targets = paid_sources.paid_provider_targets(_cfg(), candidate)
    assert any(target.target_id.endswith("worldwide-remote-intern") for target in full_targets)


def test_elite_ai_internship_campaign_expands_only_high_signal_intern_queries() -> None:
    candidate = CandidateConstraints(
        candidate_id="elite-ai-intern",
        preferred_technical_tracks=[TechnicalTrack.AI_ML, TechnicalTrack.BACKEND],
        accepted_opportunity_types=[OpportunityType.INTERNSHIP],
        minimum_monthly_compensation_inr=100_000,
        target_monthly_compensation_inr=200_000,
        minimum_monthly_compensation_usd=1_200,
        target_monthly_compensation_usd=2_400,
    )
    targets = paid_sources.paid_provider_targets(
        _cfg(paid_provider_daily_request_cap="20"), candidate
    )
    ids = {target.target_id for target in targets}
    assert "paid:serpapi:generative-ai-intern-india" in ids
    assert "paid:serpapi:ai-agent-intern-india" in ids
    assert "paid:serpapi:applied-ai-intern-india" in ids
    assert "paid:serpapi:worldwide-remote-intern" in ids
    assert not any("new-grad" in target_id or "entry-level" in target_id for target_id in ids)
    assert [target.target_id for target in targets[:4]] == [
        "paid:serpapi:worldwide-remote-intern",
        "paid:serpapi:ai-agent-intern-india",
        "paid:serpapi:applied-ai-intern-india",
        "paid:serpapi:generative-ai-intern-india",
    ]


def test_provider_status_is_redacted_and_reports_retention_gate() -> None:
    status = paid_sources.redacted_provider_status("serpapi", _cfg(), {
        "requests_today": 4,
        "requests_month": 12,
        "successful_requests": 10,
        "eligible_opportunities": 20,
        "net_new_eligible_opportunities": 3,
        "net_new_eligible_yield_percent": 15.0,
    })
    assert status["state"] == "ready"
    assert status["alert"] == "warning_80"
    assert status["experiment"]["benchmark"] == "retain"
    assert "secret" not in repr(status).lower()


def test_http_client_log_filter_redacts_query_and_path_credentials() -> None:
    record = logging.LogRecord(
        "httpx", logging.INFO, __file__, 1, "HTTP Request: %s %s", (
            "GET",
            "https://serpapi.com/search.json?engine=google_jobs&api_key=serp-secret&app_key=adzuna-secret",
        ), None,
    )
    paid_sources._PaidCredentialLogFilter().filter(record)
    rendered = record.getMessage()
    assert "serp-secret" not in rendered
    assert "adzuna-secret" not in rendered
    assert rendered.count("[REDACTED]") == 2

    jooble = logging.LogRecord(
        "httpx", logging.INFO, __file__, 1, "%s", ("https://in.jooble.org/api/jooble-secret",), None,
    )
    paid_sources._PaidCredentialLogFilter().filter(jooble)
    assert "jooble-secret" not in jooble.getMessage()


def test_serpapi_parser_prefers_real_apply_option() -> None:
    rows = paid_sources._serpapi_rows({"jobs_results": [{
        "job_id": "job-1",
        "title": "Software Engineering Intern",
        "company_name": "Acme",
        "location": "Bengaluru, India",
        "share_link": "https://google.example/jobs/1",
        "apply_options": [{"title": "Acme", "link": "https://acme.example/jobs/1"}],
        "description": "Paid internship building Python services.",
        "detected_extensions": {"posted_at": "2 days ago"},
    }]})
    assert rows[0]["url"] == "https://acme.example/jobs/1"
    assert rows[0]["platform"] == "serpapi"
    assert rows[0]["source_meta"]["id"] == "job-1"


def test_scraper_never_fetches_when_reservation_is_rejected(monkeypatch) -> None:
    fetched = False

    async def fake_fetch(*_args, **_kwargs):
        nonlocal fetched
        fetched = True
        return []

    monkeypatch.setattr(paid_sources, "_fetch", fake_fetch)
    store = SimpleNamespace(
        reserve_request=lambda *_args, **_kwargs: {"allowed": False, "reason": "daily_request_cap"},
        finish_request=lambda *_args, **_kwargs: None,
    )
    with pytest.raises(paid_sources.PaidProviderBudgetExceeded):
        asyncio.run(paid_sources.scrape_paid_target(
            "paid:serpapi:software intern@@India", cfg=_cfg(), run_id="run-1", paid_store=store
        ))
    assert fetched is False


def test_scraper_records_successful_request(monkeypatch) -> None:
    finished: list[tuple] = []

    async def fake_fetch(*_args, **_kwargs):
        return [{"title": "Intern"}]

    monkeypatch.setattr(paid_sources, "_fetch", fake_fetch)
    store = SimpleNamespace(
        reserve_request=lambda *_args, **_kwargs: {"allowed": True, "request_id": "req-1"},
        finish_request=lambda *args, **kwargs: finished.append((args, kwargs)),
    )
    rows = asyncio.run(paid_sources.scrape_paid_target(
        "paid:serpapi:software intern@@India", cfg=_cfg(), run_id="run-1", paid_store=store
    ))
    assert rows == [{"title": "Intern"}]
    assert finished == [(('req-1',), {"status": "success", "response_rows": 1})]
