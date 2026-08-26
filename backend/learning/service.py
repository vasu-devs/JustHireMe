"""Learning-insights service — business layer behind the learning router.

Owns the corpus fetch and the memoisation. The computation walks the whole
corpus (regex taxonomy pass + n-gram mining + one batched embed) — several
seconds on 500 leads — so identical corpus state must serve from memory rather
than recompute on every page visit.
"""

from __future__ import annotations

import asyncio

from data.repository import Repository
from learning.insights import compute_learning_insights

_CORPUS_LIMIT = 500

# Module-level, not an instance attribute: api/dependencies.get_learning_service
# is deliberately NOT @lru_cache'd (same reason get_lead_service isn't -- repo
# overridability for tests), so a fresh LearningService is constructed on every
# single request. An instance-attribute cache reset itself before it could ever
# serve a second request, which is why this memoisation never actually fired in
# production: profiling showed /api/v1/learning/insights recomputing the full
# ~14s corpus scan on every request, every time, instead of once per corpus
# state as the docstring below always intended. A plain module dict survives
# for the life of the process regardless of how many service instances get
# built around it.
_CACHE: dict = {"key": None, "payload": None}


class LearningService:
    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    @staticmethod
    def _corpus_key(leads: list[dict], profile: dict) -> tuple:
        newest = max((str(lead.get("created_at") or "") for lead in leads), default="")
        return (len(leads), newest, len(str(profile)))

    async def insights(self) -> dict:
        """What to learn next, mined from the candidate's own live lead corpus.

        Deterministic and local: recent postings vs. the profile's evidence, with
        near-miss roles (score 55-84) weighted as the highest-leverage gaps.
        """
        leads = await asyncio.to_thread(self._repo.leads.get_leads_for_learning, _CORPUS_LIMIT)
        profile = await asyncio.to_thread(self._repo.profile.get_profile)
        key = self._corpus_key(leads, profile or {})
        if _CACHE["key"] == key and _CACHE["payload"] is not None:
            return _CACHE["payload"]
        payload = await asyncio.to_thread(compute_learning_insights, leads, profile or {})
        _CACHE["key"] = key
        _CACHE["payload"] = payload
        return payload


def create_learning_service(repo: Repository) -> LearningService:
    return LearningService(repo)


__all__ = ["LearningService", "create_learning_service"]
