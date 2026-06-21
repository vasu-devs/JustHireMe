"""Tests for the always-current model catalog (llm/model_catalog.py).

The catalog pulls models.dev live (cached) and falls back to a bundled snapshot
offline, mapping models.dev's provider keys to JustHireMe's. These tests pin the
mapping, the live-vs-snapshot precedence, and the graceful offline fallback —
without hitting the network (httpx.get is monkeypatched).
"""

from __future__ import annotations

import pytest

from llm import model_catalog as mc


@pytest.fixture(autouse=True)
def _reset_live_cache():
    mc._live["at"] = 0.0
    mc._live["providers"] = None
    yield
    mc._live["at"] = 0.0
    mc._live["providers"] = None


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_bundled_snapshot_has_mapped_providers_with_metadata():
    snap = mc._load_snapshot()
    assert {"openai", "anthropic", "openrouter", "gemini"} <= set(snap)
    assert len(snap["openrouter"]) > 50  # OpenRouter aggregates hundreds
    row = snap["openai"][0]
    assert {"id", "name", "release_date"} <= set(row)


def test_normalize_maps_modelsdev_keys_to_jhm_providers():
    api = {
        "google": {"models": {"gemini-x": {
            "id": "gemini-x", "name": "G", "release_date": "2026-01-01",
            "limit": {"context": 1000}, "cost": {"input": 1, "output": 2}, "reasoning": True,
        }}},
        "moonshotai": {"models": {"kimi-z": {"id": "kimi-z", "name": "K", "release_date": "2025-01-01"}}},
        "alibaba": {"models": {"qwen-z": {"id": "qwen-z", "name": "Q", "release_date": "2025-06-01"}}},
    }
    out = mc._normalize(api)
    # models.dev "google"/"moonshotai"/"alibaba" -> JHM "gemini"/"kimi"/"qwen"
    assert out["gemini"][0]["id"] == "gemini-x"
    assert out["gemini"][0]["context"] == 1000 and out["gemini"][0]["reasoning"] is True
    assert out["kimi"][0]["id"] == "kimi-z"
    assert out["qwen"][0]["id"] == "qwen-z"


def test_live_catalog_used_when_fetch_succeeds(monkeypatch):
    payload = {"openai": {"models": {"brand-new-2099": {"id": "brand-new-2099", "name": "New", "release_date": "2099-01-01"}}}}
    monkeypatch.setattr("httpx.get", lambda *a, **k: _Resp(payload))
    rows = mc.catalog_for_provider("openai")
    assert any(r["id"] == "brand-new-2099" for r in rows), "live models.dev result must win over the snapshot"


def test_falls_back_to_snapshot_when_offline(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("offline")

    monkeypatch.setattr("httpx.get", boom)
    rows = mc.catalog_for_provider("openai")
    assert len(rows) >= 10, "offline must still yield the full bundled snapshot"
    assert all("id" in r for r in rows)


def test_newest_first_ordering(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    rows = mc.catalog_for_provider("anthropic")
    dates = [r["release_date"] for r in rows if r["release_date"]]
    assert dates == sorted(dates, reverse=True)


def test_unmapped_providers_have_no_catalog(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    assert mc.has_catalog("sambanova") is False
    assert mc.has_catalog("custom") is False
    assert mc.catalog_for_provider("custom") == []
