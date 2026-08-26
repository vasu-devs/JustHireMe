from __future__ import annotations

import platform
from pathlib import Path
from typing import TYPE_CHECKING

from . import env

if TYPE_CHECKING:  # avoids a cycle: tenancy is pure, paths is imported very early
    from .tenancy import TenantContext

APP_DIR_NAME = "JustHireMe"
TAURI_IDENTIFIER = "com.vasudev-siddh.justhireme"

# NOTE on JHM_APP_DATA_DIR defaulting: app_data_dir() below is deliberately a
# *pure* function of the environment (unit tests mock exactly these env vars
# and expect deterministic output — see tests/unit/common/test_app_data_paths.py).
# The "guess the real Tauri directory" fix for a bare `python main.py` (no
# JHM_APP_DATA_DIR from the Rust shell) lives in main.py instead, as a
# one-time startup step that sets JHM_APP_DATA_DIR itself before any other
# module reads it — see main.py's _adopt_tauri_app_data_dir_if_unset(). That
# keeps this module side-effect-free and keeps probing the disk for a
# hardcoded personal path out of a function every test in this file mocks.


def app_data_base_dir() -> Path:
    configured = env.text(env.APP_DATA_BASE_DIR)
    if configured:
        return Path(configured).expanduser()
    system = platform.system().lower()
    if system == "windows":
        return Path(env.text(env.LOCAL_APP_DATA) or Path.home() / "AppData" / "Local").expanduser()
    if system == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(env.text(env.XDG_DATA_HOME) or Path.home() / ".local" / "share").expanduser()


def app_data_dir() -> Path:
    configured = env.text(env.APP_DATA_DIR)
    if configured:
        return Path(configured).expanduser()
    return app_data_base_dir() / APP_DIR_NAME


def app_data_path(*parts: str) -> Path:
    return app_data_dir().joinpath(*parts)


def adopt_tauri_app_data_dir_if_unset() -> Path | None:
    """Adopt an existing desktop data root for standalone backend tooling.

    Tauri passes ``JHM_APP_DATA_DIR`` to the sidecar. Standalone scripts do not,
    so without this explicit one-time adoption they can silently target the
    fallback Local-AppData database instead of the installed desktop database.
    ``app_data_dir`` itself stays a pure function of the environment.
    """
    if configured := env.text(env.APP_DATA_DIR):
        return Path(configured).expanduser()
    system = platform.system().lower()
    if system == "windows":
        base = Path(
            env.text(env.ROAMING_APP_DATA) or Path.home() / "AppData" / "Roaming"
        )
    elif system == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(env.text(env.XDG_DATA_HOME) or Path.home() / ".local" / "share")
    candidate = base.expanduser() / TAURI_IDENTIFIER
    if not (candidate / "crm.db").exists():
        return None
    env.set_value(env.APP_DATA_DIR, str(candidate))
    return candidate


def tenant_data_dir(tenant: TenantContext | None = None) -> Path:
    """Root for stores that isolate by namespace rather than by row.

    Kùzu and LanceDB have no row-level security, so each tenant gets its own
    directory. This is the ONLY place that mapping is made — a path built by
    hand somewhere else is how one tenant ends up reading another's graph.

    The desktop build (single tenant) keeps using the flat app-data directory so
    existing installs are untouched; only the hosted build namespaces.
    """
    from .tenancy import LOCAL_TENANT_ID

    if tenant is None or tenant.tenant_id == LOCAL_TENANT_ID:
        return app_data_dir()
    return app_data_dir() / "tenants" / tenant.namespace


def tenant_data_path(*parts: str, tenant: TenantContext | None = None) -> Path:
    return tenant_data_dir(tenant).joinpath(*parts)
