import ast
import json
import tomllib
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _json(path: Path) -> dict:
    return json.loads(_read(path))


def _handler_catches_exception(handler: ast.ExceptHandler) -> bool:
    node = handler.type
    if node is None:
        return True
    if isinstance(node, ast.Name):
        return node.id == "Exception"
    if isinstance(node, ast.Tuple):
        return any(isinstance(item, ast.Name) and item.id == "Exception" for item in node.elts)
    return False


def _handler_is_observable(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise):
            return True
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in {
                "critical",
                "debug",
                "error",
                "exception",
                "info",
                "warning",
            }:
                return True
            if isinstance(func, ast.Name) and func.id in {"record_error"}:
                return True
    return False


def test_manifest_critical_exception_handlers_are_observable():
    critical_paths = [
        "api/routers/automation.py",
        "api/routers/generation.py",
        "api/routers/leads.py",
        "api/routers/misc.py",
        "automation/actuator.py",
        "automation/selectors.py",
        "automation/service.py",
        "data/graph/profile.py",
        "discovery/quality_gate.py",
        "profile/ingestor.py",
        "profile/service.py",
        "ranking/scoring_engine.py",
        "ranking/semantic.py",
    ]
    issues: list[str] = []
    for rel in critical_paths:
        path = BACKEND / rel
        tree = ast.parse(_read(path), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ExceptHandler)
                and _handler_catches_exception(node)
                and not _handler_is_observable(node)
            ):
                issues.append(f"{rel}:{node.lineno}")

    assert issues == []


def test_high_risk_dependencies_are_compatible_pinned():
    pyproject = tomllib.loads(_read(BACKEND / "pyproject.toml"))
    dependencies = pyproject["project"]["dependencies"]
    by_name = {dep.split("~=", 1)[0].split(">=", 1)[0]: dep for dep in dependencies}
    for package in {
        "anthropic",
        "instructor",
        "kuzu",
        "lancedb",
        "langchain-core",
        "langgraph",
        "openai",
        "sentence-transformers",
    }:
        assert by_name[package].startswith(f"{package}~=")

    dev_deps = "\n".join(pyproject["dependency-groups"]["dev"])
    assert "pytest-cov" in dev_deps
    assert "mypy" in dev_deps
    assert "ruff" in dev_deps


def test_ci_enforces_manifest_guardrails():
    ci = _read(ROOT / ".github/workflows/ci.yml")
    assert "uv sync --dev --frozen" in ci
    assert "uv run ruff check ." in ci
    assert "uv run mypy" in ci
    assert "--cov-fail-under=60" in ci
    assert "npm run lint" in ci
    assert "npm run test:coverage" in ci
    assert "Release smoke" in ci
    assert "npm run release:smoke" in ci
    assert "ubuntu-latest" in ci
    assert "windows-latest" in ci
    assert "macos-latest" in ci


def test_runtime_pack_installs_browser_runtime_for_clean_ci_checkout():
    runtime_pack = _read(ROOT / "scripts/package-runtime-pack.mjs")
    assert "PLAYWRIGHT_BROWSERS_PATH" in runtime_pack
    assert '"playwright", "install", "chromium"' in runtime_pack
    assert "hasChromiumRuntime" in runtime_pack


def test_tauri_relaunch_acl_is_granted():
    for name in ("default.json", "desktop.json"):
        capability = _json(ROOT / "src-tauri" / "capabilities" / name)
        permissions = set(capability["permissions"])
        assert "process:allow-restart" in permissions


def test_release_installer_stays_slim_and_runtime_pack_is_ota_only():
    tauri_config = _json(ROOT / "src-tauri" / "tauri.conf.json")
    bundle = tauri_config["bundle"]
    assert "resources" not in bundle or "resources/sidecar-internal" not in str(bundle["resources"])

    backend_spec = _read(BACKEND / "backend.spec")
    assert "onedir_sidecar = False" in backend_spec

    build_sidecar = _read(ROOT / "scripts/build-sidecar.mjs")
    assert "Release sidecars must be PyInstaller onefile builds" in build_sidecar

    windows_smoke = _read(ROOT / "scripts/smoke-windows-update.mjs")
    assert "Slim installer must not include bundled PyInstaller runtime directory" in windows_smoke
    assert "Missing installed runtime DLL" not in windows_smoke

    release = _read(ROOT / ".github" / "workflows" / "release.yml")
    assert "src-tauri/resources/sidecar-internal/" not in release
    assert "python313.dll" not in release
    assert "base_library.zip" not in release
    assert release.count("path: src-tauri/resources/backend/") == 3


def test_release_includes_frozen_backend_and_windows_smoke():
    release = _read(ROOT / ".github/workflows/release.yml")
    assert "uv sync --dev --frozen" in release
    assert "Smoke packaged Windows sidecar" in release


def test_sidecar_packaging_checks_manifest_and_runtime_path():
    check_sidecar = _read(ROOT / "scripts/check-sidecar.mjs")
    assert "sidecar-manifest.json" in check_sidecar
    assert "platformTriple" in check_sidecar
    assert "sidecarBinaryBytes" in check_sidecar
    assert "minSidecarBytes" in check_sidecar

    tauri_lib = _read(ROOT / "src-tauri/src/lib.rs")
    assert "packaged_sidecar_path" in tauri_lib
    assert "Bundled backend sidecar was not found" in tauri_lib
    assert 'join("resources").join("backend")' in tauri_lib


def test_global_mutable_state_has_locks():
    assert "STABILITY: thread-safe LLM repository singleton" in _read(BACKEND / "llm/client.py")
    assert "STABILITY: thread-safe vector store reconnect/status" in _read(BACKEND / "data/vector/connection.py")
    assert "STABILITY: thread-safe lazy embedding model initialization" in _read(BACKEND / "data/vector/embeddings.py")

    websocket = _read(BACKEND / "api/websocket.py")
    assert "STABILITY: synchronized websocket connection list and bounded fanout" in websocket
    assert "max_connections: int = 50" in websocket

    for rel in ("automation/free_scout.py", "automation/scout.py", "automation/x_scout.py"):
        text = _read(BACKEND / rel)
        assert "STABILITY: thread-safe scout diagnostics snapshot" in text
        assert "def _publish_state" in text


def test_degradation_status_is_exposed_to_api_and_frontend():
    health = _read(BACKEND / "api/routers/health.py")
    assert '"/api/v1/health/subsystems"' in health
    assert "vector_status" in health
    assert "embedding_status" in health

    assert "def vector_status" in _read(BACKEND / "data/vector/connection.py")
    assert "def embedding_status" in _read(BACKEND / "data/vector/embeddings.py")

    app = _read(ROOT / "src/App.tsx")
    css = _read(ROOT / "src/index.css")
    assert "SubsystemBanner" in app
    assert "/api/v1/health/subsystems" in app
    assert ".subsystem-banner" in css
