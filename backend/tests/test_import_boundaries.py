from __future__ import annotations

import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]

DOMAIN_PACKAGES = {
    "profile",
    "discovery",
    "ranking",
    "generation",
}

PROJECT_PACKAGES = DOMAIN_PACKAGES | {
    "api",
    "automation",
    "contracts",
    "core",
    "data",
    "db",
    "gateway",
    "graph_service",
    "help",
    "llm",
    "main",
    "services",
}

ALLOWED_IMPORTS: dict[str, set[str]] = {
    "api": {"api", "contracts", "core", "data", "gateway", "graph_service", "help", "llm"},
    "automation": {"automation", "core", "data", "discovery", "llm"},
    "data": {"core", "data", "graph_service"},
    "profile": {"automation", "core", "data", "llm", "profile"},
    "discovery": {"automation", "core", "data", "discovery", "llm"},
    "help": {"help", "llm"},
    "llm": {"core", "data", "llm"},
    "ranking": {"core", "data", "llm", "ranking"},
    "generation": {"core", "data", "generation", "llm"},
    "db": {"core", "data", "automation", "ranking"},
    "contracts": {"contracts"},
    "gateway": {"contracts", "core", "data", "gateway"},
    "graph_service": {"core", "data", "graph_service"},
    "services": {"automation", "contracts", "core", "data", "discovery", "generation", "graph_service", "profile", "ranking", "services"},
}

LEGACY_IMPORT_EXCEPTIONS: dict[str, set[str]] = {}


def _project_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in PROJECT_PACKAGES:
                    imports.add(root)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if node.module:
                root = node.module.split(".", 1)[0]
                if root in PROJECT_PACKAGES:
                    imports.add(root)
    return imports


def test_modular_package_import_boundaries_are_explicit():
    violations: list[str] = []
    for package, allowed in ALLOWED_IMPORTS.items():
        for path in (BACKEND_ROOT / package).rglob("*.py"):
            rel = path.relative_to(BACKEND_ROOT).as_posix()
            allowed_for_file = allowed | LEGACY_IMPORT_EXCEPTIONS.get(rel, set())
            imports = _project_imports(path)
            forbidden = imports - allowed_for_file
            if forbidden:
                violations.append(f"{rel}: {', '.join(sorted(forbidden))}")

    assert not violations, "Unexpected cross-boundary imports:\n" + "\n".join(violations)


def test_core_remains_dependency_free_inside_the_project():
    violations = []
    for path in (BACKEND_ROOT / "core").rglob("*.py"):
        imports = _project_imports(path)
        if imports:
            rel = path.relative_to(BACKEND_ROOT).as_posix()
            violations.append(f"{rel}: {', '.join(sorted(imports))}")

    assert not violations, "core/ must not import project packages:\n" + "\n".join(violations)


def test_gateway_clients_do_not_import_domain_packages():
    violations = []
    clients_root = BACKEND_ROOT / "gateway" / "clients"
    for path in clients_root.rglob("*.py"):
        imports = _project_imports(path)
        forbidden = imports & {"automation", "discovery", "generation", "graph_service", "profile", "ranking"}
        if forbidden:
            rel = path.relative_to(BACKEND_ROOT).as_posix()
            violations.append(f"{rel}: {', '.join(sorted(forbidden))}")

    assert not violations, "gateway clients must use contracts, not domain internals:\n" + "\n".join(violations)


def test_services_do_not_import_gateway_or_api():
    violations = []
    for path in (BACKEND_ROOT / "services").rglob("*.py"):
        imports = _project_imports(path)
        forbidden = imports & {"api", "gateway"}
        if forbidden:
            rel = path.relative_to(BACKEND_ROOT).as_posix()
            violations.append(f"{rel}: {', '.join(sorted(forbidden))}")

    assert not violations, "internal services must not import gateway/api:\n" + "\n".join(violations)
