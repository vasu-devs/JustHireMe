import asyncio

from profile.service import ProfileService
from models.schema import C, S, E, P


def _sync_status():
    return {"status": "ok", "relationships": {"status": "ok"}, "vectors": {"status": "ok", "synced": 1}}


async def _ok_post_ingest_sync():
    return _sync_status()


def test_run_graph_propagates_bulk_profile_import_context():
    from data.graph import profile as graph_profile
    from data.graph.connection import run_graph

    async def read_bulk_import_state():
        with graph_profile.bulk_profile_import():
            return await run_graph(graph_profile._bulk_import_active)

    assert asyncio.run(read_bulk_import_state()) is True


def test_resume_ingestor_strips_unicode_and_legacy_bullets():
    from profile import ingestor

    assert ingestor._strip_md("\u2022 FastAPI") == "FastAPI"
    assert ingestor._strip_md("\u00e2\u20ac\u00a2 FastAPI") == "FastAPI"


def test_resume_ingestor_put_node_updates_existing_without_duplicate_create(monkeypatch):
    from profile import ingestor
    from data.graph import connection

    calls = []

    class ExistingResult:
        def has_next(self):
            return True

        def get_next(self):
            return ["skill-1"]

    def fake_execute(query, params=None):
        calls.append((query, params))
        if " RETURN " in query:
            return ExistingResult()
        return None

    monkeypatch.setattr(connection, "execute_query", fake_execute)

    ingestor._put_node("Skill", {"id": "skill-1", "n": "Python", "cat": "general"})

    assert calls[0][1] == {"id": "skill-1"}
    assert any(" SET " in query for query, _params in calls)
    assert not any(query.startswith("CREATE") for query, _params in calls)


def test_resume_ingestor_put_node_creates_missing_node(monkeypatch):
    from profile import ingestor
    from data.graph import connection

    calls = []

    class EmptyResult:
        def has_next(self):
            return False

    def fake_execute(query, params=None):
        calls.append((query, params))
        if " RETURN " in query:
            return EmptyResult()
        return None

    monkeypatch.setattr(connection, "execute_query", fake_execute)

    ingestor._put_node("Skill", {"id": "skill-1", "n": "Python", "cat": "general"})

    assert any(query.startswith("CREATE (:Skill") for query, _params in calls)


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
    monkeypatch.setattr(service, "_run_post_ingest_sync", _ok_post_ingest_sync)

    result = asyncio.run(service.import_profile_data({
        "candidate": {"name": "Vasu", "summary": "AI engineer"},
        "identity": {"email": "alex@example.test", "github_url": "https://github.com/alex-example"},
        "skills": [{"name": "Python", "category": "technical"}],
        "experience": [{"role": "Engineer", "company": "Acme", "period": "2024", "description": "Built agents"}],
        "projects": [{"title": "JustHireMe", "stack": "Python, React", "repo": "", "impact": "Local-first job workbench"}],
        "education": [{"title": "B.Tech"}],
        "certifications": [{"title": "Cloud cert"}],
        "achievements": [{"title": "Shipped product"}],
    }))

    assert result["status"] == "ok"
    assert {key: value for key, value in result["stats"].items() if key not in {"vector_sync", "graph_sync"}} == {
        "skills": 1,
        "experience": 1,
        "projects": 1,
        "education": 1,
        "certifications": 1,
        "achievements": 1,
    }
    assert result["stats"]["vector_sync"] == {"status": "ok", "synced": 1}
    assert result["stats"]["graph_sync"] == _sync_status()
    assert calls["identity"][0]["email"] == "alex@example.test"
    assert calls["identity"][0]["github_url"] == "https://github.com/alex-example"


def test_profile_service_update_identity_saves_profile_contact(monkeypatch):
    service = ProfileService()
    saved = {}
    snapshot = {"n": "Vasu", "s": "AI engineer", "skills": [], "projects": [], "exp": []}

    monkeypatch.setattr("profile.service.graph_profile.load_profile_snapshot", lambda _db_path=None: snapshot)
    monkeypatch.setattr("profile.service.graph_profile.save_profile_snapshot", lambda profile, _db_path=None: saved.update(profile))
    monkeypatch.setattr("profile.service.graph_profile.read_profile_from_graph", lambda: snapshot)
    monkeypatch.setattr("profile.service.graph_profile.save_settings", lambda _payload, *_args: None)

    identity = service.update_identity({
        "email": "alex@example.test",
        "phone": "+1 555 010 0002",
        "linkedin_url": "https://linkedin.com/in/example-candidate",
    })

    assert identity["email"] == "alex@example.test"
    assert identity["phone"] == "+1 555 010 0002"
    assert saved["identity"]["linkedin_url"] == "https://linkedin.com/in/example-candidate"


