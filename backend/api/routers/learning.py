from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from api.dependencies import get_repository
from data.repository import Repository
from learning import compute_learning_insights

router = APIRouter(prefix="/api/v1", tags=["learning"])


@router.get("/learning/insights")
async def learning_insights(repo: Repository = Depends(get_repository)):
    """What to learn next, mined from the candidate's own live lead corpus.

    Deterministic and local: recent postings vs. the profile's evidence,
    with near-miss roles (score 55-84) weighted as the highest-leverage gaps.
    """
    leads = await asyncio.to_thread(repo.leads.get_leads_for_learning, 500)
    profile = await asyncio.to_thread(repo.profile.get_profile)
    return await asyncio.to_thread(compute_learning_insights, leads, profile or {})
