"""Unit tests for settings/ — masking, persistence, provider catalog, reset."""

from __future__ import annotations

import types

import pytest

from core.errors import ValidationError
from settings.masking import MASK, mask_secrets, resolve_masked, sensitive_keys
from settings.service import SettingsService


def _repo(stored=None, save_error=None):
    state = {"settings": dict(stored or {}), "saved": []}

    class Store:
        def get_settings(self):
            return dict(state["settings"])

        def get_setting(self, key, default=""):
            return state["settings"].get(key, default)

        def save_settings(self, payload):
            if save_error:
                raise ValueError(save_error)
            state["saved"].append(payload)
            state["settings"].update(payload)

    repo = types.SimpleNamespace(settings=Store())
    repo._state = state
    return repo


# --------------------------------------------------------------------- masking


@pytest.mark.parametrize("key", [
    "anthropic_key", "openai_api_key", "linkedin_cookie", "x_bearer_token",
    "custom_connector_headers", "some_provider_token",
])
def test_sensitive_keys_covers_fixed_and_suffix_matched_names(key):
    assert key in sensitive_keys({key: "v"})


def test_non_secret_settings_are_not_treated_as_sensitive():
    assert "job_preferences" not in sensitive_keys({"job_preferences": "remote"})


def test_mask_secrets_replaces_values_but_keeps_empty_ones():
    masked = mask_secrets({"openai_api_key": "sk-real", "anthropic_key": "", "city": "Pune"})
    assert masked["openai_api_key"] == MASK
    assert masked["anthropic_key"] == ""      # nothing stored -> nothing to hide
    assert masked["city"] == "Pune"


def test_resolve_masked_restores_the_stored_secret():
    resolved = resolve_masked({"openai_api_key": MASK}, {"openai_api_key": "sk-real"})
    assert resolved["openai_api_key"] == "sk-real"


def test_resolve_masked_keeps_a_genuinely_new_secret():
    resolved = resolve_masked({"openai_api_key": "sk-new"}, {"openai_api_key": "sk-old"})
    assert resolved["openai_api_key"] == "sk-new"


@pytest.mark.parametrize("legacy", ["•" * 20, "â€¢" * 20])
def test_resolve_masked_understands_the_legacy_bullet_masks(legacy):
    """Older builds echoed bullets back; writing them would destroy a real key."""
    resolved = resolve_masked({"openai_api_key": legacy}, {"openai_api_key": "sk-real"})
    assert resolved["openai_api_key"] == "sk-real"


# -------------------------------------------------------------------- settings


@pytest.mark.asyncio
async def test_get_settings_never_returns_a_real_secret():
    repo = _repo({"openai_api_key": "sk-real", "city": "Pune"})
    result = await SettingsService(repo).get_settings()
    assert result["openai_api_key"] == MASK
    assert result["city"] == "Pune"


@pytest.mark.asyncio
async def test_save_settings_resolves_masks_before_writing():
    repo = _repo({"openai_api_key": "sk-real"})
    await SettingsService(repo).save_settings({"openai_api_key": MASK, "city": "Pune"})
    assert repo._state["saved"][0]["openai_api_key"] == "sk-real"


@pytest.mark.asyncio
async def test_save_settings_normalises_none_to_empty_string():
    repo = _repo()
    await SettingsService(repo).save_settings({"city": None})
    assert repo._state["saved"][0]["city"] == ""


@pytest.mark.asyncio
async def test_save_settings_reports_whether_ghost_mode_was_enabled():
    repo = _repo()
    service = SettingsService(repo)
    assert await service.save_settings({"ghost_mode": "true"}) is True
    assert await service.save_settings({"ghost_mode": "false"}) is False


@pytest.mark.asyncio
async def test_save_settings_maps_a_rejected_value_to_a_domain_error():
    with pytest.raises(ValidationError, match="bad value"):
        await SettingsService(_repo(save_error="bad value")).save_settings({"city": "x"})


@pytest.mark.asyncio
async def test_template_and_preferences_round_trip():
    repo = _repo()
    service = SettingsService(repo)
    await service.save_resume_template("TEMPLATE")
    await service.save_preferences("remote python")
    assert (await service.get_resume_template())["template"] == "TEMPLATE"
    assert (await service.get_preferences())["preferences"] == "remote python"


