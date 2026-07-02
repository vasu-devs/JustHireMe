from __future__ import annotations

import logging
import time

from fastapi import APIRouter

from core.telemetry import get_error_count, get_metric_state, get_metrics, get_top_errors
from core.version import APP_VERSION


def _embedding_mode() -> str:
    """Report which embedding provider is actually in use (onnx/openai/hash).

    A ``hash`` result means the local model isn't installed and semantic matching
    is degraded — surfacing it here makes that honest instead of silent. Lazy +
    fail-safe so a diagnostics hit never pulls in a heavy import or raises.
    """
    try:
        from data.vector.embeddings import embedding_status

        # Use the status mode (not active_provider): it reports 'hashing' when a
        # runtime openai/onnx fallback happened, so degradation is honest here too.
        return str(embedding_status().get("mode") or "unknown")
    except Exception as log_exc:
        logging.getLogger(__name__).debug('suppressed exception in diagnostics._embedding_mode: %s', log_exc)
        return "unknown"


def create_router(started_at: float) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["diagnostics"])

    @router.get("/diagnostics")
    async def diagnostics():
        return {
            "top_errors": get_top_errors(limit=10),
            "error_count_24h": get_error_count(hours=24),
            "metrics": get_metrics(),
            "last_scan": get_metric_state("last_scan"),
            "embedding_mode": _embedding_mode(),
            "version": APP_VERSION,
            "uptime_seconds": round(time.monotonic() - started_at, 2),
        }

    return router
