from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from contracts.common import LeadSnapshot


class AutomationFormReadRequest(BaseModel):
    url: str
    identity: dict[str, Any]
    cover_letter: str = ""


class AutomationFireRequest(BaseModel):
    job_id: str


class AutomationPreviewRequest(BaseModel):
    lead: LeadSnapshot | dict[str, Any]
    asset: str
