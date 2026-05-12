from __future__ import annotations

import base64

from fastapi import Depends, FastAPI

from contracts.services import (
    AutomationFormReadRequest,
    AutomationPreviewRequest,
    DiscoveryPlanRequest,
    DiscoveryRunResponse,
    DiscoveryScanRequest,
    GenerationPackageRequest,
    GenerationPackageResponse,
    GraphStatsRequest,
    HealthResponse,
    ProfileIngestGithubRequest,
    ProfileIngestLinkedInRequest,
    ProfileIngestPortfolioRequest,
    ProfileIngestResumeRequest,
    ProfileImportRequest,
    RankingFeedbackRequest,
    RankingRequest,
    RankingResponse,
)
from core.types import CandidateBody, ExperienceBody, ProjectBody, SkillBody
from services.auth import require_internal_token


def create_service_app(service_name: str, *, internal_token: str) -> FastAPI:
    app = FastAPI(title=f"JustHireMe {service_name} service", version="0.1.0")
    app.state.internal_token = internal_token

    @app.get("/health", response_model=HealthResponse)
    async def health():
        return HealthResponse(service=service_name)

    guard = Depends(require_internal_token)

    if service_name == "generation":
        _register_generation(app, guard)
    elif service_name == "ranking":
        _register_ranking(app, guard)
    elif service_name == "discovery":
        _register_discovery(app, guard)
    elif service_name == "profile":
        _register_profile(app, guard)
    elif service_name == "automation":
        _register_automation(app, guard)
    elif service_name == "graph":
        _register_graph(app, guard)
    else:
        raise ValueError(f"unknown service: {service_name}")

    return app


def _register_generation(app: FastAPI, guard) -> None:
    from generation.service import create_generation_service

    service = create_generation_service()

    @app.post("/internal/v1/generation/package", response_model=GenerationPackageResponse, dependencies=[guard])
    async def generate_package(body: GenerationPackageRequest):
        result = await service.generate_with_contacts(
            body.lead,
            template=body.template,
            include_contacts=body.include_contacts,
        )
        return GenerationPackageResponse(package=result.package, contact_lookup=result.contact_lookup)


def _register_ranking(app: FastAPI, guard) -> None:
    from ranking.service import create_ranking_service

    service = create_ranking_service()

    @app.post("/internal/v1/ranking/score", response_model=RankingResponse, dependencies=[guard])
    async def score(body: RankingRequest):
        return RankingResponse(result=await service.evaluate_lead(body.lead if isinstance(body.lead, dict) else {"description": body.lead}, body.profile))

    @app.post("/internal/v1/ranking/deterministic-score", response_model=RankingResponse, dependencies=[guard])
    async def deterministic_score(body: RankingRequest):
        score_result = await service.deterministic_score(body.lead, body.profile)
        if hasattr(score_result, "model_dump"):
            return RankingResponse(result=score_result.model_dump())
        return RankingResponse(result=dict(score_result))

    @app.post("/internal/v1/ranking/semantic-match", response_model=RankingResponse, dependencies=[guard])
    async def semantic_match(body: RankingRequest):
        return RankingResponse(result=await service.semantic_match(body.lead, body.profile) or {})

    @app.post("/internal/v1/ranking/apply-feedback", response_model=RankingResponse, dependencies=[guard])
    async def apply_feedback(body: RankingFeedbackRequest):
        return RankingResponse(result=await service.apply_feedback(body.lead, body.examples))


def _register_discovery(app: FastAPI, guard) -> None:
    from discovery.service import create_discovery_service

    service = create_discovery_service()

    @app.post("/internal/v1/discovery/plan", dependencies=[guard])
    async def plan(body: DiscoveryPlanRequest):
        return {"urls": await service.plan_board_targets(body.profile, body.raw_urls, body.market_focus)}

    @app.post("/internal/v1/discovery/scan", response_model=DiscoveryRunResponse, dependencies=[guard])
    async def scan(body: DiscoveryScanRequest):
        result = await service.scan_job_boards(body.urls, body.cfg)
        return DiscoveryRunResponse(leads=result.leads, usage=result.usage, errors=result.errors)

    @app.post("/internal/v1/discovery/free-sources", response_model=DiscoveryRunResponse, dependencies=[guard])
    async def free_sources(body: DiscoveryScanRequest):
        result = await service.scan_free_sources(body.cfg, kind_filter=body.kind_filter, profile=body.profile, force=body.force)
        return DiscoveryRunResponse(leads=result.leads, usage=result.usage, errors=result.errors)

    @app.post("/internal/v1/discovery/x", response_model=DiscoveryRunResponse, dependencies=[guard])
    async def x(body: DiscoveryScanRequest):
        result = await service.scan_x(body.cfg, kind_filter=body.kind_filter or "job", profile=body.profile)
        return DiscoveryRunResponse(leads=result.leads, usage=result.usage, errors=result.errors)


