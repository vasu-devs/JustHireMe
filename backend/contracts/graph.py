from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GraphStatsRequest(BaseModel):
    repair: bool = False


class GraphSyncRequest(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    repair: bool = False
