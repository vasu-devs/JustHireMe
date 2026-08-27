"""Optional local runtimes: the LanceDB pack and the ONNX embedding model.

Installs run on a background thread and are reported through a status payload
the UI polls. Module-level job state is process-wide on purpose — there is one
sidecar process and one runtime to install.
"""

from __future__ import annotations

import logging
import sys
import threading

from data.vector.runtime import install_vector_runtime, vector_runtime_progress, vector_runtime_status

_log = logging.getLogger(__name__)

_JOB_LOCK = threading.RLock()
_INSTALL_JOB: threading.Thread | None = None
_ONNX_DOWNLOAD_JOB: threading.Thread | None = None
_LAST_SYNC: dict | None = None
_LAST_ERROR = ""

EMBEDDING_PROVIDERS = frozenset({"onnx", "openai", "hash"})


def _job_running() -> bool:
    return bool(_INSTALL_JOB and _INSTALL_JOB.is_alive())


def _loaded_vector_status(runtime_ready: bool) -> dict:
    module = sys.modules.get("data.vector.connection")
    if module is None:
        if runtime_ready:
            return {"status": "initializing", "tables": []}
        return {"status": "disabled", "tables": [], "error": "LanceDB runtime is not installed"}

    status_fn = getattr(module, "vector_status", None)
    if callable(status_fn):
        try:
            return status_fn(refresh=False)
        except Exception as exc:
            return {"status": "degraded", "tables": [], "error": str(exc)}
    return {"status": "initializing", "tables": []}


def runtime_payload(sync: dict | None = None) -> dict:
    runtime = vector_runtime_status()
    progress = vector_runtime_progress()
    runtime_ready = bool(runtime.get("ready"))
    vector = _loaded_vector_status(runtime_ready)
    restart_required = bool(vector.get("restart_required"))
    job_active = _job_running() or bool(progress.get("active", False))
    payload = {
        # The archive can become file-complete before the background worker has
        # imported LanceDB, connected it, and synced existing profile rows. Do
        # not advertise the runtime as ready during that window: callers would
        # otherwise observe a disabled vector store immediately after success.
        "ready": runtime_ready and not restart_required and not job_active,
        "required": not runtime_ready and not restart_required,
        "restart_required": restart_required,
        "runtime": runtime,
        "vector": vector,
        "progress": progress | {"active": job_active},
    }
    current_sync = sync if sync is not None else _LAST_SYNC
    if current_sync is not None:
        payload["sync"] = current_sync
    if _LAST_ERROR:
        payload["install_error"] = _LAST_ERROR
    return payload


def _install_and_refresh() -> dict:
    from data.graph import profile as graph_profile
    from data.vector import connection

    install_vector_runtime()
    vector = connection.refresh_vector_store()
    sync = {"status": "skipped", "synced": 0}
    if vector.get("status") == "ok":
        sync = graph_profile.sync_vectors_from_graph()
    return runtime_payload(sync)


def _install_worker() -> None:
    global _LAST_ERROR, _LAST_SYNC

    try:
        _LAST_ERROR = ""
        _LAST_SYNC = _install_and_refresh().get("sync")
    except Exception as exc:
        _LAST_ERROR = str(exc)


def ensure_install_job() -> None:
    global _INSTALL_JOB, _LAST_ERROR

    with _JOB_LOCK:
        if _job_running():
            return
        _LAST_ERROR = ""
        _INSTALL_JOB = threading.Thread(target=_install_worker, name="jhm-runtime-pack-install", daemon=True)
        _INSTALL_JOB.start()


def spawn_vector_resync() -> None:
    """Rebuild all vector tables in the background at the current provider's dim.

    A provider change almost always changes the embedding dimension, leaving the
    existing tables in the wrong vector space. Rebuilding here means semantic
    matching uses the new embeddings and no later single-item write ever meets a
    dim-mismatched table (which now skips itself to avoid data loss).
    """
    def _run() -> None:
        try:
            from graph_service.helpers import sync_vectors_from_graph

            sync_vectors_from_graph()
        except Exception as exc:
            _log.warning("vector re-sync after provider switch failed: %s", exc)

    threading.Thread(target=_run, name="jhm-vector-resync", daemon=True).start()


def embedding_status() -> dict:
    from data.vector.embeddings import embedding_status as _status

    return _status()


def set_embedding_provider(provider: str) -> dict:
    """Set the preferred embedding provider (onnx, openai, hash)."""
    from data.sqlite.settings import get_settings, save_settings
    from data.vector.embeddings import embedding_status as _status
    from data.vector.embeddings import reset_onnx_session

    provider = str(provider or "onnx").strip().lower()
    if provider not in EMBEDDING_PROVIDERS:
        provider = "onnx"

    previous = str((get_settings() or {}).get("embedding_provider", "onnx") or "onnx").strip().lower()
    save_settings({"embedding_provider": provider})
    # Reset cached state so the new provider takes effect.
    reset_onnx_session()
    if provider != previous:
        spawn_vector_resync()
    return _status()


def _onnx_download_running() -> bool:
    return bool(_ONNX_DOWNLOAD_JOB and _ONNX_DOWNLOAD_JOB.is_alive())


def download_onnx_model() -> dict:
    """Download the ONNX embedding model in the background."""
    global _ONNX_DOWNLOAD_JOB

    from data.vector.embeddings import download_onnx_model as _download
    from data.vector.embeddings import embedding_status as _status
    from data.vector.embeddings import reset_onnx_session

    if _onnx_download_running():
        return {"status": "already_running", **_status()}

    def _worker():
        if _download().get("status") == "ok":
            reset_onnx_session()
            # hash -> onnx is a SAME-dimension (384) transition, so put_vec_rows'
            # dim-mismatch guard can't detect it and no rebuild would otherwise
            # happen — leaving profile tables full of hash vectors compared against
            # ONNX query vectors. Re-embed the graph with the now-active ONNX model.
            spawn_vector_resync()

    _ONNX_DOWNLOAD_JOB = threading.Thread(target=_worker, name="jhm-onnx-download", daemon=True)
    _ONNX_DOWNLOAD_JOB.start()
    return {"status": "downloading", **_status()}
