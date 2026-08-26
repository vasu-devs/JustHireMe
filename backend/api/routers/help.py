"""In-app help API.

Every help endpoint lives here; answering is owned by ``help.service``.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from api.rate_limit import RateLimiter, require_rate_limit
from core.types import HelpChatBody


router = APIRouter(prefix="/api/v1", tags=["help"])
_help_limiter = RateLimiter(20, 60)


@router.post("/help/chat")
async def help_chat(body: HelpChatBody):
    require_rate_limit(_help_limiter)
    from help.service import answer

    history = [item.model_dump() for item in body.history]
    return await asyncio.to_thread(answer, body.question, history)
