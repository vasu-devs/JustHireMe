from __future__ import annotations

from functools import lru_cache
from importlib import import_module

from core.events import InProcessEventBus
from data.repository import Repository, create_repository
from gateway.clients import automation_client, discovery_client, generation_client, profile_client, ranking_client
from gateway.jobs import JobStore, get_job_store

_event_bus = InProcessEventBus()


def get_event_bus() -> InProcessEventBus:
    return _event_bus


@lru_cache
def get_repository() -> Repository:
    return create_repository()


def get_gateway_repository() -> Repository:
    return get_repository()


def _local_service(module_name: str, factory_name: str):
    module = import_module(module_name)
    return getattr(module, factory_name)()


@lru_cache
def get_profile_service():
    client = profile_client()
    if client:
        return client
    module = import_module("profile.service")
    return module.ProfileService()


@lru_cache
def get_discovery_service():
    return discovery_client() or _local_service("discovery.service", "create_discovery_service")


@lru_cache
def get_ranking_service():
    return ranking_client() or _local_service("ranking.service", "create_ranking_service")


@lru_cache
def get_generation_service():
    return generation_client() or _local_service("generation.service", "create_generation_service")


@lru_cache
def get_automation_service():
    client = automation_client()
    if client:
        return client
    module = import_module("automation.service")
    return module.create_automation_service(get_repository())


def get_job_runner() -> JobStore:
    return get_job_store()
