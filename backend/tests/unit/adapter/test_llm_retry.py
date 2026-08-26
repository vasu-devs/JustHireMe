# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs
"""Regression tests for C2: LLM client retries transient errors with backoff.

``instructor`` is an optional heavy dependency that may be absent in minimal
environments; we stub it so the retry logic (pure Python) is exercised either
way. The stub is only installed if the real module is unavailable.
"""

import sys
import types

import httpx
import openai
import pytest

if "instructor" not in sys.modules:
    try:  # pragma: no cover - prefer the real module when present
        import instructor  # noqa: F401
    except ModuleNotFoundError:
        _stub = types.ModuleType("instructor")
        _stub.from_openai = lambda *a, **k: None  # type: ignore[attr-defined]
        _mode = types.SimpleNamespace(JSON="json", TOOLS="tools")
        _stub.Mode = _mode  # type: ignore[attr-defined]
        sys.modules["instructor"] = _stub

from llm import client  # noqa: E402


def _conn_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx.Request("POST", "https://api.test/v1"))


class _ServerError(Exception):
    """Stand-in for an SDK APIStatusError carrying a status_code."""

    def __init__(self, status_code: int):
        super().__init__(f"status {status_code}")
        self.status_code = status_code


def test_connection_error_is_retryable():
    assert client._is_retryable_llm_error(_conn_error()) is True


def test_5xx_is_retryable():
    assert client._is_retryable_llm_error(_ServerError(503)) is True


def test_4xx_is_not_retryable():
    assert client._is_retryable_llm_error(_ServerError(400)) is False


def test_generic_error_is_not_retryable():
    assert client._is_retryable_llm_error(ValueError("bad request")) is False


def test_retry_succeeds_after_transient_failures(monkeypatch):
    monkeypatch.setattr(client.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _ServerError(502)
        return "ok"

    assert client._retry_llm_call(flaky, max_retries=3) == "ok"
    assert calls["n"] == 3


def test_retry_exhausts_and_reraises(monkeypatch):
    monkeypatch.setattr(client.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def always_fails():
        calls["n"] += 1
        raise _ServerError(500)

    with pytest.raises(_ServerError):
        client._retry_llm_call(always_fails, max_retries=3)
    assert calls["n"] == 4  # 1 initial + 3 retries


def test_permanent_error_raises_immediately(monkeypatch):
    monkeypatch.setattr(client.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def auth_fails():
        calls["n"] += 1
        raise _ServerError(401)

    with pytest.raises(_ServerError):
        client._retry_llm_call(auth_fails, max_retries=3)
    assert calls["n"] == 1  # no retries for permanent errors


def test_timeout_is_reduced_to_120s():
    # H5: a 300s timeout could starve the thread pool; 120s is the new ceiling.
    assert client._TIMEOUT.read == 120.0


def test_llm_executor_is_dedicated_and_bounded():
    # H5: LLM calls run on their own bounded pool, not the default executor.
    assert client.LLM_EXECUTOR._max_workers == 4
    assert client.LLM_EXECUTOR._thread_name_prefix == "llm"


@pytest.mark.asyncio
async def test_acall_llm_runs_on_dedicated_executor(monkeypatch):
    captured = {}

    def fake_once(s, u, m, step=None):
        captured["thread"] = __import__("threading").current_thread().name
        return "structured"

    monkeypatch.setattr(client, "_call_llm_once", fake_once)
    result = await client.acall_llm("sys", "user", object, "ingestor")
    assert result == "structured"
    assert captured["thread"].startswith("llm")


@pytest.mark.asyncio
async def test_acall_raw_runs_on_dedicated_executor(monkeypatch):
    captured = {}

    def fake_once(s, u, step=None):
        captured["thread"] = __import__("threading").current_thread().name
        return "raw-text"

    monkeypatch.setattr(client, "_call_raw_once", fake_once)
    result = await client.acall_raw("sys", "user", "help")
    assert result == "raw-text"
    assert captured["thread"].startswith("llm")
