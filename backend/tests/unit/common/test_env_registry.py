"""The Common layer owns configuration: core/env.py is the only env reader.

Two guarantees:
  1. No module outside core/env.py calls os.environ / os.getenv, so the
     configuration surface is discoverable and defaults cannot drift.
  2. Every JHM_* variable the code understands is documented in .env.example.
"""

from __future__ import annotations

import ast

from paths import BACKEND_ROOT, REPO_ROOT

from core import env

#: The registry itself, plus test helpers that legitimately manipulate the
#: process environment to exercise the code under test.
ENV_ACCESS_ALLOWED = {"core/env.py"}

SEARCHED_PACKAGES = (
    "api", "automation", "core", "data", "discovery", "gateway", "generation",
    "graph_service", "help", "leads", "learning", "llm", "models", "profile",
    "ranking", "settings", "system", "templates",
)


def _reads_environment(path) -> list[int]:
    """Line numbers where this module touches os.environ / os.getenv."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[int] = []
    for node in ast.walk(tree):
        # os.getenv(...) / os.environ.get(...)
        if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
            value = node.value
            if isinstance(value, ast.Name) and value.id == "os":
                hits.append(node.lineno)
        # from os import environ  /  from os import getenv
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            if any(alias.name in {"environ", "getenv"} for alias in node.names):
                hits.append(node.lineno)
    return hits


def test_environment_is_read_only_through_core_env():
    violations: list[str] = []
    for package in SEARCHED_PACKAGES:
        for path in sorted((BACKEND_ROOT / package).rglob("*.py")):
            rel = path.relative_to(BACKEND_ROOT).as_posix()
            if rel in ENV_ACCESS_ALLOWED:
                continue
            for lineno in _reads_environment(path):
                violations.append(f"{rel}:{lineno}")

    assert not violations, (
        "read configuration through core.env (add an accessor there) instead of "
        "os.environ/os.getenv:\n" + "\n".join(violations)
    )


def test_env_example_documents_every_jhm_variable():
    documented = {
        line.split("=", 1)[0].strip()
        for line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.strip().startswith("#")
    }
    undocumented = sorted(set(env.JHM_VARIABLES) - documented)
    assert not undocumented, f"add these to .env.example: {undocumented}"


def test_registry_exposes_every_jhm_variable_it_declares():
    assert env.JHM_VARIABLES, "the registry should not be empty"
    assert all(name.startswith("JHM_") for name in env.JHM_VARIABLES)


# ------------------------------------------------------------------ accessors


def test_flag_uses_the_shared_truthy_vocabulary(monkeypatch):
    for raw in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv(env.AUTO_APPLY, raw)
        assert env.flag(env.AUTO_APPLY) is True
    for raw in ("0", "false", "no", "off"):
        monkeypatch.setenv(env.AUTO_APPLY, raw)
        assert env.flag(env.AUTO_APPLY) is False


def test_flag_falls_back_to_the_default_when_unset(monkeypatch):
    monkeypatch.delenv(env.AUTO_APPLY, raising=False)
    assert env.flag(env.AUTO_APPLY) is False
    assert env.flag(env.AUTO_APPLY, default=True) is True


def test_text_trims_and_defaults(monkeypatch):
    monkeypatch.setenv(env.LOG_LEVEL, "  DEBUG  ")
    assert env.log_level() == "DEBUG"
    monkeypatch.setenv(env.LOG_LEVEL, "")
    assert env.log_level() == "INFO"
    monkeypatch.delenv(env.LOG_LEVEL, raising=False)
    assert env.log_level() == "INFO"


def test_first_prefers_the_earlier_name(monkeypatch):
    monkeypatch.setenv(env.X_BEARER_TOKEN, "x-token")
    monkeypatch.setenv(env.TWITTER_BEARER_TOKEN, "legacy-token")
    assert env.x_bearer_token() == "x-token"

    monkeypatch.delenv(env.X_BEARER_TOKEN, raising=False)
    assert env.x_bearer_token() == "legacy-token"

    monkeypatch.delenv(env.TWITTER_BEARER_TOKEN, raising=False)
    assert env.x_bearer_token() == ""


def test_portfolio_llm_is_opt_out_not_opt_in(monkeypatch):
    monkeypatch.delenv(env.PORTFOLIO_LLM, raising=False)
    assert env.portfolio_llm_disabled() is False  # unset => enabled
    monkeypatch.setenv(env.PORTFOLIO_LLM, "false")
    assert env.portfolio_llm_disabled() is True
    monkeypatch.setenv(env.PORTFOLIO_LLM, "1")
    assert env.portfolio_llm_disabled() is False


def test_any_set_and_is_set(monkeypatch):
    monkeypatch.delenv(env.GOOGLE_API_KEY, raising=False)
    monkeypatch.delenv(env.GEMINI_API_KEY, raising=False)
    assert env.any_set(env.GOOGLE_API_KEY, env.GEMINI_API_KEY) is False
    monkeypatch.setenv(env.GEMINI_API_KEY, "k")
    assert env.any_set(env.GOOGLE_API_KEY, env.GEMINI_API_KEY) is True
    assert env.is_set(env.GEMINI_API_KEY) is True


def test_get_returns_the_default_for_a_blank_value(monkeypatch):
    monkeypatch.setenv(env.FIT_ENGINE, "")
    assert env.get(env.FIT_ENGINE, "fallback") == "fallback"
    monkeypatch.setenv(env.FIT_ENGINE, "cgfe")
    assert env.get(env.FIT_ENGINE, "fallback") == "cgfe"


def test_reads_are_live_not_captured_at_import(monkeypatch):
    """The shell sets the app-data dir after import; captured values would be stale."""
    monkeypatch.setenv(env.FIT_ENGINE, "cgfe")
    assert env.fit_engine() == "cgfe"
    monkeypatch.setenv(env.FIT_ENGINE, "legacy")
    assert env.fit_engine() == "legacy"
