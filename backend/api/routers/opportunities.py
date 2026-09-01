from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from api.dependencies import get_auto_apply_campaign_service, get_opportunity_service
from api.rate_limit import RateLimiter, require_rate_limit
from api.uploads import MAX_UPLOAD_SIZE, temp_upload
from core.types import (
    OpportunityCandidateProfileImportBody,
    OpportunityCandidateBody,
    OpportunityOutcomeBody,
    OpportunityProfileSnapshotBody,
    OpportunityScanBody,
)


router = APIRouter(prefix="/api/v1/opportunities", tags=["opportunities"])
_scan_limiter = RateLimiter(2, 60)
_resume_limiter = RateLimiter(5, 60)
_auto_apply_limiter = RateLimiter(10, 60)


@router.get("")
async def list_opportunities(
    candidate_id: str,
    decision: str = "",
    limit: int = 100,
    service=Depends(get_opportunity_service),
):
    return await service.list_queue(candidate_id=candidate_id, decision=decision, limit=limit)


@router.get("/candidate/{candidate_id}")
async def get_candidate_constraints(
    candidate_id: str,
    service=Depends(get_opportunity_service),
):
    return await service.get_candidate(candidate_id=candidate_id)


@router.get("/candidates")
async def list_opportunity_candidates(
    service=Depends(get_opportunity_service),
):
    return await service.list_candidates()


@router.get("/candidate/{candidate_id}/application-profile")
async def candidate_application_profile_status(
    candidate_id: str,
    service=Depends(get_opportunity_service),
):
    return await service.application_profile_status(candidate_id=candidate_id)


@router.get("/candidate/{candidate_id}/application-profile/preview")
async def preview_candidate_application_profile(
    candidate_id: str,
    service=Depends(get_opportunity_service),
):
    return await service.preview_application_profile(candidate_id=candidate_id)


@router.post("/candidate/{candidate_id}/application-profile/resume/preview")
async def preview_candidate_resume(
    candidate_id: str,
    file: UploadFile = File(...),
    service=Depends(get_opportunity_service),
):
    require_rate_limit(_resume_limiter, candidate_id)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt", ".md"}:
        raise HTTPException(415, "Resume must be PDF, DOCX, TXT, or Markdown")
    if file.size and file.size > MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_SIZE // 1024 // 1024} MB)")
    async with temp_upload(file) as document_path:
        if not document_path:
            raise HTTPException(400, "Resume file is required")
        return await service.preview_candidate_resume(
            candidate_id=candidate_id,
            document_path=document_path,
        )


@router.post("/candidate/{candidate_id}/application-profile/resume/confirm")
async def confirm_candidate_resume(
    candidate_id: str,
    body: OpportunityCandidateProfileImportBody,
    service=Depends(get_opportunity_service),
):
    return await service.confirm_candidate_resume(
        candidate_id=candidate_id,
        profile=body.profile,
        identity=body.identity.model_dump(),
        expected_payload_sha256=body.expected_payload_sha256,
    )


@router.post("/candidate/{candidate_id}/application-profile/snapshot")
async def snapshot_candidate_application_profile(
    candidate_id: str,
    body: OpportunityProfileSnapshotBody,
    service=Depends(get_opportunity_service),
):
    return await service.snapshot_application_profile(
        candidate_id=candidate_id,
        identity=body.identity.model_dump(),
        expected_payload_sha256=body.expected_payload_sha256,
    )


@router.put("/candidate/{candidate_id}")
async def save_candidate_constraints(
    candidate_id: str,
    body: OpportunityCandidateBody,
    service=Depends(get_opportunity_service),
):
    return await service.save_candidate(candidate_id=candidate_id, payload=body.model_dump())


@router.post("/scan")
async def start_opportunity_scan(
    body: OpportunityScanBody,
    request: Request,
    service=Depends(get_opportunity_service),
):
    require_rate_limit(_scan_limiter, body.candidate_id)
    manager = getattr(request.app.state, "connection_manager", None)
    notify = manager.broadcast if manager is not None else None
    return await service.start_scan(
        candidate_id=body.candidate_id,
        target_limit=body.target_limit,
        max_concurrency=body.max_concurrency,
        notify=notify,
    )


@router.get("/scan/status")
async def opportunity_scan_status(
    candidate_id: str,
    service=Depends(get_opportunity_service),
):
    return await service.scan_status(candidate_id=candidate_id)


@router.get("/providers")
async def opportunity_provider_status(
    service=Depends(get_opportunity_service),
):
    return await service.provider_status()


@router.get("/coverage")
async def opportunity_coverage_status(
    candidate_id: str,
    service=Depends(get_opportunity_service),
):
    return await service.coverage_status(candidate_id=candidate_id)


@router.get("/metrics")
async def opportunity_funnel_metrics(
    candidate_id: str,
    service=Depends(get_opportunity_service),
):
    return await service.funnel_metrics(candidate_id=candidate_id)


@router.get("/cohort/metrics")
async def opportunity_cohort_metrics(
    service=Depends(get_opportunity_service),
):
    return await service.cohort_metrics()


@router.get("/events")
async def list_opportunity_events(
    candidate_id: str,
    opportunity_id: str = "",
    limit: int = 500,
    service=Depends(get_opportunity_service),
):
    return await service.list_events(
        candidate_id=candidate_id,
        opportunity_id=opportunity_id,
        limit=limit,
    )


@router.post("/{opportunity_id}/track")
async def track_opportunity_application(
    opportunity_id: str,
    candidate_id: str,
    service=Depends(get_opportunity_service),
):
    return await service.track_application(candidate_id=candidate_id, opportunity_id=opportunity_id)


@router.post("/{opportunity_id}/auto-apply")
async def auto_apply_to_opportunity(
    opportunity_id: str,
    candidate_id: str,
    service=Depends(get_auto_apply_campaign_service),
):
    require_rate_limit(_auto_apply_limiter, candidate_id)
    return await service.apply(candidate_id=candidate_id, opportunity_id=opportunity_id)


@router.post("/{opportunity_id}/outcomes")
async def record_opportunity_outcome(
    opportunity_id: str,
    candidate_id: str,
    body: OpportunityOutcomeBody,
    service=Depends(get_opportunity_service),
):
    return await service.record_outcome(
        candidate_id=candidate_id,
        opportunity_id=opportunity_id,
        **body.model_dump(),
    )


@router.get("/{opportunity_id}")
async def get_opportunity(
    opportunity_id: str,
    candidate_id: str,
    service=Depends(get_opportunity_service),
):
    return await service.get_detail(candidate_id=candidate_id, opportunity_id=opportunity_id)
