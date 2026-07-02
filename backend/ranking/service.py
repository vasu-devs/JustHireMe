from __future__ import annotations
import logging

import asyncio
from dataclasses import dataclass, field
from functools import lru_cache

from ranking.evaluator import Evaluator
from ranking.feedback_ranker import FeedbackRanker
from ranking.scoring_engine import ScoringEngine
from ranking.semantic import SemanticMatcher


@lru_cache
def _settings_repository():
    from data.repository import create_repository

    return create_repository()


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

    async def evaluate_lead(self, lead: dict, profile: dict, settings: dict | None = None) -> dict:
        # `settings` is loop-invariant across a scan/reevaluate; callers that loop
        # over many leads pass the already-loaded cfg to avoid an N+1 SELECT on the
        # settings table (and an extra thread hop) per lead.
        if settings is None:
            settings = await asyncio.to_thread(self._load_settings)
        return await asyncio.to_thread(
            self.evaluator.score, self.job_document(lead), profile, settings
        )

    @staticmethod
    def _load_settings() -> dict:
        """Fetch live app settings so the evaluator sees the configured LLM route.

        Without this the evaluator always falls back to the deterministic rubric,
        even when the user has configured an evaluator provider/key.
        """
        try:
            return _settings_repository().settings.get_settings() or {}
        except Exception as log_exc:
            logging.getLogger(__name__).warning(
                'suppressed exception in backend/ranking/service.py:_load_settings: %s', log_exc
            )
            return {}

    async def deterministic_score(self, lead: dict | str, profile: dict):
        jd = lead if isinstance(lead, str) else self.job_document(lead)
        return await asyncio.to_thread(self.scoring_engine.score, jd, profile)

    async def semantic_match(self, lead: dict | str, profile: dict) -> dict | None:
        jd = lead if isinstance(lead, str) else self.job_document(lead)
        return await asyncio.to_thread(self.semantic.match, jd, candidate_data=profile)

    async def apply_feedback(self, lead: dict, examples: list[dict]) -> dict:
        return await asyncio.to_thread(self.feedback.apply, lead, examples)

    async def recompute_feedback_signals(self, *, limit: int = 500) -> list[dict]:
        """Re-rank existing leads from the current feedback model and persist.

        This is what makes the app "get better with use": after a user marks a
        lead good/bad, every other still-open lead is re-scored by what that
        feedback taught the model (liked platforms/companies/stacks get a signal
        boost, disliked ones a penalty). Returns the leads whose signal changed so
        the caller can push live updates.
        """
        return await asyncio.to_thread(self._recompute_feedback_signals, limit)

    def _recompute_feedback_signals(self, limit: int) -> list[dict]:
        repo = _settings_repository()
        examples = repo.feedback.get_feedback_training_examples()
        if not examples:
            return []
        # Build the feedback model ONCE, then score every lead against it — the
        # examples are loop-invariant, so rebuilding per lead was O(leads x examples).
        model = self.feedback.build_model(examples)
        leads = repo.leads.get_leads_for_learning(limit)
        changed: list[dict] = []
        for lead in leads:
            # Re-rank from the ORIGINAL base signal, not the already-adjusted one,
            # so repeated recomputes are idempotent instead of stacking deltas.
            delta_applied = int(lead.get("learning_delta") or 0)
            base = int(lead.get("base_signal_score") or 0) if delta_applied else int(lead.get("signal_score") or 0)
            seed = {k: v for k, v in lead.items() if k not in ("learning_delta", "learning_reason")}
            seed["signal_score"] = base
            seed["base_signal_score"] = base
            ranked = self.feedback.apply_with_model(seed, model)
            if int(ranked.get("signal_score") or 0) != int(lead.get("signal_score") or 0) or int(
                ranked.get("learning_delta") or 0
            ) != delta_applied:
                repo.leads.update_learning_score(lead["job_id"], ranked, base)
                changed.append(ranked)
        return changed

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
