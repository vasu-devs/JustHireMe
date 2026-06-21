"""The user's free-text 'what I'm looking for' preferences must flow into both the
scan (query planner) and the ranking (evaluator), so roles they want surface and
rank higher.

These tests pin the plumbing without any network: config injection, the evaluator
prompt + threading, and the query planner's prompt.
"""

from __future__ import annotations

from types import SimpleNamespace

from core.config import profile_for_discovery
from ranking import evaluator as ev


# ── config: preferences land on the discovery profile ───────────────────────────

def test_profile_for_discovery_injects_job_preferences():
    out = profile_for_discovery({"n": "A", "s": "Backend engineer"}, {"job_preferences": "remote fintech, no on-call"})
    assert out["_job_preferences"] == "remote fintech, no on-call"


def test_profile_for_discovery_empty_when_unset():
    out = profile_for_discovery({"n": "A"}, {})
    assert out["_job_preferences"] == ""


# ── evaluator: preferences appear in the prompt + thread from settings ───────────

def test_user_prompt_includes_preferences_when_present():
    p = ev._user_prompt("Senior Python role", {"n": "A", "s": "eng"}, {"score": 50}, "remote fintech, no on-call")
    assert "What the candidate is looking for" in p
    assert "no on-call" in p


def test_user_prompt_omits_section_when_empty():
    p = ev._user_prompt("role", {"n": "A"}, {"score": 1}, "")
    assert "What the candidate is looking for" not in p


def test_score_threads_preferences_from_settings(monkeypatch):
    captured = {}

    def fake_score_with_llm(jd, candidate_data, baseline, preferences=""):
        captured["preferences"] = preferences
        return {**baseline, "score": 70}

    monkeypatch.setattr(ev, "_evaluator_llm_requested", lambda settings=None: True)
    monkeypatch.setattr(ev, "_score_with_llm", fake_score_with_llm)
    ev.score("Some job", {"n": "A", "s": "eng"}, {"job_preferences": "remote senior backend, fintech"})
    assert captured["preferences"] == "remote senior backend, fintech"


# ── query planner: preferences steer the generated queries ──────────────────────

def test_query_gen_passes_preferences_to_the_planner(monkeypatch):
    from discovery import query_gen

    seen = {}
    plan = SimpleNamespace(queries=["site:jobs.example.com fintech"])

    def fake_call_llm(system, user, schema, step=None):
        seen["system"] = system
        seen["user"] = user
        return plan

    monkeypatch.setattr("llm.call_llm", fake_call_llm)
    profile = {"s": "Backend engineer", "skills": [{"n": "Python"}], "_job_preferences": "fintech, remote, mission-driven"}
    query_gen.generate(profile, ["site:jobs.example.com"], "global")
    blob = seen["system"] + seen["user"]
    assert "fintech, remote, mission-driven" in blob
    assert "candidate_preferences" in seen["system"]
