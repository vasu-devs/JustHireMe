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

    async def evaluate_lead(self, lead: dict, profile: dict, settings: dict | None = None, use_llm: bool = True) -> dict:
        # `settings` is loop-invariant across a scan/reevaluate; callers that loop
        # over many leads pass the already-loaded cfg to avoid an N+1 SELECT on the
        # settings table (and an extra thread hop) per lead. `use_llm=False` lets the
        # caller gate the expensive LLM call to only the top-K leads of a scan.
        if settings is None:
            settings = await asyncio.to_thread(self._load_settings)
        return await asyncio.to_thread(
            self.evaluator.score, self.job_document(lead), profile, settings, use_llm
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

    async def select_llm_eval_ids(self, leads: list[dict], profile: dict, *, max_llm: int = 25) -> set[str]:
        """Job_ids worth an LLM evaluation: the top ``max_llm`` by the cheap
        deterministic score. A scan then spends the model only on the leads the user
        actually looks at, not the whole backlog; the rest keep the calibrated
        deterministic score. ``max_llm <= 0`` disables the cap (evaluate all)."""
        ids = [str(lead.get("job_id") or "") for lead in leads]
        if max_llm <= 0 or len(leads) <= max_llm:
            return {jid for jid in ids if jid}
        scored: list[tuple[int, str]] = []
        for lead, jid in zip(leads, ids, strict=False):
            if not jid:
                continue
            det = await self.deterministic_score(lead, profile)
            scored.append((int(getattr(det, "score", 0) or 0), jid))
        scored.sort(key=lambda item: -item[0])
        return {jid for _, jid in scored[:max_llm]}

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
        # Content-based feedback for the MATCH score the user actually ranks on:
        # "jobs like ones you rated good score higher" (field-agnostic, via embeddings).
        from ranking.feedback_semantic import preference_deltas
        score_deltas = preference_deltas(examples, leads)
        changed: list[dict] = []
        pending: list[tuple[str, dict, int]] = []
        for lead in leads:
            # Re-rank from the ORIGINAL base signal, not the already-adjusted one,
            # so repeated recomputes are idempotent instead of stacking deltas.
            delta_applied = int(lead.get("learning_delta") or 0)
            base = int(lead.get("base_signal_score") or 0) if delta_applied else int(lead.get("signal_score") or 0)
            seed = {k: v for k, v in lead.items() if k not in ("learning_delta", "learning_reason")}
            seed["signal_score"] = base
            seed["base_signal_score"] = base
            ranked = self.feedback.apply_with_model(seed, model)

            # Shift the match score toward semantically-liked jobs, ALWAYS from the
            # original evaluator score (base_score) so repeated recomputes are idempotent.
            match_base = int(lead.get("base_score") or 0) or int(lead.get("score") or 0)
            new_score = max(0, min(100, match_base + int(score_deltas.get(lead["job_id"], 0))))
            ranked["base_score"] = match_base
            ranked["score"] = new_score

            signal_changed = int(ranked.get("signal_score") or 0) != int(lead.get("signal_score") or 0) or int(
                ranked.get("learning_delta") or 0
            ) != delta_applied
            if signal_changed or new_score != int(lead.get("score") or 0):
                pending.append((lead["job_id"], ranked, base))
                changed.append(ranked)
        # One transaction for the whole burst instead of one-per-lead (see
        # data.sqlite.leads.update_learning_scores).
        repo.leads.update_learning_scores(pending)
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
