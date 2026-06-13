from __future__ import annotations
import logging

import asyncio
import math
import signal

from fastapi import APIRouter, Depends

from api.dependencies import get_repository
from api.rate_limit import RateLimiter, require_rate_limit
from core.types import HelpChatBody
from core.telemetry import log_error, redact_sensitive, redact_text
from data.graph.connection import run_graph
from data.repository import Repository
from graph_service.helpers import is_bad_vector_label


router = APIRouter(prefix="/api/v1", tags=["misc"])
_help_limiter = RateLimiter(20, 60)
_background_tasks: set[asyncio.Task] = set()


def _track_background_task(task: asyncio.Task) -> None:
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@router.get("/graph")
async def graph_stats(repo: Repository = Depends(get_repository), repair: bool = False):
    errors: list[str] = []
    profile_repo = getattr(repo, "profile", None)
    if repair:
        # The hard purge (DETACH DELETE of tombstoned nodes) is expensive and
        # only needed to physically clean the graph. Read-time filtering
        # (filter_graph_deletions / filter_embedding_deletions below) already
        # hides deleted items, so keep the common read path fast and purge only
        # on an explicit repair (and during ingest vector sync).
        if profile_repo and hasattr(profile_repo, "purge_profile_deletion_tombstones"):
            await _safe_graph_step_async(profile_repo.purge_profile_deletion_tombstones, "profile deletion purge", errors, default={"status": "skipped"})
        leads = await asyncio.to_thread(repo.leads.get_all_leads)
        sync = await _safe_graph_step_async(lambda: repo.graph.sync_job_leads(leads), "lead sync", errors)
        profile_sync = await _safe_graph_step_async(
            lambda: repo.graph.sync_profile_relationships() if hasattr(repo.graph, "sync_profile_relationships") else {"status": "skipped"},
            "profile sync",
            errors,
        )
        vector_sync = await run_graph(_sync_vectors_from_graph)
        if vector_sync.get("status") == "error" and vector_sync.get("error"):
            errors.append(f"vector sync: {vector_sync['error']}")
    else:
        sync = {"status": "skipped", "reason": "read-only snapshot"}
        profile_sync = {"status": "skipped", "reason": "read-only snapshot"}
        vector_sync = {"status": "skipped", "synced": 0, "reason": "read-only snapshot"}
    counts = await _safe_graph_step_async(repo.graph.graph_counts, "counts", errors, default={})
    available = await _safe_graph_step_async(repo.graph.graph_available, "availability", errors, default=False)
    graph = await _safe_graph_step_async(repo.graph.graph_snapshot, "snapshot", errors, default={"nodes": [], "edges": [], "available": False})
    graph = _apply_graph_deletions(graph)
    profile_snapshot = {}
    if profile_repo:
        profile_snapshot = await _safe_graph_step_async(
            lambda: profile_repo.get_profile() or profile_repo.load_profile_snapshot(),
            "profile snapshot",
            errors,
            default={},
        )
    embedding = _apply_embedding_deletions(_embedding_space(repo))
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
        "profile": profile_snapshot,
    }


def _apply_graph_deletions(graph: dict) -> dict:
    # Keep the Knowledge page (raw Kùzu snapshot) consistent with the deletion
    # tombstones the Profile page applies. Failsafe: never break the endpoint.
    try:
        from data.graph.profile import filter_graph_deletions

        return filter_graph_deletions(graph)
    except Exception as exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/api/routers/misc.py:_apply_graph_deletions: %s', exc)
        return graph


def _apply_embedding_deletions(embedding: dict) -> dict:
    # Same as above for the raw LanceDB embedding-space points.
    try:
        from data.graph.profile import filter_embedding_deletions

        return filter_embedding_deletions(embedding)
    except Exception as exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/api/routers/misc.py:_apply_embedding_deletions: %s', exc)
        return embedding


