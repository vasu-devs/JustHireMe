"""Knowledge-graph API — transport only.

The payload is built by the graph business layer (``graph_service.stats``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_graph_service

router = APIRouter(prefix="/api/v1", tags=["graph"])


@router.get("/graph")
async def graph_stats(repair: bool = False, service=Depends(get_graph_service)):
    return await service.stats(repair=repair)
