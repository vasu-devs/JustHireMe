"""Tests for the subscription-CLI LLM provider (claude_cli / codex_cli).

These mock subprocess entirely — no real CLI is invoked — so they're fast,
deterministic, and safe to run anywhere. The real end-to-end call is exercised
separately against the live `claude` CLI.
"""
import importlib.util
import json
import pathlib
import subprocess

import pytest

# Load the module directly by path so the test doesn't drag in llm/__init__.py
# (which imports heavy provider deps). subscription_cli is pure-stdlib + lazy pydantic.
_MOD = pathlib.Path(__file__).resolve().parents[1] / "llm" / "subscription_cli.py"
_spec = importlib.util.spec_from_file_location("subscription_cli", _MOD)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


def _fake_run(*, stdout="", stderr="", code=0, capture=None):
    def run(argv, **kw):
        if capture is not None:
            capture["argv"] = argv
            capture["kw"] = kw
        return subprocess.CompletedProcess(argv, code, stdout, stderr)
    return run


@pytest.fixture(autouse=True)
def _exe_present(monkeypatch):
    # default: pretend both CLIs are installed (tests that need "missing" override this)
    monkeypatch.setattr(sc.shutil, "which", lambda exe: exe)


def test_claude_argv_user_on_stdin_system_replaced(monkeypatch):
    cap = {}
    monkeypatch.setattr(sc.subprocess, "run",
                        _fake_run(stdout=json.dumps({"result": "ok", "is_error": False}), capture=cap))
    out = sc.complete_text("claude_cli", "SYSTEM", "USER", model="claude-sonnet-4-6")
    assert out == "ok"
    argv = cap["argv"]
    assert argv[0] == "claude" and "-p" in argv
    assert "--system-prompt" in argv and "SYSTEM" in argv
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--model") + 1] == "claude-sonnet-4-6"
    assert cap["kw"].get("input") == "USER"          # user content via stdin, not argv


def test_env_scrubs_billing_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-would-bill")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-would-bill-2")
    cap = {}
    monkeypatch.setattr(sc.subprocess, "run",
                        _fake_run(stdout=json.dumps({"result": "x", "is_error": False}), capture=cap))
    sc.complete_text("claude_cli", "s", "u")
    env = cap["kw"]["env"]
    assert "ANTHROPIC_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env


def test_claude_is_error_raises(monkeypatch):
    monkeypatch.setattr(sc.subprocess, "run",
                        _fake_run(stdout=json.dumps({"result": "boom", "is_error": True})))
    with pytest.raises(sc.CliError):
        sc.complete_text("claude_cli", "s", "u")


def test_not_logged_in_classified(monkeypatch):
    monkeypatch.setattr(sc.subprocess, "run",
                        _fake_run(stderr="Invalid API key · Please run /login", code=1))
    with pytest.raises(sc.CliNotLoggedIn):
        sc.complete_text("claude_cli", "s", "u")


def test_credit_exhausted_classified(monkeypatch):
    monkeypatch.setattr(sc.subprocess, "run",
                        _fake_run(stderr="You have exceeded your usage limit / credit", code=1))
    with pytest.raises(sc.CliCreditExhausted):
        sc.complete_text("claude_cli", "s", "u")


def test_not_installed_classified(monkeypatch):
    monkeypatch.setattr(sc.shutil, "which", lambda exe: None)
    with pytest.raises(sc.CliNotInstalled):
        sc.complete_text("claude_cli", "s", "u")


def test_codex_argv_exec_and_stdout(monkeypatch):
    cap = {}
    monkeypatch.setattr(sc.subprocess, "run",
                        _fake_run(stdout="hello from codex\n", capture=cap))
    out = sc.complete_text("codex_cli", "SYSTEM", "USER")
    assert out == "hello from codex"
    assert cap["argv"][0] == "codex" and cap["argv"][1] == "exec"


