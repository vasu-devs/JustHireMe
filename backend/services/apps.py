from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI

from services.automation import create_app as create_automation_app
from services.discovery import create_app as create_discovery_app
from services.generation import create_app as create_generation_app
from services.graph import create_app as create_graph_app
from services.profile import create_app as create_profile_app
from services.ranking import create_app as create_ranking_app


_APP_FACTORIES: dict[str, Callable[[str], FastAPI]] = {
    "automation": create_automation_app,
    "discovery": create_discovery_app,
    "generation": create_generation_app,
    "graph": create_graph_app,
    "profile": create_profile_app,
    "ranking": create_ranking_app,
}


def create_service_app(service_name: str, *, internal_token: str) -> FastAPI:
    try:
        factory = _APP_FACTORIES[service_name]
    except KeyError as exc:
        raise ValueError(f"unknown service: {service_name}") from exc
    return factory(internal_token)
