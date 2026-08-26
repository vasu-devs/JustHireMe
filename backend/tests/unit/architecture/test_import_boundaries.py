"""Executable definition of the layered architecture (see docs/LAYERS.md).

Layer rule, top to bottom — a package may import its own layer and any layer
BELOW it, never above:

    SERVICE   api/            transport only: HTTP in, JSON out
    BUSINESS  profile/ discovery/ ranking/ generation/ automation/
              learning/ help/ graph_service/ gateway/
    DATA      data/ models/    SQLite, Kùzu, LanceDB, filesystem
    COMMON    core/           config, constants, types, errors, paths

``llm/`` is an outbound service adapter: business may call it, it may not call
business back.
"""

from __future__ import annotations

import ast
from pathlib import Path
from paths import BACKEND_ROOT



# One entry per layer. Every project package must appear in exactly one.
LAYERS: dict[str, set[str]] = {
    "service": {"api"},
    "business": {
        "automation",
        "catalog",
        "discovery",
        "gateway",
        "generation",
        "graph_service",
        "help",
        "leads",
        "learning",
        "reporting",
        "settings",
        "system",
        "templates",
        "profile",
        "opportunities",
        "ranking",
        "services",
    },
    "adapter": {"llm"},
    "data": {"data", "models"},
    "common": {"core", "ports"},
}

DOMAIN_PACKAGES = {
    "catalog",
    "profile",
    "discovery",
    "opportunities",
    "ranking",
    "generation",
}

PROJECT_PACKAGES = DOMAIN_PACKAGES | {
    "api",
    "ports",
    "automation",
    "core",
    "leads",
    "settings",
    "system",
    "templates",
    "data",
    "gateway",
    "graph_service",
    "help",
    "learning",
    "llm",
    "main",
    "reporting",
    "services",
}