def test_profile_service_import_profile_data_accepts_legacy_keys(monkeypatch):
    service = ProfileService()
    seen = {}

    monkeypatch.setattr(service, "add_skill", lambda name, category: seen.setdefault("skill", (name, category)))
    monkeypatch.setattr(service, "add_experience", lambda role, company, period, description: seen.setdefault("exp", (role, company, period, description)))
    monkeypatch.setattr(service, "refresh_profile_snapshot", lambda: None)
    monkeypatch.setattr(service, "_run_post_ingest_sync", _ok_post_ingest_sync)

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
    monkeypatch.setattr(service, "_run_post_ingest_sync", _ok_post_ingest_sync)

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


def test_profile_normalization_rejects_github_metadata_as_skills():
    from profile.github_ingestor import _fallback_project
    from profile.normalization import normalize_profile_payload

    cleaned = normalize_profile_payload({
        "skills": [
            {"name": "maintained through 2026-03-06", "category": "project_stack"},
            {"name": "2 forks", "category": "project_stack"},
            {"name": "memfs", "category": "project_stack"},
            {"name": "send", "category": "project_stack"},
            {"name": "TypeScript", "category": "github"},
        ],
        "projects": [
            {
                "title": "EmailDrafter",
                "stack": "maintained through 2026-03-06, 2 forks, TypeScript, memfs, send",
                "impact": "AI email draft tool",
            }
        ],
    })

    assert cleaned["skills"] == [{"name": "TypeScript", "category": "github"}]
    assert cleaned["projects"][0]["stack"] == "TypeScript"
    assert cleaned["projects"][0]["impact"] == "AI email draft tool"

    fallback = _fallback_project(
        {
            "name": "EmailDrafter",
            "description": "AI email draft tool",
            "language": "TypeScript",
            "topics": ["react"],
            "html_url": "https://github.com/example/EmailDrafter",
            "stargazers_count": 3,
            "forks_count": 2,
            "pushed_at": "2026-03-06T00:00:00Z",
        },
        "Built a dashboard API workflow with clean export.",
        {"TypeScript": 1000},
        [],
    )
    assert "fork" not in fallback["impact"].lower()
    assert "maintained through" not in fallback["impact"].lower()


def test_profile_service_import_profile_data_repairs_project_links_and_certificates(monkeypatch):
    service = ProfileService()
    calls = {"projects": [], "certifications": [], "candidate": []}

    monkeypatch.setattr(service, "update_candidate", lambda name, summary: calls["candidate"].append((name, summary)))
    monkeypatch.setattr(service, "add_project", lambda title, stack, repo, impact: calls["projects"].append((title, stack, repo, impact)))
    monkeypatch.setattr(service, "add_certification", lambda title: calls["certifications"].append(title))
    monkeypatch.setattr(service, "refresh_profile_snapshot", lambda: None)
    monkeypatch.setattr(service, "_run_post_ingest_sync", _ok_post_ingest_sync)

    result = asyncio.run(service.import_profile_data({
        "candidate": {
            "name": "Casey Example",
            "summary": "Email: casey@example.test. Phone: +1 555 010 0001. Links: https://github.com/example-candidate/Vanta",
        },
        "projects": [
            {"title": "conditioning. - https://github.com/example-candidate/Vanta", "impact": "Deployed FastAPI backend."},
            {"title": "APIs.", "impact": "Playwright | https://github.com/example-candidate/Specula"},
        ],
        "certifications": [
            {"title": "Social Networks"},
            {"title": "Jan2025 - Apr 2025"},
            {"title": "NPTEL -- Certificate Link"},
        ],
    }))

    assert result["status"] == "ok"
    assert calls["candidate"][0] == ("Casey Example", "")
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
    monkeypatch.setattr(service, "_run_post_ingest_sync", _ok_post_ingest_sync)
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
    monkeypatch.setattr(service, "_run_post_ingest_sync", _ok_post_ingest_sync)

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
    monkeypatch.setattr(service, "_run_post_ingest_sync", _ok_post_ingest_sync)

    result = asyncio.run(service.ingest_resume("resume text", None))

    assert result.projects[0].title == "Hiring Agent"
    assert saved_profiles[-1]["projects"][0]["title"] == "Hiring Agent"