def _register_profile(app: FastAPI, guard) -> None:
    from profile.service import ProfileService

    service = ProfileService()

    @app.get("/internal/v1/profile", dependencies=[guard])
    async def get_profile():
        return service.get_profile()

    @app.put("/internal/v1/profile/candidate", dependencies=[guard])
    async def update_candidate(body: CandidateBody):
        return service.update_candidate(body.n, body.s)

    @app.post("/internal/v1/profile/skill", dependencies=[guard])
    async def add_skill(body: SkillBody):
        return service.add_skill(body.n, body.cat)

    @app.put("/internal/v1/profile/skill/{sid}", dependencies=[guard])
    async def update_skill(sid: str, body: SkillBody):
        return service.update_skill(sid, body.n, body.cat)

    @app.delete("/internal/v1/profile/skill/{sid}", dependencies=[guard])
    async def delete_skill(sid: str):
        service.delete_skill(sid)
        return {"ok": True}

    @app.post("/internal/v1/profile/experience", dependencies=[guard])
    async def add_experience(body: ExperienceBody):
        return service.add_experience(body.role, body.co, body.period, body.d)

    @app.put("/internal/v1/profile/experience/{eid}", dependencies=[guard])
    async def update_experience(eid: str, body: ExperienceBody):
        return service.update_experience(eid, body.role, body.co, body.period, body.d)

    @app.delete("/internal/v1/profile/experience/{eid}", dependencies=[guard])
    async def delete_experience(eid: str):
        service.delete_experience(eid)
        return {"ok": True}

    @app.post("/internal/v1/profile/project", dependencies=[guard])
    async def add_project(body: ProjectBody):
        return service.add_project(body.title, body.stack, body.repo, body.impact)

    @app.put("/internal/v1/profile/project/{pid}", dependencies=[guard])
    async def update_project(pid: str, body: ProjectBody):
        return service.update_project(pid, body.title, body.stack, body.repo, body.impact)

    @app.delete("/internal/v1/profile/project/{pid}", dependencies=[guard])
    async def delete_project(pid: str):
        service.delete_project(pid)
        return {"ok": True}

    @app.post("/internal/v1/profile/ingest/resume", dependencies=[guard])
    async def ingest_resume(body: ProfileIngestResumeRequest):
        result = await service.ingest_resume(body.raw, body.pdf_path)
        return result.model_dump() if hasattr(result, "model_dump") else result

    @app.post("/internal/v1/profile/ingest/github", dependencies=[guard])
    async def ingest_github(body: ProfileIngestGithubRequest):
        return await service.ingest_github(body.username, token=body.token, max_repos=body.max_repos)

    @app.post("/internal/v1/profile/ingest/linkedin", dependencies=[guard])
    async def ingest_linkedin(body: ProfileIngestLinkedInRequest):
        return await service.ingest_linkedin(base64.b64decode(body.zip_b64.encode("ascii")))

    @app.post("/internal/v1/profile/ingest/portfolio", dependencies=[guard])
    async def ingest_portfolio(body: ProfileIngestPortfolioRequest):
        return await service.ingest_portfolio(body.url, auto_import=body.auto_import)

    @app.post("/internal/v1/profile/import", dependencies=[guard])
    async def import_profile(body: ProfileImportRequest):
        return await service.import_profile_data(body.payload)


def _register_automation(app: FastAPI, guard) -> None:
    from automation.service import create_automation_service

    service = create_automation_service()

    @app.post("/internal/v1/automation/form-read", dependencies=[guard])
    async def form_read(body: AutomationFormReadRequest):
        return await service.read_form(body.url, body.identity, cover_letter=body.cover_letter)

    @app.post("/internal/v1/automation/preview-apply", dependencies=[guard])
    async def preview(body: AutomationPreviewRequest):
        return await service.preview_application(body.lead, body.asset)

    @app.post("/internal/v1/automation/fire", dependencies=[guard])
    async def fire(body: AutomationPreviewRequest):
        return {"ok": await service.submit_application(body.lead, body.asset)}

    @app.post("/internal/v1/automation/selectors/refresh", dependencies=[guard])
    async def refresh_selectors():
        data = await service.refresh_selectors()
        return {"version": data.get("version"), "platforms": list(data.get("platforms", {}).keys())}


def _register_graph(app: FastAPI, guard) -> None:
    from graph_service.stats import graph_stats_payload

    @app.post("/internal/v1/graph/stats", dependencies=[guard])
    async def stats(body: GraphStatsRequest):
        return graph_stats_payload(repair=body.repair)
