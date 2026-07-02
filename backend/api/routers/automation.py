from __future__ import annotations
import logging

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import Field

from api.dependencies import get_automation_service, get_job_runner, get_repository
from core.types import StrictBody
from data.repository import Repository

_log = logging.getLogger(__name__)


class FormReadBody(StrictBody):
    url: str = Field(default="", max_length=2000)


def resolve_cover_letter_text(asset_path: str, logger) -> str:
    """Resolve cover letter *text* from a stored asset path (H3).

    The asset path may point at a ``.pdf`` or ``.md`` artifact. Form-fill needs
    the text, so we prefer the ``.md`` sibling and only read text-like files —
    never the raw PDF bytes, and never the path string itself. Returns "" (with
    a warning) when no readable text file exists.
    """
    if not asset_path:
        return ""
    asset = Path(asset_path)
    md_path = asset.with_suffix(".md")
    for candidate in (md_path, asset):
        try:
            if candidate.suffix.lower() in {".md", ".txt"} and candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("could not read cover letter %s: %s", candidate, exc)
            return ""
    logger.warning(
        "no readable cover letter text for asset %s (.pdf exists=%s)",
        asset_path,
        asset.is_file() and asset.suffix.lower() == ".pdf",
    )
    return ""


def asset_ready(path: str) -> bool:
    return bool(path) and os.path.isfile(path)


def fire_blocker(lead: dict, asset: str) -> tuple[int, str]:
    if not lead:
        return 404, "Lead not found"
    if lead.get("status") == "applied":
        return 409, "Lead is already marked applied"
    if not lead.get("url"):
        return 409, "Lead has no application URL"
    if not asset_ready(asset):
        return 409, "Generate a resume before firing this application"
    cover = lead.get("cover_letter_asset") or lead.get("cover_letter_path") or ""
    if not asset_ready(cover):
        return 409, "Generate a cover letter before firing this application"
    return 0, ""


async def actuate_job(job_id: str, manager, repo: Repository | None = None, service=None, job_store=None) -> None:
    repo = repo or get_repository()
    service = service or get_automation_service()
    job_store = job_store or get_job_runner()
    job = job_store.create("automation_fire", {"job_id": job_id})
    try:
        job_store.update(job.job_id, status="running", progress=10)
        # Enrich with candidate identity (name/email/phone/links/cover_letter) the
        # same way the Ghost auto-apply path does — the bare get_lead_by_id row has
        # only job metadata, so the actuator would fill every identity field blank.
        lead, asset = await service.get_lead_for_fire(job_id)
        _status, detail = fire_blocker(lead, asset)
        if detail:
            await manager.broadcast({
                "type": "agent",
                "event": "failed",
                "job_id": job_id,
                "msg": f"Submission blocked for {job_id}: {detail}",
            })
            job_store.update(job.job_id, status="failed", error=detail)
            return

        await manager.broadcast({
            "type": "agent",
            "event": "actuating",
            "job_id": job_id,
            "msg": f"Opening browser for {lead.get('title','')} @ {lead.get('company','')}",
        })
        ok = await service.submit_application(lead, asset)
    except Exception as exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/api/routers/automation.py:actuate_job: %s', exc)
        await manager.broadcast({
            "type": "agent",
            "event": "failed",
            "job_id": job_id,
            "msg": f"Submission failed for {job_id}: {exc}",
        })
        job_store.update(job.job_id, status="failed", error=str(exc))
        return

    if ok:
        await asyncio.to_thread(repo.leads.mark_applied, job_id)
        job_store.update(job.job_id, status="succeeded", progress=100)
        await manager.broadcast({
            "type": "agent",
            "event": "applied",
            "job_id": job_id,
            "msg": f"Application submitted for {job_id}",
        })
    else:
        job_store.update(job.job_id, status="failed", error="submit_application returned false")
        await manager.broadcast({
            "type": "agent",
            "event": "failed",
            "job_id": job_id,
            "msg": f"Submission failed for {job_id}",
        })


def create_router(manager) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["automation"])

    @router.post("/fire/{job_id}")
    async def fire(
        job_id: str,
        bt: BackgroundTasks,
        repo: Repository = Depends(get_repository),
        service=Depends(get_automation_service),
    ):
        lead = await asyncio.to_thread(repo.leads.get_lead_by_id, job_id)
        asset = (lead or {}).get("resume_asset") or (lead or {}).get("asset") or ""
        status, detail = fire_blocker(lead, asset)
        if detail:
            raise HTTPException(status_code=status, detail=detail)
        bt.add_task(actuate_job, job_id, manager, repo, service)
        return {"status": "firing", "job_id": job_id}

    @router.post("/leads/{job_id}/form/read")
    async def read_lead_form(
        job_id: str,
        body: FormReadBody,
        repo: Repository = Depends(get_repository),
        service=Depends(get_automation_service),
    ):
        lead = repo.leads.get_lead_by_id(job_id)
        if not lead:
            raise HTTPException(404, "lead not found")

        url = (body.url or lead.get("url") or "").strip()
        if not url:
            raise HTTPException(400, "no url available for this lead")

        profile = repo.profile.get_profile()
        cfg = repo.settings.get_settings()
        # The profile is FLAT: the candidate name is profile["n"], not a "candidate"
        # sub-dict (there is none), and no "full_name" setting is ever written. Read
        # it the way get_lead_for_fire_sync does, else the form-read preview shows a
        # blank name/first/last for a fully-configured candidate.
        candidate_name = str(profile.get("n") or "").strip() if isinstance(profile, dict) else ""
        identity = {
            "name": cfg.get("full_name", "") or candidate_name,
            "email": cfg.get("email", ""),
            "phone": cfg.get("phone", ""),
            "linkedin_url": cfg.get("linkedin_url", ""),
            "github": cfg.get("github_url", ""),
            "website": cfg.get("website_url", ""),
            "city": cfg.get("city", ""),
            "current_company": cfg.get("current_company", ""),
        }

        cover_letter = resolve_cover_letter_text(lead.get("cover_letter_asset", ""), _log)

        return await service.read_form(url, identity, cover_letter=cover_letter)

    @router.get("/identity")
    async def get_identity(repo: Repository = Depends(get_repository)):
        cfg = repo.settings.get_settings()
        return {
            "full_name": cfg.get("full_name", ""),
            "email": cfg.get("email", ""),
            "phone": cfg.get("phone", ""),
            "linkedin_url": cfg.get("linkedin_url", ""),
            "github_url": cfg.get("github_url", ""),
            "website_url": cfg.get("website_url", ""),
            "city": cfg.get("city", ""),
            "current_company": cfg.get("current_company", ""),
        }

    @router.post("/selectors/refresh")
    async def refresh_selectors(service=Depends(get_automation_service)):
        data = await service.refresh_selectors()
        return {"version": data.get("version"), "platforms": list(data.get("platforms", {}).keys())}

    @router.post("/leads/{job_id}/apply/preview")
    async def preview_apply(
        job_id: str,
        service=Depends(get_automation_service),
    ):
        # Enrich with candidate identity like the fire path, else the preview
        # renders every name/email/phone field blank.
        lead, asset = await service.get_lead_for_fire(job_id)
        status_code, detail = fire_blocker(lead, asset)
        if detail:
            raise HTTPException(status_code=status_code, detail=detail)
        return await service.preview_application(lead, asset)

    return router
