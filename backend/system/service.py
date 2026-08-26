"""System service — business layer behind the health, diagnostics and runtime routers."""

from __future__ import annotations

import asyncio
import time

from core.telemetry import (
    get_error_count,
    get_metric_state,
    get_metrics,
    get_top_errors,
    log_error,
    redact_sensitive,
    redact_text,
)
from core.version import APP_VERSION
from data.repository import Repository
from system import health, runtime


def _clip(value: object, max_len: int = 4000) -> str:
    return str(value or "")[:max_len]


class SystemService:
    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    # ------------------------------------------------------------------ health

    async def liveness(self, started_at: float) -> dict:
        from datetime import datetime, timezone

        return {
            "status": "alive",
            "uptime_seconds": round(time.monotonic() - started_at, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def component_checks(self) -> dict:
        return {
            "sqlite": health.check_sqlite(self._repo),
            "graph": health.check_graph(self._repo),
            "vector": health.check_vector(self._repo),
            "profile": health.check_profile(self._repo),
            "llm": health.check_llm(self._repo),
        }

    async def last_scan_finished_at(self) -> str:
        return await asyncio.to_thread(self._repo.settings.get_setting, "last_scan_finished_at", "")

    async def subsystems(self) -> dict:
        checks = {
            "graph": health.check_graph(self._repo),
            "vector": health.check_vector(self._repo),
            "llm": health.check_llm(self._repo),
            "embeddings": health.check_embeddings(),
        }
        return {name: health.as_subsystem_status(name, payload) for name, payload in checks.items()}

    # ------------------------------------------------------------- diagnostics

    async def diagnostics(self, started_at: float) -> dict:
        return {
            "top_errors": get_top_errors(limit=10),
            "error_count_24h": get_error_count(hours=24),
            "metrics": get_metrics(),
            "last_scan": get_metric_state("last_scan"),
            "embedding_mode": health.embedding_mode(),
            "version": APP_VERSION,
            "uptime_seconds": round(time.monotonic() - started_at, 2),
        }

    async def record_frontend_error(self, payload: dict) -> None:
        # Bound every field so a runaway/abusive client can't write multi-MB lines
        # into errors.jsonl (redact_sensitive truncates strings but not a giant
        # nested dict passed as componentStack).
        safe_payload = redact_sensitive({
            "error": _clip(payload.get("error") or "Frontend error", 2000),
            "componentStack": _clip(payload.get("componentStack", ""), 8000),
            "url": _clip(payload.get("url", ""), 1000),
            "userAgent": _clip(payload.get("userAgent", ""), 500),
        })
        log_error(redact_text(_clip(payload.get("error") or "Frontend error", 2000)), {"frontend": safe_payload})

    # ----------------------------------------------------------------- runtime

    async def vector_runtime(self) -> dict:
        return runtime.runtime_payload()

    async def install_vector_runtime(self) -> dict:
        runtime.ensure_install_job()
        return runtime.runtime_payload()

    async def embedding_status(self) -> dict:
        return runtime.embedding_status()

    async def set_embedding_provider(self, provider: str) -> dict:
        return await asyncio.to_thread(runtime.set_embedding_provider, provider)

    async def download_onnx_model(self) -> dict:
        return runtime.download_onnx_model()


def create_system_service(repo: Repository) -> SystemService:
    return SystemService(repo)


__all__ = ["SystemService", "create_system_service"]
