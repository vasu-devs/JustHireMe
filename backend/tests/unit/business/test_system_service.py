"""Unit tests for system/ — subsystem probes, diagnostics, runtime state.

The probes must never raise: a health endpoint that 500s tells the user nothing
about which subsystem is actually broken.
"""

from __future__ import annotations

import types

import pytest

from system import health
from system.service import SystemService


def _repo(*, leads=None, graph_ok=True, profile=None, settings=None, explode=None):
    class Leads:
        def get_all_leads(self):
            if explode == "sqlite":
                raise RuntimeError("database is locked")
            return leads if leads is not None else []

    class Graph:
        def graph_available(self):
            return graph_ok

        def graph_counts(self):
            return {"skill": 3}

        def graph_error(self):
            return "" if graph_ok else "kuzu locked"

    class Profile:
        def get_profile(self):
            if explode == "profile":
                raise RuntimeError("graph unavailable")
            return profile if profile is not None else {}

    class Settings:
        def get_settings(self):
            return settings or {}

        def get_setting(self, key, default=""):
            return (settings or {}).get(key, default)

    return types.SimpleNamespace(leads=Leads(), graph=Graph(), profile=Profile(), settings=Settings())


# ---------------------------------------------------------------------- probes


def test_check_sqlite_reports_the_lead_count():
    assert health.check_sqlite(_repo(leads=[1, 2, 3])) == {"status": "ok", "lead_count": 3}


def test_check_sqlite_reports_an_error_instead_of_raising():
    result = health.check_sqlite(_repo(explode="sqlite"))
    assert result["status"] == "error" and "locked" in result["error"]


def test_check_graph_surfaces_the_reason_when_unavailable():
    result = health.check_graph(_repo(graph_ok=False))
    assert result["status"] == "error" and result["error"] == "kuzu locked"
    assert result["counts"] == {"skill": 3}


def test_check_graph_is_ok_when_available():
    assert health.check_graph(_repo())["status"] == "ok"


@pytest.mark.parametrize("profile, expected", [
    ({"n": "Ada"}, True),
    ({"skills": ["Python"]}, True),
    ({"projects": [{"title": "x"}]}, True),
    ({}, False),
    ({"n": "", "skills": []}, False),
])
def test_check_profile_detects_whether_anything_was_imported(profile, expected):
    assert health.check_profile(_repo(profile=profile))["has_profile"] is expected


def test_check_profile_reports_an_error_instead_of_raising():
    assert health.check_profile(_repo(explode="profile"))["status"] == "error"


def test_check_embeddings_never_raises(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "data.vector.embeddings", None)
    assert health.check_embeddings()["status"] in {"unavailable", "ok", "degraded", "hashing"}


def test_embedding_mode_falls_back_to_unknown(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "data.vector.embeddings", None)
    assert health.embedding_mode() == "unknown"


# ------------------------------------------------------------- status mapping


@pytest.mark.parametrize("raw, expected", [
    ("ok", "ok"),
    ("missing_key", "unavailable"),
    ("disabled", "unavailable"),
    ("error", "unavailable"),
    ("unavailable", "unavailable"),
    ("initializing", "degraded"),
    ("anything-else", "degraded"),
])
def test_as_subsystem_status_normalises_the_vocabulary(raw, expected):
    assert health.as_subsystem_status("vector", {"status": raw})["status"] == expected


def test_as_subsystem_status_explains_a_missing_llm_key():
    result = health.as_subsystem_status("llm", {"status": "missing_key"})
    assert result["error"] == "LLM API key is not configured"


def test_as_subsystem_status_keeps_extra_detail_but_not_status_or_error():
    result = health.as_subsystem_status("vector", {"status": "ok", "tables": ["skills"], "reason": "x"})
    assert result["tables"] == ["skills"]
    assert "reason" not in result


# --------------------------------------------------------------------- service


@pytest.mark.asyncio
async def test_liveness_reports_uptime_and_a_timestamp():
    import time

    result = await SystemService(_repo()).liveness(time.monotonic() - 5)
    assert result["status"] == "alive"
    assert result["uptime_seconds"] >= 5
    assert result["timestamp"].endswith("+00:00")


@pytest.mark.asyncio
async def test_component_checks_cover_every_subsystem():
    checks = await SystemService(_repo()).component_checks()
    assert set(checks) == {"sqlite", "graph", "vector", "profile", "llm"}


@pytest.mark.asyncio
async def test_subsystems_returns_normalised_statuses():
    result = await SystemService(_repo()).subsystems()
    assert set(result) == {"graph", "vector", "llm", "embeddings"}
    assert all("status" in entry for entry in result.values())


@pytest.mark.asyncio
async def test_diagnostics_reports_version_uptime_and_embedding_mode():
    import time

    result = await SystemService(_repo()).diagnostics(time.monotonic())
    for key in ("top_errors", "error_count_24h", "metrics", "embedding_mode", "version", "uptime_seconds"):
        assert key in result


@pytest.mark.asyncio
async def test_record_frontend_error_bounds_every_field(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr("system.service.log_error", lambda msg, ctx: captured.update(msg=msg, ctx=ctx))
    monkeypatch.setattr("system.service.redact_sensitive", lambda payload: payload)
    monkeypatch.setattr("system.service.redact_text", lambda text: text)

    await SystemService(_repo()).record_frontend_error({
        "error": "x" * 5000,
        "componentStack": "y" * 20000,
        "url": "u" * 3000,
        "userAgent": "a" * 2000,
    })

    frontend = captured["ctx"]["frontend"]
    assert len(frontend["error"]) == 2000
    assert len(frontend["componentStack"]) == 8000
    assert len(frontend["url"]) == 1000
    assert len(frontend["userAgent"]) == 500


@pytest.mark.asyncio
async def test_record_frontend_error_defaults_a_missing_message(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr("system.service.log_error", lambda msg, ctx: captured.update(msg=msg))
    monkeypatch.setattr("system.service.redact_sensitive", lambda payload: payload)
    monkeypatch.setattr("system.service.redact_text", lambda text: text)
    await SystemService(_repo()).record_frontend_error({})
    assert captured["msg"] == "Frontend error"


@pytest.mark.asyncio
async def test_last_scan_finished_at_reads_the_setting():
    repo = _repo(settings={"last_scan_finished_at": "2026-08-02T00:00:00Z"})
    assert await SystemService(repo).last_scan_finished_at() == "2026-08-02T00:00:00Z"
