"""Provider key probing and model listing.

Outbound HTTP to the LLM vendors' own endpoints. Kept apart from
``settings.service`` so the probe/list logic can be tested without a repository.
"""

from __future__ import annotations

import time

from core import env


def provider_key(cfg: dict, provider: str) -> str:
    from llm import _ENV_NAMES, _KEY_NAMES

    key_name = _KEY_NAMES.get(provider, "")
    return str(
        cfg.get(key_name)
        or env.get(_ENV_NAMES.get(provider, ""))
        or (env.google_api_key() if provider == "gemini" else "")
        or ""
    ).strip()


def _azure_base(cfg: dict) -> str:
    endpoint = str(cfg.get("azure_openai_endpoint") or env.azure_openai_endpoint()).strip().rstrip("/")
    if not endpoint:
        return ""
    return endpoint if endpoint.endswith("/openai/v1") else f"{endpoint}/openai/v1"


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
                endpoint = _azure_base(settings or {})
                if not endpoint:
                    status = "unchecked"
                else:
                    response = await client.get(f"{endpoint}/models", headers={"api-key": key})
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
        endpoint = _azure_base(cfg)
        if not endpoint:
            return []
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


__all__ = ["list_provider_models", "probe_provider_key", "provider_key"]
