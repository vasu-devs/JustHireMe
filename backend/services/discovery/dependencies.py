from __future__ import annotations

from functools import lru_cache


@lru_cache
def get_discovery_service():
    from discovery.service import create_discovery_service

    return create_discovery_service()
