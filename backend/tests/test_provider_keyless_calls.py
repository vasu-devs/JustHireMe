"""End-to-end-ish tests for the KEYLESS LLM providers (ollama, claude_cli,
codex_cli) driven through the real public client surface — call_llm (structured)
and call_raw (raw text).

Every external I/O boundary is mocked: no real CLI is spawned and no network
socket is opened. The provider is selected by stubbing the settings repository
(configure_repository, exactly like test_regression_llm_help.py), the
subscription CLIs are exercised by patching subscription_cli.subprocess.run /
shutil.which (the seams used by test_subscription_cli.py), and ollama's HTTP
call is mocked at the OpenAI-client factory (client._openai).

The assertions are deliberately conservative: the contract we care about for
keyless providers is "populated model / expected text on success, graceful
empty fallback on failure — never crash", not byte-exact output.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
import types

import pytest

# instructor is an optional heavy dep in minimal envs; stub it before importing
# llm.client (same pattern as test_llm_retry.py) so the import never fails.
if "instructor" not in sys.modules:
    try:  # pragma: no cover - prefer the real module when present
        import instructor  # noqa: F401
    except ModuleNotFoundError:  # pragma: no cover
        _stub = types.ModuleType("instructor")
        _stub.from_openai = lambda *a, **k: None  # type: ignore[attr-defined]
        _stub.Mode = types.SimpleNamespace(JSON="json", TOOLS="tools")  # type: ignore[attr-defined]
        sys.modules["instructor"] = _stub

from llm import client  # noqa: E402
from llm import subscription_cli as sc  # noqa: E402
from data.repository import create_repository  # noqa: E402
from pydantic import BaseModel  # noqa: E402

pytestmark = pytest.mark.integration

# Load subscription_cli a second time by path under its own name — the
# subscription_cli imported above (via the llm package) and the one the client
# lazily imports inside _subscription_call are the SAME module object, so
# patching sc.subprocess.run / sc.shutil.which is what the client actually
# executes. (test_subscription_cli.py loads it standalone; here we want the
# package instance the client uses.)
_MOD = pathlib.Path(__file__).resolve().parents[1] / "llm" / "subscription_cli.py"
assert importlib.util.spec_from_file_location("subscription_cli", _MOD) is not None


class Extracted(BaseModel):
    """A schema with a required field + a defaulted one, so a *populated* model
    is distinguishable from the empty _parse_fallback() instance."""

    title: str = ""
    count: int = 0


@pytest.fixture
def use_provider():
    """Point the client's settings at a chosen keyless provider, then restore
    the real repository afterwards (configure_repository is process-global)."""

    def _apply(provider: str, extra: dict | None = None):
        settings_map = {"llm_provider": provider}
        if extra:
            settings_map.update(extra)

        class _Settings:
            def get_setting(self, key, default=""):
                return settings_map.get(key, default)

        class _Repo:
            settings = _Settings()

        client.configure_repository(_Repo())
        return provider

    yield _apply
    client.configure_repository(create_repository())


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch):
    """Never actually sleep between retries (the raw-text retry path can wrap a
    transient error); keeps the suite fast and deterministic."""
    monkeypatch.setattr(client.time, "sleep", lambda _s: None)


@pytest.fixture(autouse=True)
def _cli_installed(monkeypatch):
    """Default: pretend both subscription CLIs are on PATH. Tests that need the
    'not installed' case override shutil.which themselves."""
    monkeypatch.setattr(sc.shutil, "which", lambda exe: f"/usr/bin/{exe}")


def _fake_claude_run(*, result: str, is_error: bool = False, code: int = 0, stderr: str = ""):
    """A subprocess.run replacement that mimics `claude -p --output-format json`."""
    stdout = json.dumps({"result": result, "is_error": is_error})

    def run(argv, **kw):
        return subprocess.CompletedProcess(argv, code, stdout, stderr)

    return run


# ───────────────────────── claude_cli ─────────────────────────


def test_claude_cli_call_raw_returns_cli_text(use_provider, monkeypatch):
    use_provider("claude_cli")
    monkeypatch.setattr(sc.subprocess, "run", _fake_claude_run(result="hello from claude"))
    assert client.call_raw("system", "user") == "hello from claude"


def test_claude_cli_call_llm_returns_populated_model(use_provider, monkeypatch):
    use_provider("claude_cli")
    payload = json.dumps({"title": "Backend Engineer", "count": 3})
    monkeypatch.setattr(sc.subprocess, "run", _fake_claude_run(result=payload))
    out = client.call_llm("system", "user", Extracted)
    assert isinstance(out, Extracted)
    assert out.title == "Backend Engineer" and out.count == 3


def test_claude_cli_call_llm_strips_fences(use_provider, monkeypatch):
    """The CLI often wraps JSON in ```json fences; complete_structured strips
    them, so call_llm still yields a populated model."""
    use_provider("claude_cli")
    fenced = "```json\n{\"title\":\"SRE\",\"count\":2}\n```"
    monkeypatch.setattr(sc.subprocess, "run", _fake_claude_run(result=fenced))
    out = client.call_llm("system", "user", Extracted)
    assert out.title == "SRE" and out.count == 2


def test_claude_cli_error_falls_back_gracefully(use_provider, monkeypatch):
    """is_error=true from the CLI must NOT crash: call_llm degrades to the empty
    fallback model and call_raw degrades to ''."""
    use_provider("claude_cli")
    monkeypatch.setattr(sc.subprocess, "run", _fake_claude_run(result="boom", is_error=True))

    out = client.call_llm("system", "user", Extracted)
    assert isinstance(out, Extracted)
    assert out.title == "" and out.count == 0  # empty/fallback, not populated

    assert client.call_raw("system", "user") == ""


def test_claude_cli_not_installed_falls_back_gracefully(use_provider, monkeypatch):
    """CLI missing from PATH (CliNotInstalled) is handled, not raised."""
    use_provider("claude_cli")
    monkeypatch.setattr(sc.shutil, "which", lambda exe: None)

    out = client.call_llm("system", "user", Extracted)
    assert isinstance(out, Extracted) and out.title == "" and out.count == 0
    assert client.call_raw("system", "user") == ""


def test_claude_cli_not_logged_in_falls_back_gracefully(use_provider, monkeypatch):
    """A login failure (CliNotLoggedIn) is a CliError subclass — handled."""
    use_provider("claude_cli")
    monkeypatch.setattr(
        sc.subprocess,
        "run",
        _fake_claude_run(result="", code=1, stderr="Invalid API key · Please run /login"),
    )
    assert client.call_raw("system", "user") == ""
    out = client.call_llm("system", "user", Extracted)
    assert isinstance(out, Extracted) and out.title == ""


# ───────────────────────── codex_cli ─────────────────────────


def test_codex_cli_call_raw_returns_output_file_text(use_provider, monkeypatch):
    """codex writes its final message to --output-last-message; call_raw returns
    that (not the noisy streamed stdout)."""
    use_provider("codex_cli")

    def fake_run(argv, **kw):
        out_path = argv[argv.index("--output-last-message") + 1]
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("final codex message\n")
        return subprocess.CompletedProcess(argv, 0, "noisy streamed stdout", "")

    monkeypatch.setattr(sc.subprocess, "run", fake_run)
    assert client.call_raw("system", "user") == "final codex message"


def test_codex_cli_retries_without_rejected_model(use_provider, monkeypatch):
    """A -m model rejected by a ChatGPT account must transparently retry WITHOUT
    -m (the account default), surfaced through the real call_raw path. The
    default codex model is gpt-5.5, so route a step whose model is a genuine
    override to force the -m path."""
    use_provider("codex_cli", extra={"codex_cli_model": "gpt-5.1"})
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        out_path = argv[argv.index("--output-last-message") + 1]
        if "-m" in argv:
            banner = "OpenAI Codex v0.137.0\n" + ("x" * 400) + "\n"
            err = banner + 'ERROR: {"message":"model is not supported when using Codex with a ChatGPT account."}'
            return subprocess.CompletedProcess(argv, 1, "", err)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("recovered")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(sc.subprocess, "run", fake_run)
    assert client.call_raw("system", "user") == "recovered"
    assert len(calls) == 2  # first with -m (rejected), retry without
    assert "-m" in calls[0] and "-m" not in calls[1]


def test_codex_cli_failure_falls_back_gracefully(use_provider, monkeypatch):
    """codex returning a hard error degrades gracefully through both surfaces."""
    use_provider("codex_cli")

    def fake_run(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, "", "fatal: something broke")

    monkeypatch.setattr(sc.subprocess, "run", fake_run)
    assert client.call_raw("system", "user") == ""
    out = client.call_llm("system", "user", Extracted)
    assert isinstance(out, Extracted) and out.title == "" and out.count == 0


def test_codex_cli_not_installed_falls_back_gracefully(use_provider, monkeypatch):
    use_provider("codex_cli")
    monkeypatch.setattr(sc.shutil, "which", lambda exe: None)
    assert client.call_raw("system", "user") == ""
    out = client.call_llm("system", "user", Extracted)
    assert isinstance(out, Extracted) and out.title == ""


# ───────────────────────── ollama ─────────────────────────


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeChatNS:
    def __init__(self, content):
        self.completions = types.SimpleNamespace(
            create=lambda **kw: _FakeCompletion(content)
        )


class _FakeOpenAIClient:
    """Minimal OpenAI-client stand-in for the ollama raw-text path."""

    def __init__(self, content):
        self.chat = _FakeChatNS(content)


def test_ollama_call_raw_returns_completion_text(use_provider, monkeypatch):
    """With a mocked HTTP/OpenAI client, ollama's call_raw returns the model
    text. We patch client._openai (the cached raw-client factory) so no socket
    is opened."""
    use_provider("ollama")
    monkeypatch.setattr(
        client, "_openai", lambda **kw: _FakeOpenAIClient("ollama says hi")
    )
    assert client.call_raw("system", "user") == "ollama says hi"


def test_ollama_unreachable_does_not_crash(use_provider, monkeypatch):
    """When ollama isn't running the OpenAI client raises a connection error.
    For raw text this surfaces (no keyless fallback on ollama), so the test only
    asserts the failure is the expected transient connection error — never a
    crash from our own code / unparsed garbage."""
    import httpx
    import openai

    use_provider("ollama")

    def boom(**kw):
        raise openai.APIConnectionError(request=httpx.Request("POST", "http://localhost:11434/v1"))

    monkeypatch.setattr(client, "_openai", boom)
    with pytest.raises(openai.APIConnectionError):
        client.call_raw("system", "user")


# ─────────────────────── per-step provider routing ───────────────────────


def test_per_step_provider_falls_back_to_global(use_provider, monkeypatch):
    """A step with no {step}_provider configured resolves to the global
    llm_provider — here claude_cli — exercised through the real call_raw path."""
    use_provider("claude_cli")  # global only; no scout_provider configured
    monkeypatch.setattr(sc.subprocess, "run", _fake_claude_run(result="scout via global claude"))
    assert client.call_raw("system", "user", step="scout") == "scout via global claude"


def test_per_step_provider_override_beats_global(use_provider, monkeypatch):
    """A configured {step}_provider overrides the global provider for that step:
    global is ollama, evaluator_provider is claude_cli, so step='evaluator' routes
    to claude_cli and ollama is never contacted."""
    use_provider("ollama", extra={"evaluator_provider": "claude_cli"})
    monkeypatch.setattr(sc.subprocess, "run", _fake_claude_run(result="evaluator via claude override"))
    # If routing wrongly fell through to the global ollama provider, the raw-text
    # path would build an OpenAI client; make that an immediate, loud failure.
    monkeypatch.setattr(
        client,
        "_openai",
        lambda **kw: (_ for _ in ()).throw(AssertionError("ollama contacted; per-step override failed")),
    )
    assert client.call_raw("system", "user", step="evaluator") == "evaluator via claude override"
