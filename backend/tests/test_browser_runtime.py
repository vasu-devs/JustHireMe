"""Tests for cross-platform browser fallback paths and runtime pack version stamping."""
from __future__ import annotations

import logging
import os
import types
from pathlib import Path
from unittest.mock import patch


# ── Browser fallback tests ────────────────────────────────────────────────


def test_system_browser_candidates_returns_windows_paths_on_windows(monkeypatch):
    from automation import browser_runtime

    monkeypatch.setattr(browser_runtime, "sys_platform", lambda: "windows")
    candidates = browser_runtime._system_browser_candidates()

    assert any("chrome.exe" in c for c in candidates)
    assert any("msedge.exe" in c for c in candidates)
    assert any("brave.exe" in c for c in candidates)
    assert all("\\" in c or "/" not in c for c in candidates)


def test_system_browser_candidates_returns_macos_paths_on_darwin(monkeypatch):
    from automation import browser_runtime

    monkeypatch.setattr(browser_runtime, "sys_platform", lambda: "darwin")
    candidates = browser_runtime._system_browser_candidates()

    assert any("Google Chrome" in c for c in candidates)
    assert any("Microsoft Edge" in c for c in candidates)
    assert any("Brave Browser" in c for c in candidates)
    assert any("Chromium.app" in c for c in candidates)
    assert any("/Applications/" in c for c in candidates)


def test_system_browser_candidates_returns_linux_paths_on_linux(monkeypatch):
    from automation import browser_runtime

    monkeypatch.setattr(browser_runtime, "sys_platform", lambda: "linux")
    candidates = browser_runtime._system_browser_candidates()

    assert "/usr/bin/google-chrome" in candidates
    assert "/usr/bin/chromium" in candidates
    assert "/usr/bin/chromium-browser" in candidates
    assert "/usr/bin/microsoft-edge" in candidates
    assert "/usr/bin/brave-browser" in candidates
    assert "/snap/bin/chromium" in candidates


def test_chromium_executable_finds_linux_chrome(monkeypatch, tmp_path):
    from automation import browser_runtime

    chrome = tmp_path / "google-chrome"
    chrome.write_text("#!/bin/sh\n")

    monkeypatch.setattr(browser_runtime, "sys_platform", lambda: "linux")
    monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "")
    monkeypatch.setattr(browser_runtime, "_runtime_chromium_executable", lambda: None)
    monkeypatch.setattr(
        browser_runtime,
        "_system_browser_candidates",
        lambda: [str(chrome)],
    )

    result = browser_runtime.chromium_executable()
    assert result == str(chrome)


def test_chromium_executable_finds_macos_chrome(monkeypatch, tmp_path):
    from automation import browser_runtime

    chrome = tmp_path / "Google Chrome"
    chrome.write_text("#!/bin/sh\n")

    monkeypatch.setattr(browser_runtime, "sys_platform", lambda: "darwin")
    monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "")
    monkeypatch.setattr(browser_runtime, "_runtime_chromium_executable", lambda: None)
    monkeypatch.setattr(
        browser_runtime,
        "_system_browser_candidates",
        lambda: [str(chrome)],
    )

    result = browser_runtime.chromium_executable()
    assert result == str(chrome)


def test_chromium_executable_returns_none_when_nothing_exists(monkeypatch):
    from automation import browser_runtime

    monkeypatch.setattr(browser_runtime, "sys_platform", lambda: "linux")
    monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "")
    monkeypatch.setattr(browser_runtime, "_runtime_chromium_executable", lambda: None)
    monkeypatch.setattr(
        browser_runtime,
        "_system_browser_candidates",
        lambda: ["/does/not/exist/chrome", "/also/missing/chromium"],
    )

    result = browser_runtime.chromium_executable()
    assert result is None


