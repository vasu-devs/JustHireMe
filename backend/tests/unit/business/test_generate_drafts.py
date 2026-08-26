"""scripts/generate_drafts.py -- pure logic only (slugging + the no-LLM
deterministic template). The task requires drafts to reference the actual
matching project, never generic filler, EVEN when no LLM is available -- this
is what guarantees that.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import generate_drafts  # noqa: E402

_PROFILE = {
    "n": "Alex Candidate",
    "s": "Applied AI Engineer with 11+ years of enterprise backend experience.",
    "identity": {"portfolio_url": "https://candidate.example.test"},
}
_PROJECT = {
    "title": "AegisQuery",
    "impact": "AST-based static-analysis engine that detects and blocks SQL-injection-shaped queries.",
}


def test_deterministic_draft_names_the_matched_project_and_its_impact_not_filler():
    lead = {"title": "Security Engineer", "company": "Acme Corp"}
    draft = generate_drafts._deterministic_draft(_PROFILE, lead, [_PROJECT])

    assert draft["mode"] == "deterministic"
    assert "AegisQuery" in draft["cover_letter"]
    assert "SQL-injection" in draft["cover_letter"]
    assert "Acme Corp" in draft["cover_letter"]
    assert "AegisQuery" in draft["resume_summary"]


def test_deterministic_draft_degrades_gracefully_with_no_matched_project():
    lead = {"title": "Warehouse Ops", "company": "Acme Corp"}
    draft = generate_drafts._deterministic_draft(_PROFILE, lead, [])
    assert draft["mode"] == "deterministic"
    assert draft["cover_letter"]  # still non-empty, just no project-specific sentence
    assert "no closely-matching project" in draft["evidence_block"]


def test_slug_is_filesystem_safe_and_stable_per_job():
    lead = {"company": "Acme Corp!", "title": "Security / Infra Engineer", "job_id": "abcdef1234567890"}
    slug = generate_drafts._slug(lead)
    assert all(c.isalnum() or c == "-" for c in slug)
    assert slug == generate_drafts._slug(lead)  # deterministic
    assert slug.endswith("abcdef12")  # first 8 chars of job_id, for uniqueness


def test_llm_draft_returns_none_on_malformed_output(monkeypatch):
    monkeypatch.setattr(generate_drafts, "call_raw", lambda *a, **k: "not the expected format at all")
    assert generate_drafts._llm_draft(_PROFILE, {"title": "x", "company": "y"}, [_PROJECT]) is None


def test_llm_draft_parses_the_documented_format(monkeypatch):
    raw = "RESUME SUMMARY:\nA tailored two sentence summary here.\n---COVER LETTER---\n" + ("Dear team, " * 20)
    monkeypatch.setattr(generate_drafts, "call_raw", lambda *a, **k: raw)
    result = generate_drafts._llm_draft(_PROFILE, {"title": "x", "company": "y"}, [_PROJECT])
    assert result is not None
    assert result["mode"] == "llm"
    assert "tailored two sentence summary" in result["resume_summary"]
    assert result["cover_letter"].startswith("Dear team,")
