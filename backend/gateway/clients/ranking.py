from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from gateway.clients.base import BaseServiceClient


@dataclass
class ReevaluationResult:
    total: int = 0
    scored: int = 0
    failed: int = 0
    items: list[dict] = field(default_factory=list)


class RankingHttpClient(BaseServiceClient):
    service_name = "ranking"
    timeout = 90.0

    async def evaluate_lead(self, lead: dict, profile: dict) -> dict:
        data = await self._request("POST", "/internal/v1/ranking/score", json={"lead": lead, "profile": profile}, timeout=90.0)
        return data.get("result") or {}

    async def deterministic_score(self, lead: dict | str, profile: dict) -> dict:
        data = await self._request("POST", "/internal/v1/ranking/deterministic-score", json={"lead": lead, "profile": profile}, timeout=90.0)
        return data.get("result") or {}

    async def semantic_match(self, lead: dict | str, profile: dict) -> dict | None:
        data = await self._request("POST", "/internal/v1/ranking/semantic-match", json={"lead": lead, "profile": profile}, timeout=90.0)
        return data.get("result") or None

    async def apply_feedback(self, lead: dict, examples: list[dict]) -> dict:
        data = await self._request("POST", "/internal/v1/ranking/apply-feedback", json={"lead": lead, "examples": examples}, timeout=90.0)
        return data.get("result") or lead

    async def reevaluate_all(self, leads: list[dict], profile: dict, *, stop_event: asyncio.Event | None = None) -> ReevaluationResult:
        result = ReevaluationResult(total=len(leads))
        for lead in leads:
            if stop_event and stop_event.is_set():
                break
            try:
                scored = await self.evaluate_lead(lead, profile)
                result.scored += 1
                result.items.append({**lead, **scored})
            except Exception:
                result.failed += 1
        return result
