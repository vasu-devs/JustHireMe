from __future__ import annotations

from functools import lru_cache

from profile.service import ProfileService


@lru_cache
def get_profile_service() -> ProfileService:
    return ProfileService()
