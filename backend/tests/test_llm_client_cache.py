"""LLM SDK clients are cached/reused across calls (Tier-2 deferred: client cache).

Each call used to construct a fresh OpenAI/Anthropic client (new httpx pool +
TLS). Clients are now cached by their exact constructor kwargs so the connection
pool is reused, while different configs still get distinct clients.
"""
import threading

import llm.client as c


def test_openai_client_is_cached_per_config():
    c.reset_client_cache()
    a = c._openai(api_key="k1", timeout=c._TIMEOUT)
    b = c._openai(api_key="k1", timeout=c._TIMEOUT)
    assert a is b  # identical config -> same cached client


def test_different_key_or_base_url_gives_distinct_clients():
    c.reset_client_cache()
    a = c._openai(api_key="k1", timeout=c._TIMEOUT)
    assert c._openai(api_key="k2", timeout=c._TIMEOUT) is not a
    g = c._openai(base_url="https://api.groq.com/openai/v1", api_key="k1", timeout=c._TIMEOUT, max_retries=0)
    d = c._openai(base_url="https://api.deepseek.com", api_key="k1", timeout=c._TIMEOUT, max_retries=0)
    assert g is not d


def test_max_retries_difference_is_distinct():
    # openai branch omits max_retries (SDK default); others pass 0 — must not collide.
    c.reset_client_cache()
    default_retries = c._openai(api_key="k", timeout=c._TIMEOUT)
    zero_retries = c._openai(api_key="k", timeout=c._TIMEOUT, max_retries=0)
    assert default_retries is not zero_retries


def test_cache_handles_unhashable_httpx_timeout():
    # _TIMEOUT is an httpx.Timeout (not hashable) — the repr-based key must work.
    c.reset_client_cache()
    client = c._openai(api_key="k", timeout=c._TIMEOUT, max_retries=0)
    assert client is c._openai(api_key="k", timeout=c._TIMEOUT, max_retries=0)


def test_anthropic_client_is_cached():
    c.reset_client_cache()
    a = c._anthropic(api_key="k", timeout=120.0)
    assert c._anthropic(api_key="k", timeout=120.0) is a


def test_reset_clears_cache():
    c.reset_client_cache()
    a = c._openai(api_key="k", timeout=c._TIMEOUT)
    c.reset_client_cache()
    assert c._openai(api_key="k", timeout=c._TIMEOUT) is not a


def test_provider_helpers_return_cached_clients():
    c.reset_client_cache()
    assert c._client_gemini("gkey") is c._client_gemini("gkey")
    assert c._client_openai_compat("openrouter", "okey") is c._client_openai_compat("openrouter", "okey")


def test_concurrent_calls_share_one_client():
    c.reset_client_cache()
    results = []

    def grab():
        results.append(c._openai(api_key="shared", timeout=c._TIMEOUT))

    threads = [threading.Thread(target=grab) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(map(id, results))) == 1  # all threads got the same cached instance


def test_cache_boundary_splits_anthropic_and_strips_elsewhere(monkeypatch):
    """The \x1e marker becomes a cache_control prefix block on the anthropic
    path and is stripped for every other provider."""
    from types import SimpleNamespace
    from pydantic import BaseModel

    from llm import client as llm_client

    class _Out(BaseModel):
        answer: str = ""

    captured = {}

    class _FakeMessages:
        def parse(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(parsed_output=_Out(answer="ok"))

    monkeypatch.setattr(llm_client, "_resolve", lambda step: ("anthropic", "k", "claude-sonnet-5"))
    monkeypatch.setattr(
        llm_client, "_anthropic",
        lambda **kw: SimpleNamespace(messages=_FakeMessages()),
    )
    prompt = "STATIC PROFILE" + llm_client.CACHE_BOUNDARY + "PER-LEAD JD"
    out = llm_client._call_llm_once("sys", prompt, _Out, step="evaluator")
    assert out.answer == "ok"
    content = captured["messages"][0]["content"]
    assert isinstance(content, list) and len(content) == 2
    assert content[0]["text"] == "STATIC PROFILE"
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    assert content[1]["text"] == "PER-LEAD JD"
    assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}

    # Marker-free prompts stay plain strings (no behavior change).
    captured.clear()
    llm_client._call_llm_once("sys", "no marker here", _Out, step="evaluator")
    assert captured["messages"][0]["content"] == "no marker here"

    # Non-anthropic providers must never see the marker.
    assert llm_client.CACHE_BOUNDARY not in "x".join(
        llm_client._anthropic_user_content("a" + llm_client.CACHE_BOUNDARY + "b")[1]["text"]
    )
