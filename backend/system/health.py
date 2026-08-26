"""Subsystem probes.

Each probe answers "is this dependency usable right now?" and never raises —
a health endpoint that 500s tells the user nothing about which part is broken.
"""

from __future__ import annotations

import logging
import sys

from core import env
from data.repository import Repository

_log = logging.getLogger(__name__)


def check_sqlite(repo: Repository) -> dict:
    try:
        leads = repo.leads.get_all_leads()
        return {"status": "ok", "lead_count": len(leads)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def check_graph(repo: Repository) -> dict:
    try:
        if not repo.graph.graph_available():
            return {"status": "error", "error": repo.graph.graph_error(), "counts": repo.graph.graph_counts()}
        return {"status": "ok", "counts": repo.graph.graph_counts()}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def check_vector(repo: Repository) -> dict:
    try:
        module = sys.modules.get("data.vector.connection")
        if module is None:
            from data.vector.runtime import vector_runtime_status

            if vector_runtime_status().get("ready"):
                return {"status": "ok", "tables": [], "mode": "not_loaded"}
            return {"status": "disabled", "tables": [], "error": "LanceDB runtime is not installed"}

        status_fn = getattr(module, "vector_status", None)
        if callable(status_fn):
            return status_fn()
        if getattr(module.vec, "available", True) is False:
            return {"status": "unavailable", "tables": [], "error": getattr(module.vec, "reason", "")}
        return {"status": "ok", "tables": list(module.vec.list_tables() or [])}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def check_profile(repo: Repository) -> dict:
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


def check_llm(repo: Repository) -> dict:
    try:
        from llm import SUBSCRIPTION_CLI_PROVIDERS, _ENV_NAMES, _KEY_NAMES, provider_needs_key, resolve_config

        provider, key, model = resolve_config()
        cfg = repo.settings.get_settings()
        key_name = _KEY_NAMES.get(provider, "")
        env_name = _ENV_NAMES.get(provider, "")
        configured = not provider_needs_key(provider) or bool(key)
        source = "none"
        if provider == "ollama":
            source = "local"
        elif provider in SUBSCRIPTION_CLI_PROVIDERS:
            source = "subscription"
        elif key_name and cfg.get(key_name):
            source = "settings"
        elif env_name and env.is_set(env_name):
            source = "environment"
        return {
            "status": "ok" if configured else "missing_key",
            "provider": provider,
            "model": model,
            "key_source": source,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def check_embeddings() -> dict:
    try:
        from data.vector.embeddings import embedding_status

        return embedding_status()
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}


def embedding_mode() -> str:
    """Which embedding provider is actually in use (onnx/openai/hashing).

    A ``hashing`` result means the local model isn't installed and semantic
    matching is degraded — surfacing it here makes that honest instead of
    silent. Lazy + fail-safe so a diagnostics hit never pulls a heavy import.
    """
    try:
        from data.vector.embeddings import embedding_status

        # Use the status mode (not active_provider): it reports 'hashing' when a
        # runtime openai/onnx fallback happened, so degradation is honest here too.
        return str(embedding_status().get("mode") or "unknown")
    except Exception as exc:
        _log.debug("suppressed exception in system.health.embedding_mode: %s", exc)
        return "unknown"


def as_subsystem_status(name: str, payload: dict) -> dict:
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
