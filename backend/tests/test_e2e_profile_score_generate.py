from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


class InMemoryProfileRepo:
    def __init__(self) -> None:
        self.profile: dict = {}

    def get_profile(self) -> dict:
        return dict(self.profile)

    def set_profile(self, profile: dict) -> None:
        self.profile = dict(profile)


class InMemoryLeadsRepo:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def save_lead(self, lead: dict) -> None:
        row = {**lead}
        row.setdefault("status", "discovered")
        row.setdefault("score", 0)
        row.setdefault("reason", "")
        row.setdefault("match_points", [])
        row.setdefault("gaps", [])
        row.setdefault("source_meta", {})
        self.rows[row["job_id"]] = row

    def get_lead_by_id(self, job_id: str) -> dict:
        return dict(self.rows.get(job_id, {}))

    def get_all_leads(self) -> list[dict]:
        return [dict(row) for row in self.rows.values()]

    def get_job_leads_for_evaluation(self) -> list[dict]:
        return [
            dict(row)
            for row in self.rows.values()
            if (row.get("kind") or "job") == "job"
        ]

    def update_lead_status(self, job_id: str, status: str) -> None:
        self.rows[job_id]["status"] = status

    def update_lead_score(
        self,
        job_id: str,
        score: int,
        reason: str,
        match_points: list | None = None,
        gaps: list | None = None,
        preserve_status: bool = False,
        scored_by: str = "",
    ) -> None:
        row = self.rows[job_id]
        row["score"] = score
        row["reason"] = reason
        row["match_points"] = match_points or []
        row["gaps"] = gaps or []
        if not preserve_status:
            row["status"] = "tailoring" if score >= 76 else "discarded"
        if scored_by:
            row["source_meta"] = {**(row.get("source_meta") or {}), "scored_by": scored_by}

    def save_asset_package(
        self,
        job_id: str,
        resume_path: str,
        cover_letter_path: str = "",
        selected_projects: list | None = None,
        keyword_coverage: dict | None = None,
    ) -> None:
        row = self.rows[job_id]
        row["status"] = "approved"
        row["asset"] = resume_path
        row["resume_asset"] = resume_path
        row["cover_letter_asset"] = cover_letter_path
        row["selected_projects"] = selected_projects or []
        row["source_meta"] = {
            **(row.get("source_meta") or {}),
            "keyword_coverage": keyword_coverage or {},
        }

    def update_outreach_fields(self, job_id: str, fields: dict[str, str]) -> None:
        self.rows[job_id].update(fields)

    def save_contact_lookup(self, job_id: str, contact_lookup: dict | None) -> None:
        row = self.rows[job_id]
        row["source_meta"] = {
            **(row.get("source_meta") or {}),
            "contact_lookup": contact_lookup or {"contacts": []},
        }


class InMemorySettingsRepo:
    def __init__(self) -> None:
        self.values = {"llm_provider": "test", "resume_template": ""}

    def get_settings(self) -> dict[str, str]:
        return dict(self.values)

    def get_setting(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)

    def save_settings(self, values: dict[str, str]) -> None:
        self.values.update(values)


class InMemoryRepo:
    def __init__(self) -> None:
        self.profile = InMemoryProfileRepo()
        self.leads = InMemoryLeadsRepo()
        self.settings = InMemorySettingsRepo()
        self.feedback = SimpleNamespace(get_feedback_training_examples=lambda: [])


class FakeProfileService:
    def __init__(self, repo: InMemoryRepo) -> None:
        self.repo = repo

    async def ingest_resume(self, raw: str = "", pdf_path: str | None = None) -> dict:
        assert pdf_path is None
        assert "Vasu" in raw
        profile = {
            "n": "Vasu",
            "s": "Applied AI engineer building local-first FastAPI and React systems.",
            "skills": [{"n": "Python", "cat": "language"}, {"n": "FastAPI", "cat": "backend"}, {"n": "React", "cat": "frontend"}],
            "exp": [{"role": "Full Stack Engineer", "co": "Freelance", "period": "2025-2026", "d": "Built AI workflows."}],
            "projects": [{"title": "JustHireMe", "stack": ["Python", "FastAPI", "React"], "impact": "Automated job intelligence."}],
            "education": [],
            "certifications": [],
            "achievements": [],
        }
        self.repo.profile.set_profile(profile)
        return profile

    def get_profile(self) -> dict:
        return self.repo.profile.get_profile()


class FakeRankingService:
    def __init__(self) -> None:
        self.evaluated: list[str] = []

    async def apply_feedback(self, lead: dict, _examples: list[dict]) -> dict:
        return lead

    async def evaluate_lead(self, lead: dict, profile: dict) -> dict:
        self.evaluated.append(lead["job_id"])
        text = f"{lead.get('title', '')} {lead.get('description', '')}".lower()
        score = 91 if "fastapi" in text and "react" in text else 68
        return {
            "score": score,
            "reason": f"Scored against {profile.get('n', 'candidate')}",
            "match_points": ["Python/FastAPI/React"] if score >= 76 else ["Some backend overlap"],
            "gaps": [] if score >= 76 else ["Missing React evidence"],
            "scored_by": "integration_fake",
        }


