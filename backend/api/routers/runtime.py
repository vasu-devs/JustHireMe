"""Optional-runtime API — transport only.

Install jobs and driver state live in ``system.runtime``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_system_service

router = APIRouter(prefix="/api/v1/runtime", tags=["runtime"])


@router.get("/vector")
async def get_vector_runtime(service=Depends(get_system_service)):
    return await service.vector_runtime()


@router.post("/vector/install")
async def install_vector_runtime_endpoint(service=Depends(get_system_service)):
    return await service.install_vector_runtime()


@router.get("/embeddings")
async def get_embedding_status(service=Depends(get_system_service)):
    """The current embedding provider status."""
    return await service.embedding_status()


@router.post("/embeddings/provider")
async def set_embedding_provider(body: dict, service=Depends(get_system_service)):
    """Set the preferred embedding provider (onnx, openai, hash)."""
    return await service.set_embedding_provider(str(body.get("provider") or "onnx"))


@router.post("/embeddings/onnx/download")
async def download_onnx_model_endpoint(service=Depends(get_system_service)):
    """Download the ONNX embedding model in the background."""
    return await service.download_onnx_model()
