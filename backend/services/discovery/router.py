from __future__ import annotations

from fastapi import APIRouter, Depends

from contracts.discovery import DiscoveryPlanRequest, DiscoveryPlanResponse, DiscoveryRunResponse, DiscoveryScanRequest
from discovery.service import DiscoveryService
from services.auth import require_internal_token
from services.discovery.dependencies import get_discovery_service


router = APIRouter(prefix="/internal/v1/discovery", dependencies=[Depends(require_internal_token)])


def _dump(value):
    return value.model_dump() if hasattr(value, "model_dump") else value


@router.post("/plan", response_model=DiscoveryPlanResponse)
async def plan(body: DiscoveryPlanRequest, service: DiscoveryService = Depends(get_discovery_service)):
    return DiscoveryPlanResponse(urls=await service.plan_board_targets(_dump(body.profile), body.raw_urls, body.market_focus))


@router.post("/scan", response_model=DiscoveryRunResponse)
async def scan(body: DiscoveryScanRequest, service: DiscoveryService = Depends(get_discovery_service)):
    result = await service.scan_job_boards(body.urls, body.cfg)
    return DiscoveryRunResponse(leads=result.leads, usage=result.usage, errors=result.errors)


@router.post("/free-sources", response_model=DiscoveryRunResponse)
async def free_sources(body: DiscoveryScanRequest, service: DiscoveryService = Depends(get_discovery_service)):
    result = await service.scan_free_sources(body.cfg, kind_filter=body.kind_filter, profile=_dump(body.profile), force=body.force)
    return DiscoveryRunResponse(leads=result.leads, usage=result.usage, errors=result.errors)


@router.post("/x", response_model=DiscoveryRunResponse)
async def x(body: DiscoveryScanRequest, service: DiscoveryService = Depends(get_discovery_service)):
    result = await service.scan_x(body.cfg, kind_filter=body.kind_filter or "job", profile=_dump(body.profile))
    return DiscoveryRunResponse(leads=result.leads, usage=result.usage, errors=result.errors)
