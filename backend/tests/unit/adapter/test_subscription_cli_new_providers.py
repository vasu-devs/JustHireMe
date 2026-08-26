"""Tests for the Gemini CLI and GitHub Copilot CLI subscription providers.

These CLIs aren't installed in CI, so every boundary is mocked (subprocess.run +
shutil.which). The contract pinned here is what we CAN verify without the real
binaries: the exact non-interactive command each provider runs, how its output is
parsed (Gemini's JSON `response`, Copilot's plain stdout), the dispatch from
complete_text, and graceful error classification. Live behaviour still needs the
user's signed-in CLI.
"""

from __future__ import annotations

import subprocess

import pytest

from llm import subscription_cli as sc


@pytest.fixture
def fake_run(monkeypatch):
    """Patch subprocess.run, capturing the call and returning a scripted result."""
    calls = {}

    def _make(returncode=0, stdout="", stderr=""):
        def _run(argv, *args, **kwargs):
            calls["argv"] = argv
            calls["input"] = kwargs.get("input")
            return subprocess.CompletedProcess(argv, returncode, stdout, stderr)
        monkeypatch.setattr(sc.subprocess, "run", _run)
        return calls

    return _make


def test_exe_map_and_install_hints():
    assert sc._exe("gemini_cli") == "gemini"
    assert sc._exe("copilot_cli") == "copilot"
    assert sc.install_hint("gemini_cli")["name"] == "Gemini CLI"
    assert "@google/gemini-cli" in sc.install_hint("gemini_cli")["cmd"]
    assert sc.install_hint("copilot_cli")["name"] == "GitHub Copilot CLI"
    assert "@github/copilot" in sc.install_hint("copilot_cli")["cmd"]


def test_gemini_exec_runs_headless_json_and_parses_response(fake_run):
    calls = fake_run(stdout='{"response": "extracted text", "stats": {"tokens": 12}}')
    out = sc._gemini_exec("/x/gemini", "SYS", "USER", model="gemini-2.5-pro", timeout=30)
    assert out == "extracted text"
    assert calls["argv"] == ["/x/gemini", "--output-format", "json", "-m", "gemini-2.5-pro"]
    assert calls["input"] == "SYS\n\nUSER"  # prompt on stdin, not argv


def test_gemini_omits_model_flag_when_default(fake_run):
    calls = fake_run(stdout='{"response": "ok"}')
    sc._gemini_exec("/x/gemini", "", "hi", model="", timeout=30)
    assert "-m" not in calls["argv"]  # "" => use the plan's default model


def test_gemini_plain_text_fallback(fake_run):
    fake_run(stdout="just text, not json")
    assert sc._gemini_exec("/x/gemini", "", "hi", model=None, timeout=30) == "just text, not json"


def test_gemini_error_field_is_classified_as_login(fake_run):
    fake_run(stdout='{"error": {"message": "Please sign in to your Google account"}}')
    with pytest.raises(sc.CliNotLoggedIn):
        sc._gemini_exec("/x/gemini", "", "hi", model=None, timeout=30)


def test_copilot_exec_runs_programmatic_mode(fake_run):
    calls = fake_run(stdout="copilot answer")
    out = sc._copilot_exec("/x/copilot", "SYS", "USER", model="claude-sonnet-4.5", timeout=30)
    assert out == "copilot answer"
    assert calls["argv"] == ["/x/copilot", "-p", "SYS\n\nUSER", "-s", "--no-ask-user", "--model", "claude-sonnet-4.5"]


def test_copilot_nonzero_exit_raises(fake_run):
    fake_run(returncode=1, stderr="not logged in to GitHub")
    with pytest.raises(sc.CliNotLoggedIn):
        sc._copilot_exec("/x/copilot", "", "hi", model=None, timeout=30)


def test_complete_text_dispatches_to_the_right_cli(fake_run, monkeypatch):
    monkeypatch.setattr(sc.shutil, "which", lambda exe: f"/x/{exe}")
    # gemini -> JSON response
    calls = fake_run(stdout='{"response": "G"}')
    assert sc.complete_text("gemini_cli", "s", "u") == "G"
    assert calls["argv"][0] == "/x/gemini" and "--output-format" in calls["argv"]
    # copilot -> plain stdout
    calls = fake_run(stdout="C")
    assert sc.complete_text("copilot_cli", "s", "u") == "C"
    assert calls["argv"][0] == "/x/copilot" and "-p" in calls["argv"]


