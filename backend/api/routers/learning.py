"""Learning-insights API — transport only."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_learning_service

router = APIRouter(prefix="/api/v1", tags=["learning"])


@router.get("/learning/insights")
async def learning_insights(service=Depends(get_learning_service)):
    return await service.insights()