def test_chromium_executable_prefers_env_var_over_system(monkeypatch, tmp_path):
    from automation import browser_runtime

    env_chrome = tmp_path / "env-chrome"
    env_chrome.write_text("#!/bin/sh\n")
    sys_chrome = tmp_path / "sys-chrome"
    sys_chrome.write_text("#!/bin/sh\n")

    monkeypatch.setattr(browser_runtime, "sys_platform", lambda: "linux")
    monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", str(env_chrome))
    monkeypatch.setattr(browser_runtime, "_runtime_chromium_executable", lambda: None)
    monkeypatch.setattr(
        browser_runtime,
        "_system_browser_candidates",
        lambda: [str(sys_chrome)],
    )

    result = browser_runtime.chromium_executable()
    assert result == str(env_chrome)


# ── Runtime pack version stamp tests ──────────────────────────────────────


def test_version_stamp_written_and_read(monkeypatch, tmp_path):
    from data.vector import runtime

    monkeypatch.setattr(runtime, "_data_root", lambda: tmp_path)
    monkeypatch.setattr(runtime, "_app_version", lambda: "1.0.31")

    runtime._write_version_stamp()

    stamp_path = tmp_path / "runtime-pack-version"
    assert stamp_path.exists()
    assert stamp_path.read_text(encoding="utf-8").strip() == "1.0.31"
    assert runtime._installed_runtime_version() == "1.0.31"


def test_runtime_pack_stale_when_versions_differ(monkeypatch, tmp_path):
    from data.vector import runtime

    monkeypatch.setattr(runtime, "_data_root", lambda: tmp_path)

    # Write stamp for old version
    monkeypatch.setattr(runtime, "_app_version", lambda: "1.0.30")
    runtime._write_version_stamp()

    # Now app is at 1.0.31
    monkeypatch.setattr(runtime, "_app_version", lambda: "1.0.31")
    assert runtime._runtime_pack_is_stale() is True


def test_runtime_pack_not_stale_when_versions_match(monkeypatch, tmp_path):
    from data.vector import runtime

    monkeypatch.setattr(runtime, "_data_root", lambda: tmp_path)
    monkeypatch.setattr(runtime, "_app_version", lambda: "1.0.31")
    runtime._write_version_stamp()

    assert runtime._runtime_pack_is_stale() is False


def test_runtime_pack_not_stale_without_app_version(monkeypatch, tmp_path):
    """Dev mode: no JHM_APP_VERSION set, never stale."""
    from data.vector import runtime

    monkeypatch.setattr(runtime, "_data_root", lambda: tmp_path)
    monkeypatch.setattr(runtime, "_app_version", lambda: "")

    assert runtime._runtime_pack_is_stale() is False


def test_runtime_pack_not_stale_on_first_install(monkeypatch, tmp_path):
    """First install: no stamp file exists, not considered stale."""
    from data.vector import runtime

    monkeypatch.setattr(runtime, "_data_root", lambda: tmp_path)
    monkeypatch.setattr(runtime, "_app_version", lambda: "1.0.31")

    assert runtime._runtime_pack_is_stale() is False


def test_vector_runtime_status_reports_stale(monkeypatch, tmp_path):
    from data.vector import runtime

    monkeypatch.setattr(runtime, "_data_root", lambda: tmp_path)
    monkeypatch.setattr(runtime, "vector_runtime_dir", lambda: tmp_path / "vr")
    monkeypatch.setattr(runtime, "browser_runtime_dir", lambda: tmp_path / "br")

    # Write old stamp
    monkeypatch.setattr(runtime, "_app_version", lambda: "1.0.30")
    runtime._write_version_stamp()
    monkeypatch.setattr(runtime, "_app_version", lambda: "1.0.31")

    status = runtime.vector_runtime_status()

    assert status["stale"] is True
    assert status["status"] == "stale"
    assert status["installed_version"] == "1.0.30"
    assert status["app_version"] == "1.0.31"


# ── Runtime pack content-version tests ────────────────────────────────────


def test_expected_version_prefers_runtime_pack_env(monkeypatch):
    """JHM_RUNTIME_PACK_VERSION (content version) wins over the app version."""
    from data.vector import runtime

    monkeypatch.setattr(runtime, "_app_version", lambda: "1.0.40")
    monkeypatch.setenv("JHM_RUNTIME_PACK_VERSION", "rt-abc123")

    assert runtime._expected_runtime_pack_version() == "rt-abc123"


