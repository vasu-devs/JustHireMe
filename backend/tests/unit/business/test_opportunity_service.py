from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from core.errors import ConflictError, NotFoundError, UnprocessableError, ValidationError
from opportunities.service import OpportunityService


IDENTITY = {
    "email": "friend@example.test",
    "phone": "+91 98765 43210",
    "linkedin_url": "",
    "github_url": "",
    "website_url": "",
    "city": "Bengaluru",
}


class FakeStore:
    def __init__(self, *, consented=True, application_ready=True):
        self.links = []
        self.events = []
        self.consented = consented
        self.application_ready = application_ready

    def get_candidate_profile(self, candidate_id):
        return {
            "candidate_id": candidate_id,
            "consent_confirmed_at": "2026-08-25T00:00:00Z" if self.consented else None,
        }

    def list_candidate_opportunities(self, candidate_id, *, decision, limit):
        return [{
            "opportunity": {
                "opportunity_id": "opp_123",
                "employer_name": "Acme",
                "title": "Software Engineering Intern",
                "location_text": "Bengaluru, India",
                "canonical_apply_url": "https://example.test/apply",
                "lifecycle": {"status": "active"},
                "observations": [
                    {"provider": "greenhouse", "description_full": "long private-list payload"},
                    {"provider": "aggregator", "description_full": "duplicate payload"},
                ],
            },
            "applicability": {"decision": decision or "apply_now", "hard_blockers": []},
            "updated_at": "2026-08-24T00:00:00Z",
        }]

    def get_candidate_opportunity(self, candidate_id, opportunity_id):
        if opportunity_id == "missing":
            return {}
        return self.list_candidate_opportunities(candidate_id, decision="apply_now", limit=1)[0]

    def link_lead_to_opportunity(self, job_id, opportunity_id):
        self.links.append((job_id, opportunity_id))

    def record_candidate_event(self, candidate_id, opportunity_id, event_type, **payload):
        event = {"candidate_id": candidate_id, "opportunity_id": opportunity_id, "event_type": event_type, **payload}
        self.events.append(event)
        return event

    def list_candidate_events(self, candidate_id, *, opportunity_id, limit):
        return self.events[:limit]

    def candidate_funnel_metrics(self, candidate_id):
        return {"candidate_id": candidate_id, "funnel": {"application_submitted": 10, "meaningful_contacts": 2, "interviews": 1, "offers": 0}}

    def list_candidate_profiles(self):
        return [
            {"candidate_id": "friend-1", "graduation_year": 2027, "consent_confirmed_at": "2026-08-25T00:00:00Z", "profile_updated_at": "now"},
            {"candidate_id": "friend-2", "graduation_year": 2026, "consent_confirmed_at": "2026-08-25T00:00:00Z", "profile_updated_at": "before"},
        ]

    def candidate_application_profile_status(self, candidate_id):
        return {"candidate_id": candidate_id, "ready": self.application_ready}

    def list_candidate_source_health(self, candidate_id):
        return [
            {"target_id": "greenhouse:acme", "provider": "greenhouse", "status": "success", "raw_rows": 12, "accepted_source_records": 11, "attempted_at": "2026-08-25T00:00:00Z"},
            {"target_id": "ashby:broken", "provider": "ashby", "status": "failure", "raw_rows": 0, "accepted_source_records": 0, "attempted_at": "2026-08-25T00:00:01Z"},
        ]

    def get_public_index_status(self):
        return {
            "source_record_count": 34_734,
            "canonical_opportunity_count": 22_171,
            "active_opportunity_count": 21_193,
            "observation_count": 34_734,
            "identity_alias_count": 59_177,
            "status_counts": {"active": 21_193, "closed": 978},
            "latest_observed_at": "2026-08-25T12:00:00Z",
            "last_sync": {"source_label": "verified.sqlite3"},
        }

    def save_candidate_application_profile(self, candidate_id, profile, *, source="local_profile_snapshot"):
        self.application_ready = True
        return {
            "candidate_id": candidate_id,
            "ready": True,
            "skill_count": len(profile.get("skills") or []),
            "source": source,
        }


class FakeLeads:
    def __init__(self):
        self.saved = {}

    def save_lead(self, lead):
        self.saved[lead["job_id"]] = {**lead, "status": "discovered"}

    def get_lead_by_id(self, job_id):
        return self.saved.get(job_id, {})

    def update_lead_status(self, job_id, status):
        self.saved[job_id]["status"] = status


