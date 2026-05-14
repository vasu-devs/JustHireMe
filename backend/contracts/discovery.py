from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from contracts.common import LeadSnapshot, ProfileSnapshot


class DiscoveryCandidate(LeadSnapshot):
    platform: str = ""
    signal_score: int = 0
    signal_reason: str = ""
    signal_tags: list[str] = Field(default_factory=list)


class DiscoveryPlanRequest(BaseModel):
    profile: ProfileSnapshot | dict[str, Any]
    raw_urls: list[str] = Field(default_factory=list)
    market_focus: str = "global"


class DiscoveryPlanResponse(BaseModel):
    urls: list[str] = Field(default_factory=list)


class DiscoveryScanRequest(BaseModel):
    cfg: dict[str, Any] = Field(default_factory=dict)
    profile: ProfileSnapshot | dict[str, Any] | None = None
    urls: list[str] = Field(default_factory=list)
    kind_filter: str | None = "job"
    force: bool = False


class DiscoveryRunResponse(BaseModel):
    leads: list[DiscoveryCandidate | dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
