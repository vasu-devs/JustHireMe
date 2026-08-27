from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, model_validator


LeadStatus = Literal[
    "discovered",
    "evaluating",
    "tailoring",
    "approved",
    "applied",
    "interviewing",
    "rejected",
    "accepted",
    "discarded",
    "matched",
    "bidding",
    "proposal_sent",
    "awarded",
    "completed",
    # scripts/generate_drafts.py: a human-review-only resume/cover-letter draft
    # has been written to disk for this lead (see backend/scripts/drafts/).
    # Deliberately distinct from "approved" so it is never picked up by the
    # ghost-mode auto-apply path, which never queries by status at all but
    # this keeps the two concepts unambiguous in the data itself.
    "draft_ready",
]


class Lead(TypedDict, total=False):
    # Identity
    job_id: str
    title: str
    company: str
    url: str
    platform: str
    kind: str
    text: str
    source: str

    # Status and scoring
    status: LeadStatus
    score: int
    score_stale: bool
    reason: str
    match_points: list[str]
    gaps: list[str]
    seniority: str
    seniority_level: str

    # Signal intelligence
    signal_score: int
    signal_reason: str
    signal_tags: list[str]
    base_signal_score: int
    learning_delta: int
    learning_reason: str

    # Content
    description: str
    location: str
    urgency: str
    budget: str
    tech_stack: list[str]

    # Outreach
    outreach_reply: str
    outreach_dm: str
    outreach_email: str
    proposal_draft: str
    fit_bullets: list[str]
    followup_sequence: list[str]
    proof_snippet: str

    # Assets
    asset_path: str
    resume_asset: str
    cover_letter_asset: str
    cover_letter_path: str
    selected_projects: list[str]
    keyword_coverage: dict
    resume_version: int

    # User interaction
    feedback: str
    feedback_note: str
    followup_due_at: str
    last_contacted_at: str
    contact_lookup: dict

    # Metadata
    source_meta: dict
    created_at: str


class Profile(TypedDict, total=False):
    n: str
    s: str
    desired_position: str
    identity: dict
    skills: list[dict]
    exp: list[dict]
    projects: list[dict]
    education: list
    certifications: list
    achievements: list


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StatusBody(StrictBody):
    status: LeadStatus


class FeedbackBody(StrictBody):
    feedback: Literal[
        "good",
        "trash",
        "too_generic",
        "not_ai",
        "already_contacted",
        "relevant",
        "not_relevant",
        "duplicate",
        "low_quality",
        "incorrect_category",
    ]
    note: str = Field(default="", max_length=1000)


class FollowupBody(StrictBody):
    days: int = Field(default=5, ge=1, le=60)


class ManualLeadBody(StrictBody):
    text: str = Field(default="", max_length=20000)
    url: str = Field(default="", max_length=2000)
    kind: Literal["job"] = "job"

    @model_validator(mode="after")
    def _validate_content(self):
        if not self.text.strip() and not self.url.strip():
            raise ValueError("Provide either text or a URL")
        return self


class HelpMessage(StrictBody):
    role: Literal["user", "assistant"]
    content: str = Field(default="", max_length=4000)


class HelpChatBody(StrictBody):
    question: str = Field(max_length=2000)
    history: list[HelpMessage] = Field(default_factory=list, max_length=12)


class TemplateBody(StrictBody):
    template: str = Field(default="", max_length=20000)


class PreferencesBody(StrictBody):
    preferences: str = Field(default="", max_length=2000)


class ResetDataBody(StrictBody):
    # Require an explicit literal so a destructive reset can never fire from an
    # empty/accidental request body.
    confirm: Literal["DELETE"]
    # Data-only by default (keeps settings + provider config); true = full wipe.
    clear_settings: bool = False


class CandidateBody(StrictBody):
    n: str = Field(default="", max_length=160)
    s: str = Field(default="", max_length=4000)


class OpportunityCandidateBody(StrictBody):
    consent_confirmed_at: datetime | None = None
    home_country: str = Field(default="IN", min_length=2, max_length=2)
    graduation_year: int = Field(default=2027, ge=2020, le=2040)
    currently_enrolled: bool = True
    current_degree_level: Literal["unknown", "bachelors", "masters", "doctorate"] = "unknown"
    accepted_india_cities: list[str] = Field(default_factory=list, max_length=30)
    technical_skills: list[str] = Field(default_factory=list, max_length=100)
    project_keywords: list[str] = Field(default_factory=list, max_length=100)
    spoken_languages: list[str] = Field(default_factory=list, max_length=30)
    preferred_technical_tracks: list[Literal[
        "software", "backend", "frontend", "fullstack", "ai_ml", "data",
        "cloud_devops", "security", "mobile", "qa_automation", "embedded_systems",
    ]] = Field(default_factory=list, max_length=12)
    accepted_opportunity_types: list[Literal[
        "internship", "new_grad", "entry_level_full_time", "stretch_full_time",
    ]] = Field(
        default_factory=lambda: ["internship", "new_grad", "entry_level_full_time", "stretch_full_time"],
        min_length=1,
        max_length=4,
    )
    allow_india_onsite: bool = True
    allow_india_hybrid: bool = True
    allow_india_remote: bool = True
    allow_worldwide_remote: bool = True
    allow_unpaid: bool = False
    allow_bond: bool = False
    professional_experience_years: float = Field(default=0.0, ge=0.0, le=50.0)
    minimum_monthly_compensation_inr: int = Field(default=0, ge=0, le=10_000_000)
    target_monthly_compensation_inr: int = Field(default=0, ge=0, le=10_000_000)
    minimum_monthly_compensation_usd: int = Field(default=0, ge=0, le=1_000_000)
    target_monthly_compensation_usd: int = Field(default=0, ge=0, le=1_000_000)
    unknown_compensation_policy: Literal["allow", "review", "skip"] = "allow"
    maximum_internship_months: int = Field(default=12, ge=1, le=36)

    @model_validator(mode="after")
    def validate_opportunity_compensation_targets(self) -> OpportunityCandidateBody:
        pairs = (
            (self.minimum_monthly_compensation_inr, self.target_monthly_compensation_inr),
            (self.minimum_monthly_compensation_usd, self.target_monthly_compensation_usd),
        )
        if any(target and minimum and target < minimum for minimum, target in pairs):
            raise ValueError("target compensation must be at least the corresponding minimum")
        return self


