from __future__ import annotations

from typing import Protocol, TypedDict

from pydantic import BaseModel, Field


class GeneratedAsset(TypedDict, total=False):
    type: str
    path: str
    text: str
    metadata: dict


class GeneratedPackage(TypedDict, total=False):
    resume: str
    cover_letter: str
    founder_message: str
    linkedin_note: str
    cold_email: str
    keyword_coverage: dict


class Generator(Protocol):
    name: str

    def generate(self, lead: dict, profile: dict, config: dict | None = None) -> GeneratedAsset: ...

class _DocPackage(BaseModel):
    selected_projects: list[str] = Field(default_factory=list)
    resume_markdown: str = Field(
        default="",
        description="Only the tailored resume markdown. Must not include a cover letter section.",
    )
    cover_letter_markdown: str = Field(
        default="",
        description="Only the tailored cover letter markdown. Must not include resume content.",
    )
    founder_message: str = Field(
        default="",
        description=(
            "A punchy 3-line message to the founder/hiring manager. "
            "Line 1: what caught your eye about their company/role. "
            "Line 2: your single strongest proof point mapped to their need. "
            "Line 3: soft CTA (happy to chat, share more, etc). "
            "Must be under 280 characters total. No fluff, no generic praise."
        ),
    )
    linkedin_note: str = Field(
        default="",
        description=(
            "A LinkedIn connection request note or DM (under 300 chars). "
            "Reference the specific role, one concrete skill match, and a CTA."
        ),
    )
    cold_email: str = Field(
        default="",
        description=(
            "A short cold email (subject line + 4-6 sentence body). "
            "Subject must name the role. Body: hook tied to their product/mission, "
            "2-3 sentences of proof mapped to JD requirements, clear CTA. "
            "Under 150 words total."
        ),
    )
