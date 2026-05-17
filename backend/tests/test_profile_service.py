import asyncio

from profile.service import ProfileService
from models.schema import C, S, E, P


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


def test_profile_service_import_profile_data_sanitizes_bad_buckets(monkeypatch):
    service = ProfileService()
    calls = {"skills": [], "projects": [], "education": []}

    monkeypatch.setattr(service, "add_skill", lambda name, category: calls["skills"].append((name, category)))
    monkeypatch.setattr(service, "add_project", lambda title, stack, repo, impact: calls["projects"].append((title, stack, repo, impact)))
    monkeypatch.setattr(service, "add_education", lambda title: calls["education"].append(title))
    monkeypatch.setattr(service, "refresh_profile_snapshot", lambda: None)
    monkeypatch.setattr("profile.service.graph_profile.sync_vectors_from_graph", lambda: {"status": "ok"})

    result = asyncio.run(service.import_profile_data({
        "skills": [
            {"name": "React, FastAPI"},
            {"name": "Built a dashboard with PostgreSQL automation for operators."},
        ],
        "projects": [
            {"title": "React"},
            {"title": "JustHireMe", "stack": "React, FastAPI", "impact": "Local-first job workbench"},
            {"title": "Built graph ranking and resume generation workflows."},
            {"title": "Punjab"},
        ],
        "education": [
            {"title": "Lovely Professional University"},
            {"title": "Punjab"},
            {"title": "CGPA 8.5"},
        ],
    }))

    assert result["status"] == "ok"
    assert calls["skills"] == [("React", "general"), ("FastAPI", "general")]
    assert len(calls["projects"]) == 1
    assert calls["projects"][0][0] == "JustHireMe"
    assert "Built graph ranking" in calls["projects"][0][3]
    assert calls["education"] == ["Lovely Professional University, Punjab, CGPA 8.5"]


def test_profile_service_import_profile_data_repairs_project_links_and_certificates(monkeypatch):
    service = ProfileService()
    calls = {"projects": [], "certifications": [], "candidate": []}

    monkeypatch.setattr(service, "update_candidate", lambda name, summary: calls["candidate"].append((name, summary)))
    monkeypatch.setattr(service, "add_project", lambda title, stack, repo, impact: calls["projects"].append((title, stack, repo, impact)))
    monkeypatch.setattr(service, "add_certification", lambda title: calls["certifications"].append(title))
    monkeypatch.setattr(service, "refresh_profile_snapshot", lambda: None)
    monkeypatch.setattr("profile.service.graph_profile.sync_vectors_from_graph", lambda: {"status": "ok"})

    result = asyncio.run(service.import_profile_data({
        "candidate": {
            "name": "Komalpreet Kaur",
            "summary": "Email: kaur@example.com. Phone: +91 9451735039. Links: https://github.com/Komalpreet2809/Vanta",
        },
        "projects": [
            {"title": "conditioning. - https://github.com/Komalpreet2809/Vanta", "impact": "Deployed FastAPI backend."},
            {"title": "APIs.", "impact": "Playwright | https://github.com/Komalpreet2809/Specula"},
        ],
        "certifications": [
            {"title": "Social Networks"},
            {"title": "Jan2025 - Apr 2025"},
            {"title": "NPTEL -- Certificate Link"},
        ],
    }))

    assert result["status"] == "ok"
    assert calls["candidate"][0] == ("Komalpreet Kaur", "")
    assert [project[0] for project in calls["projects"]] == ["Vanta", "Specula"]
    assert calls["projects"][1][1] == "Playwright"
    assert calls["certifications"] == ["Social Networks - NPTEL Jan 2025 - Apr 2025"]


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


