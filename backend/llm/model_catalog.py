"""Always-current model catalog, backed by models.dev.

The set of usable models changes constantly, so hardcoding it goes stale fast.
Instead we pull the open, community-maintained models.dev database — every
provider, every model, with context window, pricing, reasoning support and
release date — and merge it with what the user's own API key can actually see
(the live ``/v1/models`` call). A trimmed snapshot is bundled (models_snapshot.json)
so the picker is complete and instant even offline, and is refreshed from the
network when reachable.

This is how tools like OpenCode / LiteLLM stay current: a live registry, not a
list someone has to hand-edit. Anything the registry doesn't know about still
works — the model field is always free-form, so a brand-new id can be typed in.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from core.logging import get_logger

_log = get_logger(__name__)

_SNAPSHOT_PATH = Path(__file__).with_name("models_snapshot.json")
_MODELS_DEV_URL = "https://models.dev/api.json"
_CACHE_TTL_SECONDS = 24 * 3600

# JustHireMe provider id -> models.dev provider key. Providers absent here
# (sambanova, custom, ollama, the subscription CLIs) simply have no catalog and
# fall back to the live /v1/models call and/or free-form entry.
_PROVIDER_MAP: dict[str, str] = {
    "anthropic": "anthropic",
    "openai": "openai",
    "gemini": "google",
    "groq": "groq",
    "deepseek": "deepseek",
    "xai": "xai",
    "kimi": "moonshotai",
    "mistral": "mistral",
    "openrouter": "openrouter",
    "together": "togetherai",
    "fireworks": "fireworks-ai",
    "cerebras": "cerebras",
    "perplexity": "perplexity",
    "huggingface": "huggingface",
    "cohere": "cohere",
    "qwen": "alibaba",
    "nvidia": "nvidia",
    "azure": "azure",
}

_lock = threading.Lock()
_snapshot: dict | None = None
_live: dict = {"at": 0.0, "providers": None}


def _load_snapshot() -> dict:
    global _snapshot
    if _snapshot is None:
        try:
            _snapshot = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8")).get("providers", {})
        except Exception as exc:
            _log.warning("bundled model snapshot unreadable: %s", exc)
            _snapshot = {}
    return _snapshot


def _normalize(api: dict) -> dict[str, list[dict]]:
    """Map a models.dev api.json payload to {jhm_provider: [model rows]}, newest
    first, keeping only the fields the picker needs."""
    out: dict[str, list[dict]] = {}
    for jhm, mdev in _PROVIDER_MAP.items():
        prov = api.get(mdev) or {}
        rows: list[dict] = []
        for mid, m in (prov.get("models") or {}).items():
            if not isinstance(m, dict):
                continue
            limit = m.get("limit") or {}
            cost = m.get("cost") or {}
            rows.append({
                "id": m.get("id", mid),
                "name": m.get("name", mid),
                "release_date": m.get("release_date", ""),
                "reasoning": bool(m.get("reasoning")),
                "context": limit.get("context"),
                "input": cost.get("input"),
                "output": cost.get("output"),
            })
        rows.sort(key=lambda r: (r.get("release_date") or "0000"), reverse=True)
        if rows:
            out[jhm] = rows
    return out


def _fetch_live() -> dict[str, list[dict]] | None:
    """Fetch + normalize models.dev, cached in-memory for the TTL. None on any
    failure (caller falls back to the bundled snapshot)."""
    now = time.monotonic()
    with _lock:
        cached = _live["providers"]
        if cached is not None and (now - _live["at"]) < _CACHE_TTL_SECONDS:
            return cached
    try:
        import httpx

        response = httpx.get(_MODELS_DEV_URL, timeout=10.0, headers={"User-Agent": "JustHireMe model catalog"})
        response.raise_for_status()
        data = _normalize(response.json())
    except Exception as exc:
        _log.info("models.dev fetch failed (%s) — using bundled snapshot", exc)
        return None
    with _lock:
        _live["at"] = now
        _live["providers"] = data
    return data


def catalog_for_provider(provider: str) -> list[dict]:
    """Current models for a provider, with metadata — from models.dev (live,
    cached) falling back to the bundled snapshot. Empty for providers not in the
    catalog (local / custom / subscription CLIs); those rely on live /v1/models
    and free-form entry."""
    live = _fetch_live()
    if live and provider in live:
        return live[provider]
    return _load_snapshot().get(provider, [])


def catalog_ids(provider: str) -> list[str]:
    """Just the model ids for a provider (newest first)."""
    return [str(row["id"]) for row in catalog_for_provider(provider) if row.get("id")]


def has_catalog(provider: str) -> bool:
    return provider in _PROVIDER_MAP