def _safe_graph_step(fn, label: str, errors: list[str], default=None):
    try:
        return fn()
    except Exception as exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/api/routers/misc.py:_safe_graph_step: %s', exc)
        errors.append(f"{label}: {exc}")
        if default is not None:
            return default
        return {"status": "error", "error": str(exc)}


async def _safe_graph_step_async(fn, label: str, errors: list[str], default=None):
    try:
        return await run_graph(fn)
    except Exception as exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/api/routers/misc.py:_safe_graph_step_async: %s', exc)
        errors.append(f"{label}: {exc}")
        if default is not None:
            return default
        return {"status": "error", "error": str(exc)}


def _sync_vectors_from_graph() -> dict:
    try:
        from data.graph.profile import sync_vectors_from_graph

        return sync_vectors_from_graph()
    except Exception as exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/api/routers/misc.py:_sync_vectors_from_graph: %s', exc)
        return {"status": "error", "synced": 0, "error": str(exc)}


def _embedding_space(repo: Repository, limit: int = 80) -> dict:
    points: list[dict] = []
    try:
        tables = [
            name for name in _vector_table_names(repo.vector.vec)
            if name in {"profile", "candidates", "skills", "projects", "experiences", "credentials"}
        ]
    except Exception as exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/api/routers/misc.py:_embedding_space: %s', exc)
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
        except Exception as log_exc:
            logging.getLogger(__name__).warning('suppressed exception in backend/api/routers/misc.py:_embedding_space: %s', log_exc)
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
            if is_bad_vector_label(label):
                continue
            point = {
                "id": str(row.get("id") or f"{table_name}:{len(points)}"),
                "label": str(label),
                "type": _vector_type(table_name, row),
                "x": x / mag,
                "y": y / mag,
                "z": z / mag,
                "source": table_name,
            }
            subtitle = row.get("cat") or row.get("category") or row.get("co") or row.get("company") or row.get("kind")
            text = row.get("text") or row.get("impact") or row.get("d") or row.get("description") or row.get("summary")
            stack = row.get("stack")
            if subtitle:
                point["subtitle"] = str(subtitle)
            if text:
                point["text"] = str(text)
            if stack:
                point["stack"] = stack
            points.append(point)
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
        except Exception as log_exc:
            logging.getLogger(__name__).warning('suppressed exception in backend/api/routers/misc.py:_project_vector: %s', log_exc)
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
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/api/routers/misc.py:_vector_table_names: %s', log_exc)
        pass
    return [str(item) for item in raw]


@router.post("/help/chat")
async def help_chat(body: HelpChatBody):
    require_rate_limit(_help_limiter)
    from help.service import answer

    history = [item.model_dump() for item in body.history]
    return await asyncio.to_thread(answer, body.question, history)


_errors_limiter = RateLimiter(30, 60)


def _clip(value: object, max_len: int = 4000) -> str:
    return str(value or "")[:max_len]


@router.post("/errors")
async def record_frontend_error(payload: dict):
    # Bound every field so a runaway/abusive client can't write multi-MB lines
    # into errors.jsonl (redact_sensitive truncates strings but not a giant
    # nested dict passed as componentStack).
    require_rate_limit(_errors_limiter)
    safe_payload = redact_sensitive({
        "error": _clip(payload.get("error") or "Frontend error", 2000),
        "componentStack": _clip(payload.get("componentStack", ""), 8000),
        "url": _clip(payload.get("url", ""), 1000),
        "userAgent": _clip(payload.get("userAgent", ""), 500),
    })
    log_error(redact_text(_clip(payload.get("error") or "Frontend error", 2000)), {"frontend": safe_payload})
    return {"ok": True}


@router.post("/shutdown")
async def request_shutdown():
    async def _shutdown_soon():
        await asyncio.sleep(0.1)
        signal.raise_signal(signal.SIGTERM)

    _track_background_task(asyncio.create_task(_shutdown_soon()))
    return {"ok": True}
