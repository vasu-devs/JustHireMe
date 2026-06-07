from __future__ import annotations

import os
import secrets
import sys
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request

from api.dependencies import get_repository
from data.repository import Repository


def _details_authorized(request: Request) -> bool:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return False
    token_getter = getattr(request.app.state, "token_getter", None)
    if not callable(token_getter):
        return False
    try:
        expected = token_getter()
    except Exception:
        return False
    return bool(expected) and secrets.compare_digest(auth[7:], expected)


def _check_sqlite(repo: Repository) -> dict:
    try:
        leads = repo.leads.get_all_leads()
        return {"status": "ok", "lead_count": len(leads)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _check_graph(repo: Repository) -> dict:
    try:
        if not repo.graph.graph_available():
            return {"status": "error", "error": repo.graph.graph_error(), "counts": repo.graph.graph_counts()}
        counts = repo.graph.graph_counts()
        return {"status": "ok", "counts": counts}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


async def _check_graph_service(repo: Repository) -> dict:
    # In-process monolith: the graph lives in this process, so check it directly.
    return _check_graph(repo)


def _check_vector(repo: Repository) -> dict:
    try:
        module = sys.modules.get("data.vector.connection")
        if module is None:
            from data.vector.runtime import vector_runtime_status

            runtime = vector_runtime_status()
            if runtime.get("ready"):
                return {"status": "ok", "tables": [], "mode": "not_loaded"}
            return {"status": "disabled", "tables": [], "error": "LanceDB runtime is not installed"}

        status_fn = getattr(module, "vector_status", None)
        if callable(status_fn):
            return status_fn()
        if getattr(module.vec, "available", True) is False:
            return {"status": "unavailable", "tables": [], "error": getattr(module.vec, "reason", "")}
        tables = list(module.vec.list_tables() or [])
        return {"status": "ok", "tables": tables}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _check_profile(repo: Repository) -> dict:
    try:
        profile = repo.profile.get_profile()
        return {
            "status": "ok",
            "has_profile": bool(
                profile.get("n")
                or profile.get("s")
                or profile.get("skills")
                or profile.get("projects")
                or profile.get("exp")
            ),
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


async def _check_profile_service(repo: Repository) -> dict:
    return _check_profile(repo)


def _check_llm(repo: Repository) -> dict:
    try:
        from llm import _ENV_NAMES, _KEY_NAMES, provider_needs_key, resolve_config

        provider, key, model = resolve_config()
        cfg = repo.settings.get_settings()
        key_name = _KEY_NAMES.get(provider, "")
        env_name = _ENV_NAMES.get(provider, "")
        configured = not provider_needs_key(provider) or bool(key)
        source = "none"
        if provider == "ollama":
            source = "local"
        elif provider in ("claude_cli", "codex_cli"):
            source = "subscription"
        elif key_name and cfg.get(key_name):
            source = "settings"
        elif env_name and os.environ.get(env_name):
            source = "environment"
        return {
            "status": "ok" if configured else "missing_key",
            "provider": provider,
            "model": model,
            "key_source": source,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _check_embeddings() -> dict:
    try:
        from data.vector.embeddings import embedding_status

        return embedding_status()
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}


def _as_subsystem_status(name: str, payload: dict) -> dict:
    raw_status = str(payload.get("status") or "unavailable")
    error = str(payload.get("error") or payload.get("reason") or "")
    if raw_status == "ok":
        status = "ok"
    elif raw_status in {"missing_key", "disabled", "error", "unavailable"}:
        status = "unavailable"
    else:
        status = "degraded"
    details = {key: value for key, value in payload.items() if key not in {"status", "error", "reason"}}
    if name == "llm" and raw_status == "missing_key" and not error:
        error = "LLM API key is not configured"
    return {"status": status, "error": error, **details}


def create_router(started_at: float) -> APIRouter:
    router = APIRouter()

    @router.get("/health", dependencies=[])
    async def health(request: Request, repo: Repository = Depends(get_repository)):
        base = {
            "status": "alive",
            "uptime_seconds": round(time.monotonic() - started_at, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details_available": _details_authorized(request),
        }
        if not base["details_available"]:
            return base

        checks = {
            "sqlite": _check_sqlite(repo),
            "graph": await _check_graph_service(repo),
            "vector": _check_vector(repo),
            "profile": await _check_profile_service(repo),
            "llm": _check_llm(repo),
        }
        status = "alive" if checks["sqlite"]["status"] == "ok" and checks["graph"]["status"] == "ok" else "degraded"
        return {
            **base,
            "status": status,
            "log_level": os.environ.get("JHM_LOG_LEVEL", "INFO"),
            "last_scan_finished_at": repo.settings.get_setting("last_scan_finished_at", ""),
            "components": checks,
            "checks": checks,
            "services": {},
        }

    @router.get("/api/v1/health/subsystems")
    async def health_subsystems(repo: Repository = Depends(get_repository)):
        checks = {
            "graph": await _check_graph_service(repo),
            "vector": _check_vector(repo),
            "llm": _check_llm(repo),
            "embeddings": _check_embeddings(),
        }
        return {name: _as_subsystem_status(name, payload) for name, payload in checks.items()}

    return router
