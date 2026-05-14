from __future__ import annotations

import math

from data.repository import Repository


BAD_VECTOR_LABEL_PATTERNS = (
    "404:",
    "not_found",
    "not found",
    "error code",
    "failed to fetch",
    "server returned",
    "traceback",
)


def is_bad_vector_label(value: object) -> bool:
    text = str(value or "").strip()
    lower = text.lower()
    return not text or any(pattern in lower for pattern in BAD_VECTOR_LABEL_PATTERNS)


def safe_graph_step(fn, label: str, errors: list[str], default=None):
    try:
        return fn()
    except Exception as exc:
        errors.append(f"{label}: {exc}")
        if default is not None:
            return default
        return {"status": "error", "error": str(exc)}


def sync_vectors_from_graph() -> dict:
    try:
        from data.graph.profile import sync_vectors_from_graph as _sync

        return _sync()
    except Exception as exc:
        return {"status": "error", "synced": 0, "error": str(exc)}


def embedding_space(repo: Repository, limit: int = 80) -> dict:
    points: list[dict] = []
    try:
        tables = [
            name for name in vector_table_names(repo.vector.vec)
            if name in {"profile", "candidates", "skills", "projects", "experiences", "credentials"}
        ]
    except Exception as exc:
        return {"available": False, "points": points, "error": str(exc)}

    for table_name in tables:
        try:
            table = repo.vector.vec.open_table(table_name)
            if hasattr(table, "to_arrow"):
                rows = table.to_arrow().to_pylist()[:limit]
            elif hasattr(table, "to_pandas"):
                rows = table.to_pandas().head(limit).to_dict("records")
            else:
                rows = []
        except Exception:
            rows = []
        for row in rows:
            vector = row.get("vector") or []
            if hasattr(vector, "tolist"):
                vector = vector.tolist()
            if not isinstance(vector, list) or len(vector) < 2:
                continue
            x, y, z = project_vector(vector)
            mag = math.sqrt(x * x + y * y + z * z) or 1.0
            label = row.get("label") or row.get("n") or row.get("title") or row.get("role") or row.get("id") or table_name
            if is_bad_vector_label(label):
                continue
            points.append({
                "id": str(row.get("id") or f"{table_name}:{len(points)}"),
                "label": str(label),
                "type": vector_type(table_name, row),
                "x": x / mag,
                "y": y / mag,
                "z": z / mag,
            })
            if len(points) >= limit:
                break
    return {"available": bool(points), "points": points, "error": ""}


def vector_type(table_name: str, row: dict) -> str:
    if table_name == "profile":
        return "Profile"
    if table_name == "candidates":
        return "Candidate"
    if table_name == "skills":
        return "Skill"
    if table_name == "projects":
        return "Project"
    if table_name == "experiences":
        return "Experience"
    if table_name == "credentials":
        kind = str(row.get("kind") or "").strip().title()
        return kind or "Credential"
    return table_name.title()


def project_vector(vector: list) -> tuple[float, float, float]:
    x = 0.0
    y = 0.0
    z = 0.0
    dims = max(len(vector), 1)
    for idx, raw in enumerate(vector):
        try:
            value = float(raw)
        except Exception:
            continue
        if value == 0:
            continue
        angle = (idx * 2.399963229728653) % (math.pi * 2)
        radius = 0.65 + ((idx % 17) / 48)
        x += math.cos(angle) * value * radius
        y += math.sin(angle) * value * radius
        z += math.sin(idx * 1.618033988749895) * value * (0.55 + ((idx % 11) / 38))
    if x == 0 and y == 0 and z == 0 and dims:
        return 0.0, 0.0, 0.0
    return x, y, z


def vector_table_names(vec) -> list[str]:
    raw = vec.list_tables()
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if hasattr(raw, "tables"):
        return [str(item) for item in raw.tables]
    if isinstance(raw, dict):
        tables = raw.get("tables", raw)
        if isinstance(tables, list):
            return [str(item) for item in tables]
    try:
        pairs = dict(raw)
        tables = pairs.get("tables", [])
        if isinstance(tables, list):
            return [str(item) for item in tables]
    except Exception:
        pass
    return [str(item) for item in raw]
