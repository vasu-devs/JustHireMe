from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path


def test_vector_store_uses_jhm_app_data_dir(monkeypatch, tmp_path):
    calls: list[str] = []

    fake_lancedb = types.SimpleNamespace(
        connect=lambda path: calls.append(path) or types.SimpleNamespace()
    )
    monkeypatch.setitem(sys.modules, "lancedb", fake_lancedb)
    monkeypatch.setenv("JHM_APP_DATA_DIR", str(tmp_path / "roaming-app-data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))

    from data.vector import connection

    module = importlib.reload(connection)

    expected_base = tmp_path / "roaming-app-data" / "JustHireMe"
    expected_vector = expected_base / "vector"
    assert Path(module.BASE_DIR) == expected_base
    assert Path(module.VECTOR_DIR) == expected_vector
    assert Path(calls[-1]) == expected_vector


def test_vector_store_falls_back_to_local_app_data(monkeypatch, tmp_path):
    calls: list[str] = []

    fake_lancedb = types.SimpleNamespace(
        connect=lambda path: calls.append(path) or types.SimpleNamespace()
    )
    monkeypatch.setitem(sys.modules, "lancedb", fake_lancedb)
    monkeypatch.delenv("JHM_APP_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))

    from data.vector import connection

    module = importlib.reload(connection)

    expected_vector = tmp_path / "local-app-data" / "JustHireMe" / "vector"
    assert Path(module.VECTOR_DIR) == expected_vector
    assert Path(calls[-1]) == expected_vector


def test_null_vector_store_reports_disabled_reason():
    from data.vector.connection import NullVectorStore

    vec = NullVectorStore("LanceDB not bundled")

    assert vec.available is False
    assert vec.reason == "LanceDB not bundled"
    assert vec.list_tables() == []


def test_vector_status_reports_disabled_for_null_store(monkeypatch):
    from data.vector import connection

    monkeypatch.setattr(connection, "vec", connection.NullVectorStore("LanceDB not bundled"))

    status = connection.vector_status()

    assert status["status"] == "disabled"
    assert status["error"] == "LanceDB not bundled"


def test_graph_vector_sync_skips_when_store_is_disabled(monkeypatch):
    from data.graph import profile as graph_profile
    from data.vector import connection as vector_connection
    from data.vector.connection import NullVectorStore

    monkeypatch.setattr(vector_connection, "vec", NullVectorStore("LanceDB not bundled"))
    monkeypatch.setattr(
        graph_profile,
        "execute_query",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("graph should not be queried")),
    )

    status = graph_profile.sync_vectors_from_graph()

    assert status == {"status": "disabled", "synced": 0, "error": "LanceDB not bundled"}


def test_vector_runtime_asset_name_is_platform_specific(monkeypatch):
    from data.vector import runtime

    monkeypatch.setattr(runtime, "sys_platform", lambda: "windows")
    assert runtime.vector_runtime_asset_name() == "JustHireMe-vector-runtime-windows.zip"

    monkeypatch.setattr(runtime, "sys_platform", lambda: "darwin")
    assert runtime.vector_runtime_asset_name() == "JustHireMe-vector-runtime-macos.zip"

    monkeypatch.setattr(runtime, "sys_platform", lambda: "linux")
    assert runtime.vector_runtime_asset_name() == "JustHireMe-vector-runtime-linux.zip"


def test_vector_runtime_roots_include_common_site_package_layouts(tmp_path, monkeypatch):
    from data.vector import runtime

    monkeypatch.setenv("JHM_VECTOR_RUNTIME_DIR", str(tmp_path / "vector-runtime"))

    roots = runtime.vector_runtime_roots()

    assert tmp_path / "vector-runtime" in roots
    assert tmp_path / "vector-runtime" / "site-packages" in roots
    assert tmp_path / "vector-runtime" / "Lib" / "site-packages" in roots