def test_resume_heuristic_keeps_all_projects_and_single_education_entry():
    from profile import ingestor

    resume = """
Vasudev Siddh
Full Stack AI Engineer

Skills
Python, TypeScript, React, FastAPI, Tauri, PostgreSQL

Experience
AI Engineering Intern | Vaani Labs | Jan 2025 - Apr 2025
- Built FastAPI services for real-time voice agents.
- Developed React dashboards for prompt review.
- Engineered LLM evaluation workflows for production releases.

Projects
BranchGPT - Multi-agent branching chat interface for experiments.
Stack: Python, FastAPI, React
JustHireMe - Local-first job search workbench with graph matching.
Stack: TypeScript, Tauri, FastAPI, PostgreSQL
ASCIIRealTime - Live video-to-ASCII renderer with browser processing.
Stack: TypeScript, Canvas API, React
EmailDrafter - AI email draft tool with editable previews.
Stack: Python, OpenAI, FastAPI

Education
Lovely Professional University
Bachelor of Technology in Computer Science
2022 - 2026
Lovely Professional University
CGPA 8.5
"""

    parsed = ingestor._parse_resume_heuristic(resume)

    assert [project.title for project in parsed.projects] == [
        "BranchGPT",
        "JustHireMe",
        "ASCIIRealTime",
        "EmailDrafter",
    ]
    assert len(parsed.exp) == 1
    assert parsed.exp[0].role == "AI Engineering Intern"
    assert parsed.exp[0].co == "Vaani Labs"
    assert len(parsed.education) == 1
    assert "Lovely Professional University" in parsed.education[0]
    assert "Bachelor of Technology" in parsed.education[0]


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
    monkeypatch.setattr(graph_profile, "read_profile_from_graph", lambda **_kwargs: graph)
    monkeypatch.setattr(graph_profile, "read_profile_from_vectors", lambda _db_path=None: {})
    monkeypatch.setattr(graph_profile, "save_profile_snapshot", lambda profile, _db_path=None: saved.update(profile))

    merged = graph_profile.get_profile(prefer_snapshot=False)

    assert merged["n"] == "Old Candidate"
    assert {skill["n"] for skill in merged["skills"]} == {"Python", "React"}
    assert saved["skills"][0]["n"] == "Python"


def test_graph_profile_get_profile_prefers_saved_snapshot(monkeypatch):
    from data.graph import profile as graph_profile

    snapshot = {
        "n": "Jane Doe",
        "s": "Imported resume",
        "skills": [{"id": "python", "n": "Python", "cat": "resume"}],
        "projects": [],
        "exp": [],
    }

    monkeypatch.setattr(graph_profile, "load_profile_snapshot", lambda _db_path=None: snapshot)
    monkeypatch.setattr(graph_profile, "read_profile_from_graph", lambda: (_ for _ in ()).throw(RuntimeError("graph read should not block profile load")))

    assert graph_profile.get_profile() == snapshot


def test_graph_profile_get_profile_hydrates_sparse_snapshot_from_graph(monkeypatch):
    from data.graph import profile as graph_profile

    snapshot = {
        "n": "Jane Doe",
        "s": "Imported resume",
        "skills": [],
        "projects": [],
        "exp": [],
    }
    graph = {
        "n": "Candidate",
        "s": "",
        "skills": [{"id": "python", "n": "Python", "cat": "graph"}],
        "projects": [{"id": "ops", "title": "Ops Console", "stack": ["Python"], "repo": "", "impact": "Built it"}],
        "exp": [],
    }
    saved = {}

    monkeypatch.setattr(graph_profile, "load_profile_snapshot", lambda _db_path=None: snapshot)
    monkeypatch.setattr(graph_profile, "read_profile_from_graph", lambda **_kwargs: graph)
    monkeypatch.setattr(graph_profile, "read_profile_from_vectors", lambda _db_path=None: {})
    monkeypatch.setattr(graph_profile, "save_profile_snapshot", lambda profile, _db_path=None: saved.update(profile))

    merged = graph_profile.get_profile()

    assert merged["n"] == "Jane Doe"
    assert [skill["n"] for skill in merged["skills"]] == ["Python"]
    assert [project["title"] for project in merged["projects"]] == ["Ops Console"]
    assert saved["projects"][0]["title"] == "Ops Console"


