from __future__ import annotations

import asyncio
import csv
import io
import os
import re

from fastapi import APIRouter, HTTPException
from fastapi import Depends
from fastapi.responses import FileResponse, StreamingResponse

from api.dependencies import get_generation_service, get_job_runner, get_ranking_service, get_repository
from api.rate_limit import RateLimiter, require_rate_limit
from core.types import FeedbackBody, FollowupBody, ManualLeadBody, StatusBody
from data.repository import Repository

MANUAL_FEEDBACK_TIMEOUT_SECONDS = 8


def annotate_job_lead(lead: dict) -> dict:
    from gateway.lead_adapters import classify_job_seniority

    meta = dict(lead.get("source_meta") or {})
    level = str(meta.get("seniority_level") or lead.get("seniority_level") or "").strip().lower()
    if level not in {"fresher", "junior", "mid", "senior", "unknown"}:
        level = classify_job_seniority(lead)
    meta["seniority_level"] = level
    meta["is_beginner"] = level in {"fresher", "junior"}
    return {**lead, "source_meta": meta, "seniority_level": level}


def versioned_assets(job_id: str, base_dir: str) -> list[dict]:
    versions: dict[int, dict] = {}
    patterns = [
        ("resume", re.compile(rf"^{re.escape(job_id)}_v(\d+)\.pdf$")),
        ("cover_letter", re.compile(rf"^{re.escape(job_id)}_cl_v(\d+)\.pdf$")),
    ]
    try:
        names = os.listdir(base_dir)
    except Exception:
        return []
    for name in names:
        full = os.path.join(base_dir, name)
        if not os.path.isfile(full):
            continue
        for key, pattern in patterns:
            match = pattern.match(name)
            if match:
                version = int(match.group(1))
                versions.setdefault(version, {"version": version})[key] = full
    return [versions[version] for version in sorted(versions, reverse=True)]


