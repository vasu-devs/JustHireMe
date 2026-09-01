from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_auto_apply_campaign_service, get_opportunity_service
from api.routers.opportunities import router


class FakeOpportunityService:
    async def list_queue(self, *, candidate_id: str, decision: str, limit: int):
        return [{
            "opportunity_id": "opp_123",
            "candidate_id": candidate_id,
            "decision": decision,
            "limit": limit,
        }]

    async def get_detail(self, *, candidate_id: str, opportunity_id: str):
        return {"opportunity_id": opportunity_id, "candidate_id": candidate_id}

    async def get_candidate(self, *, candidate_id: str):
        return {"candidate_id": candidate_id, "home_country": "IN"}

    async def save_candidate(self, *, candidate_id: str, payload: dict):
        return {"candidate_id": candidate_id, **payload}

    async def list_candidates(self):
        return [{"candidate_id": "friend-1"}]

    async def application_profile_status(self, *, candidate_id: str):
        return {"candidate_id": candidate_id, "ready": False}

    async def preview_application_profile(self, *, candidate_id: str):
        return {"candidate_id": candidate_id, "ready": True, "profile_name": "Pilot Candidate", "payload_sha256": "a" * 64}

    async def snapshot_application_profile(self, *, candidate_id: str, identity: dict, expected_payload_sha256: str):
        return {"candidate_id": candidate_id, "ready": True, "payload_sha256": expected_payload_sha256}

    async def preview_candidate_resume(self, *, candidate_id: str, document_path: str):
        return {
            "candidate_id": candidate_id,
            "ready": True,
            "profile_name": "Uploaded Candidate",
            "payload_sha256": "b" * 64,
            "profile": {"n": "Uploaded Candidate", "s": "Engineer", "skills": [{"n": "Python"}]},
        }

    async def confirm_candidate_resume(self, *, candidate_id: str, profile: dict, identity: dict, expected_payload_sha256: str):
        return {
            "candidate_id": candidate_id,
            "ready": True,
            "profile_name": profile["n"],
            "payload_sha256": expected_payload_sha256,
        }

    async def start_scan(self, *, candidate_id: str, target_limit: int, max_concurrency: int, notify=None):
        return {"candidate_id": candidate_id, "status": "running", "target_count": target_limit}

    async def scan_status(self, *, candidate_id: str):
        return {"candidate_id": candidate_id, "status": "completed"}

    async def provider_status(self):
        return {"master_enabled": False, "secrets_redacted": True, "providers": []}

    async def coverage_status(self, *, candidate_id: str):
        return {"candidate_id": candidate_id, "inventory_target_count": 219, "attempted_target_count": 0}

    async def track_application(self, *, candidate_id: str, opportunity_id: str):
        return {"candidate_id": candidate_id, "opportunity_id": opportunity_id, "status": "discovered"}

    async def record_outcome(self, *, candidate_id: str, opportunity_id: str, **payload):
        return {"candidate_id": candidate_id, "opportunity_id": opportunity_id, **payload}

    async def list_events(self, *, candidate_id: str, opportunity_id: str, limit: int):
        return [{"candidate_id": candidate_id, "opportunity_id": opportunity_id, "limit": limit}]

    async def funnel_metrics(self, *, candidate_id: str):
        return {"candidate_id": candidate_id, "funnel": {"interviews": 1}}

    async def cohort_metrics(self):
        return {"candidate_count": 1, "funnel": {"interviews": 1}}


class FakeAutoApplyCampaignService:
    async def apply(self, *, candidate_id: str, opportunity_id: str):
        return {
            "status": "submitted",
            "candidate_id": candidate_id,
            "opportunity_id": opportunity_id,
            "confirmation_evidence": "application received",
        }


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_opportunity_service] = lambda: FakeOpportunityService()
    app.dependency_overrides[get_auto_apply_campaign_service] = (
        lambda: FakeAutoApplyCampaignService()
    )
    return TestClient(app)


def test_opportunity_queue_endpoint_forwards_candidate_and_decision() -> None:
    response = _client().get(
        "/api/v1/opportunities",
        params={"candidate_id": "friend-1", "decision": "apply_now", "limit": 25},
    )
    assert response.status_code == 200
    assert response.json() == [{
        "opportunity_id": "opp_123",
        "candidate_id": "friend-1",
        "decision": "apply_now",
        "limit": 25,
    }]


def test_opportunity_detail_endpoint_is_candidate_scoped() -> None:
    response = _client().get(
        "/api/v1/opportunities/opp_123",
        params={"candidate_id": "friend-1"},
    )
    assert response.status_code == 200
    assert response.json() == {"opportunity_id": "opp_123", "candidate_id": "friend-1"}


