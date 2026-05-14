from __future__ import annotations

import asyncio
import math

from fastapi import APIRouter, Depends

from api.dependencies import get_repository
from api.rate_limit import RateLimiter, require_rate_limit
from core.types import HelpChatBody
from core.telemetry import log_error
from data.repository import Repository
from gateway.clients import graph_client
from graph_service.stats import graph_stats_payload


router = APIRouter(prefix="/api/v1", tags=["misc"])
_help_limiter = RateLimiter(20, 60)


@router.get("/graph")
async def graph_stats(repo: Repository = Depends(get_repository), repair: bool = False):
    client = graph_client()
    if client and isinstance(repo, Repository):
        return await client.stats(repair=repair)

    errors: list[str] = []
    if repair:
        sync = _safe_graph_step(lambda: repo.graph.sync_job_leads(repo.leads.get_all_leads()), "lead sync", errors)
        profile_sync = _safe_graph_step(
            lambda: repo.graph.sync_profile_relationships() if hasattr(repo.graph, "sync_profile_relationships") else {"status": "skipped"},
            "profile sync",
            errors,
        )
        vector_sync = _sync_vectors_from_graph()
        if vector_sync.get("status") == "error" and vector_sync.get("error"):
            errors.append(f"vector sync: {vector_sync['error']}")
    else:
        sync = {"status": "skipped", "reason": "read-only snapshot"}
        profile_sync = {"status": "skipped", "reason": "read-only snapshot"}
        vector_sync = {"status": "skipped", "synced": 0, "reason": "read-only snapshot"}
    counts = _safe_graph_step(repo.graph.graph_counts, "counts", errors, default={})
    available = _safe_graph_step(repo.graph.graph_available, "availability", errors, default=False)
    graph = _safe_graph_step(repo.graph.graph_snapshot, "snapshot", errors, default={"nodes": [], "edges": [], "available": False})
    embedding = _embedding_space(repo)
    if embedding.get("error"):
        errors.append(f"embedding: {embedding['error']}")
    graph_error = "" if available else repo.graph.graph_error()
    if graph_error:
        errors.append(graph_error)
    sync_ok = sync.get("status") == "ok" if repair else True
    return {
        "candidate": 0,
        "skill": 0,
        "project": 0,
        "experience": 0,
        "joblead": 0,
        **counts,
        "available": available,
        "status": "live" if available and sync_ok and not errors else "degraded",
        "error": "; ".join(dict.fromkeys(error for error in errors if error)),
        "sync": {**sync, "profile": profile_sync, "vectors": vector_sync},
        "graph": graph,
        "embedding": embedding,
    }


def _safe_graph_step(fn, label: str, errors: list[str], default=None):
    try:
        return fn()
    except Exception as exc:
        errors.append(f"{label}: {exc}")
        if default is not None:
            return default
        return {"status": "error", "error": str(exc)}


def _sync_vectors_from_graph() -> dict:
    try:
        from data.graph.profile import sync_vectors_from_graph

        return sync_vectors_from_graph()
    except Exception as exc:
        return {"status": "error", "synced": 0, "error": str(exc)}


def _embedding_space(repo: Repository, limit: int = 80) -> dict:
    points: list[dict] = []
    try:
        tables = [
            name for name in _vector_table_names(repo.vector.vec)
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
            x, y, z = _project_vector(vector)
            mag = math.sqrt(x * x + y * y + z * z) or 1.0
            label = row.get("label") or row.get("n") or row.get("title") or row.get("role") or row.get("id") or table_name
            points.append({
                "id": str(row.get("id") or f"{table_name}:{len(points)}"),
                "label": str(label),
                "type": _vector_type(table_name, row),
                "x": x / mag,
                "y": y / mag,
                "z": z / mag,
            })
            if len(points) >= limit:
                break
    return {"available": bool(points), "points": points, "error": ""}


def _vector_type(table_name: str, row: dict) -> str:
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


def _project_vector(vector: list) -> tuple[float, float, float]:
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


def _vector_table_names(vec) -> list[str]:
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


@router.post("/help/chat")
async def help_chat(body: HelpChatBody):
    require_rate_limit(_help_limiter)
    from help.service import answer

    history = [item.model_dump() for item in body.history]
    return await asyncio.to_thread(answer, body.question, history)


@router.post("/errors")
async def record_frontend_error(payload: dict):
    log_error(str(payload.get("error") or "Frontend error"), {"frontend": payload})
    return {"ok": True}
