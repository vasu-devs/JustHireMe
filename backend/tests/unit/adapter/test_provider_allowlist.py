"""Regression: the subscription-CLI providers must pass settings validation
(this is what blocked Save when codex_cli/claude_cli were chosen)."""
from data.sqlite.settings import validate_setting


def test_subscription_providers_allowed():
    for key in ("llm_provider", "evaluator_provider"):
        for prov in ("claude_cli", "codex_cli"):
            ok, msg = validate_setting(key, prov)
            assert ok, f"{key}={prov} should be allowed but got: {msg}"


def test_bogus_provider_still_rejected():
    ok, msg = validate_setting("llm_provider", "totally-fake")
    assert not ok and "must be one of" in msg
