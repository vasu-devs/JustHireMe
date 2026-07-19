from __future__ import annotations

import asyncio
from importlib import import_module

from fastapi import APIRouter, Depends

from api.dependencies import get_repository
from data.repository import Repository

router = APIRouter(prefix="/api/v1", tags=["learning"])

# The computation walks the whole corpus (regex taxonomy pass + n-gram mining
# + one batched embed) — several seconds on 500 leads. Identical corpus state
# must serve from memory, not recompute per page visit.
_CACHE: dict = {"key": None, "payload": None}


def _corpus_key(leads: list[dict], profile: dict) -> tuple:
    newest = max((str(lead.get("created_at") or "") for lead in leads), default="")
    return (len(leads), newest, len(str(profile)))


@router.get("/learning/insights")
async def learning_insights(repo: Repository = Depends(get_repository)):
    """What to learn next, mined from the candidate's own live lead corpus.

    Deterministic and local: recent postings vs. the profile's evidence,
    with near-miss roles (score 55-84) weighted as the highest-leverage gaps.
    """
    # Dynamic import: the api layer reaches domain packages through
    # import_module by design (see api.dependencies._local_service).
    compute = import_module("learning").compute_learning_insights
    leads = await asyncio.to_thread(repo.leads.get_leads_for_learning, 500)
    profile = await asyncio.to_thread(repo.profile.get_profile)
    key = _corpus_key(leads, profile or {})
    if _CACHE["key"] == key and _CACHE["payload"] is not None:
        return _CACHE["payload"]
    payload = await asyncio.to_thread(compute, leads, profile or {})
    _CACHE["key"] = key
    _CACHE["payload"] = payload
    return payload
