"""Unit tests for settings/providers.py — key probing and model listing.

Every provider gets its own endpoint and auth header; a wrong one silently
reports a valid key as unreachable. All HTTP is faked, so no network and no key.
"""

from __future__ import annotations

import httpx
import pytest

from settings import providers


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


def _fake_client(monkeypatch, response=None, record=None, raises=None):
    calls = record if record is not None else []

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, headers=None):
            calls.append(("GET", url, headers))
            if raises:
                raise raises
            return response or _Response()

        async def post(self, url, headers=None, json=None):
            calls.append(("POST", url, headers))
            if raises:
                raise raises
            return response or _Response()

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    return calls


# --------------------------------------------------------------- provider_key


def test_provider_key_prefers_the_stored_setting(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    assert providers.provider_key({"openai_api_key": " stored "}, "openai") == "stored"


def test_provider_key_falls_back_to_the_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    assert providers.provider_key({}, "openai") == "env-key"


def test_gemini_also_accepts_the_google_variable(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    assert providers.provider_key({}, "gemini") == "google-key"


def test_provider_key_is_empty_for_an_unknown_provider(monkeypatch):
    assert providers.provider_key({}, "not-a-provider") == ""


# ----------------------------------------------------------------- probing


@pytest.mark.asyncio
@pytest.mark.parametrize("provider, expected_url", [
    ("openai", "https://api.openai.com/v1/models"),
    ("groq", "https://api.groq.com/openai/v1/models"),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/models"),
    ("deepseek", "https://api.deepseek.com/models"),
])
async def test_probe_hits_each_providers_own_endpoint(provider, expected_url, monkeypatch):
    calls = _fake_client(monkeypatch)
    result = await providers.probe_provider_key(provider, "k")
    assert result["status"] == "ok"
    assert calls[0][1] == expected_url
    assert "latency_ms" in result


@pytest.mark.asyncio
async def test_anthropic_probe_posts_a_one_token_message(monkeypatch):
    calls = _fake_client(monkeypatch)
    result = await providers.probe_provider_key("anthropic", "sk-ant")
    assert result["status"] == "ok"
    method, url, headers = calls[0]
    assert method == "POST" and url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "sk-ant"


@pytest.mark.asyncio
async def test_anthropic_treats_400_as_a_valid_key(monkeypatch):
    """A 400 means the request shape was rejected — the key still authenticated."""
    _fake_client(monkeypatch, _Response(400))
    assert (await providers.probe_provider_key("anthropic", "k"))["status"] == "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize("status, expected", [(401, "invalid_key"), (500, "unreachable"), (200, "ok")])
async def test_probe_classifies_http_status(status, expected, monkeypatch):
    _fake_client(monkeypatch, _Response(status))
    assert (await providers.probe_provider_key("openai", "k"))["status"] == expected


@pytest.mark.asyncio
async def test_probe_reports_unreachable_instead_of_raising(monkeypatch):
    _fake_client(monkeypatch, raises=httpx.ConnectError("no route"))
    assert (await providers.probe_provider_key("openai", "k"))["status"] == "unreachable"


@pytest.mark.asyncio
async def test_an_unknown_provider_is_unchecked_not_invalid(monkeypatch):
    _fake_client(monkeypatch)
    assert (await providers.probe_provider_key("ollama", "k"))["status"] == "unchecked"


@pytest.mark.asyncio
async def test_azure_without_an_endpoint_is_unchecked(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    _fake_client(monkeypatch)
    assert (await providers.probe_provider_key("azure", "k", {}))["status"] == "unchecked"


@pytest.mark.asyncio
async def test_azure_endpoint_is_normalised_and_uses_the_api_key_header(monkeypatch):
    calls = _fake_client(monkeypatch)
    await providers.probe_provider_key("azure", "k", {"azure_openai_endpoint": "https://acme.openai.azure.com/"})
    _method, url, headers = calls[0]
    assert url == "https://acme.openai.azure.com/openai/v1/models"
    assert headers == {"api-key": "k"}


# ------------------------------------------------------------ model listing


@pytest.mark.asyncio
async def test_list_models_parses_the_openai_shape(monkeypatch):
    _fake_client(monkeypatch, _Response(200, {"data": [{"id": "gpt-b"}, {"id": "gpt-a"}]}))
    assert await providers.list_provider_models("openai", "k") == ["gpt-a", "gpt-b"]


@pytest.mark.asyncio
async def test_list_models_accepts_plain_strings_and_dedupes(monkeypatch):
    _fake_client(monkeypatch, _Response(200, {"models": ["b", "a", "a"]}))
    assert await providers.list_provider_models("groq", "k") == ["a", "b"]


@pytest.mark.asyncio
async def test_list_models_reads_alternate_id_fields(monkeypatch):
    _fake_client(monkeypatch, _Response(200, {"data": [{"name": "by-name"}, {"model": "by-model"}]}))
    assert await providers.list_provider_models("openai", "k") == ["by-model", "by-name"]


@pytest.mark.asyncio
async def test_list_models_is_empty_for_an_unknown_provider(monkeypatch):
    _fake_client(monkeypatch)
    assert await providers.list_provider_models("nope", "k") == []


@pytest.mark.asyncio
async def test_list_models_is_empty_for_azure_without_an_endpoint(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    _fake_client(monkeypatch)
    assert await providers.list_provider_models("azure", "k", {}) == []


@pytest.mark.asyncio
async def test_anthropic_listing_uses_the_versioned_header(monkeypatch):
    calls = _fake_client(monkeypatch, _Response(200, {"data": []}))
    await providers.list_provider_models("anthropic", "sk-ant")
    _method, url, headers = calls[0]
    assert url == "https://api.anthropic.com/v1/models"
    assert headers["anthropic-version"] == "2023-06-01"


@pytest.mark.asyncio
async def test_list_models_propagates_an_http_error(monkeypatch):
    """The caller falls back to the catalog; it must see the failure to do that."""
    _fake_client(monkeypatch, _Response(401))
    with pytest.raises(httpx.HTTPStatusError):
        await providers.list_provider_models("openai", "bad-key")