def test_profile_service_ingest_resume_saves_snapshot_fallback(monkeypatch):
    service = ProfileService()
    saved = {}
    parsed = C(
        n="Jane Doe",
        s="Applied AI engineer",
        skills=[S(n="Python", cat="technical")],
        exp=[E(role="Engineer", co="Acme", period="2025", d="Built agents")],
        projects=[P(title="Hiring Agent", stack=["FastAPI", "React"], repo="", impact="Automated matching")],
        education=["B.Tech"],
    )

    monkeypatch.setattr("profile.ingestor.ingest", lambda _raw, _path: parsed)
    monkeypatch.setattr(service, "get_profile", lambda: {"n": "", "s": "", "skills": [], "projects": [], "exp": []})
    monkeypatch.setattr(service, "refresh_profile_snapshot", lambda: None)
    monkeypatch.setattr("profile.service.graph_profile.save_profile_snapshot", lambda profile: saved.update(profile))
    monkeypatch.setattr("profile.service.graph_profile.sync_vectors_from_graph", lambda: {"status": "ok"})

    result = asyncio.run(service.ingest_resume("resume text", None))

    assert result.n == "Jane Doe"
    assert saved["n"] == "Jane Doe"
    assert saved["skills"][0]["n"] == "Python"
    assert saved["exp"][0]["role"] == "Engineer"
    assert saved["projects"][0]["title"] == "Hiring Agent"


