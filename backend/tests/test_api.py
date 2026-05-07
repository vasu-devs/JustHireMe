import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

# ── Must run before any backend module is imported ───────────────────────────
os.environ["LOCALAPPDATA"] = str(Path(__file__).resolve().parent)
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
    sys.modules.setdefault(
        "kuzu",
        types.SimpleNamespace(
            Database=lambda _path: object(),
            Connection=lambda _db: _FakeConnection(),
        ),
    )
    sys.modules["sqlite3"] = types.SimpleNamespace(
        connect=lambda _path: _FakeSqlConnection()
    )
    sys.modules.setdefault(
        "lancedb",
        types.SimpleNamespace(
            LanceDBConnection=_FakeVectorStore,
            connect=lambda _path: _FakeVectorStore(),
        ),
    )


_install_storage_fakes()

# ── Import app and override the randomly-generated token ────────────────────
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

main._API_TOKEN = "test-token-abc123"

from main import app  # noqa: E402  (same cached module, just for IDE clarity)

CLIENT = TestClient(app, raise_server_exceptions=False)
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

    def test_websocket_valid_token_connects(self):
        with CLIENT.websocket_connect("/ws?token=test-token-abc123") as ws:
            msg = ws.receive_json()
        self.assertEqual(msg["type"], "heartbeat")

    def test_websocket_missing_token_closes_without_server_error(self):
        with self.assertRaises(Exception):
            with CLIENT.websocket_connect("/ws"):
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
        # ManualLeadBody all fields have defaults → Pydantic passes
        # handler raises 400 when both text and url are empty strings
        resp = post("/api/v1/leads/manual", json={})
        self.assertEqual(resp.status_code, 400)

    def test_manual_lead_text_too_long(self):
        resp = post("/api/v1/leads/manual", json={"text": "x" * 25000})
        self.assertEqual(resp.status_code, 422)


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


class TestProviderKeyProbe(unittest.IsolatedAsyncioTestCase):
    """Probe should hit /v1/models on each provider (cheap, no inference cost)
    and map auth-failure codes to invalid_key rather than unreachable."""

    async def _probe(self, provider, status_code):
        from main import _probe_provider_key

        captured = {}

        class _FakeResponse:
            def __init__(self, code):
                self.status_code = code

        class _FakeAsyncClient:
            def __init__(self, *_a, **_kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_a):
                return False

            async def get(self, url, headers=None):
                captured["method"] = "GET"
                captured["url"] = url
                captured["headers"] = dict(headers or {})
                return _FakeResponse(status_code)

            async def post(self, *_a, **_kw):
                raise AssertionError("probe must not POST — that costs tokens")

        with mock.patch("httpx.AsyncClient", _FakeAsyncClient):
            result = await _probe_provider_key(provider, "k-test-123")
        return result, captured

    async def test_anthropic_uses_models_endpoint_with_x_api_key(self):
        result, captured = await self._probe("anthropic", 200)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(captured["url"], "https://api.anthropic.com/v1/models")
        self.assertEqual(captured["headers"].get("x-api-key"), "k-test-123")
        self.assertIn("anthropic-version", captured["headers"])

    async def test_openai_uses_models_endpoint_with_bearer(self):
        result, captured = await self._probe("openai", 200)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(captured["url"], "https://api.openai.com/v1/models")
        self.assertEqual(captured["headers"].get("Authorization"), "Bearer k-test-123")

    async def test_groq_uses_openai_compat_models_endpoint(self):
        result, captured = await self._probe("groq", 200)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(captured["url"], "https://api.groq.com/openai/v1/models")

    async def test_deepseek_probe(self):
        result, captured = await self._probe("deepseek", 200)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(captured["url"], "https://api.deepseek.com/v1/models")

    async def test_nvidia_probe(self):
        result, captured = await self._probe("nvidia", 200)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(captured["url"], "https://integrate.api.nvidia.com/v1/models")

    async def test_401_maps_to_invalid_key(self):
        result, _ = await self._probe("anthropic", 401)
        self.assertEqual(result["status"], "invalid_key")

    async def test_403_maps_to_invalid_key(self):
        result, _ = await self._probe("openai", 403)
        self.assertEqual(result["status"], "invalid_key")

    async def test_5xx_maps_to_unreachable(self):
        result, _ = await self._probe("groq", 503)
        self.assertEqual(result["status"], "unreachable")


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
        from db import client as db_client

        mock_lead = {
            "job_id": "test-form-001",
            "title": "Engineer",
            "company": "Test Co",
            "url": "",
            "kind": "job",
        }
        with mock.patch.object(db_client, "get_lead_by_id", return_value=mock_lead):
            resp = post(
                "/api/v1/leads/test-form-001/form/read",
                json={"url": ""},
            )
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
        from db import client as db_client

        mock_lead = {
            "job_id": "test-pipeline-001",
            "title": "Software Engineer",
            "company": "Acme",
            "url": "https://example.com/job/001",
            "description": "Python and FastAPI role.",
            "kind": "job",
        }
        with (
            mock.patch.object(db_client, "get_lead_by_id", return_value=mock_lead),
            mock.patch.object(db_client, "get_profile", return_value={}),
            mock.patch.object(db_client, "get_settings", return_value={}),
        ):
            resp = post("/api/v1/leads/test-pipeline-001/pipeline/run")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("status"), "started")


class TestIngestionEndpoints(unittest.TestCase):
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
        import agents.github_ingestor as _gh_mod

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

    def test_profile_import_empty_body(self):
        resp = post("/api/v1/ingest/profile", json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("stats", data)
        self.assertIn("errors", data)

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
        import agents.portfolio_ingestor as _portfolio_mod

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
