"""Dashboard/audit-report API — transport only.

The payload is built by the business layer (``reporting.service``): headline
metrics, the funnel, source breakdown, daily timeseries and recent activity
for the Overview/Sources screens, plus per-lead verification evidence and
drafted-answers text for the Application Detail screen.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_dashboard_service

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


@router.get("/dashboard/overview")
async def dashboard_overview(service=Depends(get_dashboard_service)):
    return await service.overview()


@router.get("/dashboard/applications/{job_id}")
async def dashboard_application_detail(job_id: str, service=Depends(get_dashboard_service)):
    return await service.application_detail(job_id)
