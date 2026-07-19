"""The frozen sidecar must bundle every backend package.

PyInstaller only follows STATIC imports; this repo's architecture reaches
domain packages through import_module() (api.dependencies._local_service), so
each package must be explicitly collected in backend.spec. The `learning`
package shipped MISSING this way — startup passed, and the Learn endpoint
500'd with ModuleNotFoundError only in the installed app. This test makes an
unregistered package a unit-test failure instead of a field bug.
"""

from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SPEC = (BACKEND_ROOT / "backend.spec").read_text(encoding="utf-8")

# Not shipped inside the sidecar binary on purpose.
NOT_BUNDLED = {"tests", "evals"}


def _backend_packages() -> list[str]:
    return sorted(
        entry.name
        for entry in BACKEND_ROOT.iterdir()
        if entry.is_dir()
        and (entry / "__init__.py").exists()
        and entry.name not in NOT_BUNDLED
        and not entry.name.startswith((".", "_"))
    )


def test_every_backend_package_is_collected_into_the_frozen_sidecar() -> None:
    packages = _backend_packages()
    assert packages, "no backend packages found next to backend.spec"
    missing = [
        package
        for package in packages
        if f'collect_submodules("{package}")' not in SPEC and f'"{package}"' not in SPEC
    ]
    assert not missing, (
        "backend.spec does not collect these packages - the frozen sidecar "
        f"will die with ModuleNotFoundError at whatever route first imports them: {missing}. "
        'Add collect_submodules("<name>") to the hidden imports in backend.spec.'
    )
