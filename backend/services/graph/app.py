from __future__ import annotations

from fastapi import FastAPI

from contracts.common import ServiceHealth
from core.version import APP_VERSION
from services.graph.router import router


def create_app(internal_token: str) -> FastAPI:
    app = FastAPI(title="JustHireMe graph service", version=APP_VERSION)
    app.state.internal_token = internal_token

    @app.get("/health", response_model=ServiceHealth)
    async def health():
        return ServiceHealth(service="graph")

    app.include_router(router)
    return app
