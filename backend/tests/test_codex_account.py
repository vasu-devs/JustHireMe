"""Codex subscription status surfaces the signed-in account, like Claude does.

The account email + ChatGPT plan live in the id_token claims of ~/.codex/auth.json.
These tests craft a synthetic auth.json (no real token) and assert the local JWT
decode extracts email/plan and that status('codex_cli') reports them.
"""

from __future__ import annotations

import base64
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from llm import subscription_cli as sc


def _b64(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def _fake_jwt(payload: dict) -> str:
    return f"{_b64({'alg': 'none'})}.{_b64(payload)}.sig"


@pytest.fixture
def fake_home(monkeypatch):
    """Point ~ at a throwaway dir (tmp_path is flaky on this machine) and write a
    synthetic codex auth.json into it."""
    home = Path(tempfile.mkdtemp())
    monkeypatch.setattr(sc.os.path, "expanduser", lambda p: str(home) if p == "~" else p)

    def _write(auth: dict | None):
        codex = home / ".codex"
        codex.mkdir(parents=True, exist_ok=True)
        if auth is not None:
            (codex / "auth.json").write_text(json.dumps(auth), encoding="utf-8")

    try:
        yield _write
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_jwt_claims_decodes_payload_only():
    tok = _fake_jwt({"email": "a@b.com", "n": 1})
    assert sc._jwt_claims(tok) == {"email": "a@b.com", "n": 1}
    assert sc._jwt_claims("not-a-jwt") == {}
    assert sc._jwt_claims("") == {}


def test_codex_auth_status_extracts_email_and_plan(fake_home):
    idtok = _fake_jwt({"email": "yo@example.com", "https://api.openai.com/auth": {"chatgpt_plan_type": "pro"}})
    fake_home({"auth_mode": "chatgpt", "tokens": {"id_token": idtok}})
    out = sc._codex_auth_status()
    assert out is not None
    assert out["logged_in"] is True
    assert out["email"] == "yo@example.com"
    assert out["plan"] == "ChatGPT Pro"
    assert out["method"] == "chatgpt"


def test_codex_auth_status_none_when_no_file(fake_home):
    fake_home(None)  # ~/.codex exists but no auth.json
    assert sc._codex_auth_status() is None


def test_codex_auth_status_handles_missing_plan(fake_home):
    # API-key auth mode (no ChatGPT plan claims) — still logged in, no plan.
    fake_home({"auth_mode": "apikey", "tokens": {"id_token": _fake_jwt({"email": "k@k.com"})}})
    out = sc._codex_auth_status()
    assert out["logged_in"] is True and out["email"] == "k@k.com" and out["plan"] is None


def test_status_codex_cli_surfaces_account(fake_home, monkeypatch):
    monkeypatch.setattr(sc.shutil, "which", lambda exe: "/x/codex")
    idtok = _fake_jwt({"email": "x@y.com", "https://api.openai.com/auth": {"chatgpt_plan_type": "plus"}})
    fake_home({"auth_mode": "chatgpt", "tokens": {"id_token": idtok}})
    st = sc.status("codex_cli")
    assert st["installed"] is True
    assert st["logged_in"] is True
    assert st["email"] == "x@y.com"
    assert st["plan"] == "ChatGPT Plus"