def test_structured_parses_and_strips_fences(monkeypatch):
    BaseModel = pytest.importorskip("pydantic").BaseModel

    class Person(BaseModel):
        name: str
        years: int

    fenced = "```json\n{\"name\":\"Anna\",\"years\":8}\n```"
    monkeypatch.setattr(sc.subprocess, "run",
                        _fake_run(stdout=json.dumps({"result": fenced, "is_error": False})))
    p = sc.complete_structured("claude_cli", "extract", "Anna 8", Person)
    assert p.name == "Anna" and p.years == 8


def test_status_reports_install_and_login(monkeypatch):
    monkeypatch.setattr(sc.shutil, "which", lambda exe: None)
    st = sc.status("codex_cli")
    assert st["installed"] is False and st["logged_in"] is False


def test_status_parses_claude_auth_json(monkeypatch):
    payload = json.dumps({"loggedIn": True, "email": "a@b.com", "subscriptionType": "max", "authMethod": "claude.ai"})
    monkeypatch.setattr(sc.subprocess, "run", _fake_run(stdout=payload))
    st = sc.status("claude_cli")
    assert st["installed"] is True and st["logged_in"] is True
    assert st["email"] == "a@b.com" and st["plan"] == "max"


def test_login_claude_argv_and_scrub(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-would-bill")
    cap = {}

    class FakePopen:
        def __init__(self, argv, **kw):
            cap["argv"] = argv
            cap["kw"] = kw
            self.pid = 4242
    monkeypatch.setattr(sc.subprocess, "Popen", FakePopen)
    out = sc.login("claude_cli")
    assert out["started"] is True and out["pid"] == 4242
    assert cap["argv"] == ["claude", "auth", "login"]
    assert "ANTHROPIC_API_KEY" not in cap["kw"]["env"]


def test_login_codex_argv(monkeypatch):
    cap = {}

    class FakePopen:
        def __init__(self, argv, **kw):
            cap["argv"] = argv
            self.pid = 1
    monkeypatch.setattr(sc.subprocess, "Popen", FakePopen)
    sc.login("codex_cli")
    assert cap["argv"] == ["codex", "login"]


def test_login_not_installed(monkeypatch):
    monkeypatch.setattr(sc.shutil, "which", lambda exe: None)
    with pytest.raises(sc.CliNotInstalled):
        sc.login("claude_cli")


def test_install_hint_has_cmd_and_url():
    for p in ("claude_cli", "codex_cli"):
        h = sc.install_hint(p)
        assert h["cmd"] and h["url"].startswith("http")


def test_complete_structured_parses_valid_json(monkeypatch):
    from pydantic import BaseModel

    class M(BaseModel):
        name: str
        age: int

    monkeypatch.setattr(sc.subprocess, "run",
                        _fake_run(stdout=json.dumps({"result": '{"name":"Al","age":3}', "is_error": False})))
    out = sc.complete_structured("claude_cli", "S", "U", M, model="claude-sonnet-4-6")
    assert out.name == "Al" and out.age == 3


def test_complete_text_timeout_raises_clitimeout(monkeypatch):
    def boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)
    monkeypatch.setattr(sc.subprocess, "run", boom)
    with pytest.raises(sc.CliTimeout):
        sc.complete_text("claude_cli", "S", "U")
    # CliTimeout must remain a CliError so existing handlers still catch it.
    assert issubclass(sc.CliTimeout, sc.CliError)


def test_complete_structured_raises_clierror_on_bad_output(monkeypatch):
    # A flaky CLI returns prose instead of schema JSON -> must raise CliError
    # (not a raw pydantic.ValidationError the caller wouldn't catch).
    from pydantic import BaseModel

    class M(BaseModel):
        name: str
        age: int

    monkeypatch.setattr(sc.subprocess, "run",
                        _fake_run(stdout=json.dumps({"result": "sorry, I can't do that", "is_error": False})))
    with pytest.raises(sc.CliError):
        sc.complete_structured("claude_cli", "S", "U", M, model="claude-sonnet-4-6")
