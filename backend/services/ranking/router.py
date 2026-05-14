from __future__ import annotations

from fastapi import APIRouter, Depends

from contracts.ranking import RankingFeedbackRequest, RankingRequest, RankingResponse
from ranking.service import RankingService
from services.auth import require_internal_token
from services.ranking.dependencies import get_ranking_service


router = APIRouter(prefix="/internal/v1/ranking", dependencies=[Depends(require_internal_token)])


def _dump(value):
    return value.model_dump() if hasattr(value, "model_dump") else value


@router.post("/score", response_model=RankingResponse)
async def score(body: RankingRequest, service: RankingService = Depends(get_ranking_service)):
    lead = _dump(body.lead)
    profile = _dump(body.profile)
    return RankingResponse(result=await service.evaluate_lead(lead if isinstance(lead, dict) else {"description": lead}, profile))


@router.post("/deterministic-score", response_model=RankingResponse)
async def deterministic_score(body: RankingRequest, service: RankingService = Depends(get_ranking_service)):
    result = await service.deterministic_score(_dump(body.lead), _dump(body.profile))
    return RankingResponse(result=_dump(result))


@router.post("/semantic-match", response_model=RankingResponse)
async def semantic_match(body: RankingRequest, service: RankingService = Depends(get_ranking_service)):
    return RankingResponse(result=await service.semantic_match(_dump(body.lead), _dump(body.profile)) or {})


@router.post("/apply-feedback", response_model=RankingResponse)
async def apply_feedback(body: RankingFeedbackRequest, service: RankingService = Depends(get_ranking_service)):
    return RankingResponse(result=await service.apply_feedback(_dump(body.lead), body.examples))
