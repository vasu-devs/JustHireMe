from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

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


class CandidateBody(StrictBody):
    n: str = Field(default="", max_length=160)
    s: str = Field(default="", max_length=4000)


class IdentityBody(StrictBody):
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=80)
    linkedin_url: str = Field(default="", max_length=500)
    github_url: str = Field(default="", max_length=500)
    website_url: str = Field(default="", max_length=500)
    city: str = Field(default="", max_length=200)


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

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "reason": self.reason,
            "match_points": self.match_points,
            "gaps": self.gaps,
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
