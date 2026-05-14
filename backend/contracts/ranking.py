from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from contracts.common import LeadSnapshot, ProfileSnapshot


class RankingScore(BaseModel):
    score: int = 0
    reason: str = ""
    match_points: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    semantic: dict[str, Any] = Field(default_factory=dict)


class RankingRequest(BaseModel):
    lead: LeadSnapshot | dict[str, Any] | str
    profile: ProfileSnapshot | dict[str, Any]


class RankingFeedbackRequest(BaseModel):
    lead: LeadSnapshot | dict[str, Any]
    examples: list[dict[str, Any]] = Field(default_factory=list)


class RankingResponse(BaseModel):
    result: RankingScore | dict[str, Any]
