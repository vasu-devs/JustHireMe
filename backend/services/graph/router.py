from __future__ import annotations

from fastapi import APIRouter, Depends

from contracts.graph import GraphStatsRequest, GraphSyncRequest
from graph_service.stats import graph_stats_payload
from services.auth import require_internal_token


router = APIRouter(prefix="/internal/v1/graph", dependencies=[Depends(require_internal_token)])


@router.post("/stats")
async def stats(body: GraphStatsRequest):
    return graph_stats_payload(repair=body.repair)


@router.get("/stats")
async def stats_get(repair: bool = False):
    return graph_stats_payload(repair=repair)


@router.post("/sync-leads")
async def sync_leads(_body: GraphSyncRequest):
    return graph_stats_payload(repair=True)


@router.post("/sync-profile")
async def sync_profile(_body: GraphSyncRequest):
    return graph_stats_payload(repair=True)


@router.post("/repair")
async def repair(_body: GraphStatsRequest):
    return graph_stats_payload(repair=True)
