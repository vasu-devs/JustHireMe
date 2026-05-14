from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InternalEvent(BaseModel):
    type: str = "agent"
    event: str
    job_id: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    msg: str = ""