ALLOWED_IMPORTS: dict[str, set[str]] = {
    # The API layer may call any business package (that is the flow), plus core.
    # `data` is allowed ONLY for the composition root + api infra — routers are
    # held to the stricter rule in test_routers_never_reach_past_the_business_layer.
    "api": {"ports", "api", "core", "data", *LAYERS["business"], "llm"},
    "automation": {"ports", "automation", "core", "data", "discovery", "gateway", "generation", "llm", "ranking"},
    "catalog": {"ports", "catalog", "core", "discovery", "opportunities"},
    "data": {"ports", "core", "data"},
    "profile": {"ports", "automation", "core", "data", "llm", "profile"},
    "discovery": {"ports", "automation", "core", "data", "discovery", "gateway", "llm", "ranking"},
    "help": {"ports", "help", "llm"},
    "leads": {"ports", "core", "data", "gateway", "leads", "ranking"},
    "learning": {"ports", "core", "data", "discovery", "learning", "ranking"},
    "opportunities": {"ports", "catalog", "core", "data", "discovery", "opportunities"},
    "reporting": {"ports", "core", "data", "leads", "reporting"},
    "settings": {"ports", "core", "data", "llm", "settings"},
    "system": {"ports", "core", "data", "graph_service", "llm", "system"},
    "templates": {"ports", "core", "data", "templates"},
    "llm": {"ports", "core", "data", "llm"},
    "ranking": {"ports", "core", "data", "llm", "ranking"},
    "generation": {"ports", "core", "data", "gateway", "generation", "llm"},
    "gateway": {"ports", "core", "data", "gateway"},
    "graph_service": {"ports", "core", "data", "graph_service"},
    "services": {"ports", "automation", "core", "data", "discovery", "generation", "graph_service", "profile", "ranking", "services"},
    "ports": {"ports"},
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


def _layer_of(package: str) -> str:
    for layer, packages in LAYERS.items():
        if package in packages:
            return layer
    raise AssertionError(f"package {package!r} belongs to no layer — add it to LAYERS")


def test_every_project_package_is_assigned_to_exactly_one_layer():
    assigned = [package for packages in LAYERS.values() for package in packages]
    duplicates = {name for name in assigned if assigned.count(name) > 1}
    assert not duplicates, f"packages in more than one layer: {sorted(duplicates)}"

    on_disk = {
        path.name
        for path in BACKEND_ROOT.iterdir()
        if path.is_dir() and (path / "__init__.py").exists() and not path.name.startswith((".", "_"))
    }
    unassigned = on_disk - set(assigned) - {"tests", "evals", "graph", "db"}
    assert not unassigned, f"packages on disk with no layer: {sorted(unassigned)}"


def test_no_package_imports_a_layer_above_itself():
    """The core structural guarantee: dependencies only ever point downward."""
    rank = {"service": 0, "business": 1, "adapter": 2, "data": 3, "common": 4}
    violations: list[str] = []
    for package, allowed in ALLOWED_IMPORTS.items():
        if package not in {name for names in LAYERS.values() for name in names}:
            continue
        package_rank = rank[_layer_of(package)]
        for target in allowed:
            if target == package:
                continue
            target_layer = _layer_of(target)
            # Equal rank (sibling in the same layer) is fine; lower rank is not.
            if rank[target_layer] < package_rank:
                violations.append(f"{package} ({_layer_of(package)}) -> {target} ({target_layer})")

    assert not violations, "upward dependencies break the layering:\n" + "\n".join(sorted(violations))


def test_api_layer_holds_no_business_logic():
    """Routers are transport. Long handlers mean logic that belongs in a service.

    Enforced by size, which is crude but objective: the moment a router function
    grows past this it is doing orchestration a business module should own.
    """
    # Ratchet: the largest handler today is 19 statements (median 3), now that
    # every router delegates to a business service. Tighten, never raise — if a
    # handler needs more room, the orchestration belongs in a service.
    max_statements = 22
    oversized: list[str] = []
    for path in (BACKEND_ROOT / "api" / "routers").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            has_route_decorator = any(
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr in {"get", "post", "put", "delete", "patch"}
                for dec in node.decorator_list
            )
            if not has_route_decorator:
                continue
            statements = sum(1 for _ in ast.walk(node) if isinstance(_, ast.stmt))
            if statements > max_statements:
                oversized.append(f"{path.name}:{node.lineno} {node.name} ({statements} statements)")

    assert not oversized, (
        "route handlers too large — move the orchestration into a service:\n" + "\n".join(sorted(oversized))
    )


# Which router module owns a URL segment. Every endpoint is resolved to exactly
# one owner, so a new endpoint cannot be quietly filed under the wrong feature.
ROUTER_OWNER_BY_SEGMENT = {
    "apply": "automation", "fire": "automation", "form": "automation", "selectors": "automation",
    "diagnostics": "diagnostics", "errors": "diagnostics",
    "cleanup": "discovery", "free-sources": "discovery", "reevaluate": "discovery", "scan": "discovery",
    "dashboard": "dashboard",
    "events": "events",
    "generate": "generation", "pipeline": "generation",
    "graph": "graph",
    "health": "health", "shutdown": "health",
    "help": "help",
    "ingest": "ingestion",
    "export.csv": "leads", "feedback": "leads", "followup": "leads", "followups": "leads",
    "leads": "leads", "manual": "leads", "pdf": "leads", "versions": "leads",
    "learning": "learning",
    "achievement": "profile", "candidate": "profile", "certification": "profile",
    "education": "profile", "experience": "profile", "identity": "profile",
    "profile": "profile", "project": "profile", "skill": "profile",
    "embeddings": "runtime", "vector": "runtime",
    "data": "settings", "preferences": "settings", "settings": "settings", "template": "settings",
    "templates": "templates",
    "opportunities": "opportunities",
}

# `leads` is a container other features hang endpoints off (/leads/{id}/generate
# belongs to generation), so a deeper segment outranks it.
GENERIC_ROUTE_CONTAINERS = {"leads", "api", "v1"}

# Routes whose owner the segment rules can't infer.
EXACT_ROUTE_OWNER = {"/status": "discovery"}

# These modules own a feature-level APIRouter prefix, while their decorators
# intentionally use relative paths that may overlap another prefixed router
# (for example /opportunities/scan versus /discovery/scan).
PREFIXED_ROUTER_OWNER = {"opportunities": "opportunities"}


def _route_owner(route: str) -> str | None:
    if route in EXACT_ROUTE_OWNER:
        return EXACT_ROUTE_OWNER[route]
    segments = [segment for segment in route.strip("/").split("/") if segment]
    if not segments:
        return None
    first = segments[0]
    if first in ROUTER_OWNER_BY_SEGMENT and first not in GENERIC_ROUTE_CONTAINERS:
        return ROUTER_OWNER_BY_SEGMENT[first]
    # Deepest specific segment wins over the generic container it hangs off.
    for segment in reversed(segments):
        if segment in ROUTER_OWNER_BY_SEGMENT and segment not in GENERIC_ROUTE_CONTAINERS:
            return ROUTER_OWNER_BY_SEGMENT[segment]
    return ROUTER_OWNER_BY_SEGMENT.get(first)


def _declared_routes() -> list[tuple[str, str, int]]:
    found: list[tuple[str, str, int]] = []
    for path in (BACKEND_ROOT / "api" / "routers").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for dec in getattr(node, "decorator_list", []):
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                    continue
                if dec.func.attr not in {"get", "post", "put", "delete", "patch"}:
                    continue
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    found.append((path.stem, str(dec.args[0].value), dec.lineno))
    return found


def test_each_feature_owns_exactly_one_router_module():
    """One API per feature: every endpoint of a feature lives in that feature's router.

    This is what keeps the single gateway coherent — adding /leads/{id}/generate
    to leads.py instead of generation.py fails here, and so does a grab-bag
    router collecting endpoints from four unrelated features.
    """
    misplaced: list[str] = []
    unresolved: list[str] = []
    for module, route, lineno in _declared_routes():
        owner = PREFIXED_ROUTER_OWNER.get(module) or _route_owner(route)
        if owner is None:
            unresolved.append(f"{module}.py:{lineno} {route}")
        elif owner != module:
            misplaced.append(f"{module}.py:{lineno} declares {route!r} — belongs in {owner}.py")

    assert not unresolved, (
        "endpoints with no declared feature owner — add the segment to "
        "ROUTER_OWNER_BY_SEGMENT:\n" + "\n".join(sorted(unresolved))
    )
    assert not misplaced, "endpoints filed under the wrong feature:\n" + "\n".join(sorted(misplaced))


#: api modules allowed to touch the data layer. `dependencies` is the composition
#: root (it must build the Repository to inject it); the rest is process infra that
#: runs outside a request. Routers are never on this list.
API_DATA_ACCESS_ALLOWED = {
    "api/dependencies.py",       # composition root: builds the Repository to inject
    "api/scheduler.py",          # process lifespan: init_sql / prune_history / close_all
    "api/startup_validation.py", # pre-DI startup warnings
}


def test_routers_never_reach_past_the_business_layer():
    """The flow is UI -> Service -> Business -> Data, with no shortcut.

    A router that imports `data` is doing the business layer's job in the
    transport layer, which is exactly what makes the layering unreadable: two
    different call paths reach storage and neither is obviously the real one.
    """
    violations: list[str] = []
    for path in sorted((BACKEND_ROOT / "api" / "routers").rglob("*.py")):
        forbidden = _project_imports(path) & {"data", "models"}
        if forbidden:
            rel = path.relative_to(BACKEND_ROOT).as_posix()
            violations.append(f"{rel}: imports {', '.join(sorted(forbidden))} — call a business service instead")

    assert not violations, "routers must not reach the data layer directly:\n" + "\n".join(violations)


def test_only_the_composition_root_builds_data_access():
    """Everything else in api/ goes through a service, so wiring stays in one place."""
    violations: list[str] = []
    for path in sorted((BACKEND_ROOT / "api").rglob("*.py")):
        rel = path.relative_to(BACKEND_ROOT).as_posix()
        if rel in API_DATA_ACCESS_ALLOWED or rel.startswith("api/routers/"):
            continue
        forbidden = _project_imports(path) & {"data", "models"}
        if forbidden:
            violations.append(f"{rel}: {', '.join(sorted(forbidden))}")

    assert not violations, (
        "only the composition root and api infra may build data access:\n" + "\n".join(violations)
    )


def test_business_layer_never_imports_the_web_framework():
    """Domain code raises core.errors; only the API layer knows about HTTP."""
    violations: list[str] = []
    for package in sorted(LAYERS["business"]):
        for path in (BACKEND_ROOT / package).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                if any(name.split(".", 1)[0] in {"fastapi", "starlette"} for name in names):
                    rel = path.relative_to(BACKEND_ROOT).as_posix()
                    violations.append(f"{rel}:{node.lineno}")

    assert not violations, (
        "business modules must not import fastapi/starlette — raise a core.errors "
        "type and let api.app map it to a status:\n" + "\n".join(violations)
    )


def test_no_grab_bag_router_exists():
    banned = {"misc.py", "common.py", "other.py", "utils.py", "shared.py"}
    present = {path.name for path in (BACKEND_ROOT / "api" / "routers").glob("*.py")} & banned
    assert not present, f"grab-bag routers are not allowed: {sorted(present)} — file each endpoint under its feature"


def test_services_do_not_import_gateway_or_api():
    violations = []
    for path in (BACKEND_ROOT / "services").rglob("*.py"):
        imports = _project_imports(path)
        forbidden = imports & {"api", "gateway"}
        if forbidden:
            rel = path.relative_to(BACKEND_ROOT).as_posix()
            violations.append(f"{rel}: {', '.join(sorted(forbidden))}")

    assert not violations, "internal services must not import gateway/api:\n" + "\n".join(violations)
