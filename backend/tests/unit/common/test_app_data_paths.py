from __future__ import annotations

import importlib
from pathlib import Path


def test_app_data_dir_uses_xdg_data_home_on_linux(monkeypatch, tmp_path):
    from core import paths

    monkeypatch.delenv("JHM_APP_DATA_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setattr(paths.platform, "system", lambda: "Linux")

    assert paths.app_data_dir() == tmp_path / "xdg-data" / "JustHireMe"


def test_app_data_dir_uses_application_support_on_macos(monkeypatch, tmp_path):
    from core import paths

    home = tmp_path / "home"
    monkeypatch.delenv("JHM_APP_DATA_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(paths.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(paths.Path, "home", lambda: home)

    assert paths.app_data_dir() == home / "Library" / "Application Support" / "JustHireMe"


def test_app_data_dir_uses_jhm_app_data_dir_as_exact_root(monkeypatch, tmp_path):
    from core import paths

    app_root = tmp_path / "portable" / "JustHireMe"
    monkeypatch.setenv("JHM_APP_DATA_DIR", str(app_root))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))

    assert paths.app_data_dir() == app_root


def test_app_data_dir_can_use_explicit_base_dir(monkeypatch, tmp_path):
    from core import paths

    monkeypatch.delenv("JHM_APP_DATA_DIR", raising=False)
    monkeypatch.setenv("JHM_APP_DATA_BASE_DIR", str(tmp_path / "portable-base"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))

    assert paths.app_data_dir() == tmp_path / "portable-base" / "JustHireMe"


def test_standalone_tool_adopts_existing_windows_tauri_data_root(monkeypatch, tmp_path):
    from core import paths

    roaming = tmp_path / "roaming"
    desktop_root = roaming / paths.TAURI_IDENTIFIER
    desktop_root.mkdir(parents=True)
    (desktop_root / "crm.db").touch()
    monkeypatch.delenv("JHM_APP_DATA_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setattr(paths.platform, "system", lambda: "Windows")

    assert paths.adopt_tauri_app_data_dir_if_unset() == desktop_root
    assert paths.app_data_dir() == desktop_root


def test_standalone_tool_does_not_override_explicit_data_root(monkeypatch, tmp_path):
    from core import paths

    configured = tmp_path / "portable"
    monkeypatch.setenv("JHM_APP_DATA_DIR", str(configured))

    assert paths.adopt_tauri_app_data_dir_if_unset() == configured
    assert paths.app_data_dir() == configured


def test_pdf_renderer_uses_jhm_app_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("JHM_APP_DATA_DIR", str(tmp_path / "roaming-app-data" / "JustHireMe"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))

    import generation.pdf_renderer as pdf_renderer

    module = importlib.reload(pdf_renderer)

    assert Path(module._assets) == tmp_path / "roaming-app-data" / "JustHireMe" / "assets"


def test_lead_asset_fallback_uses_jhm_app_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("JHM_APP_DATA_DIR", str(tmp_path / "roaming-app-data" / "JustHireMe"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))

    from leads import service as lead_service

    assert Path(lead_service.default_assets_dir()) == tmp_path / "roaming-app-data" / "JustHireMe" / "assets"