def _service(*, consented=True, application_ready=True) -> OpportunityService:
    return OpportunityService(SimpleNamespace(
        opportunities=FakeStore(consented=consented, application_ready=application_ready),
        leads=FakeLeads(),
        profile=SimpleNamespace(get_profile=lambda: {
            "n": "Pilot Candidate",
            "s": "Backend engineer",
            "skills": [{"n": "Python"}],
        }),
    ))


class FakeProfileParser:
    def __init__(self):
        self.paths = []

    async def parse_resume(self, raw, document_path):
        self.paths.append((raw, document_path))
        return {
            "n": "Friend Candidate",
            "s": "Final-year backend and AI engineer",
            "skills": [{"n": "Python"}, {"n": "FastAPI"}],
            "projects": [{"title": "Search Engine"}],
        }


def test_queue_returns_cards_without_full_observation_descriptions() -> None:
    cards = asyncio.run(_service().list_queue(candidate_id="friend-1", decision="apply_now"))
    assert len(cards) == 1
    assert cards[0]["source_count"] == 2
    assert cards[0]["providers"] == ["aggregator", "greenhouse"]
    assert "observations" not in cards[0]


def test_invalid_queue_input_and_missing_detail_raise_domain_errors() -> None:
    with pytest.raises(ValidationError):
        asyncio.run(_service().list_queue(candidate_id="../../bad", decision="apply_now"))
    with pytest.raises(ValidationError):
        asyncio.run(_service().list_queue(candidate_id="friend-1", decision="maybe"))
    with pytest.raises(NotFoundError):
        asyncio.run(_service().get_detail(candidate_id="friend-1", opportunity_id="missing"))


def test_track_application_creates_candidate_scoped_pipeline_lead() -> None:
    service = _service()
    saved = asyncio.run(service.track_application(candidate_id="friend-1", opportunity_id="opp_123"))
    assert saved["status"] == "discovered"
    assert saved["source_meta"]["candidate_id"] == "friend-1"
    assert saved["source_meta"]["opportunity_id"] == "opp_123"
    assert saved["job_id"].startswith("opptrack_")
    assert service._repo.opportunities.links == [(saved["job_id"], "opp_123")]
    assert service._repo.opportunities.events[0]["event_type"] == "tracked"


def test_record_outcome_auto_tracks_and_updates_the_pipeline_status() -> None:
    service = _service()
    event = asyncio.run(service.record_outcome(
        candidate_id="friend-1",
        opportunity_id="opp_123",
        event_type="interview",
        note="Technical round",
    ))
    assert event["event_type"] == "interview"
    lead = next(iter(service._repo.leads.saved.values()))
    assert lead["status"] == "interviewing"
    assert [item["event_type"] for item in service._repo.opportunities.events] == ["tracked", "interview"]

    metrics = asyncio.run(service.funnel_metrics(candidate_id="friend-1"))
    assert metrics["funnel"]["interviews"] == 1


def test_cohort_metrics_measure_progress_against_real_pilot_targets() -> None:
    cohort = asyncio.run(_service().cohort_metrics())
    assert cohort["candidate_count"] == 2
    assert cohort["funnel"]["application_submitted"] == 20
    assert cohort["funnel"]["meaningful_contacts"] == 4
    assert cohort["funnel"]["interviews"] == 2
    assert cohort["candidates_with_traction"] == 2
    assert cohort["rates"]["interviews_per_20_applications"] == 2.0
    assert cohort["progress_percent"]["application_submitted"] == 20.0


def test_candidate_application_profile_snapshot_is_explicit_and_local() -> None:
    service = _service(application_ready=False)
    before = asyncio.run(service.application_profile_status(candidate_id="friend-1"))
    assert before["ready"] is False
    preview = asyncio.run(service.preview_application_profile(candidate_id="friend-1"))
    assert preview["profile_name"] == "Pilot Candidate"
    assert preview["evidence_count"] == 1
    saved = asyncio.run(service.snapshot_application_profile(
        candidate_id="friend-1",
        identity=IDENTITY,
        expected_payload_sha256=preview["payload_sha256"],
    ))
    assert saved["ready"] is True
    assert saved["skill_count"] == 1
    assert saved["source"].startswith("confirmed_profile_snapshot:")


def test_candidate_application_profile_rejects_stale_or_unreviewed_snapshot() -> None:
    service = _service(application_ready=False)
    with pytest.raises(ConflictError, match="changed after review"):
        asyncio.run(service.snapshot_application_profile(
            candidate_id="friend-1",
            identity=IDENTITY,
            expected_payload_sha256="0" * 64,
        ))


