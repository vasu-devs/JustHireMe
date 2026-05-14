import asyncio

from profile.service import ProfileService


def test_profile_service_import_profile_data_counts_and_identity(monkeypatch):
    service = ProfileService()
    calls = {"identity": []}

    monkeypatch.setattr(service, "update_candidate", lambda name, summary: {"n": name, "s": summary})
    monkeypatch.setattr(service, "add_skill", lambda name, category: {"n": name, "cat": category})
    monkeypatch.setattr(service, "add_experience", lambda role, company, period, description: {"role": role})
    monkeypatch.setattr(service, "add_project", lambda title, stack, repo, impact: {"title": title})
    monkeypatch.setattr(service, "add_education", lambda title: {"title": title})
    monkeypatch.setattr(service, "add_certification", lambda title: {"title": title})
    monkeypatch.setattr(service, "add_achievement", lambda title: {"title": title})
    monkeypatch.setattr(service, "update_identity", lambda identity: calls["identity"].append(identity) or identity)
    monkeypatch.setattr(service, "refresh_profile_snapshot", lambda: None)
    monkeypatch.setattr("profile.service.graph_profile.sync_vectors_from_graph", lambda: {"status": "ok"})

    result = asyncio.run(service.import_profile_data({
        "candidate": {"name": "Vasu", "summary": "AI engineer"},
        "identity": {"email": "vasu@example.com", "github_url": "https://github.com/vasu"},
        "skills": [{"name": "Python", "category": "technical"}],
        "experience": [{"role": "Engineer", "company": "Acme", "period": "2024", "description": "Built agents"}],
        "projects": [{"title": "JustHireMe", "stack": "Python, React", "repo": "", "impact": "Local-first job workbench"}],
        "education": [{"title": "B.Tech"}],
        "certifications": [{"title": "Cloud cert"}],
        "achievements": [{"title": "Shipped product"}],
    }))

    assert result["status"] == "ok"
    assert result["stats"] == {
        "skills": 1,
        "experience": 1,
        "projects": 1,
        "education": 1,
        "certifications": 1,
        "achievements": 1,
        "vector_sync": "queued",
    }
    assert calls["identity"][0]["email"] == "vasu@example.com"
    assert calls["identity"][0]["github_url"] == "https://github.com/vasu"


def test_profile_service_update_identity_saves_profile_contact(monkeypatch):
    service = ProfileService()
    saved = {}
    snapshot = {"n": "Vasu", "s": "AI engineer", "skills": [], "projects": [], "exp": []}

    monkeypatch.setattr("profile.service.graph_profile.load_profile_snapshot", lambda _db_path=None: snapshot)
    monkeypatch.setattr("profile.service.graph_profile.save_profile_snapshot", lambda profile, _db_path=None: saved.update(profile))
    monkeypatch.setattr("profile.service.graph_profile.read_profile_from_graph", lambda: snapshot)
    monkeypatch.setattr("profile.service.graph_profile.save_settings", lambda _payload, *_args: None)

    identity = service.update_identity({
        "email": "vasu@example.com",
        "phone": "+91 99999 99999",
        "linkedin_url": "https://linkedin.com/in/vasu",
    })

    assert identity["email"] == "vasu@example.com"
    assert identity["phone"] == "+91 99999 99999"
    assert saved["identity"]["linkedin_url"] == "https://linkedin.com/in/vasu"


def test_profile_service_import_profile_data_accepts_legacy_keys(monkeypatch):
    service = ProfileService()
    seen = {}

    monkeypatch.setattr(service, "add_skill", lambda name, category: seen.setdefault("skill", (name, category)))
    monkeypatch.setattr(service, "add_experience", lambda role, company, period, description: seen.setdefault("exp", (role, company, period, description)))
    monkeypatch.setattr(service, "refresh_profile_snapshot", lambda: None)
    monkeypatch.setattr("profile.service.graph_profile.sync_vectors_from_graph", lambda: {"status": "ok"})

    result = asyncio.run(service.import_profile_data({
        "skills": [{"n": "FastAPI", "cat": "backend"}],
        "experience": [{"role": "Dev", "co": "Acme", "period": "2025", "d": "APIs"}],
    }))

    assert result["status"] == "ok"
    assert seen["skill"] == ("FastAPI", "backend")
    assert seen["exp"] == ("Dev", "Acme", "2025", "APIs")


def test_profile_service_import_profile_data_saves_snapshot_fallback(monkeypatch):
    service = ProfileService()
    saved = {}

    monkeypatch.setattr(service, "get_profile", lambda: {"n": "", "s": "", "skills": [], "projects": [], "exp": []})
    monkeypatch.setattr(service, "update_candidate", lambda _name, _summary: (_ for _ in ()).throw(RuntimeError("graph locked")))
    monkeypatch.setattr(service, "add_skill", lambda _name, _category: (_ for _ in ()).throw(RuntimeError("graph locked")))
    monkeypatch.setattr(service, "add_project", lambda _title, _stack, _repo, _impact: (_ for _ in ()).throw(RuntimeError("graph locked")))
    monkeypatch.setattr(service, "refresh_profile_snapshot", lambda: None)
    monkeypatch.setattr("profile.service.graph_profile.sync_vectors_from_graph", lambda: {"status": "ok"})
    monkeypatch.setattr("profile.service.graph_profile.save_profile_snapshot", lambda profile: saved.update(profile))

    result = asyncio.run(service.import_profile_data({
        "candidate": {"name": "Jane Doe", "summary": "Imported portfolio profile"},
        "skills": [{"name": "React", "category": "portfolio"}],
        "projects": [{"title": "Ops Console", "stack": "React, FastAPI", "repo": "", "impact": "Built it"}],
        "achievements": [{"title": "Shipped production automation"}],
    }))

    assert result["status"] == "partial"
    assert saved["n"] == "Jane Doe"
    assert saved["skills"][0]["n"] == "React"
    assert saved["projects"][0]["title"] == "Ops Console"
    assert saved["achievements"] == ["Shipped production automation"]
