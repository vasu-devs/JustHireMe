from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request

from api.dependencies import get_repository
from data.repository import Repository


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


def _check_vector(repo: Repository) -> dict:
    try:
        tables = list(repo.vector.vec.list_tables() or [])
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


def _check_llm(repo: Repository) -> dict:
    try:
        from llm import _ENV_NAMES, _KEY_NAMES, resolve_config

        provider, key, model = resolve_config()
        cfg = repo.settings.get_settings()
        key_name = _KEY_NAMES.get(provider, "")
        env_name = _ENV_NAMES.get(provider, "")
        configured = provider == "ollama" or bool(key)
        source = "none"
        if provider == "ollama":
            source = "local"
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


def create_router(started_at: float) -> APIRouter:
    router = APIRouter()

    @router.get("/health", dependencies=[])
    async def health(request: Request, repo: Repository = Depends(get_repository)):
        service_registry = getattr(request.app.state, "service_registry", None)
        checks = {
            "sqlite": _check_sqlite(repo),
            "graph": _check_graph(repo),
            "vector": _check_vector(repo),
            "profile": _check_profile(repo),
            "llm": _check_llm(repo),
        }
        status = "alive" if checks["sqlite"]["status"] == "ok" and checks["graph"]["status"] == "ok" else "degraded"
        return {
            "status": status,
            "uptime_seconds": round(time.monotonic() - started_at, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "log_level": os.environ.get("JHM_LOG_LEVEL", "INFO"),
            "last_scan_finished_at": repo.settings.get_setting("last_scan_finished_at", ""),
            "components": checks,
            "checks": checks,
            "services": service_registry.snapshot() if service_registry else {},
        }

    return router
