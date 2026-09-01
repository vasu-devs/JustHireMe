from __future__ import annotations

from functools import lru_cache
from types import SimpleNamespace
from importlib import import_module

from fastapi import Depends

from core.events import InProcessEventBus
from data.repository import Repository, create_repository
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
    module = import_module("profile.service")
    return module.ProfileService()


@lru_cache
def get_discovery_service():
    return _local_service("discovery.service", "create_discovery_service")


@lru_cache
def get_ranking_service():
    return _local_service("ranking.service", "create_ranking_service")


@lru_cache
def get_generation_service():
    return _local_service("generation.service", "create_generation_service")


def get_automation_service(repo: Repository = Depends(get_repository)):
    # Not lru_cache'd on a module-level get_repository() call — see get_lead_service.
    module = import_module("automation.service")
    return module.create_automation_service(repo)


def get_lead_service(
    repo: Repository = Depends(get_repository),
    ranking_service=Depends(get_ranking_service),
):
    """Build the lead service from the *injected* repository.

    Deliberately not ``lru_cache``d on a module-level ``get_repository()`` call:
    a cached instance would capture the real repository forever, so a test (or
    any caller) overriding ``get_repository`` would be silently ignored and the
    service would keep talking to the production database.
    """
    module = import_module("leads.service")
    return module.create_lead_service(repo, ranking_service)


def get_opportunity_service(
    repo: Repository = Depends(get_repository),
    profile_service=Depends(get_profile_service),
):
    module = import_module("opportunities.service")
    return module.create_opportunity_service(repo, profile_service)


def get_auto_apply_campaign_service(
    repo: Repository = Depends(get_repository),
    opportunity_service=Depends(get_opportunity_service),
    generation_service=Depends(get_generation_service),
    automation_service=Depends(get_automation_service),
):
    module = import_module("automation.campaign")
    return module.AutoApplyCampaignService(
        repo,
        opportunity_service,
        generation_service,
        automation_service,
    )


def get_template_service(repo: Repository = Depends(get_repository)):
    module = import_module("templates.service")
    return module.create_template_service(repo)


def get_settings_service(repo: Repository = Depends(get_repository)):
    module = import_module("settings.service")
    return module.create_settings_service(repo)


def get_system_service(repo: Repository = Depends(get_repository)):
    module = import_module("system.service")
    return module.create_system_service(repo)


def get_learning_service(repo: Repository = Depends(get_repository)):
    module = import_module("learning.service")
    return module.create_learning_service(repo)


def get_graph_service(repo: Repository = Depends(get_repository)):
    module = import_module("graph_service.stats")
    return module.create_graph_service(repo)


def get_dashboard_service(repo: Repository = Depends(get_repository)):
    # Business package is "reporting" (see reporting/service.py's docstring for
    # why it isn't named "dashboard"); the API feature/URL segment stays "dashboard".
    module = import_module("reporting.service")
    return module.create_reporting_service(repo)


def get_job_runner() -> JobStore:
    return get_job_store()


def get_generation_orchestrator(
    repo: Repository = Depends(get_repository),
    service=Depends(get_generation_service),
    job_store: JobStore = Depends(get_job_runner),
):
    module = import_module("generation.orchestrator")
    return module.create_generation_orchestrator(repo, service, job_store)


def get_discovery_context(
    repo: Repository = Depends(get_repository),
    discovery_service=Depends(get_discovery_service),
    ranking_service=Depends(get_ranking_service),
):
    """Collaborators a scan needs, assembled here so routers stay data-free."""
    return SimpleNamespace(repo=repo, discovery_service=discovery_service, ranking_service=ranking_service)
