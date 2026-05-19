from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from data.vector.runtime import install_vector_runtime, vector_runtime_status


router = APIRouter(prefix="/api/v1/runtime", tags=["runtime"])


def _runtime_payload(sync: dict | None = None) -> dict:
    from data.vector import connection

    runtime = vector_runtime_status()
    vector = connection.vector_status()
    ready = bool(runtime.get("ready")) and vector.get("status") == "ok"
    payload = {
        "ready": ready,
        "required": True,
        "runtime": runtime,
        "vector": vector,
    }
    if sync is not None:
        payload["sync"] = sync
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


@router.get("/vector")
async def get_vector_runtime():
    return _runtime_payload()


@router.post("/vector/install")
async def install_vector_runtime_endpoint():
    try:
        return await asyncio.to_thread(_install_and_refresh)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
