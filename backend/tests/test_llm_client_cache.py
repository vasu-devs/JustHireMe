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
