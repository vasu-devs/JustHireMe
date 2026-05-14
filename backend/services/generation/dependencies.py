from __future__ import annotations

from functools import lru_cache


@lru_cache
def get_generation_service():
    from generation.service import create_generation_service

    return create_generation_service()
