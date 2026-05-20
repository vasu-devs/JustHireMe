from __future__ import annotations

import threading

from fastapi import APIRouter

from data.vector.runtime import install_vector_runtime, vector_runtime_progress, vector_runtime_status


router = APIRouter(prefix="/api/v1/runtime", tags=["runtime"])
_JOB_LOCK = threading.RLock()
_INSTALL_JOB: threading.Thread | None = None
_LAST_SYNC: dict | None = None
_LAST_ERROR = ""


def _job_running() -> bool:
    return bool(_INSTALL_JOB and _INSTALL_JOB.is_alive())


def _runtime_payload(sync: dict | None = None) -> dict:
    from data.vector import connection

    runtime = vector_runtime_status()
    vector = connection.vector_status(refresh=False)
    progress = vector_runtime_progress()
    runtime_ready = bool(runtime.get("ready"))
    last_error_requires_restart = "initialized once per interpreter" in _LAST_ERROR.lower()
    restart_required = bool(vector.get("restart_required")) or last_error_requires_restart
    ready = runtime_ready and vector.get("status") == "ok"
    payload = {
        "ready": ready,
        "required": not runtime_ready and not restart_required,
        "restart_required": restart_required,
        "runtime": runtime,
        "vector": vector,
        "progress": progress | {"active": _job_running() or progress.get("active", False)},
    }
    current_sync = sync if sync is not None else _LAST_SYNC
    if current_sync is not None:
        payload["sync"] = current_sync
    if _LAST_ERROR:
        payload["install_error"] = connection.PYO3_RESTART_MESSAGE if last_error_requires_restart else _LAST_ERROR
    return payload


def _install_and_refresh() -> dict:
    from data.graph import profile as graph_profile
    from data.vector import connection

    install_vector_runtime()
    vector = connection.refresh_vector_store()
    sync = {"status": "skipped", "synced": 0}
    if vector.get("status") == "ok":
        sync = graph_profile.sync_vectors_from_graph()
    return _runtime_payload(sync)


def _install_worker() -> None:
    global _LAST_ERROR, _LAST_SYNC

    try:
        _LAST_ERROR = ""
        payload = _install_and_refresh()
        _LAST_SYNC = payload.get("sync")
    except Exception as exc:
        _LAST_ERROR = str(exc)


def _ensure_install_job() -> None:
    global _INSTALL_JOB, _LAST_ERROR

    with _JOB_LOCK:
        if _job_running():
            return
        _LAST_ERROR = ""
        _INSTALL_JOB = threading.Thread(target=_install_worker, name="jhm-runtime-pack-install", daemon=True)
        _INSTALL_JOB.start()


@router.get("/vector")
async def get_vector_runtime():
    return _runtime_payload()


@router.post("/vector/install")
async def install_vector_runtime_endpoint():
    _ensure_install_job()
    return _runtime_payload()
