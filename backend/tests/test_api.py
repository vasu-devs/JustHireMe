import os
import sys
import types
import unittest
import asyncio
from pathlib import Path
from unittest import mock

from starlette.websockets import WebSocketDisconnect

# ── Must run before any backend module is imported ───────────────────────────
os.environ["LOCALAPPDATA"] = str(Path(__file__).resolve().parent)
os.environ["JHM_APP_DATA_DIR"] = str(Path(__file__).resolve().parent)
os.makedirs = lambda *_args, **_kwargs: None


class _FakeResult:
    def has_next(self):
        return False

    def get_next(self):
        return [0]


class _FakeConnection:
    def execute(self, *_args, **_kwargs):
        return _FakeResult()


class _FakeSqlConnection:
    def executescript(self, *_args, **_kwargs):
        return self

    def execute(self, *_args, **_kwargs):
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def commit(self):
        return None

    def close(self):
        return None


class _FakeVectorStore:
    def list_tables(self):
        return []

    def create_table(self, *_args, **_kwargs):
        return None

    def open_table(self, *_args, **_kwargs):
        return self

    def add(self, *_args, **_kwargs):
        return None


def _install_storage_fakes():
    fake_sqlite = types.SimpleNamespace(
        connect=lambda _path: _FakeSqlConnection()
    )
    sys.modules.setdefault(
        "kuzu",
        types.SimpleNamespace(
            Database=lambda _path: object(),
            Connection=lambda _db: _FakeConnection(),
        ),
    )
    sys.modules["sqlite3"] = fake_sqlite
    sys.modules.setdefault(
        "lancedb",
        types.SimpleNamespace(
            LanceDBConnection=_FakeVectorStore,
            connect=lambda _path: _FakeVectorStore(),
        ),
    )
    if "data.sqlite.connection" in sys.modules:
        sys.modules["data.sqlite.connection"].sqlite3 = fake_sqlite


_install_storage_fakes()

# ── Import app and override the randomly-generated token ────────────────────
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

main._API_TOKEN = "test-token-abc123"

from main import app  # noqa: E402  (same cached module, just for IDE clarity)

# Use a loopback Host so requests satisfy the TrustedHostMiddleware the same way
# the real Tauri webview (which talks to 127.0.0.1) does.
CLIENT = TestClient(app, raise_server_exceptions=False, base_url="http://127.0.0.1")
AUTH = {"Authorization": "Bearer test-token-abc123"}
NO_AUTH: dict = {}


# ── Request helpers ───────────────────────────────────────────────────────────

def get(path, *, auth=True, **kwargs):
    headers = AUTH if auth else NO_AUTH
    return CLIENT.get(path, headers=headers, **kwargs)


def post(path, *, auth=True, json=None, **kwargs):
    headers = AUTH if auth else NO_AUTH
    return CLIENT.post(path, headers=headers, json=json, **kwargs)


def put(path, *, auth=True, json=None, **kwargs):
    headers = AUTH if auth else NO_AUTH
    return CLIENT.put(path, headers=headers, json=json, **kwargs)


def delete(path, *, auth=True, **kwargs):
    headers = AUTH if auth else NO_AUTH
    return CLIENT.delete(path, headers=headers, **kwargs)


# ── Test classes ─────────────────────────────────────────────────────────────