def test_status_reports_not_installed_when_missing(monkeypatch):
    monkeypatch.setattr(sc.shutil, "which", lambda exe: None)
    for provider in ("gemini_cli", "copilot_cli"):
        s = sc.status(provider)
        assert s["installed"] is False and s["logged_in"] is False


# ── trailing-junk JSON salvage (the codex evaluator failure in the wild) ────────

def test_first_json_value_trims_trailing_framing():
    # codex emitted a valid object then a stray "]}" — schema validation choked.
    assert sc._first_json_value('{"score":18,"reason":"ok"}]}') == '{"score":18,"reason":"ok"}'


def test_first_json_value_is_string_and_brace_aware():
    tricky = '{"score":7,"reason":"has {curly} and \\"quotes\\" and [brackets]"}junk'
    assert sc._first_json_value(tricky) == '{"score":7,"reason":"has {curly} and \\"quotes\\" and [brackets]"}'


def test_codex_run_once_pins_low_reasoning_effort(monkeypatch):
    # xhigh reasoning makes codex too slow for the latency-bound scout step; we
    # override it for our automated calls so large feeds finish in time.
    captured = {}

    def fake_run(argv, *a, **k):
        captured["argv"] = argv
        out = argv[argv.index("--output-last-message") + 1]
        with open(out, "w", encoding="utf-8") as handle:
            handle.write("done")
        return subprocess.CompletedProcess(argv, 0, "done", "")

    monkeypatch.setattr(sc.subprocess, "run", fake_run)
    sc._codex_run_once("/x/codex", "extract jobs", model=None, timeout=30)
    argv = captured["argv"]
    flag = argv[argv.index("-c") + 1]
    assert "model_reasoning_effort" in flag and "low" in flag


def test_codex_error_detail_drops_echoed_prompt():
    # codex echoed a huge prompt (e.g. scraped RSS) then produced no turn — the
    # diagnostic must not dump that prompt into the log.
    stderr = "OpenAI Codex\n--------\nmodel: x\n--------\nuser\n<rss>...big job feed...</rss>"
    assert sc._codex_error_detail(stderr, "") == "no response from codex"
    # when codex DID respond, surface its turn (the real error), not the prompt.
    stderr2 = "banner\n--------\nx\n--------\nuser\n<prompt>\ncodex\nERROR: context length exceeded"
    assert sc._codex_error_detail(stderr2, "") == "ERROR: context length exceeded"


def test_complete_structured_salvages_trailing_junk(monkeypatch):
    from pydantic import BaseModel

    class _Score(BaseModel):
        score: int = 0
        reason: str = ""

    # The CLI returns a valid object with codex's trailing "]}" appended.
    monkeypatch.setattr(sc, "complete_text", lambda *a, **k: '{"score":18,"reason":"good fit"}]}')
    out = sc.complete_structured("codex_cli", "sys", "user", _Score)
    assert out.score == 18 and out.reason == "good fit"


# ── antigravity_cli (#147): Google's gemini-cli successor, same headless contract ──

def test_antigravity_exe_map_and_install_hint():
    assert sc._exe("antigravity_cli") == "antigravity"
    hint = sc.install_hint("antigravity_cli")
    assert hint["name"] == "Antigravity CLI"
    assert "antigravity" in hint["cmd"]


def test_antigravity_dispatches_through_gemini_contract(fake_run, monkeypatch):
    calls = fake_run(stdout='{"response": "hello from antigravity"}')
    monkeypatch.setattr(sc.shutil, "which", lambda exe: f"/x/{exe}")
    out = sc.complete_text("antigravity_cli", "SYS", "USER", model="gemini-3.5-pro", timeout=30)
    assert out == "hello from antigravity"
    assert calls["argv"][0] == "/x/antigravity"
    assert calls["argv"][1:] == ["--output-format", "json", "-m", "gemini-3.5-pro"]
    assert calls["input"] == "SYS\n\nUSER"


def test_antigravity_timeout_message_names_provider(fake_run, monkeypatch):
    def _run(argv, *args, **kwargs):
        raise sc.subprocess.TimeoutExpired(argv, 30)
    monkeypatch.setattr(sc.subprocess, "run", _run)
    with pytest.raises(sc.CliTimeout, match="antigravity_cli"):
        sc._gemini_exec("/x/antigravity", "", "hi", model=None, timeout=30, provider="antigravity_cli")


def test_antigravity_logged_in_accepts_antigravity_or_gemini_creds(monkeypatch, tmp_path):
    monkeypatch.setattr(sc.os.path, "expanduser", lambda _: str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert sc._antigravity_logged_in() is False
    (tmp_path / ".antigravity").mkdir()
    assert sc._antigravity_logged_in() is True
