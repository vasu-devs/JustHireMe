"""Unit tests for system/runtime.py — optional-runtime status and install jobs.

The payload this builds drives a blocking UI banner, so the ready/required/
restart_required combination has to be exactly right: a wrong `ready` either
hides a broken install or blocks a working app behind a permanent banner.
"""

from __future__ import annotations

import sys
import types

import pytest

from system import runtime


@pytest.fixture(autouse=True)
def _reset_job_state(monkeypatch):
    """Module-level job handles are process-wide; keep tests independent."""
    monkeypatch.setattr(runtime, "_INSTALL_JOB", None, raising=False)
    monkeypatch.setattr(runtime, "_ONNX_DOWNLOAD_JOB", None, raising=False)
    monkeypatch.setattr(runtime, "_LAST_SYNC", None, raising=False)
    monkeypatch.setattr(runtime, "_LAST_ERROR", "", raising=False)
    yield


def _stub_runtime(monkeypatch, *, ready=True, progress=None):
    monkeypatch.setattr(runtime, "vector_runtime_status", lambda: {"ready": ready})
    monkeypatch.setattr(runtime, "vector_runtime_progress", lambda: progress or {"active": False})


def _stub_vector_module(monkeypatch, status):
    module = types.SimpleNamespace(vector_status=lambda refresh=False: status)
    monkeypatch.setitem(sys.modules, "data.vector.connection", module)


# --------------------------------------------------------------- status payload


def test_payload_is_ready_when_the_pack_is_installed_and_loaded(monkeypatch):
    _stub_runtime(monkeypatch, ready=True)
    _stub_vector_module(monkeypatch, {"status": "ok", "tables": []})
    payload = runtime.runtime_payload()
    assert payload["ready"] is True
    assert payload["required"] is False
    assert payload["restart_required"] is False


def test_payload_requires_install_when_the_pack_is_missing(monkeypatch):
    _stub_runtime(monkeypatch, ready=False)
    monkeypatch.delitem(sys.modules, "data.vector.connection", raising=False)
    payload = runtime.runtime_payload()
    assert payload["required"] is True and payload["ready"] is False
    assert payload["vector"]["status"] == "disabled"


def test_restart_required_beats_ready(monkeypatch):
    """A freshly installed pack needs a restart; claiming ready would mislead."""
    _stub_runtime(monkeypatch, ready=True)
    _stub_vector_module(monkeypatch, {"status": "ok", "restart_required": True})
    payload = runtime.runtime_payload()
    assert payload["restart_required"] is True
    assert payload["ready"] is False
    assert payload["required"] is False   # installing again would not help


def test_vector_is_initializing_when_the_pack_is_ready_but_not_yet_imported(monkeypatch):
    _stub_runtime(monkeypatch, ready=True)
    monkeypatch.delitem(sys.modules, "data.vector.connection", raising=False)
    assert runtime.runtime_payload()["vector"]["status"] == "initializing"


def test_a_failing_vector_status_degrades_instead_of_raising(monkeypatch):
    def boom(refresh=False):
        raise RuntimeError("pyo3 already initialised")

    _stub_runtime(monkeypatch, ready=True)
    monkeypatch.setitem(sys.modules, "data.vector.connection", types.SimpleNamespace(vector_status=boom))
    vector = runtime.runtime_payload()["vector"]
    assert vector["status"] == "degraded" and "pyo3" in vector["error"]


def test_payload_reports_a_recorded_install_error(monkeypatch):
    _stub_runtime(monkeypatch, ready=False)
    monkeypatch.setattr(runtime, "_LAST_ERROR", "download failed", raising=False)
    assert runtime.runtime_payload()["install_error"] == "download failed"


def test_payload_carries_the_last_sync_result(monkeypatch):
    _stub_runtime(monkeypatch, ready=True)
    _stub_vector_module(monkeypatch, {"status": "ok"})
    monkeypatch.setattr(runtime, "_LAST_SYNC", {"status": "ok", "synced": 7}, raising=False)
    assert runtime.runtime_payload()["sync"] == {"status": "ok", "synced": 7}


def test_progress_reports_active_while_a_job_runs(monkeypatch):
    _stub_runtime(monkeypatch, ready=False, progress={"active": False, "percent": 10})
    monkeypatch.setattr(runtime, "_job_running", lambda: True)
    assert runtime.runtime_payload()["progress"]["active"] is True


# ------------------------------------------------------------- embedding provider


@pytest.mark.parametrize("requested, stored", [
    ("onnx", "onnx"), ("openai", "openai"), ("hash", "hash"),
    ("ONNX", "onnx"), ("  openai  ", "openai"),
    ("nonsense", "onnx"),        # unknown values fall back, never persist junk
    ("", "onnx"),
])
def test_set_embedding_provider_normalises_the_value(requested, stored, monkeypatch):
    saved: dict = {}
    monkeypatch.setattr("data.sqlite.settings.get_settings", lambda: {"embedding_provider": "onnx"})
    monkeypatch.setattr("data.sqlite.settings.save_settings", lambda payload: saved.update(payload))
    monkeypatch.setattr("data.vector.embeddings.reset_onnx_session", lambda: None)
    monkeypatch.setattr("data.vector.embeddings.embedding_status", lambda: {"mode": stored})
    monkeypatch.setattr(runtime, "spawn_vector_resync", lambda: None)

    runtime.set_embedding_provider(requested)
    assert saved["embedding_provider"] == stored


