from __future__ import annotations

from gateway.clients.automation import AutomationHttpClient
from gateway.clients.base import (
    BaseServiceClient,
    ServiceConflict,
    ServiceEndpoint,
    ServiceFailed,
    ServiceNotFound,
    ServiceRegistry,
    ServiceRequestError,
    ServiceTimeout,
    ServiceUnavailable,
    ServiceValidationError,
    get_service_registry,
    set_service_registry,
)
from gateway.clients.discovery import DiscoveryHttpClient, DiscoveryRunResult
from gateway.clients.generation import GenerationHttpClient, GenerationResult
from gateway.clients.graph import GraphHttpClient
from gateway.clients.profile import ProfileHttpClient
from gateway.clients.ranking import RankingHttpClient, ReevaluationResult


def _client(name: str, cls):
    registry = get_service_registry()
    endpoint = registry.get(name) if registry else None
    return cls(endpoint) if endpoint else None


def generation_client() -> GenerationHttpClient | None:
    return _client("generation", GenerationHttpClient)


def ranking_client() -> RankingHttpClient | None:
    return _client("ranking", RankingHttpClient)


def discovery_client() -> DiscoveryHttpClient | None:
    return _client("discovery", DiscoveryHttpClient)


def graph_client() -> GraphHttpClient | None:
    return _client("graph", GraphHttpClient)


def automation_client() -> AutomationHttpClient | None:
    return _client("automation", AutomationHttpClient)


def profile_client() -> ProfileHttpClient | None:
    return _client("profile", ProfileHttpClient)


__all__ = [
    "AutomationHttpClient",
    "BaseServiceClient",
    "DiscoveryHttpClient",
    "DiscoveryRunResult",
    "GenerationHttpClient",
    "GenerationResult",
    "GraphHttpClient",
    "ProfileHttpClient",
    "RankingHttpClient",
    "ReevaluationResult",
    "ServiceConflict",
    "ServiceEndpoint",
    "ServiceFailed",
    "ServiceNotFound",
    "ServiceRegistry",
    "ServiceRequestError",
    "ServiceTimeout",
    "ServiceUnavailable",
    "ServiceValidationError",
    "automation_client",
    "discovery_client",
    "generation_client",
    "get_service_registry",
    "graph_client",
    "profile_client",
    "ranking_client",
    "set_service_registry",
]
