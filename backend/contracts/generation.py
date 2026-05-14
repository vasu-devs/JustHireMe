from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from contracts.common import LeadSnapshot


class GeneratedPackage(BaseModel):
    resume: str
    cover_letter: str = ""
    selected_projects: list[Any] = Field(default_factory=list)
    keyword_coverage: dict[str, Any] = Field(default_factory=dict)
    founder_message: str = ""
    linkedin_note: str = ""
    cold_email: str = ""


class GenerationPackageRequest(BaseModel):
    lead: LeadSnapshot | dict[str, Any]
    template: str = ""
    include_contacts: bool = True


class GenerationPackageResponse(BaseModel):
    package: GeneratedPackage | dict[str, Any]
    contact_lookup: dict[str, Any] | None = None
