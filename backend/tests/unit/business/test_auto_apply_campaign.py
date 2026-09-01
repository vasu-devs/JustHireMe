from __future__ import annotations

import asyncio
from types import SimpleNamespace

from automation.campaign import AutoApplyCampaignService


def _candidate(**overrides) -> dict:
    return {
        "candidate_id": "friend-1",
        "consent_confirmed_at": "2026-08-25T00:00:00Z",
        "auto_apply_enabled": True,
        "auto_apply_confirmed_at": "2026-09-01T00:00:00Z",
        "auto_apply_minimum_fit_score": 80,
        "auto_apply_daily_limit": 5,
        "auto_apply_allow_strong_stretch": False,
        **overrides,
    }


def _detail() -> dict:
    return {
        "opportunity": {
            "opportunity_id": "opp-1",
            "canonical_apply_url": "https://example.test/apply",
            "lifecycle": {"status": "active"},
        },
        "applicability": {
            "decision": "apply_now",
            "eligibility": "eligible",
            "candidate_fit_score": 91,
            "paid_status": "paid",
            "hard_blockers": [],
            "safety_blockers": [],
            "unknowns": [],
            "candidate_evidence_missing": False,
            "safety_warnings": [],
        },
    }


class FakeOpportunityService:
    def __init__(self, *, detail=None):
        self.detail = detail or _detail()
        self.track_calls = 0

    async def get_detail(self, **_kwargs):
        return self.detail

    async def application_profile_status(self, **_kwargs):
        return {"ready": True}

    async def track_application(self, **_kwargs):
        self.track_calls += 1
        return {
            "job_id": "lead-1",
            "status": "discovered",
            "resume_asset": "resume.pdf",
            "cover_letter_asset": "cover.pdf",
        }


class FakeAutomation:
    def __init__(self, *, preview=None, submission=None, on_preview=None):
        self.preview = preview or {
            "ready_to_submit": True,
            "fields_filled": ["name", "email"],
            "required_unfilled": [],
            "sensitive_questions": [],
            "page_blockers": [],
            "resume_uploaded": True,
            "submit_found": True,
        }
        self.submission = submission or {
            "status": "submitted",
            "confirmation_evidence": "application received",
        }
        self.submit_calls = 0
        self.mark_calls = 0
        self.on_preview = on_preview

    async def get_lead_for_fire(self, _job_id):
        return ({"job_id": "lead-1"}, "resume.pdf")

    async def preview_application(self, _lead, _asset):
        if self.on_preview:
            self.on_preview()
        return self.preview

    async def submit_application_result(self, _lead, _asset):
        self.submit_calls += 1
        return self.submission

    async def mark_applied(self, _job_id):
        self.mark_calls += 1


class FakeRepo:
    def __init__(self, *, candidate=None, events=None):
        self.events = events or []
        self.recorded = []
        self.opportunities = SimpleNamespace(
            get_candidate_profile=lambda _candidate_id: candidate or _candidate(),
            list_candidate_events=lambda _candidate_id, limit=2000: self.events,
            record_candidate_event=self._record,
        )
        self.leads = SimpleNamespace(save_asset_package=lambda *_args: None)

    def _record(self, candidate_id, opportunity_id, event_type, **payload):
        row = {
            "event_id": f"event-{len(self.recorded) + 1}",
            "candidate_id": candidate_id,
            "opportunity_id": opportunity_id,
            "event_type": event_type,
            **payload,
        }
        self.recorded.append(row)
        return row


class FakeGeneration:
    async def generate_package(self, _lead):
        raise AssertionError("assets already exist; generation must not run")


def _service(repo=None, opportunities=None, automation=None):
    repo = repo or FakeRepo()
    opportunities = opportunities or FakeOpportunityService()
    automation = automation or FakeAutomation()
    return (
        AutoApplyCampaignService(repo, opportunities, FakeGeneration(), automation),
        repo,
        opportunities,
        automation,
    )


def test_campaign_blocks_before_creating_or_submitting_a_lead() -> None:
    service, _repo, opportunities, automation = _service(
        repo=FakeRepo(candidate=_candidate(auto_apply_enabled=False))
    )
    result = asyncio.run(service.apply(candidate_id="friend-1", opportunity_id="opp-1"))
    assert result["status"] == "blocked"
    assert opportunities.track_calls == 0
    assert automation.submit_calls == 0


def test_campaign_submits_only_after_preflight_and_records_confirmation() -> None:
    service, repo, _opportunities, automation = _service()
    result = asyncio.run(service.apply(candidate_id="friend-1", opportunity_id="opp-1"))
    assert result["status"] == "submitted"
    assert result["confirmation_evidence"] == "application received"
    assert automation.submit_calls == 1
    assert automation.mark_calls == 1
    assert [event["event_type"] for event in repo.recorded] == [
        "application_started",
        "application_submitted",
    ]


def test_campaign_stops_for_manual_review_when_preflight_finds_unknown_question() -> None:
    automation = FakeAutomation(preview={
        "ready_to_submit": False,
        "required_unfilled": ["Portfolio URL"],
        "sensitive_questions": [],
        "page_blockers": [],
        "resume_uploaded": True,
        "submit_found": True,
    })
    service, repo, _opportunities, automation = _service(automation=automation)
    result = asyncio.run(service.apply(candidate_id="friend-1", opportunity_id="opp-1"))
    assert result["status"] == "needs_review"
    assert result["preflight"]["required_unfilled"] == ["Portfolio URL"]
    assert automation.submit_calls == 0
    assert automation.mark_calls == 0
    assert [event["event_type"] for event in repo.recorded] == ["auto_apply_needs_review"]


def test_campaign_does_not_mark_unconfirmed_click_as_applied() -> None:
    automation = FakeAutomation(submission={
        "status": "submission_unconfirmed",
        "confirmation_evidence": "",
        "reason": "no positive confirmation detected",
    })
    service, repo, _opportunities, automation = _service(automation=automation)
    result = asyncio.run(service.apply(candidate_id="friend-1", opportunity_id="opp-1"))
    assert result["status"] == "submission_unconfirmed"
    assert automation.mark_calls == 0
    assert [event["event_type"] for event in repo.recorded] == [
        "application_started",
        "auto_apply_unconfirmed",
    ]


def test_campaign_rechecks_revoked_authorization_after_preflight() -> None:
    candidate = _candidate()
    repo = FakeRepo(candidate=candidate)
    automation = FakeAutomation(on_preview=lambda: candidate.update(auto_apply_enabled=False))
    service, repo, _opportunities, automation = _service(repo=repo, automation=automation)

    result = asyncio.run(service.apply(candidate_id="friend-1", opportunity_id="opp-1"))

    assert result["status"] == "blocked"
    assert any("not enabled" in item for item in result["blockers"])
    assert automation.submit_calls == 0
    assert automation.mark_calls == 0
    assert [event["event_type"] for event in repo.recorded] == ["auto_apply_blocked"]