def test_profile_service_ingest_resume_preserves_projects_after_graph_refresh(monkeypatch):
    service = ProfileService()
    saved_profiles = []
    parsed = C(
        n="Jane Doe",
        s="Applied AI engineer",
        skills=[S(n="Python", cat="technical")],
        projects=[P(title="Hiring Agent", stack=["FastAPI", "React"], repo="", impact="Automated matching")],
    )

    monkeypatch.setattr("profile.ingestor.ingest", lambda _raw, _path: parsed)
    monkeypatch.setattr(service, "get_profile", lambda: {"n": "Jane Doe", "s": "Applied AI engineer", "skills": [{"id": "python", "n": "Python"}], "projects": [], "exp": []})
    monkeypatch.setattr(service, "refresh_profile_snapshot", lambda: None)
    monkeypatch.setattr("profile.service.graph_profile.forget_profile_deletions_for_profile", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("profile.service.graph_profile.save_profile_snapshot", lambda profile: saved_profiles.append(profile))
    monkeypatch.setattr("profile.service.graph_profile.sync_vectors_from_graph", lambda: {"status": "ok"})

    result = asyncio.run(service.ingest_resume("resume text", None))

    assert result.projects[0].title == "Hiring Agent"
    assert saved_profiles[-1]["projects"][0]["title"] == "Hiring Agent"


def test_graph_profile_get_profile_merges_snapshot_with_existing_graph(monkeypatch):
    from data.graph import profile as graph_profile

    snapshot = {
        "n": "Jane Doe",
        "s": "Imported resume",
        "skills": [{"id": "python", "n": "Python", "cat": "resume"}],
        "projects": [],
        "exp": [],
    }
    graph = {
        "n": "Old Candidate",
        "s": "Old graph profile",
        "skills": [{"id": "react", "n": "React", "cat": "graph"}],
        "projects": [],
        "exp": [],
    }
    saved = {}

    monkeypatch.setattr(graph_profile, "load_profile_snapshot", lambda _db_path=None: snapshot)
    monkeypatch.setattr(graph_profile, "read_profile_from_graph", lambda: graph)
    monkeypatch.setattr(graph_profile, "save_profile_snapshot", lambda profile, _db_path=None: saved.update(profile))

    merged = graph_profile.get_profile()

    assert merged["n"] == "Old Candidate"
    assert {skill["n"] for skill in merged["skills"]} == {"Python", "React"}
    assert saved["skills"][0]["n"] == "Python"


def test_graph_profile_manual_candidate_save_updates_snapshot(monkeypatch):
    from data.graph import profile as graph_profile

    saved = {}
    rows = iter([["candidate-1"]])

    class Result:
        def has_next(self):
            return True

        def get_next(self):
            return next(rows, ["candidate-1"])

    monkeypatch.setattr(graph_profile, "execute_query", lambda *_args, **_kwargs: Result())
    monkeypatch.setattr(graph_profile, "load_profile_snapshot", lambda _db_path=None: {"n": "Old", "s": "", "skills": [], "projects": [], "exp": []})
    monkeypatch.setattr(graph_profile, "read_profile_from_graph", lambda: {"n": "Old", "s": "", "skills": [], "projects": [], "exp": []})
    monkeypatch.setattr(graph_profile, "save_profile_snapshot", lambda profile, _db_path=None: saved.update(profile))
    monkeypatch.setattr(graph_profile, "add_candidate_vec", lambda *_args, **_kwargs: None)

    result = graph_profile.update_candidate("Jane Doe", "Applied AI engineer")

    assert result == {"n": "Jane Doe", "s": "Applied AI engineer"}
    assert saved["n"] == "Jane Doe"
    assert saved["s"] == "Applied AI engineer"


def test_graph_profile_manual_candidate_save_falls_back_when_graph_unavailable(monkeypatch):
    from data.graph import profile as graph_profile

    saved = {}

    monkeypatch.setattr(graph_profile, "execute_query", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_profile, "load_profile_snapshot", lambda _db_path=None: {"n": "Old", "s": "", "skills": [], "projects": [], "exp": []})
    monkeypatch.setattr(graph_profile, "read_profile_from_graph", lambda: (_ for _ in ()).throw(RuntimeError("graph locked")))
    monkeypatch.setattr(graph_profile, "save_profile_snapshot", lambda profile, _db_path=None: saved.update(profile))
    monkeypatch.setattr(graph_profile, "add_candidate_vec", lambda *_args, **_kwargs: None)

    result = graph_profile.update_candidate("Jane Doe", "Applied AI engineer")

    assert result == {"n": "Jane Doe", "s": "Applied AI engineer"}
    assert saved["n"] == "Jane Doe"
    assert saved["s"] == "Applied AI engineer"


def test_graph_profile_delete_education_accepts_title_path_and_updates_snapshot(monkeypatch):
    from data.graph import profile as graph_profile

    saved = {}
    deleted_vec_ids = []
    graph_deletes = []

    monkeypatch.setattr(graph_profile, "_query_rows", lambda query, _params=None: [["edu-1", "B.Tech / MBA"]] if "Education" in query else [])
    monkeypatch.setattr(graph_profile, "_safe_execute", lambda query, params=None: graph_deletes.append((query, params)))
    monkeypatch.setattr(graph_profile, "delete_vec_id_from_all", lambda row_id: deleted_vec_ids.append(row_id))
    monkeypatch.setattr(graph_profile, "_refresh_after_write", lambda _db_path=None: None)
    monkeypatch.setattr(
        graph_profile,
        "load_profile_snapshot",
        lambda _db_path=None: {
            "n": "Jane",
            "s": "",
            "skills": [],
            "projects": [],
            "exp": [],
            "education": ["B.Tech / MBA", "MSc"],
        },
    )
    monkeypatch.setattr(graph_profile, "save_profile_snapshot", lambda profile, _db_path=None, **_kwargs: saved.update(profile))

    graph_profile.delete_education("B.Tech%20%2F%20MBA")

    assert deleted_vec_ids == ["edu-1"]
    assert graph_deletes[0][1] == {"id": "edu-1"}
    assert saved["education"] == ["MSc"]


def test_graph_profile_delete_skill_accepts_name_when_id_is_missing(monkeypatch):
    from data.graph import profile as graph_profile

    saved = {}
    graph_deletes = []
    deleted_vec_ids = []

    monkeypatch.setattr(graph_profile, "_query_rows", lambda query, _params=None: [["skill-1", "FastAPI"]] if "Skill" in query else [])
    monkeypatch.setattr(graph_profile, "_safe_execute", lambda query, params=None: graph_deletes.append((query, params)))
    monkeypatch.setattr(graph_profile, "delete_vec_rows", lambda _table, ids: deleted_vec_ids.extend(ids))
    monkeypatch.setattr(graph_profile, "delete_vec_id_from_all", lambda row_id: deleted_vec_ids.append(row_id))
    monkeypatch.setattr(graph_profile, "_refresh_after_write", lambda _db_path=None: None)
    monkeypatch.setattr(
        graph_profile,
        "load_profile_snapshot",
        lambda _db_path=None: {
            "n": "Jane",
            "s": "",
            "skills": [{"n": "FastAPI", "cat": "backend"}, {"id": "react", "n": "React", "cat": "frontend"}],
            "projects": [],
            "exp": [],
        },
    )
    monkeypatch.setattr(graph_profile, "save_profile_snapshot", lambda profile, _db_path=None, **_kwargs: saved.update(profile))

    graph_profile.delete_skill("FastAPI")

    assert any(params == {"id": "skill-1"} for _query, params in graph_deletes)
    assert "skill-1" in deleted_vec_ids
    assert [item["n"] for item in saved["skills"]] == ["React"]


def test_graph_profile_delete_project_accepts_title_when_id_is_missing(monkeypatch):
    from data.graph import profile as graph_profile

    saved = {}
    graph_deletes = []

    monkeypatch.setattr(graph_profile, "_query_rows", lambda query, _params=None: [["proj-1", "Hiring Agent"]] if "Project" in query else [])
    monkeypatch.setattr(graph_profile, "_safe_execute", lambda query, params=None: graph_deletes.append((query, params)))
    monkeypatch.setattr(graph_profile, "delete_vec_rows", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_profile, "delete_vec_id_from_all", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_profile, "_refresh_after_write", lambda _db_path=None: None)
    monkeypatch.setattr(
        graph_profile,
        "load_profile_snapshot",
        lambda _db_path=None: {
            "n": "Jane",
            "s": "",
            "skills": [],
            "projects": [{"title": "Hiring Agent"}, {"id": "p2", "title": "Ops Console"}],
            "exp": [],
        },
    )
    monkeypatch.setattr(graph_profile, "save_profile_snapshot", lambda profile, _db_path=None, **_kwargs: saved.update(profile))

    graph_profile.delete_project("Hiring Agent")

    assert any(params == {"id": "proj-1"} for _query, params in graph_deletes)
    assert [item["title"] for item in saved["projects"]] == ["Ops Console"]


def test_graph_profile_deleted_project_does_not_rehydrate_from_graph(monkeypatch):
    from data.graph import profile as graph_profile

    deleted_payload = {"projects": [graph_profile.hash_id("Hiring Agent"), "Hiring Agent"]}

    def fake_get_setting(key, default="", *_args):
        if key == graph_profile.PROFILE_DELETIONS_KEY:
            import json

            return json.dumps(deleted_payload)
        return default

    def fake_query_rows(query, _params=None):
        if "Project" in query:
            return [[graph_profile.hash_id("Hiring Agent"), "Hiring Agent", "Python", "", "Built it"]]
        return []

    monkeypatch.setattr(graph_profile, "get_setting", fake_get_setting)
    monkeypatch.setattr(graph_profile, "_query_rows", fake_query_rows)

    profile = graph_profile.read_profile_from_graph()

    assert profile["projects"] == []


def test_graph_profile_delete_experience_accepts_role_company_label_when_id_is_missing(monkeypatch):
    from data.graph import profile as graph_profile

    saved = {}
    graph_deletes = []

    monkeypatch.setattr(graph_profile, "_query_rows", lambda query, _params=None: [["exp-1", "Engineer", "Acme"]] if "Experience" in query else [])
    monkeypatch.setattr(graph_profile, "_safe_execute", lambda query, params=None: graph_deletes.append((query, params)))
    monkeypatch.setattr(graph_profile, "delete_vec_rows", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_profile, "delete_vec_id_from_all", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_profile, "_refresh_after_write", lambda _db_path=None: None)
    monkeypatch.setattr(
        graph_profile,
        "load_profile_snapshot",
        lambda _db_path=None: {
            "n": "Jane",
            "s": "",
            "skills": [],
            "projects": [],
            "exp": [{"role": "Engineer", "co": "Acme"}, {"id": "exp-2", "role": "Designer", "co": "Beta"}],
        },
    )
    monkeypatch.setattr(graph_profile, "save_profile_snapshot", lambda profile, _db_path=None, **_kwargs: saved.update(profile))

    graph_profile.delete_experience("Engineer at Acme")

    assert any(params == {"id": "exp-1"} for _query, params in graph_deletes)
    assert [item["role"] for item in saved["exp"]] == ["Designer"]


def test_graph_profile_delete_last_text_entry_allows_empty_snapshot(monkeypatch):
    from data.graph import profile as graph_profile

    saved = {}

    monkeypatch.setattr(graph_profile, "_query_rows", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(graph_profile, "_safe_execute", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_profile, "delete_vec_id_from_all", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_profile, "_refresh_after_write", lambda _db_path=None: None)
    monkeypatch.setattr(
        graph_profile,
        "load_profile_snapshot",
        lambda _db_path=None: {
            "n": "",
            "s": "",
            "skills": [],
            "projects": [],
            "exp": [],
            "education": ["Only entry"],
        },
    )
    monkeypatch.setattr(
        graph_profile,
        "save_profile_snapshot",
        lambda profile, _db_path=None, **kwargs: saved.update({"profile": profile, "allow_empty": kwargs.get("allow_empty")}),
    )

    graph_profile.delete_education("Only entry")

    assert saved["profile"]["education"] == []
    assert saved["allow_empty"] is True


def test_graph_profile_read_profile_tolerates_missing_query_results(monkeypatch):
    from data.graph import profile as graph_profile

    monkeypatch.setattr(graph_profile, "execute_query", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_profile, "get_setting", lambda _key, default="": default)

    profile = graph_profile.read_profile_from_graph()

    assert profile["n"] == ""
    assert profile["skills"] == []
    assert profile["projects"] == []
    assert profile["exp"] == []


def test_graph_profile_manual_skill_save_falls_back_when_graph_write_fails(monkeypatch):
    from data.graph import profile as graph_profile

    saved = {}

    def locked_graph(*_args, **_kwargs):
        raise RuntimeError("graph locked")

    monkeypatch.setattr(graph_profile, "execute_query", locked_graph)
    monkeypatch.setattr(graph_profile, "load_profile_snapshot", lambda _db_path=None: {"n": "Jane", "s": "", "skills": [], "projects": [], "exp": []})
    monkeypatch.setattr(graph_profile, "read_profile_from_graph", lambda: (_ for _ in ()).throw(RuntimeError("graph locked")))
    monkeypatch.setattr(graph_profile, "save_profile_snapshot", lambda profile, _db_path=None: saved.update(profile))
    monkeypatch.setattr(graph_profile, "add_skill_vec", lambda *_args, **_kwargs: None)

    result = graph_profile.add_skill("Python", "technical")

    assert result["n"] == "Python"
    assert saved["skills"][0]["n"] == "Python"


def test_graph_profile_manual_skill_save_updates_snapshot(monkeypatch):
    from data.graph import profile as graph_profile

    saved = {}

    class EmptyResult:
        def has_next(self):
            return False

        def get_next(self):
            return []

    monkeypatch.setattr(graph_profile, "execute_query", lambda *_args, **_kwargs: EmptyResult())
    monkeypatch.setattr(graph_profile, "load_profile_snapshot", lambda _db_path=None: {"n": "Jane", "s": "", "skills": [], "projects": [], "exp": []})
    monkeypatch.setattr(graph_profile, "read_profile_from_graph", lambda: {"n": "Jane", "s": "", "skills": [], "projects": [], "exp": []})
    monkeypatch.setattr(graph_profile, "save_profile_snapshot", lambda profile, _db_path=None: saved.update(profile))
    monkeypatch.setattr(graph_profile, "add_skill_vec", lambda *_args, **_kwargs: None)

    result = graph_profile.add_skill("Python", "technical")

    assert result["n"] == "Python"
    assert saved["skills"][0]["n"] == "Python"