def test_candidate_scoped_resume_is_parsed_without_using_shared_profile() -> None:
    parser = FakeProfileParser()
    service = _service(application_ready=False)
    service._profile_parser = parser

    preview = asyncio.run(service.preview_candidate_resume(
        candidate_id="friend-1",
        document_path="candidate-resume.pdf",
    ))
    assert preview["profile_name"] == "Friend Candidate"
    assert preview["skill_count"] == 2
    assert parser.paths == [("", "candidate-resume.pdf")]

    saved = asyncio.run(service.confirm_candidate_resume(
        candidate_id="friend-1",
        profile=preview["profile"],
        identity=IDENTITY,
        expected_payload_sha256=preview["payload_sha256"],
    ))
    assert saved["ready"] is True
    assert saved["source"].startswith("confirmed_candidate_resume:")


def test_candidate_resume_confirmation_rejects_tampering_and_missing_consent() -> None:
    parser = FakeProfileParser()
    service = _service(application_ready=False)
    service._profile_parser = parser
    preview = asyncio.run(service.preview_candidate_resume(
        candidate_id="friend-1",
        document_path="candidate-resume.pdf",
    ))
    changed = {**preview["profile"], "n": "Different Candidate"}
    with pytest.raises(ConflictError, match="changed after review"):
        asyncio.run(service.confirm_candidate_resume(
            candidate_id="friend-1",
            profile=changed,
            identity=IDENTITY,
            expected_payload_sha256=preview["payload_sha256"],
        ))

    no_consent = _service(consented=False)
    no_consent._profile_parser = parser
    with pytest.raises(UnprocessableError, match="consent"):
        asyncio.run(no_consent.preview_candidate_resume(
            candidate_id="friend-1",
            document_path="candidate-resume.pdf",
        ))


def test_candidate_consent_and_application_profile_are_hard_pilot_gates() -> None:
    without_consent = _service(consented=False)
    with pytest.raises(UnprocessableError, match="consent"):
        asyncio.run(without_consent.preview_application_profile(candidate_id="friend-1"))
    with pytest.raises(UnprocessableError, match="consent"):
        asyncio.run(without_consent.track_application(candidate_id="friend-1", opportunity_id="opp_123"))

    without_profile = _service(application_ready=False)
    with pytest.raises(UnprocessableError, match="application profile"):
        asyncio.run(without_profile.track_application(candidate_id="friend-1", opportunity_id="opp_123"))


def test_cohort_excludes_saved_candidates_that_are_not_application_ready() -> None:
    cohort = asyncio.run(_service(application_ready=False).cohort_metrics())
    assert cohort["saved_candidate_count"] == 2
    assert cohort["candidate_count"] == 0
    assert cohort["pending_candidate_count"] == 2
    assert cohort["funnel"]["application_submitted"] == 0


def test_paid_provider_status_never_returns_credentials() -> None:
    usage = {
        "requests_today": 0, "requests_month": 0,
        "estimated_spend_today_usd": 0, "estimated_spend_month_usd": 0,
        "successful_requests": 0, "failed_requests": 0,
        "net_new_eligible_yield_percent": 0,
    }
    repo = SimpleNamespace(
        settings=SimpleNamespace(get_settings=lambda: {
            "paid_sources_enabled": "true",
            "serpapi_jobs_enabled": "true",
            "serpapi_api_key": "do-not-leak",
        }),
        paid_sources=SimpleNamespace(provider_usage=lambda _provider: dict(usage)),
    )
    status = asyncio.run(OpportunityService(repo).provider_status())
    assert status["secrets_redacted"] is True
    assert status["providers"][0]["state"] == "ready"
    assert "do-not-leak" not in repr(status)


def test_coverage_status_reports_inventory_and_persisted_source_health(monkeypatch) -> None:
    from opportunities import service as service_module

    targets = [
        SimpleNamespace(target_id="greenhouse:acme", provider="greenhouse"),
        SimpleNamespace(target_id="ashby:broken", provider="ashby"),
        SimpleNamespace(target_id="remote:jobicy", provider="jobicy"),
    ]
    monkeypatch.setattr(service_module, "production_market_targets", lambda company_limit: targets)
    coverage = asyncio.run(_service().coverage_status(candidate_id="friend-1"))
    assert coverage["inventory_target_count"] == 3
    assert coverage["inventory_provider_count"] == 3
    assert coverage["attempted_target_count"] == 2
    assert coverage["unattempted_target_count"] == 1
    assert coverage["health_counts"] == {"failure": 1, "success": 1}
    assert coverage["provider_health"]["greenhouse"]["accepted_source_records"] == 11
    assert coverage["index"]["canonical_opportunity_count"] == 22_171
    assert coverage["index"]["active_opportunity_count"] == 21_193
