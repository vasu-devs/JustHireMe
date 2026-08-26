"""Round-11 audit fixes: the MCP quality tool must honour an explicit min_quality=0,
and the gemini CLI must not leak its raw JSON envelope as the completion."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest import mock

import pytest


def _accepted(result: dict) -> bool:
    return json.loads(result["content"][0]["text"])["accepted"]


def test_mcp_evaluate_lead_honours_explicit_zero_min_quality():
    from mcp_server import _evaluate_lead

    lead = {
        "url": "https://example.com/jobs/1",
        "company": "Acme AI",
        "title": "Engineer",
        "description": "Build reliable Python services and data pipelines. " * 5,
        "signal_score": 30,
        "_fresh_source": "google_past_week",
    }
    # score 30 < default 60: rejected at the default, accepted at an explicit 0.
    assert _accepted(_evaluate_lead({"lead": lead, "min_quality": 0})) is True
    assert _accepted(_evaluate_lead({"lead": lead, "min_quality": 60})) is False
    # omitted -> default 60
    assert _accepted(_evaluate_lead({"lead": lead})) is False


def test_gemini_exec_raises_on_empty_parsed_response():
    from llm import subscription_cli as sc

    fake = SimpleNamespace(stdout='{"response": ""}', stderr="", returncode=0)
    with mock.patch.object(sc.subprocess, "run", return_value=fake), pytest.raises(sc.CliError):
        sc._gemini_exec("gemini", "sys", "user", model="gemini-2.5", timeout=30)


def test_gemini_exec_returns_parsed_response_text():
    from llm import subscription_cli as sc

    fake = SimpleNamespace(stdout='{"response": "hello world"}', stderr="", returncode=0)
    with mock.patch.object(sc.subprocess, "run", return_value=fake):
        assert sc._gemini_exec("gemini", "sys", "user", model="gemini-2.5", timeout=30) == "hello world"