def test_changing_provider_triggers_a_vector_resync(monkeypatch):
    """A new provider almost always changes the dimension, invalidating the tables."""
    resync = {"called": False}
    monkeypatch.setattr("data.sqlite.settings.get_settings", lambda: {"embedding_provider": "onnx"})
    monkeypatch.setattr("data.sqlite.settings.save_settings", lambda payload: None)
    monkeypatch.setattr("data.vector.embeddings.reset_onnx_session", lambda: None)
    monkeypatch.setattr("data.vector.embeddings.embedding_status", lambda: {})
    monkeypatch.setattr(runtime, "spawn_vector_resync", lambda: resync.update(called=True))

    runtime.set_embedding_provider("openai")
    assert resync["called"] is True


def test_reselecting_the_same_provider_does_not_resync(monkeypatch):
    resync = {"called": False}
    monkeypatch.setattr("data.sqlite.settings.get_settings", lambda: {"embedding_provider": "onnx"})
    monkeypatch.setattr("data.sqlite.settings.save_settings", lambda payload: None)
    monkeypatch.setattr("data.vector.embeddings.reset_onnx_session", lambda: None)
    monkeypatch.setattr("data.vector.embeddings.embedding_status", lambda: {})
    monkeypatch.setattr(runtime, "spawn_vector_resync", lambda: resync.update(called=True))

    runtime.set_embedding_provider("onnx")
    assert resync["called"] is False


# ------------------------------------------------------------------ onnx download


def test_onnx_download_reports_already_running(monkeypatch):
    monkeypatch.setattr(runtime, "_onnx_download_running", lambda: True)
    monkeypatch.setattr("data.vector.embeddings.embedding_status", lambda: {"mode": "hashing"})
    result = runtime.download_onnx_model()
    assert result["status"] == "already_running"


def test_onnx_download_starts_a_background_job(monkeypatch):
    started: dict = {}

    class FakeThread:
        def __init__(self, target=None, name=None, daemon=None):
            started["target"] = target

        def start(self):
            started["started"] = True

    monkeypatch.setattr(runtime, "_onnx_download_running", lambda: False)
    monkeypatch.setattr("data.vector.embeddings.embedding_status", lambda: {"mode": "hashing"})
    monkeypatch.setattr(runtime.threading, "Thread", FakeThread)

    result = runtime.download_onnx_model()
    assert result["status"] == "downloading" and started["started"] is True


def test_a_successful_onnx_download_resyncs_vectors(monkeypatch):
    """hash -> onnx keeps the same 384 dims, so nothing else would trigger a rebuild."""
    captured: dict = {}
    resync = {"called": False}

    class FakeThread:
        def __init__(self, target=None, name=None, daemon=None):
            captured["target"] = target

        def start(self):
            captured["target"]()      # run the worker inline

    monkeypatch.setattr(runtime, "_onnx_download_running", lambda: False)
    monkeypatch.setattr("data.vector.embeddings.embedding_status", lambda: {})
    monkeypatch.setattr("data.vector.embeddings.download_onnx_model", lambda: {"status": "ok"})
    monkeypatch.setattr("data.vector.embeddings.reset_onnx_session", lambda: None)
    monkeypatch.setattr(runtime, "spawn_vector_resync", lambda: resync.update(called=True))
    monkeypatch.setattr(runtime.threading, "Thread", FakeThread)

    runtime.download_onnx_model()
    assert resync["called"] is True


def test_a_failed_onnx_download_does_not_resync(monkeypatch):
    captured: dict = {}
    resync = {"called": False}

    class FakeThread:
        def __init__(self, target=None, name=None, daemon=None):
            captured["target"] = target

        def start(self):
            captured["target"]()

    monkeypatch.setattr(runtime, "_onnx_download_running", lambda: False)
    monkeypatch.setattr("data.vector.embeddings.embedding_status", lambda: {})
    monkeypatch.setattr("data.vector.embeddings.download_onnx_model", lambda: {"status": "error"})
    monkeypatch.setattr("data.vector.embeddings.reset_onnx_session", lambda: None)
    monkeypatch.setattr(runtime, "spawn_vector_resync", lambda: resync.update(called=True))
    monkeypatch.setattr(runtime.threading, "Thread", FakeThread)

    runtime.download_onnx_model()
    assert resync["called"] is False


# ------------------------------------------------------------------ install job


def test_ensure_install_job_is_idempotent_while_running(monkeypatch):
    spawned = {"count": 0}

    class FakeThread:
        def __init__(self, *a, **k):
            pass

        def start(self):
            spawned["count"] += 1

        def is_alive(self):
            return True

    monkeypatch.setattr(runtime.threading, "Thread", FakeThread)
    runtime.ensure_install_job()
    runtime.ensure_install_job()   # a second click must not spawn a second install
    assert spawned["count"] == 1


def test_install_worker_records_a_failure_instead_of_raising(monkeypatch):
    def boom():
        raise RuntimeError("disk full")

    monkeypatch.setattr(runtime, "_install_and_refresh", boom)
    runtime._install_worker()
    assert runtime._LAST_ERROR == "disk full"
