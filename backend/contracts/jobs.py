from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatusValue = Literal["queued", "running", "cancel_requested", "succeeded", "failed", "cancelled"]


class JobStatus(BaseModel):
    job_id: str
    kind: str
    status: JobStatusValue
    progress: int = 0
    input_json: dict[str, Any] = Field(default_factory=dict)
    result_json: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
