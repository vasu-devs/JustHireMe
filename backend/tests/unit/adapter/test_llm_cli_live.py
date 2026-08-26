"""OPT-IN live smoke for the keyless subscription CLIs (claude_cli, codex_cli).

Unlike test_provider_keyless_calls.py (which mocks subprocess and runs everywhere,
including CI), these tests make REAL calls to the locally-installed ``claude`` /
``codex`` CLIs against a logged-in subscription. They are therefore:

  - SKIPPED by default and in CI (CI has no subscription) — gated behind the
    JHM_LIVE_CLI env var, which CI never sets.
  - SKIPPED per-provider if that CLI is not on PATH.

This is a correctly-gated external-resource integration test, not a silenced one:
when you opt in WITH the CLIs present, it must pass. Run it with:

    cd backend && JHM_LIVE_CLI=1 uv run python -m pytest tests/test_llm_cli_live.py -v
    # or, cross-platform, from the repo root:
    npm run smoke:llm-cli

A graceful fallback (empty string / blank model) is treated as a FAILURE here,
because opting in asserts the real subscription is reachable and working.
"""

from __future__ import annotations

import os
import shutil

import pytest
from pydantic import BaseModel

from llm import client

_OPT_IN = os.environ.get("JHM_LIVE_CLI", "").strip().lower() in {"1", "true", "yes", "on"}

pytestmark = pytest.mark.skipif(
    not _OPT_IN,
    reason="opt-in live-CLI smoke: set JHM_LIVE_CLI=1 (needs a logged-in claude/codex subscription)",
)

# (settings key value, PATH binary name) for each keyless subscription provider.
_PROVIDERS = [
    pytest.param("claude_cli", "claude", id="claude_cli"),
    pytest.param("codex_cli", "codex", id="codex_cli"),
]


class _Greeting(BaseModel):
    """A schema with two required-ish fields so a populated model is clearly
    distinguishable from the empty _parse_fallback() instance."""

    greeting: str = ""
    language: str = ""


@pytest.fixture
def use_provider():
    """Point the LLM client's settings at a chosen keyless provider, restoring
    the real repository afterwards (configure_repository is process-global)."""
    from data.repository import create_repository

    def _apply(provider: str):
        class _Settings:
            def get_setting(self, key, default=""):
                return {"llm_provider": provider}.get(key, default)

        class _Repo:
            settings = _Settings()

        client.configure_repository(_Repo())

    yield _apply
    client.configure_repository(create_repository())


@pytest.mark.parametrize("provider,binary", _PROVIDERS)
def test_live_cli_call_raw(use_provider, provider, binary):
    if shutil.which(binary) is None:
        pytest.skip(f"{binary} CLI not on PATH")
    use_provider(provider)

    out = client.call_raw("You are terse.", "Reply with exactly one word: pong")

    assert isinstance(out, str)
    assert out.strip(), (
        f"{provider} call_raw returned empty — the CLI was unreachable or not "
        f"logged in (run `{binary}` and sign in)."
    )


@pytest.mark.parametrize("provider,binary", _PROVIDERS)
def test_live_cli_call_llm_structured(use_provider, provider, binary):
    if shutil.which(binary) is None:
        pytest.skip(f"{binary} CLI not on PATH")
    use_provider(provider)

    out = client.call_llm(
        "Extract a greeting as structured data.",
        "Greet me in French. Return the greeting text and the language name.",
        _Greeting,
    )

    assert isinstance(out, _Greeting)
    assert out.greeting.strip(), f"{provider} call_llm returned an empty greeting (fallback model?)"
    assert out.language.strip(), f"{provider} call_llm returned an empty language (fallback model?)"
