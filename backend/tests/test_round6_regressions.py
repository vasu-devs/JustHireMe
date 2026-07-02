"""Round-6 audit regressions: keyless-CLI key-source labels + per-call scan usage.

- startup_validation / health must treat gemini_cli & copilot_cli as keyless
  subscription CLIs (no spurious 'no API key' warning; key_source 'subscription').
- source_adapters must return each scan's OWN usage/errors, not a concurrent scan's
  (previously round-tripped through shared module globals).
"""

from __future__ import annotations

import threading

import pytest


class _FakeSettings:
    def __init__(self, cfg: dict):
        self._cfg = cfg

    def get_settings(self) -> dict:
        return self._cfg


class _FakeRepo:
    def __init__(self, cfg: dict):
        self.settings = _FakeSettings(cfg)


# --- startup_validation: keyless CLIs must not trigger a 'no key' warning ---------

@pytest.mark.parametrize("provider", ["gemini_cli", "copilot_cli", "claude_cli", "codex_cli", "ollama"])
def test_no_key_warning_for_keyless_providers(provider):
    from api.startup_validation import startup_warnings

    warns = startup_warnings(_FakeRepo({"llm_provider": provider}))
    assert not any("no API key" in w for w in warns), (provider, warns)


def test_key_warning_still_fires_for_keyed_provider(monkeypatch):
    from api.startup_validation import startup_warnings

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    warns = startup_warnings(_FakeRepo({"llm_provider": "openai"}))
    assert any("no API key" in w for w in warns), warns


# --- health: subscription CLIs report key_source 'subscription' -------------------

@pytest.mark.parametrize("provider", ["gemini_cli", "copilot_cli", "claude_cli", "codex_cli"])
def test_health_reports_subscription_source_for_clis(provider, monkeypatch):
    import llm
    from api.routers.health import _check_llm

    monkeypatch.setattr(llm, "resolve_config", lambda: (provider, "", f"{provider}-model"))
    out = _check_llm(_FakeRepo({}))
    assert out["status"] == "ok", out
    assert out["key_source"] == "subscription", out


# --- source_adapters: per-call usage sink, no cross-scan bleed --------------------

def test_run_free_scout_reads_per_call_usage(monkeypatch):
    from automation import free_scout, source_adapters

    def fake_run(**kwargs):
        free_scout._publish_state(["e1"], {"candidates": 7})
        return [{"job_id": "a"}]

    monkeypatch.setattr(free_scout, "run", fake_run)
    res = source_adapters.run_free_scout()
    assert res.leads == [{"job_id": "a"}]
    assert res.usage.get("candidates") == 7
    assert res.errors == ["e1"]


def test_concurrent_free_scans_do_not_cross_report(monkeypatch):
    from automation import free_scout, source_adapters

    barrier = threading.Barrier(2)
    results: dict[str, object] = {}

    def fake_run(**kwargs):
        tag, cand = kwargs["tag"], kwargs["cand"]
        free_scout._publish_state([f"err-{tag}"], {"candidates": cand, "tag": tag})
        # Block until BOTH calls have published, so the shared module global is
        # whichever ran last — proving the returned usage comes from the per-call
        # sink and not the clobbered global.
        barrier.wait(timeout=5)
        return [{"job_id": tag}]

    monkeypatch.setattr(free_scout, "run", fake_run)

    def worker(tag: str, cand: int):
        results[tag] = source_adapters.run_free_scout(tag=tag, cand=cand)

    t1 = threading.Thread(target=worker, args=("A", 7))
    t2 = threading.Thread(target=worker, args=("B", 99))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results["A"].usage["candidates"] == 7
    assert results["A"].usage["tag"] == "A"
    assert results["A"].errors == ["err-A"]
    assert results["B"].usage["candidates"] == 99
    assert results["B"].usage["tag"] == "B"
    assert results["B"].errors == ["err-B"]