def test_expected_version_falls_back_to_app_version(monkeypatch):
    """No content version env set → behave exactly as before (key off app version)."""
    from data.vector import runtime

    monkeypatch.delenv("JHM_RUNTIME_PACK_VERSION", raising=False)
    monkeypatch.setattr(runtime, "_app_version", lambda: "1.0.40")

    assert runtime._expected_runtime_pack_version() == "1.0.40"


def test_runtime_pack_not_stale_across_app_update_when_content_unchanged(monkeypatch, tmp_path):
    """The core fix: an app update must NOT re-download a pack whose content is unchanged."""
    from data.vector import runtime

    monkeypatch.setattr(runtime, "_data_root", lambda: tmp_path)
    monkeypatch.setattr(runtime, "_app_version", lambda: "1.0.31")
    monkeypatch.setenv("JHM_RUNTIME_PACK_VERSION", "rt-abc123")
    runtime._write_version_stamp()

    # App bumps to a new release, but the runtime pack content is identical.
    monkeypatch.setattr(runtime, "_app_version", lambda: "1.0.40")
    monkeypatch.setenv("JHM_RUNTIME_PACK_VERSION", "rt-abc123")

    assert runtime._installed_runtime_version() == "rt-abc123"
    assert runtime._runtime_pack_is_stale() is False


def test_runtime_pack_stale_when_content_version_changes(monkeypatch, tmp_path):
    """A pack whose pinned contents changed (Chromium bump, dep bump) is stale."""
    from data.vector import runtime

    monkeypatch.setattr(runtime, "_data_root", lambda: tmp_path)
    monkeypatch.setattr(runtime, "_app_version", lambda: "1.0.31")
    monkeypatch.setenv("JHM_RUNTIME_PACK_VERSION", "rt-abc123")
    runtime._write_version_stamp()

    # New build pins a newer Chromium → new content version.
    monkeypatch.setenv("JHM_RUNTIME_PACK_VERSION", "rt-def456")

    assert runtime._runtime_pack_is_stale() is True


# ── NullVectorStore logging tests ─────────────────────────────────────────


def test_null_vector_store_logs_create_table(caplog):
    from data.vector.connection import NullVectorStore

    store = NullVectorStore("test: not bundled")

    with caplog.at_level(logging.WARNING, logger="data.vector.null"):
        result = store.create_table("skills", data=[{"id": "1"}])

    assert result is None
    assert "create_table(skills)" in caplog.text
    assert "data dropped" in caplog.text
    assert "not bundled" in caplog.text


def test_null_vector_store_logs_add(caplog):
    from data.vector.connection import NullVectorStore

    store = NullVectorStore("test: not bundled")

    with caplog.at_level(logging.WARNING, logger="data.vector.null"):
        result = store.add([{"id": "1"}])

    assert result is None
    assert "add()" in caplog.text
    assert "data dropped" in caplog.text


def test_null_vector_store_logs_open_table(caplog):
    from data.vector.connection import NullVectorStore

    store = NullVectorStore("test: not bundled")

    with caplog.at_level(logging.WARNING, logger="data.vector.null"):
        result = store.open_table("skills")

    assert result is store  # Returns self
    assert "open_table(skills)" in caplog.text


def test_null_vector_store_logs_list_tables(caplog):
    from data.vector.connection import NullVectorStore

    store = NullVectorStore("test: not bundled")

    with caplog.at_level(logging.WARNING, logger="data.vector.null"):
        result = store.list_tables()

    assert result == []
    assert "list_tables" in caplog.text


def test_null_vector_store_has_delete_method(caplog):
    from data.vector.connection import NullVectorStore

    store = NullVectorStore("test: not bundled")

    with caplog.at_level(logging.WARNING, logger="data.vector.null"):
        result = store.delete("id = '1'")

    assert result is None
    assert "delete()" in caplog.text
