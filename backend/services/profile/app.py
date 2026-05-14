from __future__ import annotations

from fastapi import FastAPI

from contracts.common import ServiceHealth
from services.profile.router import router


def create_app(internal_token: str) -> FastAPI:
    app = FastAPI(title="JustHireMe profile service", version="0.1.0")
    app.state.internal_token = internal_token

    @app.get("/health", response_model=ServiceHealth)
    async def health():
        return ServiceHealth(service="profile")

    app.include_router(router)
    return app