class FakeGenerationService:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    async def generate_with_contacts(self, lead: dict, *, template: str = "", include_contacts: bool = True):
        assert template == ""
        resume = self.output_dir / f"{lead['job_id']}_resume.pdf"
        cover = self.output_dir / f"{lead['job_id']}_cover.pdf"
        resume.write_text("resume pdf placeholder", encoding="utf-8")
        cover.write_text("cover pdf placeholder", encoding="utf-8")
        return SimpleNamespace(
            package={
                "resume": str(resume),
                "cover_letter": str(cover),
                "selected_projects": ["JustHireMe"],
                "keyword_coverage": {"coverage_pct": 100},
                "founder_message": "Relevant FastAPI and React work.",
            },
            contact_lookup={"contacts": [{"email": "jobs@example.com"}]} if include_contacts else None,
        )


class FakeJobStore:
    def __init__(self) -> None:
        self.created = 0
        self.updates: list[tuple[str, dict]] = []

    def create(self, kind: str, payload: dict):
        self.created += 1
        return SimpleNamespace(job_id=f"{kind}-{self.created}", payload=payload)

    def update(self, job_id: str, **payload) -> None:
        self.updates.append((job_id, payload))


def _install_overrides(app, overrides: dict):
    sentinel = object()
    previous = {dependency: app.dependency_overrides.get(dependency, sentinel) for dependency in overrides}
    app.dependency_overrides.update(overrides)
    return previous, sentinel


def _restore_overrides(app, previous: dict, sentinel: object) -> None:
    for dependency, value in previous.items():
        if value is sentinel:
            app.dependency_overrides.pop(dependency, None)
        else:
            app.dependency_overrides[dependency] = value


def test_profile_to_score_to_generate_flow(tmp_path, monkeypatch):
    import main
    from api.dependencies import get_generation_service, get_profile_service, get_ranking_service, get_repository
    from api.routers import discovery, generation, ingestion

    repo = InMemoryRepo()
    profile_service = FakeProfileService(repo)
    ranking_service = FakeRankingService()
    generation_service = FakeGenerationService(tmp_path)
    job_store = FakeJobStore()

    monkeypatch.setattr(main, "_API_TOKEN", "e2e-token")
    monkeypatch.setattr(ingestion, "get_profile_service", lambda: profile_service)
    monkeypatch.setattr(discovery, "get_job_runner", lambda: job_store)
    monkeypatch.setattr(generation, "get_job_runner", lambda: job_store)
    previous, sentinel = _install_overrides(main.app, {
        get_repository: lambda: repo,
        get_profile_service: lambda: profile_service,
        get_ranking_service: lambda: ranking_service,
        get_generation_service: lambda: generation_service,
    })

    try:
        client = TestClient(main.app, raise_server_exceptions=True, base_url="http://127.0.0.1")
        headers = {"Authorization": "Bearer e2e-token"}

        ingest = client.post(
            "/api/v1/ingest",
            headers=headers,
            data={"raw": "Vasu\nApplied AI Engineer\nPython FastAPI React local-first systems."},
        )
        assert ingest.status_code == 200
        assert ingest.json()["n"] == "Vasu"
        assert repo.profile.get_profile()["skills"][0]["n"] == "Python"

        lead_texts = [
            "Applied AI Engineer\nCompany: NimbusWorks\nWe are hiring for Python FastAPI React LLM automation on a remote product team.",
            "Backend Engineer\nCompany: DataForge\nWe need Python API engineering and SQL reliability for internal platforms.",
            "Product Analyst\nCompany: MetricsCo\nAnalyze funnels, dashboards, and stakeholder reporting for growth teams.",
        ]
        for text in lead_texts:
            response = client.post("/api/v1/leads/manual", headers=headers, json={"text": text, "url": ""})
            assert response.status_code == 200

        asyncio.run(discovery.run_reevaluate_jobs(main.cm, repo=repo, ranking_service=ranking_service))

        assert len(ranking_service.evaluated) == 3
        best = max(repo.leads.get_all_leads(), key=lambda lead: lead["score"])
        assert best["score"] == 91
        assert best["status"] == "tailoring"

        generated = client.post(f"/api/v1/leads/{best['job_id']}/generate", headers=headers)

        assert generated.status_code == 200
        payload = generated.json()
        assert payload["status"] == "ready"
        assert payload["lead"]["selected_projects"] == ["JustHireMe"]
        assert Path(payload["lead"]["resume_asset"]).exists()
        assert Path(payload["lead"]["cover_letter_asset"]).exists()
        assert repo.leads.get_lead_by_id(best["job_id"])["status"] == "approved"
    finally:
        _restore_overrides(main.app, previous, sentinel)
