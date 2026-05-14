from __future__ import annotations

from fastapi import APIRouter, Depends

from automation.service import AutomationService
from contracts.automation import AutomationFormReadRequest, AutomationPreviewRequest
from services.auth import require_internal_token
from services.automation.dependencies import get_automation_service


router = APIRouter(prefix="/internal/v1/automation", dependencies=[Depends(require_internal_token)])


def _dump(value):
    return value.model_dump() if hasattr(value, "model_dump") else value


@router.post("/form-read")
async def form_read(body: AutomationFormReadRequest, service: AutomationService = Depends(get_automation_service)):
    return await service.read_form(body.url, body.identity, cover_letter=body.cover_letter)


@router.post("/preview-apply")
async def preview(body: AutomationPreviewRequest, service: AutomationService = Depends(get_automation_service)):
    return await service.preview_application(_dump(body.lead), body.asset)


@router.post("/fire")
async def fire(body: AutomationPreviewRequest, service: AutomationService = Depends(get_automation_service)):
    return {"ok": await service.submit_application(_dump(body.lead), body.asset)}


@router.post("/selectors/refresh")
async def refresh_selectors(service: AutomationService = Depends(get_automation_service)):
    data = await service.refresh_selectors()
    return {"version": data.get("version"), "platforms": list(data.get("platforms", {}).keys())}
