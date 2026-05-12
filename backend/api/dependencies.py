from __future__ import annotations

from functools import lru_cache

from automation.service import AutomationService, create_automation_service
from core.events import InProcessEventBus
from data.repository import Repository, create_repository
from discovery.service import DiscoveryService, create_discovery_service
from generation.service import GenerationService, create_generation_service
from gateway.clients import automation_client, discovery_client, generation_client, profile_client, ranking_client
from profile.service import ProfileService
from ranking.service import RankingService, create_ranking_service

_event_bus = InProcessEventBus()


def get_event_bus() -> InProcessEventBus:
    return _event_bus


@lru_cache
def get_repository() -> Repository:
    return create_repository()


@lru_cache
def get_profile_service() -> ProfileService:
    return profile_client() or ProfileService()


@lru_cache
def get_discovery_service() -> DiscoveryService:
    return discovery_client() or create_discovery_service()


@lru_cache
def get_ranking_service() -> RankingService:
    return ranking_client() or create_ranking_service()


@lru_cache
def get_generation_service() -> GenerationService:
    return generation_client() or create_generation_service()


@lru_cache
def get_automation_service() -> AutomationService:
    return automation_client() or create_automation_service(get_repository())
