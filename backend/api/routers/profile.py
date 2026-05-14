from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_profile_service
from core.types import CandidateBody, ExperienceBody, IdentityBody, ProfileEntryBody, ProjectBody, SkillBody


router = APIRouter(prefix="/api/v1", tags=["profile"])


@router.get("/profile")
async def get_profile_endpoint(service=Depends(get_profile_service)):
    return await _maybe_await(service.get_profile())


@router.put("/profile/candidate")
async def update_candidate_endpoint(body: CandidateBody, service=Depends(get_profile_service)):
    if not body.n.strip() and not body.s.strip():
        raise HTTPException(status_code=422, detail="Name or summary is required")
    return await _maybe_await(service.update_candidate(body.n, body.s))


@router.put("/profile/identity")
async def update_identity_endpoint(body: IdentityBody, service=Depends(get_profile_service)):
    return await _maybe_await(service.update_identity(body.model_dump()))


@router.post("/profile/skill")
async def add_skill_endpoint(body: SkillBody, service=Depends(get_profile_service)):
    if not body.n.strip():
        raise HTTPException(status_code=422, detail="Skill name is required")
    return await _maybe_await(service.add_skill(body.n, body.cat))


@router.put("/profile/skill/{sid}")
async def update_skill_endpoint(sid: str, body: SkillBody, service=Depends(get_profile_service)):
    if not body.n.strip():
        raise HTTPException(status_code=422, detail="Skill name is required")
    return await _maybe_await(service.update_skill(sid, body.n, body.cat))


@router.delete("/profile/skill/{sid}")
async def delete_skill_endpoint(sid: str, service=Depends(get_profile_service)):
    await _maybe_await(service.delete_skill(sid))
    return {"ok": True}


@router.post("/profile/experience")
async def add_experience_endpoint(body: ExperienceBody, service=Depends(get_profile_service)):
    if not body.role.strip() and not body.co.strip():
        raise HTTPException(status_code=422, detail="Role or company is required")
    return await _maybe_await(service.add_experience(body.role, body.co, body.period, body.d))


@router.put("/profile/experience/{eid}")
async def update_experience_endpoint(eid: str, body: ExperienceBody, service=Depends(get_profile_service)):
    if not body.role.strip() and not body.co.strip():
        raise HTTPException(status_code=422, detail="Role or company is required")
    return await _maybe_await(service.update_experience(eid, body.role, body.co, body.period, body.d))


@router.delete("/profile/experience/{eid}")
async def delete_experience_endpoint(eid: str, service=Depends(get_profile_service)):
    await _maybe_await(service.delete_experience(eid))
    return {"ok": True}


@router.post("/profile/project")
async def add_project_endpoint(body: ProjectBody, service=Depends(get_profile_service)):
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="Project title is required")
    return await _maybe_await(service.add_project(body.title, body.stack, body.repo, body.impact))


@router.put("/profile/project/{pid}")
async def update_project_endpoint(pid: str, body: ProjectBody, service=Depends(get_profile_service)):
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="Project title is required")
    return await _maybe_await(service.update_project(pid, body.title, body.stack, body.repo, body.impact))


@router.delete("/profile/project/{pid}")
async def delete_project_endpoint(pid: str, service=Depends(get_profile_service)):
    await _maybe_await(service.delete_project(pid))
    return {"ok": True}


@router.post("/profile/education")
async def add_education_endpoint(body: ProfileEntryBody, service=Depends(get_profile_service)):
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="Education title is required")
    return await _maybe_await(service.add_education(body.title))


@router.post("/profile/certification")
async def add_certification_endpoint(body: ProfileEntryBody, service=Depends(get_profile_service)):
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="Certification title is required")
    return await _maybe_await(service.add_certification(body.title))


@router.post("/profile/achievement")
async def add_achievement_endpoint(body: ProfileEntryBody, service=Depends(get_profile_service)):
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="Achievement title is required")
    return await _maybe_await(service.add_achievement(body.title))


async def _maybe_await(value):
    if hasattr(value, "__await__"):
        return await value
    return value
