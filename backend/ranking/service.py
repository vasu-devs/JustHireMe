from __future__ import annotations
import logging

import asyncio
from dataclasses import dataclass, field

from ranking.evaluator import Evaluator
from ranking.feedback_ranker import FeedbackRanker
from ranking.scoring_engine import ScoringEngine
from ranking.semantic import SemanticMatcher


@dataclass
class ReevaluationResult:
    total: int = 0
    scored: int = 0
    failed: int = 0
    items: list[dict] = field(default_factory=list)


class RankingService:
    def __init__(
        self,
        scoring_engine: ScoringEngine | None = None,
        evaluator: Evaluator | None = None,
        semantic: SemanticMatcher | None = None,
        feedback: FeedbackRanker | None = None,
    ):
        self.scoring_engine = scoring_engine or ScoringEngine()
        self.evaluator = evaluator or Evaluator()
        self.semantic = semantic or SemanticMatcher()
        self.feedback = feedback or FeedbackRanker()

    async def evaluate_lead(self, lead: dict, profile: dict) -> dict:
        return await asyncio.to_thread(self.evaluator.score, self.job_document(lead), profile)

    async def deterministic_score(self, lead: dict | str, profile: dict):
        jd = lead if isinstance(lead, str) else self.job_document(lead)
        return await asyncio.to_thread(self.scoring_engine.score, jd, profile)

    async def semantic_match(self, lead: dict | str, profile: dict) -> dict | None:
        jd = lead if isinstance(lead, str) else self.job_document(lead)
        return await asyncio.to_thread(self.semantic.match, jd, candidate_data=profile)

    async def apply_feedback(self, lead: dict, examples: list[dict]) -> dict:
        return await asyncio.to_thread(self.feedback.apply, lead, examples)

    async def reevaluate_all(
        self,
        leads: list[dict],
        profile: dict,
        *,
        stop_event: asyncio.Event | None = None,
    ) -> ReevaluationResult:
        result = ReevaluationResult(total=len(leads))
        for lead in leads:
            if stop_event and stop_event.is_set():
                break
            try:
                scored = await self.evaluate_lead(lead, profile)
                result.scored += 1
                result.items.append({**lead, **scored})
            except Exception as log_exc:
                logging.getLogger(__name__).warning('suppressed exception in backend/ranking/service.py:reevaluate_all: %s', log_exc)
                result.failed += 1
        return result

    @staticmethod
    def job_document(lead: dict) -> str:
        desc = (lead.get("description") or "").strip()
        return (
            f"Job Title: {lead.get('title','')}\n"
            f"Company: {lead.get('company','')}\n"
            f"URL: {lead.get('url','')}\n"
            + (f"Description: {desc}" if desc else "")
        )


def create_ranking_service() -> RankingService:
    return RankingService()
