"""Cold-start retry semantics for subscription-CLI calls (Tier-1 deferred 4b)."""
from llm import subscription_cli as sc
from llm.client import _subscription_call


def test_retries_once_on_timeout_then_succeeds():
    calls = {"n": 0}

    def attempt():
        calls["n"] += 1
        if calls["n"] == 1:
            raise sc.CliTimeout("cold start")
        return "ok"

    out = _subscription_call("claude_cli", attempt, lambda: "FALLBACK", step="t")
    assert out == "ok"
    assert calls["n"] == 2  # retried exactly once


def test_falls_back_after_two_timeouts():
    def attempt():
        raise sc.CliTimeout("still cold")

    out = _subscription_call("claude_cli", attempt, lambda: "FALLBACK", step="t")
    assert out == "FALLBACK"


def test_no_retry_on_non_timeout_failure():
    calls = {"n": 0}

    def attempt():
        calls["n"] += 1
        raise sc.CliNotLoggedIn("please log in")

    out = _subscription_call("claude_cli", attempt, lambda: "FB", step="t")
    assert out == "FB"
    assert calls["n"] == 1  # login/credit/etc. fall back immediately, no retry


def test_success_passes_through_without_retry():
    calls = {"n": 0}

    def attempt():
        calls["n"] += 1
        return "result"

    assert _subscription_call("claude_cli", attempt, lambda: "FB", step="t") == "result"
    assert calls["n"] == 1
