from __future__ import annotations

import base64

from fastapi import APIRouter, Depends

from contracts.profile import (
    ProfileImportRequest,
    ProfileIngestGithubRequest,
    ProfileIngestLinkedInRequest,
    ProfileIngestPortfolioRequest,
    ProfileIngestResumeRequest,
)
from core.types import CandidateBody, ExperienceBody, IdentityBody, ProfileEntryBody, ProjectBody, SkillBody
from profile.service import ProfileService
from services.auth import require_internal_token
from services.profile.dependencies import get_profile_service


router = APIRouter(prefix="/internal/v1/profile", dependencies=[Depends(require_internal_token)])


@router.get("")
async def get_profile(service: ProfileService = Depends(get_profile_service)):
    return service.get_profile()


@router.put("/candidate")
async def update_candidate(body: CandidateBody, service: ProfileService = Depends(get_profile_service)):
    return service.update_candidate(body.n, body.s)


@router.put("/identity")
async def update_identity(body: IdentityBody, service: ProfileService = Depends(get_profile_service)):
    return service.update_identity(body.model_dump())


@router.post("/skill")
async def add_skill(body: SkillBody, service: ProfileService = Depends(get_profile_service)):
    return service.add_skill(body.n, body.cat)


@router.put("/skill/{sid}")
async def update_skill(sid: str, body: SkillBody, service: ProfileService = Depends(get_profile_service)):
    return service.update_skill(sid, body.n, body.cat)


@router.delete("/skill/{sid}")
async def delete_skill(sid: str, service: ProfileService = Depends(get_profile_service)):
    service.delete_skill(sid)
    return {"ok": True}


@router.post("/experience")
async def add_experience(body: ExperienceBody, service: ProfileService = Depends(get_profile_service)):
    return service.add_experience(body.role, body.co, body.period, body.d)


@router.put("/experience/{eid}")
async def update_experience(eid: str, body: ExperienceBody, service: ProfileService = Depends(get_profile_service)):
    return service.update_experience(eid, body.role, body.co, body.period, body.d)


@router.delete("/experience/{eid}")
async def delete_experience(eid: str, service: ProfileService = Depends(get_profile_service)):
    service.delete_experience(eid)
    return {"ok": True}


@router.post("/project")
async def add_project(body: ProjectBody, service: ProfileService = Depends(get_profile_service)):
    return service.add_project(body.title, body.stack, body.repo, body.impact)


@router.put("/project/{pid}")
async def update_project(pid: str, body: ProjectBody, service: ProfileService = Depends(get_profile_service)):
    return service.update_project(pid, body.title, body.stack, body.repo, body.impact)


@router.delete("/project/{pid}")
async def delete_project(pid: str, service: ProfileService = Depends(get_profile_service)):
    service.delete_project(pid)
    return {"ok": True}


@router.post("/education")
async def add_education(body: ProfileEntryBody, service: ProfileService = Depends(get_profile_service)):
    return service.add_education(body.title)


@router.post("/certification")
async def add_certification(body: ProfileEntryBody, service: ProfileService = Depends(get_profile_service)):
    return service.add_certification(body.title)


@router.post("/achievement")
async def add_achievement(body: ProfileEntryBody, service: ProfileService = Depends(get_profile_service)):
    return service.add_achievement(body.title)


@router.post("/ingest/resume")
async def ingest_resume(body: ProfileIngestResumeRequest, service: ProfileService = Depends(get_profile_service)):
    result = await service.ingest_resume(body.raw, body.pdf_path)
    return result.model_dump() if hasattr(result, "model_dump") else result


@router.post("/ingest/github")
async def ingest_github(body: ProfileIngestGithubRequest, service: ProfileService = Depends(get_profile_service)):
    return await service.ingest_github(body.username, token=body.token, max_repos=body.max_repos)


@router.post("/ingest/linkedin")
async def ingest_linkedin(body: ProfileIngestLinkedInRequest, service: ProfileService = Depends(get_profile_service)):
    return await service.ingest_linkedin(base64.b64decode(body.zip_b64.encode("ascii")))


@router.post("/ingest/portfolio")
async def ingest_portfolio(body: ProfileIngestPortfolioRequest, service: ProfileService = Depends(get_profile_service)):
    return await service.ingest_portfolio(body.url, auto_import=body.auto_import)


@router.post("/import")
async def import_profile(body: ProfileImportRequest, service: ProfileService = Depends(get_profile_service)):
    return await service.import_profile_data(body.payload)