def test_graph_profile_get_profile_hydrates_sparse_snapshot_from_vectors(monkeypatch):
    from data.graph import profile as graph_profile

    class FakeArrow:
        def __init__(self, rows):
            self._rows = rows

        def to_pylist(self):
            return self._rows

    class FakeTable:
        def __init__(self, rows):
            self._rows = rows

        def to_arrow(self):
            return FakeArrow(self._rows)

    class FakeVec:
        def __init__(self, tables):
            self._tables = tables

        def list_tables(self):
            return list(self._tables)

        def open_table(self, table_name):
            return FakeTable(self._tables.get(table_name, []))

    snapshot = {
        "n": "Jane Doe",
        "s": "Imported resume",
        "skills": [],
        "projects": [],
        "exp": [],
    }
    tables = {
        "skills": [{"id": "typescript", "label": "TypeScript", "cat": "seed"}],
        "projects": [{"id": "gitart", "label": "GitArt", "stack": "TypeScript", "impact": "Generated art workflow"}],
        "experiences": [],
        "credentials": [{"id": "cert-1", "label": "Cloud Cert", "kind": "certification"}],
    }
    saved = {}

    monkeypatch.setattr(graph_profile, "load_profile_snapshot", lambda _db_path=None: snapshot)
    monkeypatch.setattr(graph_profile, "read_profile_from_graph", lambda **_kwargs: graph_profile.empty_profile())
    monkeypatch.setattr(graph_profile, "_vec", lambda: FakeVec(tables))
    monkeypatch.setattr(graph_profile, "get_setting", lambda _key, default="", *_args: default)
    monkeypatch.setattr(graph_profile, "save_profile_snapshot", lambda profile, _db_path=None: saved.update(profile))

    merged = graph_profile.get_profile()

    assert merged["n"] == "Jane Doe"
    assert [skill["n"] for skill in merged["skills"]] == ["TypeScript"]
    assert [project["title"] for project in merged["projects"]] == ["GitArt"]
    assert merged["certifications"] == ["Cloud Cert"]
    assert saved["skills"][0]["n"] == "TypeScript"


def test_graph_profile_materializes_profile_snapshot(monkeypatch):
    from data.graph import profile as graph_profile

    calls = {"candidate": [], "skills": [], "projects": [], "sync": 0, "saved": []}

    monkeypatch.setattr(graph_profile, "update_candidate", lambda name, summary, _db_path=None: calls["candidate"].append((name, summary)))
    monkeypatch.setattr(graph_profile, "add_skill", lambda name, category, _db_path=None: calls["skills"].append((name, category)))
    monkeypatch.setattr(graph_profile, "add_project", lambda title, stack, repo, impact, _db_path=None: calls["projects"].append((title, stack, repo, impact)))
    monkeypatch.setattr(graph_profile, "add_experience", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_profile, "add_education", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_profile, "add_certification", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_profile, "add_achievement", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_profile, "sync_profile_relationships", lambda: calls.update(sync=calls["sync"] + 1) or {"status": "ok"})
    monkeypatch.setattr(graph_profile, "save_profile_snapshot", lambda profile, _db_path=None, **_kwargs: calls["saved"].append(profile))

    result = graph_profile.materialize_profile_snapshot({
        "n": "Jane Doe",
        "s": "Applied AI engineer",
        "skills": [{"n": "Python", "cat": "backend"}],
        "projects": [{"title": "Ops Console", "stack": ["Python", "React"], "impact": "Built workflows"}],
    })

    assert result["status"] == "ok"
    assert calls["candidate"] == [("Jane Doe", "Applied AI engineer")]
    assert calls["skills"] == [("Python", "backend")]
    assert calls["projects"] == [("Ops Console", "Python, React", "", "Built workflows")]
    assert calls["sync"] == 1
    assert calls["saved"][0]["n"] == "Jane Doe"