class OpportunityScanBody(StrictBody):
    candidate_id: str = Field(min_length=1, max_length=240, pattern=r"^[a-zA-Z0-9_.:\-]+$")
    target_limit: int = Field(default=500, ge=1, le=500)
    max_concurrency: int = Field(default=6, ge=1, le=12)


class OpportunityOutcomeBody(StrictBody):
    event_type: Literal[
        "application_started", "application_submitted", "outreach_sent",
        "recruiter_reply", "screening", "technical_assessment", "interview",
        "rejected", "offer", "withdrawn", "skipped",
    ]
    occurred_at: str = Field(default="", max_length=80)
    note: str = Field(default="", max_length=1000)
    idempotency_key: str = Field(default="", max_length=160, pattern=r"^[a-zA-Z0-9_.:\-]*$")


class IdentityBody(StrictBody):
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=80)
    linkedin_url: str = Field(default="", max_length=500)
    github_url: str = Field(default="", max_length=500)
    website_url: str = Field(default="", max_length=500)
    city: str = Field(default="", max_length=200)


class OpportunityProfileSnapshotBody(StrictBody):
    expected_payload_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    identity: IdentityBody


class OpportunityCandidateProfileImportBody(OpportunityProfileSnapshotBody):
    profile: dict[str, Any]


class ProfileEntryBody(StrictBody):
    title: str = Field(default="", max_length=500)


class SkillBody(StrictBody):
    id: str | None = Field(default=None, max_length=160)
    n: str = Field(default="", max_length=160)
    cat: str = Field(default="general", max_length=80)


class ExperienceBody(StrictBody):
    id: str | None = Field(default=None, max_length=160)
    role: str = Field(default="", max_length=180)
    co: str = Field(default="", max_length=180)
    period: str = Field(default="", max_length=120)
    d: str = Field(default="", max_length=8000)


class ProjectBody(StrictBody):
    id: str | None = Field(default=None, max_length=160)
    title: str = Field(default="", max_length=220)
    stack: str = Field(default="", max_length=2000)
    repo: str = Field(default="", max_length=1000)
    impact: str = Field(default="", max_length=8000)


class SettingsBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def _validate_extra_settings(self):
        for key, value in (self.model_extra or {}).items():
            if len(key) > 120 or any(not (ch.isalnum() or ch in "_.-") for ch in key):
                raise ValueError(f"Invalid settings key: {key}")
            if value is not None and not isinstance(value, (str, bool, int, float)):
                raise ValueError(f"Invalid value for settings key: {key}")
        return self


@dataclass(frozen=True)
class CriterionScore:
    name: str
    score: int
    weight: int
    reason: str


@dataclass(frozen=True)
class ScoreResult:
    score: int
    reason: str
    match_points: list[str]
    gaps: list[str]
    criteria: list[CriterionScore]
    # The hard-cap ceiling applied to this score (e.g. seniority mismatch), if
    # any. Carried so the LLM evaluator can raise within the guardrail band
    # rather than being pinned to the deterministic baseline.
    applied_cap: int | None = None
    # Which cap kinds fired ("wrong-field"/"seniority"/"stack"/"confidence"),
    # ordered by ascending ceiling. Structural signal for cap enforcement — the
    # display `gaps` list is truncated, so a cap note there can be cut without
    # the cap having gone away.
    cap_kinds: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "reason": self.reason,
            "match_points": self.match_points,
            "gaps": self.gaps,
            "applied_cap": self.applied_cap,
            "cap_kinds": self.cap_kinds,
        }


@dataclass
class CandidateEvidence:
    skills: set[str]
    project_terms: set[str]
    experience_terms: set[str]
    all_terms: set[str]
    project_by_term: dict[str, list[str]]
    experience_by_term: dict[str, list[str]]
    project_texts: list[tuple[str, str, set[str]]]
    experience_texts: list[tuple[str, str, set[str]]]
    role_tags: set[str]
    deliverables: set[str]
    level: str
    work_months: int
    summary: str
    location: str
