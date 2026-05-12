from __future__ import annotations

from fastapi.testclient import TestClient

from services.apps import create_service_app


def test_internal_service_auth_rejects_missing_token():
    app = create_service_app("ranking", internal_token="secret")
    client = TestClient(app)

    response = client.post("/internal/v1/ranking/score", json={"lead": {}, "profile": {}})

    assert response.status_code == 401


def test_internal_service_health_is_public_and_identifies_service():
    app = create_service_app("generation", internal_token="secret")
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["service"] == "generation"


def test_generation_contract_calls_package_service(monkeypatch):
    from generation.service import GenerationResult

    class FakeGenerationService:
        async def generate_with_contacts(self, lead, *, template="", include_contacts=True):
            return GenerationResult(
                package={
                    "resume": "resume.pdf",
                    "cover_letter": "cover.pdf",
                    "selected_projects": ["Project"],
                    "keyword_coverage": {"coverage_pct": 100},
                },
                contact_lookup={"status": "skipped"},
            )

    monkeypatch.setattr("generation.service.create_generation_service", lambda: FakeGenerationService())
    app = create_service_app("generation", internal_token="secret")
    client = TestClient(app)

    response = client.post(
        "/internal/v1/generation/package",
        headers={"Authorization": "Bearer secret"},
        json={"lead": {"job_id": "job-1"}, "template": "", "include_contacts": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["package"]["resume"] == "resume.pdf"
    assert body["package"]["cover_letter"] == "cover.pdf"
    assert body["contact_lookup"]["status"] == "skipped"
