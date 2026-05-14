from __future__ import annotations

import json
import os
import shutil
import tempfile
import contextlib
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from api.rate_limit import RateLimiter, require_rate_limit
from api.dependencies import get_profile_service
from core.types import StrictBody
from gateway.clients.base import ServiceRequestError, ServiceTimeout, ServiceUnavailable

MAX_UPLOAD_SIZE = 10 * 1024 * 1024


class GithubIngestBody(StrictBody):
    username: str = Field(max_length=100)
    token: str = Field(default="", max_length=200)
    max_repos: int = Field(default=100, ge=1, le=500)


class PortfolioIngestBody(StrictBody):
    url: str = Field(max_length=2000)
    auto_import: bool = Field(
        default=False,
        description="if true, immediately write extracted data to the graph",
    )


class ProfileSkill(BaseModel):
    name: str = Field(max_length=160)
    category: str = Field(default="general", max_length=80)


class ProfileExperience(BaseModel):
    role: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)
    period: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=5000)


class ProfileProject(BaseModel):
    title: str = Field(default="", max_length=200)
    stack: str = Field(default="", max_length=500)
    repo: str = Field(default="", max_length=500)
    impact: str = Field(default="", max_length=1000)


class ProfileEntry(BaseModel):
    title: str = Field(max_length=500)


class ProfileIdentity(BaseModel):
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=50)
    linkedin_url: str = Field(default="", max_length=500)
    github_url: str = Field(default="", max_length=500)
    website_url: str = Field(default="", max_length=500)
    city: str = Field(default="", max_length=200)


class ProfileCandidate(BaseModel):
    name: str = Field(default="", max_length=160)
    summary: str = Field(default="", max_length=4000)


class ProfileImportBody(BaseModel):
    """Accepts any subset of fields - all are optional."""

    candidate: ProfileCandidate = Field(default_factory=ProfileCandidate)
    identity: ProfileIdentity = Field(default_factory=ProfileIdentity)
    skills: list[ProfileSkill] = Field(default_factory=list)
    experience: list[ProfileExperience] = Field(default_factory=list)
    projects: list[ProfileProject] = Field(default_factory=list)
    education: list[ProfileEntry] = Field(default_factory=list)
    certifications: list[ProfileEntry] = Field(default_factory=list)
    achievements: list[ProfileEntry] = Field(default_factory=list)


@contextlib.contextmanager
def _temp_upload(file: UploadFile | None):
    if not file or not file.filename:
        yield None
        return
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.close()
        yield tmp.name
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp.name)


def create_router(manager, logger) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["ingestion"])
    ingest_limiter = RateLimiter(5, 60)

    @router.post("/ingest")
    async def ingest(
        raw: str = Form(""),
        file: UploadFile | None = File(None),
    ):
        require_rate_limit(ingest_limiter)
        if file and file.filename and file.size and file.size > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_SIZE // 1024 // 1024} MB)")
        try:
            with _temp_upload(file) as pdf_path:
                profile = await get_profile_service().ingest_resume(raw, pdf_path)
                if isinstance(profile, dict):
                    profile_payload = profile
                    skill_count = len(profile.get("skills", []))
                    profile_name = profile.get("n", "")
                else:
                    profile_payload = profile.model_dump()
                    skill_count = len(profile.skills)
                    profile_name = profile.n
                await manager.broadcast({
                    "type": "agent",
                    "event": "ingested",
                    "msg": f"Profile ingested: {profile_name} - {skill_count} skills",
                })
                return profile_payload
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/ingest/linkedin")
    async def ingest_linkedin(file: UploadFile = File(...)):
        if not (file.filename or "").endswith(".zip"):
            raise HTTPException(400, "expected a .zip file from LinkedIn data export")
        raw = await file.read()
        if len(raw) > 50 * 1024 * 1024:
            raise HTTPException(413, "file too large")
        try:
            return await get_profile_service().ingest_linkedin(raw)
        except Exception as exc:
            logger.error("linkedin parse failed: %s", exc)
            raise HTTPException(422, f"could not parse linkedin export: {exc}")

    @router.post("/ingest/github")
    async def ingest_github_endpoint(body: GithubIngestBody):
        result = await get_profile_service().ingest_github(
            body.username,
            token=body.token or None,
            max_repos=body.max_repos,
        )
        if "error" in result:
            status_code = int(result.get("status_code") or (404 if result.get("error_kind") == "not_found" else 502))
            raise HTTPException(status_code, result["error"])
        return result

    @router.post("/ingest/profile")
    async def import_profile_json(body: ProfileImportBody):
        return await get_profile_service().import_profile_data(body)

    @router.get("/ingest/profile/template")
    async def get_profile_template():
        template_path = Path(__file__).resolve().parents[2] / "data" / "profile_schema_example.json"
        with open(template_path, encoding="utf-8") as file:
            return json.load(file)

    @router.post("/ingest/portfolio")
    async def ingest_portfolio_endpoint(body: PortfolioIngestBody):
        if not body.url.startswith(("http://", "https://")):
            raise HTTPException(400, "url must start with http:// or https://")
        try:
            result = await get_profile_service().ingest_portfolio(body.url, auto_import=body.auto_import)
        except ServiceTimeout as exc:
            raise HTTPException(504, str(exc))
        except ServiceUnavailable as exc:
            raise HTTPException(503, str(exc))
        except ServiceRequestError as exc:
            raise HTTPException(502, str(exc))
        if result.get("error") and not result.get("screenshot_b64"):
            raise HTTPException(int(result.get("status_code") or 422), result["error"])
        if result.get("imported"):
            result["import_stats"] = result["imported"]["stats"]
            result["import_errors"] = result["imported"]["errors"]
        return result

    return router