def test_graph_profile_upsert_matches_with_primary_key_only(monkeypatch):
    from data.graph import profile as graph_profile

    calls = []

    class EmptyResult:
        def has_next(self):
            return False

    def fake_execute(query, params=None):
        calls.append((query, params))
        return EmptyResult()

    monkeypatch.setattr(graph_profile, "execute_query", fake_execute)

    assert graph_profile._upsert_node("Skill", {"id": "python", "n": "Python", "cat": "backend"}) is True
    assert calls[0][1] == {"id": "python"}


def test_graph_profile_get_profile_returns_snapshot_when_strict_graph_read_is_busy(monkeypatch):
    from data.graph import profile as graph_profile

    snapshot = {
        "n": "Jane Doe",
        "s": "Imported resume",
        "skills": [{"id": "python", "n": "Python", "cat": "resume"}],
        "projects": [],
        "exp": [],
    }

    monkeypatch.setattr(graph_profile, "load_profile_snapshot", lambda _db_path=None: snapshot)
    monkeypatch.setattr(graph_profile, "read_profile_from_graph", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("graph query unavailable")))
    monkeypatch.setattr(graph_profile, "read_profile_from_vectors", lambda _db_path=None: {})

    assert graph_profile.get_profile(prefer_snapshot=False) == snapshot


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

    monkeypatch.setattr(graph_profile, "_query_rows", lambda query, _params=None, **_kwargs: [["edu-1", "B.Tech / MBA"]] if "Education" in query else [])
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

    monkeypatch.setattr(graph_profile, "_query_rows", lambda query, _params=None, **_kwargs: [["skill-1", "FastAPI"]] if "Skill" in query else [])
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

    monkeypatch.setattr(graph_profile, "_query_rows", lambda query, _params=None, **_kwargs: [["proj-1", "Hiring Agent"]] if "Project" in query else [])
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

    def fake_query_rows(query, _params=None, **_kwargs):
        if "Project" in query:
            return [[graph_profile.hash_id("Hiring Agent"), "Hiring Agent", "Python", "", "Built it"]]
        return []

    from data.graph import profile_deletions

    monkeypatch.setattr(graph_profile, "get_setting", fake_get_setting)
    monkeypatch.setattr(graph_profile, "_query_rows", fake_query_rows)
    # Tombstone lookup moved to profile_deletions; patch its get_setting too.
    monkeypatch.setattr(profile_deletions, "get_setting", fake_get_setting)

    profile = graph_profile.read_profile_from_graph()

    assert profile["projects"] == []


def test_graph_profile_prunes_orphan_project_stack_skills(monkeypatch):
    from data.graph import profile as graph_profile

    monkeypatch.setattr(graph_profile, "get_setting", lambda _key, default="", *_args: default)

    profile = graph_profile.apply_profile_deletions({
        "n": "Jane",
        "skills": [
            {"id": "sqlite", "n": "SQLite", "cat": "project_stack"},
            {"id": "python", "n": "Python", "cat": "technical"},
        ],
        "projects": [],
        "exp": [],
    })

    assert [skill["n"] for skill in profile["skills"]] == ["Python"]


def test_graph_profile_keeps_project_stack_skills_still_used_by_projects(monkeypatch):
    from data.graph import profile as graph_profile

    monkeypatch.setattr(graph_profile, "get_setting", lambda _key, default="", *_args: default)

    profile = graph_profile.apply_profile_deletions({
        "n": "Jane",
        "skills": [{"id": "sqlite", "n": "SQLite", "cat": "project_stack"}],
        "projects": [{"id": "p1", "title": "Local DB", "stack": ["SQLite"]}],
        "exp": [],
    })

    assert [skill["n"] for skill in profile["skills"]] == ["SQLite"]


def test_graph_profile_delete_experience_accepts_role_company_label_when_id_is_missing(monkeypatch):
    from data.graph import profile as graph_profile

    saved = {}
    graph_deletes = []

    monkeypatch.setattr(graph_profile, "_query_rows", lambda query, _params=None, **_kwargs: [["exp-1", "Engineer", "Acme"]] if "Experience" in query else [])
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