def create_router(manager) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["leads"])
    manual_limiter = RateLimiter(10, 60)

    def _safe_job_id(job_id: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_\-]{1,128}$", job_id):
            raise HTTPException(status_code=400, detail="Invalid job ID format")
        return job_id

    @router.get("/leads")
    async def leads(
        page: int | None = None,
        limit: int = 200,
        beginner_only: bool = False,
        seniority: str | None = None,
        status: str | None = None,
        min_score: int | None = None,
        repo: Repository = Depends(get_repository),
    ):
        jobs = [annotate_job_lead(lead) for lead in repo.leads.get_all_leads() if (lead.get("kind") or "job") == "job"]
        requested = str(seniority or "").strip().lower()
        if beginner_only or requested == "beginner":
            jobs = [lead for lead in jobs if lead.get("seniority_level") in {"fresher", "junior"}]
        elif requested in {"fresher", "junior", "mid", "senior", "unknown"}:
            jobs = [lead for lead in jobs if lead.get("seniority_level") == requested]
        if status:
            jobs = [lead for lead in jobs if str(lead.get("status") or "") == status]
        if min_score is not None:
            jobs = [lead for lead in jobs if int(lead.get("score") or 0) >= min_score]
        if page is None:
            return jobs
        page = max(1, page)
        limit = max(1, min(limit, 1000))
        total = len(jobs)
        start = (page - 1) * limit
        return {"items": jobs[start:start + limit], "total": total, "page": page, "limit": limit, "pages": (total + limit - 1) // limit}

    @router.get("/leads/export.csv")
    async def export_leads_csv(repo: Repository = Depends(get_repository)):
        rows = repo.leads.get_all_leads()
        fields = [
            "job_id",
            "title",
            "company",
            "url",
            "platform",
            "status",
            "score",
            "signal_score",
            "seniority_level",
            "location",
            "reason",
            "created_at",
        ]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=jhm_pipeline.csv"},
        )

    @router.get("/leads/{job_id}/versions")
    async def get_lead_versions(job_id: str, repo: Repository = Depends(get_repository)):
        job_id = _safe_job_id(job_id)
        lead = repo.leads.get_lead_by_id(job_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        paths = [
            lead.get("resume_asset") or lead.get("asset") or "",
            lead.get("cover_letter_asset") or "",
        ]
        base_dir = next((os.path.dirname(path) for path in paths if path), None)
        if not base_dir:
            base_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "JustHireMe", "assets")
        return versioned_assets(job_id, base_dir)

    @router.get("/leads/{job_id}")
    async def get_lead(job_id: str, repo: Repository = Depends(get_repository)):
        job_id = _safe_job_id(job_id)
        lead = repo.leads.get_lead_by_id(job_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        return annotate_job_lead(lead) if (lead.get("kind") or "job") == "job" else lead

    @router.delete("/leads/{job_id}")
    async def delete_lead_endpoint(job_id: str, repo: Repository = Depends(get_repository)):
        job_id = _safe_job_id(job_id)
        try:
            repo.leads.delete_lead(job_id)
        except LookupError:
            raise HTTPException(status_code=404, detail="lead not found")
        return {"ok": True}

    @router.put("/leads/{job_id}/status")
    async def update_status(job_id: str, body: StatusBody, repo: Repository = Depends(get_repository)):
        job_id = _safe_job_id(job_id)
        try:
            repo.leads.update_lead_status(job_id, body.status)
            await manager.broadcast({"type": "LEAD_UPDATED", "data": {"job_id": job_id, "status": body.status}})
            return {"ok": True}
        except LookupError:
            raise HTTPException(status_code=404, detail="lead not found")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.put("/leads/{job_id}/feedback")
    async def update_feedback(job_id: str, body: FeedbackBody, repo: Repository = Depends(get_repository)):
        job_id = _safe_job_id(job_id)
        try:
            lead = repo.leads.save_lead_feedback(job_id, body.feedback, body.note)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        await manager.broadcast({"type": "LEAD_UPDATED", "data": lead})
        return lead

    @router.put("/leads/{job_id}/followup")
    async def update_followup(job_id: str, body: FollowupBody, repo: Repository = Depends(get_repository)):
        job_id = _safe_job_id(job_id)
        from datetime import datetime, timedelta, timezone

        days = max(1, min(int(body.days or 5), 60))
        now = datetime.now(timezone.utc).isoformat()
        due = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        lead = repo.leads.update_lead_followup(job_id, now, due)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        await manager.broadcast({"type": "LEAD_UPDATED", "data": lead})
        return lead

    @router.post("/leads/manual")
    async def create_manual_lead(
        body: ManualLeadBody,
        repo: Repository = Depends(get_repository),
        ranking_service=Depends(get_ranking_service),
    ):
        require_rate_limit(manual_limiter)
        if not body.text.strip() and not body.url.strip():
            raise HTTPException(status_code=400, detail="Paste lead text or a URL")
        from gateway.lead_adapters import manual_lead_from_text

        raw_lead = manual_lead_from_text(body.text, body.url, "job")
        examples = repo.feedback.get_feedback_training_examples()
        try:
            lead = await asyncio.wait_for(
                ranking_service.apply_feedback(raw_lead, examples),
                timeout=MANUAL_FEEDBACK_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            meta = dict(raw_lead.get("source_meta") or {})
            meta["feedback_learning_error"] = str(exc) or "timed out"
            lead = {**raw_lead, "source_meta": meta}
        if lead.get("kind") != "job":
            raise HTTPException(status_code=422, detail="Only job leads are accepted right now")
        lead = annotate_job_lead(lead)
        repo.leads.save_lead(lead)
        saved = repo.leads.get_lead_by_id(lead["job_id"]) or lead
        await manager.broadcast({"type": "LEAD_UPDATED", "data": saved})
        return saved

    @router.post("/leads/manual/generate/start")
    async def create_manual_lead_and_start_generation(
        body: ManualLeadBody,
        repo: Repository = Depends(get_repository),
        service=Depends(get_generation_service),
        job_store=Depends(get_job_runner),
    ):
        require_rate_limit(manual_limiter)
        if not body.text.strip() and not body.url.strip():
            raise HTTPException(status_code=400, detail="Paste lead text or a URL")
        from api.routers.generation import generate_one
        from gateway.lead_adapters import manual_lead_from_text

        raw_lead = manual_lead_from_text(body.text, body.url, "job")
        if raw_lead.get("kind") != "job":
            raise HTTPException(status_code=422, detail="Only job leads are accepted right now")
        lead = annotate_job_lead(raw_lead)
        queued_lead = {**lead, "status": "tailoring"}

        async def _run():
            try:
                await asyncio.to_thread(repo.leads.save_lead, lead)
                try:
                    await asyncio.to_thread(repo.leads.update_lead_status, lead["job_id"], "tailoring")
                except Exception:
                    pass
                saved = await asyncio.to_thread(repo.leads.get_lead_by_id, lead["job_id"])
                await manager.broadcast({"type": "LEAD_UPDATED", "data": saved or queued_lead})
                await generate_one(lead["job_id"], manager, repo=repo, service=service, job_store=job_store)
            except Exception as exc:
                failed = {**queued_lead, "status": "discovered"}
                meta = dict(failed.get("source_meta") or {})
                meta["generation_error"] = str(exc)
                failed["source_meta"] = meta
                await manager.broadcast({"type": "LEAD_UPDATED", "data": failed})
                await manager.broadcast({
                    "type": "agent",
                    "event": "gen_error",
                    "msg": f"Generation failed for {lead.get('title','?')}: {exc}",
                })

        asyncio.create_task(_run())
        await manager.broadcast({"type": "LEAD_UPDATED", "data": queued_lead})
        return {"status": "started", "job_id": lead["job_id"], "lead": queued_lead}

    @router.get("/followups/due")
    async def due_followups(limit: int = 25, repo: Repository = Depends(get_repository)):
        from datetime import datetime, timezone

        return repo.leads.get_due_followups(limit, datetime.now(timezone.utc).isoformat())

    @router.get("/leads/{job_id}/pdf")
    async def get_lead_pdf(
        job_id: str,
        kind: str = "resume",
        version: int | None = None,
        repo: Repository = Depends(get_repository),
    ):
        job_id = _safe_job_id(job_id)
        lead = repo.leads.get_lead_by_id(job_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        is_cover = kind in {"cover", "cover_letter", "cover-letter"}
        if version is not None:
            paths = [
                lead.get("resume_asset") or lead.get("asset") or "",
                lead.get("cover_letter_asset") or "",
            ]
            base_dir = next((os.path.dirname(path) for path in paths if path), None)
            if not base_dir:
                base_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "JustHireMe", "assets")
            filename = f"{job_id}_cl_v{version}.pdf" if is_cover else f"{job_id}_v{version}.pdf"
            path = os.path.join(base_dir, filename)
            missing = "Cover letter not generated yet" if is_cover else "Resume not generated yet"
        elif is_cover:
            path = lead.get("cover_letter_asset") or ""
            filename = f"{job_id}_cover_letter.pdf"
            missing = "Cover letter not generated yet"
        else:
            path = lead.get("resume_asset") or lead.get("asset") or ""
            filename = f"{job_id}_resume.pdf"
            missing = "Resume not generated yet"
        if not path or not os.path.exists(path):
            raise HTTPException(status_code=404, detail=missing)
        return FileResponse(path, media_type="application/pdf", filename=filename)

    return router
