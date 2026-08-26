"""Settings API — transport only.

Masking, provider probing, catalog merging and the reset live in
``settings.service``. This module only maps HTTP to those calls, plus the one
transport-owned side effect: rescheduling the ghost job.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import APIRouter, Depends

from api.dependencies import get_settings_service
from api.scheduler import ensure_ghost_job
from core.types import PreferencesBody, ResetDataBody, SettingsBody, TemplateBody

# Re-exported for callers that imported them from this module before the
# settings business layer existed.
from settings.masking import LEGACY_MASKS, MASK, sensitive_keys  # noqa: F401


def create_router(scheduler: AsyncIOScheduler, ghost_tick) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["settings"])

    @router.get("/template")
    async def get_template(service=Depends(get_settings_service)):
        return await service.get_resume_template()

    @router.post("/template")
    async def save_template(body: TemplateBody, service=Depends(get_settings_service)):
        await service.save_resume_template(body.template)
        return {"ok": True}

    @router.get("/preferences")
    async def get_preferences(service=Depends(get_settings_service)):
        return await service.get_preferences()

    @router.post("/preferences")
    async def save_preferences(body: PreferencesBody, service=Depends(get_settings_service)):
        await service.save_preferences(body.preferences)
        return {"ok": True}

    @router.get("/settings")
    async def get_cfg(service=Depends(get_settings_service)):
        return await service.get_settings()

    @router.get("/settings/validate")
    async def validate_settings(service=Depends(get_settings_service)):
        return await service.validate_providers()

    @router.post("/settings/validate")
    async def validate_pending_settings(body: SettingsBody, service=Depends(get_settings_service)):
        return await service.validate_providers(body.model_dump())

    @router.get("/settings/models/{provider}")
    async def get_provider_models(provider: str, service=Depends(get_settings_service)):
        return await service.provider_models(provider)

    @router.post("/settings/models/{provider}")
    async def post_provider_models(provider: str, body: SettingsBody, service=Depends(get_settings_service)):
        return await service.provider_models(provider, body.model_dump())

    @router.get("/settings/subscription-status")
    async def subscription_status(service=Depends(get_settings_service)):
        return await service.subscription_status()

    @router.post("/settings/subscription-login/{provider}")
    async def subscription_login(provider: str, service=Depends(get_settings_service)):
        return await service.subscription_login(provider)

    @router.post("/settings")
    async def save_cfg(body: SettingsBody, service=Depends(get_settings_service)):
        ghost_enabled = await service.save_settings(body.model_dump())
        if ghost_enabled:
            ensure_ghost_job(scheduler, ghost_tick)
        return {"ok": True}

    @router.post("/data/reset")
    async def reset_data(body: ResetDataBody, service=Depends(get_settings_service)):
        """Danger zone: requires confirm=DELETE (validated by ResetDataBody)."""
        summary = await service.reset_data(clear_settings=body.clear_settings)
        return {"ok": True, "summary": summary}

    return router