class TestAuthGate(unittest.TestCase):
    def test_health_no_token_is_200(self):
        resp = get("/health", auth=False)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("components", resp.json())
        self.assertFalse(resp.json()["details_available"])

    def test_protected_route_no_token_is_401(self):
        resp = get("/api/v1/leads", auth=False)
        self.assertEqual(resp.status_code, 401)

    def test_protected_route_wrong_token_is_401(self):
        resp = CLIENT.get(
            "/api/v1/leads",
            headers={"Authorization": "Bearer wrong-token"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_protected_route_valid_token_is_not_401(self):
        resp = get("/api/v1/leads")
        self.assertNotEqual(resp.status_code, 401)


class TestGraphEndpoint(unittest.TestCase):
    def test_graph_endpoint_reads_snapshot_without_blocking_on_repairs(self):
        from api.routers.misc import graph_stats

        class Leads:
            def get_all_leads(self):
                raise AssertionError("default graph read must not load every lead")

        class Graph:
            def __init__(self):
                self.synced = None

            def sync_job_leads(self, leads):
                raise AssertionError("default graph read must not sync leads")

            def graph_counts(self):
                return {"candidate": 1, "skill": 2, "project": 3, "experience": 4, "joblead": 1}

            def graph_snapshot(self):
                return {
                    "nodes": [{"id": "candidate:default", "label": "Candidate", "type": "Candidate"}],
                    "edges": [],
                    "available": True,
                    "error": "",
                }

            def graph_available(self):
                return True

            def graph_error(self):
                return ""

        repo = types.SimpleNamespace(
            leads=Leads(),
            graph=Graph(),
            vector=types.SimpleNamespace(vec=types.SimpleNamespace(list_tables=lambda: [])),
        )
        data = __import__("asyncio").run(graph_stats(repo))

        self.assertIsNone(repo.graph.synced)
        self.assertEqual(data["joblead"], 1)
        self.assertEqual(data["status"], "live")
        self.assertTrue(data["graph"]["available"])
        self.assertEqual(data["sync"]["status"], "skipped")

    def test_graph_endpoint_can_run_repair_when_requested(self):
        from api.routers.misc import graph_stats

        class Leads:
            def get_all_leads(self):
                return [{"job_id": "job-1", "title": "Engineer", "kind": "job"}]

        class Graph:
            def __init__(self):
                self.synced = None

            def sync_job_leads(self, leads):
                self.synced = leads
                return {"status": "ok", "synced": len(leads), "refreshed_at": "now"}

            def sync_profile_relationships(self):
                return {"status": "ok"}

            def graph_counts(self):
                return {"candidate": 1, "skill": 2, "project": 3, "experience": 4, "joblead": 1}

            def graph_snapshot(self):
                return {"nodes": [], "edges": [], "available": True, "error": ""}

            def graph_available(self):
                return True

            def graph_error(self):
                return ""

        repo = types.SimpleNamespace(
            leads=Leads(),
            graph=Graph(),
            vector=types.SimpleNamespace(vec=types.SimpleNamespace(list_tables=lambda: [])),
        )
        data = __import__("asyncio").run(graph_stats(repo, repair=True))

        self.assertEqual(repo.graph.synced[0]["job_id"], "job-1")
        self.assertEqual(data["sync"]["status"], "ok")

    def test_graph_endpoint_returns_safe_payload_when_graph_steps_fail(self):
        from api.routers.misc import graph_stats

        class Leads:
            def get_all_leads(self):
                raise RuntimeError("sqlite unavailable")

        class Graph:
            def sync_job_leads(self, _leads):
                raise RuntimeError("sync should not run")

            def sync_profile_relationships(self):
                raise RuntimeError("profile graph unavailable")

            def graph_counts(self):
                raise RuntimeError("count failed")

            def graph_snapshot(self):
                raise RuntimeError("snapshot failed")

            def graph_available(self):
                return False

            def graph_error(self):
                return "Kuzu locked"

        repo = types.SimpleNamespace(
            leads=Leads(),
            graph=Graph(),
            vector=types.SimpleNamespace(vec=types.SimpleNamespace(list_tables=lambda: [])),
        )
        data = __import__("asyncio").run(graph_stats(repo))

        self.assertEqual(data["status"], "degraded")
        self.assertEqual(data["graph"]["nodes"], [])
        self.assertEqual(data["graph"]["edges"], [])
        self.assertEqual(data["sync"]["status"], "skipped")
        self.assertIn("Kuzu locked", data["error"])

    def test_websocket_valid_token_connects(self):
        # Token rides in the Sec-WebSocket-Protocol header (2nd subprotocol), not the URL.
        # The TestClient sends "testserver" as the ws Host regardless of base_url, so
        # set a loopback Host to satisfy TrustedHostMiddleware (the real webview uses 127.0.0.1).
        with CLIENT.websocket_connect(
            "/ws", subprotocols=["jhm.bearer", "test-token-abc123"], headers={"host": "127.0.0.1"}
        ) as ws:
            msg = ws.receive_json()
        self.assertEqual(msg["type"], "heartbeat")

    def test_websocket_missing_token_closes_without_server_error(self):
        with self.assertRaises(WebSocketDisconnect), CLIENT.websocket_connect(
            "/ws", headers={"host": "127.0.0.1"}
        ):
            pass


class TestHealthEndpoint(unittest.TestCase):
    def test_health_status_code(self):
        resp = get("/health")
        self.assertEqual(resp.status_code, 200)

    def test_health_returns_uptime_key(self):
        resp = get("/health")
        self.assertIn("uptime_seconds", resp.json())

    def test_health_returns_log_level(self):
        resp = get("/health")
        self.assertIn("log_level", resp.json())

    def test_health_details_require_valid_token(self):
        no_auth = get("/health", auth=False).json()
        with_auth = get("/health").json()
        wrong_auth = CLIENT.get("/health", headers={"Authorization": "Bearer wrong-token"}).json()

        self.assertNotIn("components", no_auth)
        self.assertNotIn("components", wrong_auth)
        self.assertIn("components", with_auth)
        self.assertTrue(with_auth["details_available"])

    def test_subsystem_health_exposes_degradation_schema(self):
        resp = get("/api/v1/health/subsystems")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual({"graph", "vector", "llm", "embeddings"}, set(payload))
        for subsystem in payload.values():
            self.assertIn(subsystem["status"], {"ok", "degraded", "unavailable"})


class TestLeadsEndpoints(unittest.TestCase):
    def test_get_leads_returns_list(self):
        resp = get("/api/v1/leads")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_get_leads_seniority_filter_accepted(self):
        resp = get("/api/v1/leads", params={"seniority": "senior"})
        self.assertEqual(resp.status_code, 200)

    def test_get_lead_not_found(self):
        # get_lead_by_id returns {} (falsy) → route raises 404
        resp = get("/api/v1/leads/nonexistent-job-id")
        self.assertEqual(resp.status_code, 404)

    def test_delete_lead_not_found(self):
        resp = delete("/api/v1/leads/nonexistent-job-id")
        self.assertEqual(resp.status_code, 404)

    def test_update_status_invalid_body(self):
        # Pydantic StatusBody only accepts known LeadStatus literals → 422
        resp = put(
            "/api/v1/leads/any-id/status",
            json={"status": "not_a_real_status"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_update_status_valid_body_not_found(self):
        resp = put(
            "/api/v1/leads/nonexistent/status",
            json={"status": "applied"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_manual_lead_missing_fields(self):
        resp = post("/api/v1/leads/manual", json={})
        self.assertEqual(resp.status_code, 422)

    def test_manual_lead_text_too_long(self):
        resp = post("/api/v1/leads/manual", json={"text": "x" * 25000})
        self.assertEqual(resp.status_code, 422)

    def test_manual_lead_uses_raw_lead_when_feedback_ranking_fails(self):
        from api.dependencies import get_ranking_service, get_repository

        saved: dict = {}

        class FailingRanking:
            async def apply_feedback(self, _lead, _examples):
                raise RuntimeError("ranking unavailable")

        class Leads:
            def save_lead(self, lead):
                saved.update(lead)

            def get_lead_by_id(self, _job_id):
                return saved

        fake_repo = types.SimpleNamespace(
            feedback=types.SimpleNamespace(get_feedback_training_examples=lambda: []),
            leads=Leads(),
        )
        app.dependency_overrides[get_repository] = lambda: fake_repo
        app.dependency_overrides[get_ranking_service] = lambda: FailingRanking()
        try:
            resp = post(
                "/api/v1/leads/manual",
                json={
                    "kind": "job",
                    "url": "https://jobs.example.com/applied-ai-engineer-demo",
                    "text": "Applied AI Engineer\nCompany: NimbusWorks\nLocation: Remote\nPython FastAPI React PostgreSQL",
                },
            )
        finally:
            app.dependency_overrides.pop(get_repository, None)
            app.dependency_overrides.pop(get_ranking_service, None)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["kind"], "job")
        self.assertIn("feedback_learning_error", data.get("source_meta", {}))

    def test_manual_url_only_lead_is_saved_as_needing_description(self):
        from api.dependencies import get_ranking_service, get_repository

        saved: dict = {}

        class Ranking:
            async def apply_feedback(self, lead, _examples):
                return lead

        class Leads:
            def save_lead(self, lead):
                saved.update(lead)

            def get_lead_by_id(self, _job_id):
                return saved

        fake_repo = types.SimpleNamespace(
            feedback=types.SimpleNamespace(get_feedback_training_examples=lambda: []),
            leads=Leads(),
        )
        app.dependency_overrides[get_repository] = lambda: fake_repo
        app.dependency_overrides[get_ranking_service] = lambda: Ranking()
        try:
            resp = post(
                "/api/v1/leads/manual",
                json={
                    "kind": "job",
                    "url": "https://wellfound.com/jobs/4015090-ai-research-data-science-intern",
                    "text": "",
                },
            )
        finally:
            app.dependency_overrides.pop(get_repository, None)
            app.dependency_overrides.pop(get_ranking_service, None)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["title"], "AI Research Data Science Intern")
        self.assertEqual(data["description"], "")
        self.assertTrue(data["source_meta"]["needs_job_description"])

    def test_manual_customize_rejects_url_only_generation(self):
        from api.dependencies import get_generation_service, get_job_runner, get_repository
        from api.routers import generation

        saved: dict = {}

        class Leads:
            def save_lead(self, lead):
                saved.update(lead)

            def get_lead_by_id(self, _job_id):
                return saved

        fake_repo = types.SimpleNamespace(leads=Leads())
        generate_mock = mock.AsyncMock(return_value={})
        app.dependency_overrides[get_repository] = lambda: fake_repo
        app.dependency_overrides[get_generation_service] = lambda: object()
        app.dependency_overrides[get_job_runner] = lambda: object()
        try:
            with mock.patch.object(generation, "generate_one", new=generate_mock):
                resp = post(
                    "/api/v1/leads/manual/generate/start",
                    json={
                        "kind": "job",
                        "url": "https://wellfound.com/jobs/4015090-ai-research-data-science-intern",
                        "text": "https://wellfound.com/jobs/4015090-ai-research-data-science-intern",
                    },
                )
        finally:
            app.dependency_overrides.pop(get_repository, None)
            app.dependency_overrides.pop(get_generation_service, None)
            app.dependency_overrides.pop(get_job_runner, None)

        self.assertEqual(resp.status_code, 422)
        self.assertIn("job description", resp.json()["detail"])
        self.assertEqual(generate_mock.await_count, 0)
        self.assertTrue(saved["source_meta"]["needs_job_description"])

    def test_manual_customize_start_returns_immediately(self):
        from api.dependencies import get_generation_service, get_job_runner, get_repository
        from api.routers import generation

        saved: dict = {}

        class Leads:
            def save_lead(self, lead):
                saved.update(lead)

            def update_lead_status(self, job_id, status):
                saved["job_id"] = job_id
                saved["status"] = status

            def get_lead_by_id(self, _job_id):
                return saved

        fake_repo = types.SimpleNamespace(leads=Leads())
        generate_mock = mock.AsyncMock(return_value={**saved, "status": "approved"})
        app.dependency_overrides[get_repository] = lambda: fake_repo
        app.dependency_overrides[get_generation_service] = lambda: object()
        app.dependency_overrides[get_job_runner] = lambda: object()
        try:
            with mock.patch.object(generation, "generate_one", new=generate_mock):
                resp = post(
                    "/api/v1/leads/manual/generate/start",
                    json={
                        "kind": "job",
                        "url": "https://jobs.example.com/applied-ai-engineer-demo",
                        "text": "Applied AI Engineer\nCompany: NimbusWorks\nLocation: Remote\nPython FastAPI React PostgreSQL",
                    },
                )
        finally:
            app.dependency_overrides.pop(get_repository, None)
            app.dependency_overrides.pop(get_generation_service, None)
            app.dependency_overrides.pop(get_job_runner, None)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "started")
        self.assertEqual(data["lead"]["status"], "tailoring")
        self.assertEqual(data["lead"]["company"], "NimbusWorks")
        self.assertLessEqual(generate_mock.await_count, 1)


class TestExportEndpoint(unittest.TestCase):
    def test_export_csv_status(self):
        resp = get("/api/v1/leads/export.csv")
        self.assertEqual(resp.status_code, 200)

    def test_export_csv_content_type(self):
        resp = get("/api/v1/leads/export.csv")
        self.assertIn("text/csv", resp.headers.get("content-type", ""))

    def test_export_csv_has_header_row(self):
        resp = get("/api/v1/leads/export.csv")
        first_line = resp.text.splitlines()[0] if resp.text else ""
        self.assertIn("job_id", first_line)


class TestSettingsEndpoints(unittest.TestCase):
    def test_get_template_returns_dict(self):
        resp = get("/api/v1/template")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, dict)
        self.assertIn("template", data)

    def test_save_template_too_long(self):
        resp = post("/api/v1/template", json={"template": "x" * 25000})
        self.assertEqual(resp.status_code, 422)

    def test_validate_endpoint_exists(self):
        resp = get("/api/v1/settings/validate")
        self.assertEqual(resp.status_code, 200)

    def test_validate_returns_dict(self):
        resp = get("/api/v1/settings/validate")
        self.assertIsInstance(resp.json(), dict)


class TestFollowupsEndpoint(unittest.TestCase):
    def test_due_followups_returns_list(self):
        resp = get("/api/v1/followups/due")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)


class TestFormReaderEndpoints(unittest.TestCase):
    def test_form_read_not_found(self):
        resp = post(
            "/api/v1/leads/nonexistent/form/read",
            json={"url": "https://example.com/apply"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_form_read_no_url(self):
        from api.dependencies import get_repository

        mock_lead = {
            "job_id": "test-form-001",
            "title": "Engineer",
            "company": "Test Co",
            "url": "",
            "kind": "job",
        }
        fake_repo = types.SimpleNamespace(
            leads=types.SimpleNamespace(get_lead_by_id=lambda _job_id: mock_lead),
            profile=types.SimpleNamespace(get_profile=lambda: {}),
            settings=types.SimpleNamespace(get_settings=lambda: {}),
        )
        app.dependency_overrides[get_repository] = lambda: fake_repo
        try:
            resp = post(
                "/api/v1/leads/test-form-001/form/read",
                json={"url": ""},
            )
        finally:
            app.dependency_overrides.pop(get_repository, None)
        self.assertEqual(resp.status_code, 400)

    def test_identity_endpoint(self):
        resp = get("/api/v1/identity")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("email", resp.json())

    def test_selectors_refresh(self):
        resp = post("/api/v1/selectors/refresh")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("version", data)
        self.assertIn("platforms", data)
        self.assertIsInstance(data["platforms"], list)


class TestPipelineRunEndpoint(unittest.TestCase):
    def test_pipeline_run_not_found(self):
        # With fake db, get_lead_by_id returns {} → route raises 404
        resp = post("/api/v1/leads/nonexistent/pipeline/run")
        self.assertEqual(resp.status_code, 404)

    def test_pipeline_run_valid_id_accepted(self):
        from api.dependencies import get_repository

        mock_lead = {
            "job_id": "test-pipeline-001",
            "title": "Software Engineer",
            "company": "Acme",
            "url": "https://example.com/job/001",
            "description": "Python and FastAPI role.",
            "kind": "job",
        }
        fake_repo = types.SimpleNamespace(
            leads=types.SimpleNamespace(get_lead_by_id=lambda _job_id: mock_lead),
            profile=types.SimpleNamespace(get_profile=lambda: {}),
            settings=types.SimpleNamespace(get_settings=lambda: {}),
        )
        app.dependency_overrides[get_repository] = lambda: fake_repo
        try:
            resp = post("/api/v1/leads/test-pipeline-001/pipeline/run")
        finally:
            app.dependency_overrides.pop(get_repository, None)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("status"), "started")


class TestGenerateEndpoint(unittest.TestCase):
    def test_generate_waits_for_ready_package(self):
        from api.routers import generation

        ready_lead = {
            "job_id": "test-generate-001",
            "resume_asset": "/tmp/resume.pdf",
            "cover_letter_asset": "/tmp/cover.pdf",
        }
        with mock.patch.object(generation, "generate_one", new=mock.AsyncMock(return_value=ready_lead)):
            resp = post("/api/v1/leads/test-generate-001/generate")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["lead"], ready_lead)

    def test_generate_start_returns_before_package_is_ready(self):
        from api.dependencies import get_repository
        from api.routers import generation

        mock_lead = {
            "job_id": "test-generate-start-001",
            "title": "Applied AI Engineer",
            "company": "NimbusWorks",
            "description": "Python and FastAPI role.",
            "kind": "job",
        }
        fake_repo = types.SimpleNamespace(
            leads=types.SimpleNamespace(get_lead_by_id=lambda _job_id: mock_lead),
        )
        generate_mock = mock.AsyncMock(return_value={**mock_lead, "status": "approved"})
        app.dependency_overrides[get_repository] = lambda: fake_repo
        try:
            with mock.patch.object(generation, "generate_one", new=generate_mock):
                resp = post("/api/v1/leads/test-generate-start-001/generate/start")
        finally:
            app.dependency_overrides.pop(get_repository, None)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "started")
        self.assertEqual(resp.json()["job_id"], "test-generate-start-001")
        self.assertEqual(generate_mock.await_count, 1)

    @staticmethod
    def _generation_fixtures(leads_overrides: dict):
        broadcasts = []

        class Manager:
            async def broadcast(self, payload):
                broadcasts.append(payload)

        class JobStore:
            def create(self, *_args, **_kwargs):
                return types.SimpleNamespace(job_id="gen-1")

            def update(self, *_args, **_kwargs):
                return None

        leads_api = {
            "get_lead_by_id": lambda _job_id: {
                "job_id": "job-1",
                "title": "AI Engineer",
                "company": "Acme",
                "description": "Build and operate FastAPI backend services for our internal automation platform, owning data pipelines, API integrations, and reliability work.",
                "source_meta": {},
            },
            "update_lead_status": lambda *_args, **_kwargs: None,
            "save_asset_package": lambda *_args, **_kwargs: None,
            "update_outreach_fields": lambda *_args, **_kwargs: None,
            "save_contact_lookup": lambda *_args, **_kwargs: None,
        }
        leads_api.update(leads_overrides)
        repo = types.SimpleNamespace(
            settings=types.SimpleNamespace(get_setting=lambda *_args, **_kwargs: ""),
            leads=types.SimpleNamespace(**leads_api),
        )
        service = types.SimpleNamespace(
            generate_with_contacts=mock.AsyncMock(return_value=types.SimpleNamespace(
                package={
                    "resume": "resume.pdf",
                    "cover_letter": "cover.pdf",
                    "selected_projects": [],
                    "keyword_coverage": {},
                    "founder_message": "hello",
                },
                contact_lookup={"contacts": []},
            ))
        )
        return Manager(), JobStore(), repo, service, broadcasts

    def test_generate_one_returns_package_when_soft_persistence_steps_fail(self):
        from api.routers import generation

        manager, job_store, repo, service, _broadcasts = self._generation_fixtures({
            "update_outreach_fields": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db locked")),
            "save_contact_lookup": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db locked")),
        })

        lead = asyncio.run(generation.generate_one(
            "job-1",
            manager,
            repo=repo,
            service=service,
            job_store=job_store,
        ))

        self.assertEqual(lead["resume_asset"], "resume.pdf")
        self.assertIn("generation_persistence_errors", lead["source_meta"])

    def test_generate_one_fails_when_asset_package_save_fails(self):
        from fastapi import HTTPException
        from api.routers import generation

        statuses = []
        manager, job_store, repo, service, broadcasts = self._generation_fixtures({
            "save_asset_package": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db locked")),
            "update_lead_status": lambda _job_id, status: statuses.append(status),
        })

        # save_asset_package is the write that makes the generation real; if it
        # fails the endpoint must report failure, not "ready".
        with self.assertRaises(HTTPException):
            asyncio.run(generation.generate_one(
                "job-1",
                manager,
                repo=repo,
                service=service,
                job_store=job_store,
            ))

        self.assertIn("discovered", statuses)  # reverted, not left as approved
        self.assertTrue(any(b.get("event") == "gen_error" for b in broadcasts))

    def test_generate_one_rejects_url_only_lead(self):
        from fastapi import HTTPException
        from api.routers import generation

        broadcasts = []

        class Manager:
            async def broadcast(self, payload):
                broadcasts.append(payload)

        class JobStore:
            def create(self, *_args, **_kwargs):
                return types.SimpleNamespace(job_id="gen-url-only")

            def update(self, *_args, **_kwargs):
                return None

        repo = types.SimpleNamespace(
            settings=types.SimpleNamespace(get_setting=lambda *_args, **_kwargs: ""),
            leads=types.SimpleNamespace(
                get_lead_by_id=lambda _job_id: {
                    "job_id": "url-only",
                    "title": "https://wellfound.com/jobs/4015090-ai-research-data-science-intern",
                    "company": "Wellfound",
                    "url": "https://wellfound.com/jobs/4015090-ai-research-data-science-intern",
                    "description": "https://wellfound.com/jobs/4015090-ai-research-data-science-intern",
                    "source_meta": {"input_url_only": True, "needs_job_description": True},
                },
            ),
        )
        service = types.SimpleNamespace(generate_with_contacts=mock.AsyncMock())

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(generation.generate_one(
                "url-only",
                Manager(),
                repo=repo,
                service=service,
                job_store=JobStore(),
            ))

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(service.generate_with_contacts.await_count, 0)


