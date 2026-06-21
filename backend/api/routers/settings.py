from __future__ import annotations

import asyncio
import os
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_repository
from api.scheduler import ensure_ghost_job
from core.types import PreferencesBody, ResetDataBody, SettingsBody, TemplateBody
from data.repository import Repository


MASK = "__JHM_SECRET_SET__"
LEGACY_BULLET_MASK = "\u2022" * 20
LEGACY_MOJIBAKE_BULLET_MASK = "\u00e2\u20ac\u00a2" * 20
LEGACY_DOUBLE_ENCODED_BULLET_MASK = "\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u00a2" * 20
LEGACY_MASKS = {
    MASK,
    LEGACY_BULLET_MASK,
    LEGACY_MOJIBAKE_BULLET_MASK,
    LEGACY_DOUBLE_ENCODED_BULLET_MASK,
}


def sensitive_keys(settings: dict) -> set:
    fixed = {"anthropic_key", "linkedin_cookie", "x_bearer_token", "custom_connector_headers"}
    dynamic = {key for key in settings if key.endswith("_api_key") or key.endswith("_key") or key.endswith("_token")}
    return fixed | dynamic


async def probe_provider_key(provider: str, key: str, settings: dict | None = None) -> dict:
    import httpx
    from llm import _OPENAI_COMPAT_BASE_URLS

    started = time.perf_counter()
    try:
        timeout = httpx.Timeout(5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            if provider == "anthropic":
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
                status = "ok" if response.status_code in {200, 400} else "invalid_key" if response.status_code == 401 else "unreachable"
            elif provider == "openai":
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                status = "ok" if response.status_code == 200 else "invalid_key" if response.status_code == 401 else "unreachable"
            elif provider == "groq":
                response = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                status = "ok" if response.status_code == 200 else "invalid_key" if response.status_code == 401 else "unreachable"
            elif provider == "gemini":
                response = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/openai/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                status = "ok" if response.status_code == 200 else "invalid_key" if response.status_code in {401, 403} else "unreachable"
            elif provider == "deepseek":
                response = await client.get(
                    "https://api.deepseek.com/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                status = "ok" if response.status_code == 200 else "invalid_key" if response.status_code in {401, 403} else "unreachable"
            elif provider in _OPENAI_COMPAT_BASE_URLS:
                response = await client.get(
                    f"{_OPENAI_COMPAT_BASE_URLS[provider].rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                status = "ok" if response.status_code == 200 else "invalid_key" if response.status_code in {401, 403} else "unreachable"
            elif provider == "azure":
                cfg = settings or {}
                endpoint = str(
                    cfg.get("azure_openai_endpoint")
                    or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
                ).strip().rstrip("/")
                if not endpoint:
                    status = "unchecked"
                else:
                    if not endpoint.endswith("/openai/v1"):
                        endpoint = f"{endpoint}/openai/v1"
                    response = await client.get(
                        f"{endpoint}/models",
                        headers={"api-key": key},
                    )
                    status = "ok" if response.status_code == 200 else "invalid_key" if response.status_code in {401, 403} else "unreachable"
            else:
                status = "unchecked"
    except Exception:
        status = "unreachable"
    return {"status": status, "latency_ms": round((time.perf_counter() - started) * 1000)}


async def list_provider_models(provider: str, key: str, settings: dict | None = None) -> list[str]:
    import httpx
    from llm import _OPENAI_COMPAT_BASE_URLS

    cfg = settings or {}
    headers = {"Authorization": f"Bearer {key}"}
    url = ""
    if provider == "anthropic":
        url = "https://api.anthropic.com/v1/models"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    elif provider == "openai":
        url = "https://api.openai.com/v1/models"
    elif provider == "groq":
        url = "https://api.groq.com/openai/v1/models"
    elif provider == "gemini":
        url = "https://generativelanguage.googleapis.com/v1beta/openai/models"
    elif provider == "nvidia":
        url = "https://integrate.api.nvidia.com/v1/models"
    elif provider == "deepseek":
        url = "https://api.deepseek.com/models"
    elif provider == "azure":
        endpoint = str(
            cfg.get("azure_openai_endpoint")
            or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        ).strip().rstrip("/")
        if not endpoint:
            return []
        if not endpoint.endswith("/openai/v1"):
            endpoint = f"{endpoint}/openai/v1"
        url = f"{endpoint}/models"
        headers = {"api-key": key}
    elif provider in _OPENAI_COMPAT_BASE_URLS:
        url = f"{_OPENAI_COMPAT_BASE_URLS[provider].rstrip('/')}/models"
    else:
        return []

    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
    rows = data.get("data", data.get("models", [])) if isinstance(data, dict) else data
    ids: list[str] = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, str):
                ids.append(row)
            elif isinstance(row, dict):
                model_id = row.get("id") or row.get("name") or row.get("model")
                if model_id:
                    ids.append(str(model_id))
    return sorted(dict.fromkeys(ids), key=str.lower)


def _settings_with_incoming(repo: Repository, incoming: dict | None) -> dict:
    cfg = repo.settings.get_settings()
    if not incoming:
        return cfg
    old = cfg
    cfg = {**cfg, **{key: "" if value is None else str(value) for key, value in incoming.items()}}
    for key in sensitive_keys(cfg):
        if cfg.get(key) in LEGACY_MASKS:
            cfg[key] = old.get(key, "")
    return cfg


def _provider_key(cfg: dict, provider: str) -> str:
    from llm import _ENV_NAMES, _KEY_NAMES

    key_name = _KEY_NAMES.get(provider, "")
    return str(
        cfg.get(key_name)
        or os.environ.get(_ENV_NAMES.get(provider, ""), "")
        or (os.environ.get("GOOGLE_API_KEY", "") if provider == "gemini" else "")
        or ""
    ).strip()


async def validate_provider_settings(repo: Repository, incoming: dict | None = None) -> dict:
    from llm import _KEY_NAMES, _OPENAI_COMPAT_BASE_URLS

    cfg = _settings_with_incoming(repo, incoming)
    probed = {"anthropic", "gemini", "openai", "groq", "deepseek", "azure", *_OPENAI_COMPAT_BASE_URLS}
    providers = [
        "anthropic",
        "gemini",
        "openai",
        "groq",
        *[provider for provider in _KEY_NAMES if provider not in {"anthropic", "gemini", "openai", "groq"}],
    ]

    async def one(provider: str):
        key = _provider_key(cfg, provider)
        if not key:
            return provider, {"status": "not_configured", "latency_ms": 0}
        if provider not in probed:
            return provider, {"status": "unchecked", "latency_ms": 0}
        return provider, await probe_provider_key(provider, key, cfg)

    pairs = await asyncio.gather(*(one(provider) for provider in providers))
    return {provider: result for provider, result in pairs}


def create_router(scheduler: AsyncIOScheduler, ghost_tick) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["settings"])

    @router.get("/template")
    async def get_template(repo: Repository = Depends(get_repository)):
        return {"template": await asyncio.to_thread(repo.settings.get_setting, "resume_template", "")}

    @router.post("/template")
    async def save_template(body: TemplateBody, repo: Repository = Depends(get_repository)):
        await asyncio.to_thread(repo.settings.save_settings, {"resume_template": body.template})
        return {"ok": True}

    @router.get("/preferences")
    async def get_preferences(repo: Repository = Depends(get_repository)):
        """The user's free-text 'what I'm looking for' — steers the scan and ranking."""
        return {"preferences": await asyncio.to_thread(repo.settings.get_setting, "job_preferences", "")}

    @router.post("/preferences")
    async def save_preferences(body: PreferencesBody, repo: Repository = Depends(get_repository)):
        await asyncio.to_thread(repo.settings.save_settings, {"job_preferences": body.preferences})
        return {"ok": True}

    @router.get("/settings")
    async def get_cfg(repo: Repository = Depends(get_repository)):
        settings = await asyncio.to_thread(repo.settings.get_settings)
        for key in sensitive_keys(settings):
            if settings.get(key):
                settings[key] = MASK
        return settings

    @router.get("/settings/validate")
    async def validate_settings(repo: Repository = Depends(get_repository)):
        return await validate_provider_settings(repo)

    @router.post("/settings/validate")
    async def validate_pending_settings(body: SettingsBody, repo: Repository = Depends(get_repository)):
        return await validate_provider_settings(repo, body.model_dump())

    async def _provider_models_response(provider: str, incoming: dict | None, repo: Repository):
        provider = provider.strip().lower()
        cfg = _settings_with_incoming(repo, incoming)
        key = _provider_key(cfg, provider)
        # ollama is local-only; its models come from the user's own server, not a
        # public catalog. Keep it free-form (the picker accepts any typed id).
        if provider == "ollama":
            return {"provider": provider, "models": [], "catalog": []}

        # The always-current models.dev catalog needs no API key, so the picker is
        # populated for browsing the moment a provider is chosen. When a key IS
        # set, the live /v1/models call (what the key can actually reach) is merged
        # IN FRONT, so the user's real models lead and the rest of the catalog
        # follows. Anything neither knows about can still be typed in free-form.
        from llm.model_catalog import catalog_for_provider

        catalog = await asyncio.to_thread(catalog_for_provider, provider)
        live: list[str] = []
        if key:
            try:
                live = await list_provider_models(provider, key, cfg)
            except Exception:
                live = []  # fall back to the catalog silently rather than erroring

        seen: set[str] = set()
        merged: list[str] = []
        for model_id in [*live, *[str(row["id"]) for row in catalog if row.get("id")]]:
            low = model_id.lower()
            if low and low not in seen:
                seen.add(low)
                merged.append(model_id)

        resp = {"provider": provider, "models": merged, "catalog": catalog}
        if not merged:
            resp["error"] = "not_configured" if not key else "unreachable"
        return resp

    @router.get("/settings/models/{provider}")
    async def get_provider_models(provider: str, repo: Repository = Depends(get_repository)):
        return await _provider_models_response(provider, None, repo)

    @router.post("/settings/models/{provider}")
    async def post_provider_models(provider: str, body: SettingsBody, repo: Repository = Depends(get_repository)):
        return await _provider_models_response(provider, body.model_dump(), repo)

    @router.get("/settings/subscription-status")
    async def subscription_status():
        """Install + login state for the subscription-CLI providers (no API key needed)."""
        from llm import SUBSCRIPTION_CLI_PROVIDERS, subscription_cli
        out = {}
        for p in sorted(SUBSCRIPTION_CLI_PROVIDERS):
            s = subscription_cli.status(p)
            if not s.get("installed"):
                s["install_hint"] = subscription_cli.install_hint(p)
            out[p] = s
        return out

    @router.post("/settings/subscription-login/{provider}")
    async def subscription_login(provider: str):
        """Launch the CLI's own browser sign-in; the UI then polls subscription-status."""
        from llm import SUBSCRIPTION_CLI_PROVIDERS, subscription_cli
        if provider not in SUBSCRIPTION_CLI_PROVIDERS:
            raise HTTPException(status_code=400, detail="unknown subscription provider")
        try:
            return subscription_cli.login(provider)
        except subscription_cli.CliNotInstalled as exc:
            return {"started": False, "error": "not_installed",
                    "hint": subscription_cli.install_hint(provider), "detail": str(exc)}

    @router.post("/settings")
    async def save_cfg(body: SettingsBody, repo: Repository = Depends(get_repository)):
        payload = {key: "" if value is None else str(value) for key, value in body.model_dump().items()}
        old = await asyncio.to_thread(repo.settings.get_settings)
        for key in sensitive_keys({**old, **payload}):
            if payload.get(key) in LEGACY_MASKS:
                payload[key] = old.get(key, "")
        try:
            await asyncio.to_thread(repo.settings.save_settings, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if payload.get("ghost_mode") == "true":
            ensure_ghost_job(scheduler, ghost_tick)
        return {"ok": True}

    @router.post("/data/reset")
    async def reset_data(body: ResetDataBody):
        """Danger zone: wipe local data (leads, profile graph, vectors, generated
        documents) so the app can be reset for a clean test. Settings + provider
        config are kept unless ``clear_settings`` is set. Requires confirm=DELETE."""
        from data.maintenance import reset_all_data

        summary = await asyncio.to_thread(reset_all_data, clear_settings=body.clear_settings)
        if body.clear_settings:
            # Drop cached LLM clients so a wiped provider config isn't reused. (Done
            # here in the api layer — the data layer must not import llm.)
            from llm.client import reset_client_cache

            await asyncio.to_thread(reset_client_cache)
        return {"ok": True, "summary": summary}

    return router
