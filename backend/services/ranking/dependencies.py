from __future__ import annotations

from functools import lru_cache


@lru_cache
def get_ranking_service():
    from ranking.service import create_ranking_service

    return create_ranking_service()