class TestIngestionEndpoints(unittest.TestCase):
    def test_resume_ingest_accepts_text_upload_and_returns_profile(self):
        from api.routers import ingestion
        from models.schema import C, S

        class FakeProfileService:
            async def ingest_resume(self, raw="", pdf_path=None):
                self.raw = raw
                self.pdf_path = pdf_path
                return C(n="Jane Doe", s="Applied AI engineer", skills=[S(n="Python", cat="technical")])

        fake = FakeProfileService()
        try:
            with mock.patch.object(ingestion, "get_profile_service", return_value=fake):
                resp = CLIENT.post(
                    "/api/v1/ingest",
                    headers=AUTH,
                    files={"file": ("resume.txt", b"name: Jane Doe\nskills: Python", "text/plain")},
                )
        finally:
            pass

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["n"], "Jane Doe")
        self.assertEqual(data["skills"][0]["n"], "Python")
        self.assertTrue(str(fake.pdf_path).endswith(".txt"))

    def test_linkedin_ingest_rejects_non_zip(self):
        resp = CLIENT.post(
            "/api/v1/ingest/linkedin",
            headers=AUTH,
            files={"file": ("resume.txt", b"not a zip", "text/plain")},
        )
        self.assertEqual(resp.status_code, 400)

    def test_linkedin_ingest_rejects_invalid_zip(self):
        resp = CLIENT.post(
            "/api/v1/ingest/linkedin",
            headers=AUTH,
            files={"file": ("export.zip", b"this is not a valid zip file", "application/zip")},
        )
        self.assertEqual(resp.status_code, 422)

    def test_linkedin_ingest_accepts_valid_zip(self):
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("Profile.csv", "First Name,Last Name,Headline,Summary,Geo Location\nTest,User,Engineer,Summary,London")
            zf.writestr("Skills.csv", "Name\nPython\nTypeScript")
            zf.writestr("Positions.csv", "Company Name,Title,Description,Location,Started On,Finished On\nAcme,Engineer,Did things,London,Jan 2023,Present")
        zip_bytes = buf.getvalue()

        resp = CLIENT.post(
            "/api/v1/ingest/linkedin",
            headers=AUTH,
            files={"file": ("export.zip", zip_bytes, "application/zip")},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("stats", data)
        self.assertGreaterEqual(data["stats"]["skills"], 2)

    def test_github_ingest_unknown_user(self):
        import profile.github_ingestor as _gh_mod

        async def _fake_fetch(*args, **kwargs):
            return None

        with mock.patch.object(_gh_mod, "_fetch", side_effect=_fake_fetch):
            resp = post(
                "/api/v1/ingest/github",
                json={"username": "this-user-does-not-exist-jhm-test"},
            )
        self.assertEqual(resp.status_code, 404)

    def test_github_ingest_missing_username(self):
        resp = post("/api/v1/ingest/github", json={"username": ""})
        self.assertNotEqual(resp.status_code, 200)

    def test_github_ingest_unexpected_error_is_not_500(self):
        from api.routers import ingestion

        class FailingProfileService:
            async def ingest_github(self, *_args, **_kwargs):
                raise RuntimeError("github ingest crashed")

        with mock.patch.object(ingestion, "get_profile_service", return_value=FailingProfileService()):
            resp = post("/api/v1/ingest/github", json={"username": "example-candidate"})

        self.assertEqual(resp.status_code, 502)
        self.assertIn("Could not ingest the GitHub profile", resp.json()["detail"])

    def test_profile_import_empty_body(self):
        resp = post("/api/v1/ingest/profile", json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("stats", data)
        self.assertIn("errors", data)

    def test_profile_import_unexpected_error_returns_partial_payload(self):
        from api.routers import ingestion

        class FailingProfileService:
            async def import_profile_data(self, *_args, **_kwargs):
                raise RuntimeError("graph locked")

        with mock.patch.object(ingestion, "get_profile_service", return_value=FailingProfileService()):
            resp = post("/api/v1/ingest/profile", json={})

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "partial")
        self.assertIn("graph locked", data["errors"][0])

    def test_profile_import_valid_skills(self):
        resp = post(
            "/api/v1/ingest/profile",
            json={
                "skills": [
                    {"name": "Python", "category": "language"},
                    {"name": "React", "category": "frontend"},
                ],
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.json()["stats"]["skills"], 0)

    def test_profile_import_skill_name_too_long(self):
        resp = post(
            "/api/v1/ingest/profile",
            json={"skills": [{"name": "x" * 200, "category": "language"}]},
        )
        self.assertEqual(resp.status_code, 422)

    def test_profile_template_endpoint(self):
        resp = get("/api/v1/ingest/profile/template")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), dict)
        self.assertIn("skills", resp.json())

    def test_portfolio_ingest_invalid_url(self):
        resp = post("/api/v1/ingest/portfolio", json={"url": "not-a-url"})
        self.assertEqual(resp.status_code, 400)

    def test_portfolio_ingest_valid_url_structure(self):
        import profile.portfolio_ingestor as _portfolio_mod

        async def _fake_ingest_portfolio_url(_url):
            return {
                "source": "portfolio_url",
                "url": "https://example.com",
                "screenshot_b64": "",
                "candidate": {"name": "", "summary": ""},
                "skills": [],
                "projects": [],
                "achievements": [],
                "experience": [],
                "education": [],
                "certifications": [],
                "stats": {"skills": 0, "projects": 0},
                "error": None,
            }

        with mock.patch.object(
            _portfolio_mod,
            "ingest_portfolio_url",
            side_effect=_fake_ingest_portfolio_url,
        ):
            resp = post(
                "/api/v1/ingest/portfolio",
                json={"url": "https://example.com"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("source"), "portfolio_url")


if __name__ == "__main__":
    unittest.main()