# ------------------------------------------------------------------- providers


@pytest.mark.asyncio
async def test_provider_models_is_free_form_for_ollama():
    result = await SettingsService(_repo()).provider_models("Ollama")
    assert result == {"provider": "ollama", "models": [], "catalog": []}


@pytest.mark.asyncio
async def test_provider_models_merges_live_models_in_front_of_the_catalog(monkeypatch):
    monkeypatch.setattr("settings.service.catalog_for_provider", lambda p: [{"id": "cat-1"}, {"id": "live-1"}], raising=False)
    monkeypatch.setattr("llm.model_catalog.catalog_for_provider", lambda p: [{"id": "cat-1"}, {"id": "live-1"}])

    async def fake_list(provider, key, cfg):
        return ["live-1"]

    monkeypatch.setattr("settings.service.list_provider_models", fake_list)
    monkeypatch.setattr("settings.service.provider_key", lambda cfg, provider: "sk-key")

    result = await SettingsService(_repo()).provider_models("openai")
    assert result["models"][0] == "live-1"          # the user's real models lead
    assert "cat-1" in result["models"]              # catalog follows
    assert result["models"].count("live-1") == 1    # de-duped case-insensitively


@pytest.mark.asyncio
async def test_provider_models_falls_back_to_the_catalog_when_the_key_fails(monkeypatch):
    monkeypatch.setattr("llm.model_catalog.catalog_for_provider", lambda p: [{"id": "cat-1"}])

    async def boom(provider, key, cfg):
        raise RuntimeError("401")

    monkeypatch.setattr("settings.service.list_provider_models", boom)
    monkeypatch.setattr("settings.service.provider_key", lambda cfg, provider: "sk-key")

    result = await SettingsService(_repo()).provider_models("openai")
    assert result["models"] == ["cat-1"]
    assert "error" not in result


@pytest.mark.asyncio
async def test_provider_models_flags_an_unconfigured_provider(monkeypatch):
    monkeypatch.setattr("llm.model_catalog.catalog_for_provider", lambda p: [])
    monkeypatch.setattr("settings.service.provider_key", lambda cfg, provider: "")
    result = await SettingsService(_repo()).provider_models("openai")
    assert result["error"] == "not_configured"


@pytest.mark.asyncio
async def test_validate_providers_reports_not_configured_without_probing(monkeypatch):
    monkeypatch.setattr("settings.service.provider_key", lambda cfg, provider: "")

    async def explode(*a, **k):
        raise AssertionError("must not probe a provider with no key")

    monkeypatch.setattr("settings.service.probe_provider_key", explode)
    result = await SettingsService(_repo()).validate_providers()
    assert all(entry["status"] == "not_configured" for entry in result.values())


@pytest.mark.asyncio
async def test_subscription_login_rejects_an_unknown_provider():
    with pytest.raises(ValidationError):
        await SettingsService(_repo()).subscription_login("not-a-provider")


# ----------------------------------------------------------------- danger zone


@pytest.mark.asyncio
async def test_reset_data_keeps_provider_config_by_default(monkeypatch):
    calls = {}
    monkeypatch.setattr("data.maintenance.reset_all_data",
                        lambda clear_settings: calls.setdefault("clear", clear_settings) or {"leads": 3})

    def explode():
        raise AssertionError("LLM cache must only be reset when settings are cleared")

    monkeypatch.setattr("llm.client.reset_client_cache", explode)
    summary = await SettingsService(_repo()).reset_data(clear_settings=False)
    assert summary == {"leads": 3} and calls["clear"] is False


@pytest.mark.asyncio
async def test_reset_data_drops_cached_llm_clients_when_settings_are_wiped(monkeypatch):
    reset = {"called": False}
    monkeypatch.setattr("data.maintenance.reset_all_data", lambda clear_settings: {})
    monkeypatch.setattr("llm.client.reset_client_cache", lambda: reset.update(called=True))
    await SettingsService(_repo()).reset_data(clear_settings=True)
    assert reset["called"], "a wiped provider config must not be reused from cache"
