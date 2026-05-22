from __future__ import annotations

import os
import platform
from pathlib import Path

APP_DIR_NAME = "JustHireMe"


def app_data_base_dir() -> Path:
    configured = os.environ.get("JHM_APP_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    system = platform.system().lower()
    if system == "windows":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local").expanduser()
    if system == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share").expanduser()


def app_data_dir() -> Path:
    return app_data_base_dir() / APP_DIR_NAME


def app_data_path(*parts: str) -> Path:
    return app_data_dir().joinpath(*parts)
