from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FlexibleModel(BaseModel):
    model_config = {"extra": "allow"}


class LeadSnapshot(FlexibleModel):
    job_id: str = ""
    title: str = ""
    company: str = ""
    url: str = ""
    description: str = ""
    status: str = ""
    kind: str = "job"
    score: int = 0
    reason: str = ""
    match_points: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    source_meta: dict[str, Any] = Field(default_factory=dict)


class ProfileSnapshot(FlexibleModel):
    n: str = ""
    s: str = ""
    skills: list[dict[str, Any]] = Field(default_factory=list)
    exp: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)


class ServiceHealth(BaseModel):
    status: Literal["ok", "starting", "healthy", "degraded", "error"] = "ok"
    service: str
    pid: int | None = None
    port: int | None = None
    started_at: str = ""
    last_healthy_at: str = ""
    last_error: str = ""
    restart_count: int = 0
