from __future__ import annotations

from fastapi import APIRouter, Depends

from contracts.generation import GenerationPackageRequest, GenerationPackageResponse
from generation.service import GenerationService
from services.auth import require_internal_token
from services.generation.dependencies import get_generation_service


router = APIRouter(prefix="/internal/v1/generation", dependencies=[Depends(require_internal_token)])


@router.post("/package", response_model=GenerationPackageResponse)
async def generate_package(
    body: GenerationPackageRequest,
    service: GenerationService = Depends(get_generation_service),
):
    lead = body.lead.model_dump() if hasattr(body.lead, "model_dump") else body.lead
    result = await service.generate_with_contacts(
        lead,
        template=body.template,
        include_contacts=body.include_contacts,
    )
    return GenerationPackageResponse(package=result.package, contact_lookup=result.contact_lookup)
