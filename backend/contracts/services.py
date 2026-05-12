from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str


class GenerationPackageRequest(BaseModel):
    lead: dict
    template: str = ""
    include_contacts: bool = True


class GenerationPackageResponse(BaseModel):
    package: dict
    contact_lookup: dict | None = None


class RankingRequest(BaseModel):
    lead: dict | str
    profile: dict


class RankingFeedbackRequest(BaseModel):
    lead: dict
    examples: list[dict] = Field(default_factory=list)


class RankingResponse(BaseModel):
    result: dict


class DiscoveryPlanRequest(BaseModel):
    profile: dict
    raw_urls: list[str] = Field(default_factory=list)
    market_focus: str = "global"


class DiscoveryScanRequest(BaseModel):
    cfg: dict = Field(default_factory=dict)
    profile: dict | None = None
    urls: list[str] = Field(default_factory=list)
    kind_filter: str | None = "job"
    force: bool = False


class DiscoveryRunResponse(BaseModel):
    leads: list[dict] = Field(default_factory=list)
    usage: dict = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class ProfileIngestResumeRequest(BaseModel):
    raw: str = ""
    pdf_path: str | None = None


class ProfileIngestGithubRequest(BaseModel):
    username: str
    token: str | None = None
    max_repos: int = 12


class ProfileIngestLinkedInRequest(BaseModel):
    zip_b64: str


class ProfileIngestPortfolioRequest(BaseModel):
    url: str
    auto_import: bool = False


class ProfileImportRequest(BaseModel):
    payload: dict


class AutomationFormReadRequest(BaseModel):
    url: str
    identity: dict
    cover_letter: str = ""


class AutomationFireRequest(BaseModel):
    job_id: str


class AutomationPreviewRequest(BaseModel):
    lead: dict
    asset: str


class GraphStatsRequest(BaseModel):
    repair: bool = False
