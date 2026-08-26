"""Settings service — business layer behind the settings router."""

from __future__ import annotations

import asyncio

from core.errors import ValidationError
from data.repository import Repository
from settings.masking import mask_secrets, resolve_masked, sensitive_keys
from settings.providers import list_provider_models, probe_provider_key, provider_key


class SettingsService:
    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    # ------------------------------------------------------------ plain values

    async def get_setting(self, key: str, default: str = "") -> str:
        return await asyncio.to_thread(self._repo.settings.get_setting, key, default)

    async def set_setting(self, key: str, value: str) -> None:
        await asyncio.to_thread(self._repo.settings.save_settings, {key: value})

    async def get_resume_template(self) -> dict:
        return {"template": await self.get_setting("resume_template", "")}

    async def save_resume_template(self, template: str) -> None:
        await self.set_setting("resume_template", template)

    async def get_preferences(self) -> dict:
        """The user's free-text 'what I'm looking for' — steers the scan and ranking."""
        return {"preferences": await self.get_setting("job_preferences", "")}

    async def save_preferences(self, preferences: str) -> None:
        await self.set_setting("job_preferences", preferences)

    # ---------------------------------------------------------------- settings

    async def get_settings(self) -> dict:
        """Settings with every secret masked — the UI never receives a real key."""
        return mask_secrets(await asyncio.to_thread(self._repo.settings.get_settings))

    async def save_settings(self, payload: dict) -> bool:
        """Persist settings. Returns True when ghost mode was switched on."""
        normalised = {key: "" if value is None else str(value) for key, value in payload.items()}
        stored = await asyncio.to_thread(self._repo.settings.get_settings)
        resolved = resolve_masked(normalised, stored)
        try:
            await asyncio.to_thread(self._repo.settings.save_settings, resolved)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return resolved.get("ghost_mode") == "true"

    async def _settings_with_incoming(self, incoming: dict | None) -> dict:
        cfg = await asyncio.to_thread(self._repo.settings.get_settings)
        if not incoming:
            return cfg
        merged = {**cfg, **{key: "" if value is None else str(value) for key, value in incoming.items()}}
        return resolve_masked(merged, cfg)

    # --------------------------------------------------------------- providers

    async def validate_providers(self, incoming: dict | None = None) -> dict:
        from llm import _KEY_NAMES, _OPENAI_COMPAT_BASE_URLS

        cfg = await self._settings_with_incoming(incoming)
        probed = {"anthropic", "gemini", "openai", "groq", "deepseek", "azure", *_OPENAI_COMPAT_BASE_URLS}
        providers = [
            "anthropic",
            "gemini",
            "openai",
            "groq",
            *[provider for provider in _KEY_NAMES if provider not in {"anthropic", "gemini", "openai", "groq"}],
        ]

        async def one(provider: str):
            key = provider_key(cfg, provider)
            if not key:
                return provider, {"status": "not_configured", "latency_ms": 0}
            if provider not in probed:
                return provider, {"status": "unchecked", "latency_ms": 0}
            return provider, await probe_provider_key(provider, key, cfg)

        pairs = await asyncio.gather(*(one(provider) for provider in providers))
        return {provider: result for provider, result in pairs}

    async def provider_models(self, provider: str, incoming: dict | None = None) -> dict:
        provider = provider.strip().lower()
        cfg = await self._settings_with_incoming(incoming)
        key = provider_key(cfg, provider)
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

        response = {"provider": provider, "models": merged, "catalog": catalog}
        if not merged:
            response["error"] = "not_configured" if not key else "unreachable"
        return response

    # ----------------------------------------------------------- subscriptions

    async def subscription_status(self) -> dict:
        """Install + login state for the subscription-CLI providers (no API key needed)."""
        from llm import SUBSCRIPTION_CLI_PROVIDERS, subscription_cli

        out = {}
        for provider in sorted(SUBSCRIPTION_CLI_PROVIDERS):
            status = subscription_cli.status(provider)
            if not status.get("installed"):
                status["install_hint"] = subscription_cli.install_hint(provider)
            out[provider] = status
        return out

    async def subscription_login(self, provider: str) -> dict:
        """Launch the CLI's own browser sign-in; the UI then polls subscription-status."""
        from llm import SUBSCRIPTION_CLI_PROVIDERS, subscription_cli

        if provider not in SUBSCRIPTION_CLI_PROVIDERS:
            raise ValidationError("unknown subscription provider")
        try:
            return subscription_cli.login(provider)
        except subscription_cli.CliNotInstalled as exc:
            return {
                "started": False,
                "error": "not_installed",
                "hint": subscription_cli.install_hint(provider),
                "detail": str(exc),
            }

    # ------------------------------------------------------------ danger zone

    async def reset_data(self, *, clear_settings: bool) -> dict:
        """Wipe local data (leads, profile graph, vectors, generated documents).

        Settings and provider config are kept unless ``clear_settings`` is set.
        """
        from data.maintenance import reset_all_data

        summary = await asyncio.to_thread(reset_all_data, clear_settings=clear_settings)
        if clear_settings:
            # Drop cached LLM clients so a wiped provider config isn't reused.
            # Done here, not in data/: the data layer must not import llm.
            from llm.client import reset_client_cache

            await asyncio.to_thread(reset_client_cache)
        return summary


def create_settings_service(repo: Repository) -> SettingsService:
    return SettingsService(repo)


__all__ = ["SettingsService", "create_settings_service", "sensitive_keys"]
