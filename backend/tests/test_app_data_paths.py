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


def test_pdf_renderer_uses_jhm_app_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("JHM_APP_DATA_DIR", str(tmp_path / "roaming-app-data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))

    import generation.pdf_renderer as pdf_renderer

    module = importlib.reload(pdf_renderer)

    assert Path(module._assets) == tmp_path / "roaming-app-data" / "JustHireMe" / "assets"


def test_lead_asset_fallback_uses_jhm_app_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("JHM_APP_DATA_DIR", str(tmp_path / "roaming-app-data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))

    from api.routers import leads

    assert Path(leads.default_assets_dir()) == tmp_path / "roaming-app-data" / "JustHireMe" / "assets"