def test_auto_apply_endpoint_is_candidate_scoped_and_returns_confirmation() -> None:
    response = _client().post(
        "/api/v1/opportunities/opp_123/auto-apply",
        params={"candidate_id": "friend-1"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "status": "submitted",
        "candidate_id": "friend-1",
        "opportunity_id": "opp_123",
        "confirmation_evidence": "application received",
    }


def test_candidate_constraints_and_background_scan_endpoints() -> None:
    client = _client()
    saved = client.put("/api/v1/opportunities/candidate/friend-1", json={
        "home_country": "IN",
        "graduation_year": 2027,
        "currently_enrolled": True,
        "current_degree_level": "bachelors",
        "accepted_india_cities": ["Bengaluru"],
        "technical_skills": ["Python", "FastAPI"],
        "project_keywords": ["RAG", "PostgreSQL"],
        "spoken_languages": ["English", "Hindi"],
        "preferred_technical_tracks": ["backend", "ai_ml"],
        "accepted_opportunity_types": ["internship", "new_grad"],
        "allow_india_onsite": True,
        "allow_india_hybrid": True,
        "allow_india_remote": True,
        "allow_worldwide_remote": True,
        "allow_unpaid": False,
        "allow_bond": False,
        "professional_experience_years": 0,
        "minimum_monthly_compensation_inr": 100_000,
        "target_monthly_compensation_inr": 200_000,
        "minimum_monthly_compensation_usd": 1_200,
        "target_monthly_compensation_usd": 2_400,
        "unknown_compensation_policy": "review",
        "maximum_internship_months": 12,
    })
    assert saved.status_code == 200
    assert saved.json()["candidate_id"] == "friend-1"
    assert saved.json()["current_degree_level"] == "bachelors"
    assert saved.json()["spoken_languages"] == ["English", "Hindi"]
    assert saved.json()["target_monthly_compensation_inr"] == 200_000
    assert saved.json()["target_monthly_compensation_usd"] == 2_400
    assert saved.json()["unknown_compensation_policy"] == "review"

    started = client.post("/api/v1/opportunities/scan", json={"candidate_id": "friend-1"})
    assert started.status_code == 200
    assert started.json()["status"] == "running"

    status = client.get("/api/v1/opportunities/scan/status", params={"candidate_id": "friend-1"})
    assert status.status_code == 200
    assert status.json() == {"candidate_id": "friend-1", "status": "completed"}

    providers = client.get("/api/v1/opportunities/providers")
    assert providers.status_code == 200
    assert providers.json()["secrets_redacted"] is True

    coverage = client.get("/api/v1/opportunities/coverage", params={"candidate_id": "friend-1"})
    assert coverage.status_code == 200
    assert coverage.json()["inventory_target_count"] == 219

    tracked = client.post("/api/v1/opportunities/opp_123/track", params={"candidate_id": "friend-1"})
    assert tracked.status_code == 200
    assert tracked.json()["status"] == "discovered"


def test_outcome_events_and_funnel_endpoints_are_candidate_scoped() -> None:
    client = _client()
    outcome = client.post(
        "/api/v1/opportunities/opp_123/outcomes",
        params={"candidate_id": "friend-1"},
        json={"event_type": "interview", "note": "Technical round"},
    )
    assert outcome.status_code == 200
    assert outcome.json()["event_type"] == "interview"

    events = client.get(
        "/api/v1/opportunities/events",
        params={"candidate_id": "friend-1", "opportunity_id": "opp_123", "limit": 20},
    )
    assert events.status_code == 200
    assert events.json()[0]["candidate_id"] == "friend-1"

    metrics = client.get("/api/v1/opportunities/metrics", params={"candidate_id": "friend-1"})
    assert metrics.status_code == 200
    assert metrics.json()["funnel"]["interviews"] == 1

    candidates = client.get("/api/v1/opportunities/candidates")
    assert candidates.status_code == 200
    assert candidates.json() == [{"candidate_id": "friend-1"}]

    cohort = client.get("/api/v1/opportunities/cohort/metrics")
    assert cohort.status_code == 200
    assert cohort.json()["candidate_count"] == 1

    profile_status = client.get("/api/v1/opportunities/candidate/friend-1/application-profile")
    assert profile_status.status_code == 200
    assert profile_status.json()["ready"] is False

    preview = client.get("/api/v1/opportunities/candidate/friend-1/application-profile/preview")
    assert preview.status_code == 200
    assert preview.json()["profile_name"] == "Pilot Candidate"

    snapshot = client.post(
        "/api/v1/opportunities/candidate/friend-1/application-profile/snapshot",
        json={
            "expected_payload_sha256": preview.json()["payload_sha256"],
            "identity": {"email": "friend@example.test", "phone": "+91 98765 43210"},
        },
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["ready"] is True

    missing_confirmation = client.post(
        "/api/v1/opportunities/candidate/friend-1/application-profile/snapshot",
        json={},
    )
    assert missing_confirmation.status_code == 422


def test_candidate_resume_upload_requires_supported_file_then_exact_confirmation() -> None:
    client = _client()
    unsupported = client.post(
        "/api/v1/opportunities/candidate/friend-1/application-profile/resume/preview",
        files={"file": ("resume.exe", b"not a resume", "application/octet-stream")},
    )
    assert unsupported.status_code == 415

    preview = client.post(
        "/api/v1/opportunities/candidate/friend-1/application-profile/resume/preview",
        files={"file": ("resume.txt", b"Uploaded Candidate\nPython", "text/plain")},
    )
    assert preview.status_code == 200
    assert preview.json()["profile_name"] == "Uploaded Candidate"

    confirmed = client.post(
        "/api/v1/opportunities/candidate/friend-1/application-profile/resume/confirm",
        json={
            "expected_payload_sha256": preview.json()["payload_sha256"],
            "profile": preview.json()["profile"],
            "identity": {"email": "friend@example.test", "phone": "+91 98765 43210"},
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["ready"] is True
