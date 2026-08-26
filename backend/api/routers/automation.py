"""Application-automation API — transport only.

Form reading, identity assembly and submission live in ``automation.service``.
This module supplies the WebSocket fan-out callback and nothing else.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import Field

from api.dependencies import get_automation_service
from core.types import StrictBody

# Re-exported: api.scheduler and the regression suite import these from here.
from automation.service import (  # noqa: F401
    asset_ready,
    fire_blocker,
    resolve_cover_letter_text,
)


class FormReadBody(StrictBody):
    url: str = Field(default="", max_length=2000)


def create_router(manager) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["automation"])

    async def _notify(message: dict) -> None:
        await manager.broadcast(message)

    @router.post("/fire/{job_id}")
    async def fire(job_id: str, bt: BackgroundTasks, service=Depends(get_automation_service)):
        await service.check_can_fire(job_id)
        bt.add_task(service.actuate, job_id, _notify)
        return {"status": "firing", "job_id": job_id}

    @router.post("/leads/{job_id}/form/read")
    async def read_lead_form(job_id: str, body: FormReadBody, service=Depends(get_automation_service)):
        return await service.read_lead_form(job_id, body.url)

    @router.post("/selectors/refresh")
    async def refresh_selectors(service=Depends(get_automation_service)):
        data = await service.refresh_selectors()
        return {"version": data.get("version"), "platforms": list(data.get("platforms", {}).keys())}

    @router.post("/leads/{job_id}/apply/preview")
    async def preview_apply(job_id: str, service=Depends(get_automation_service)):
        return await service.preview_apply(job_id)

    return router
