"""scripts/ingest_resume.py -- resume ingest is the closed loop's entry point.

Pure-logic tests only (no LLM/network): the profile-merge behaviour (preserve
hand-curated fields a resume never states, prefer the new resume's own data
when it has it) and the parse_resume LLM+deterministic-merge glue with the LLM
call monkeypatched out.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import ingest_resume  # noqa: E402
from models.schema import C, S  # noqa: E402


def _parsed(**kw) -> C:
    base = {"n": "New Name", "s": "New summary", "loc": "", "skills": [], "exp": [], "projects": [],
            "certifications": [], "education": [], "achievements": []}
    base.update(kw)
    return C(**base)


def test_profile_dict_prefers_new_resume_data_and_preserves_curated_fields():
    existing = {
        "n": "Old Name", "s": "old", "identity": {"city": "Gurgaon", "portfolio_url": "https://x.com"},
        "desired_position": "Applied AI Engineer", "_discovery_location": "Gurgaon, India", "_remote_preference": "any",
    }
    parsed = _parsed(skills=[S(n="Python", cat="language")])
    out = ingest_resume.profile_dict_from_model(parsed, existing)

    assert out["n"] == "New Name"  # the resume's own data wins for fields it states
    assert out["identity"] == {"city": "Gurgaon", "portfolio_url": "https://x.com"}  # untouched
    assert out["desired_position"] == "Applied AI Engineer"
    assert out["_discovery_location"] == "Gurgaon, India"
    assert out["_remote_preference"] == "any"
    assert out["skills"] == [{"n": "Python", "cat": "language"}]


def test_profile_dict_falls_back_to_existing_when_the_new_resume_says_nothing():
    existing = {"n": "Old Name", "s": "old summary", "skills": [{"n": "C#", "cat": "language"}]}
    parsed = _parsed(n="", s="", skills=[])
    out = ingest_resume.profile_dict_from_model(parsed, existing)
    assert out["n"] == "Old Name"
    assert out["s"] == "old summary"
    assert out["skills"] == [{"n": "C#", "cat": "language"}]


def test_profile_dict_autofills_identity_city_from_resume_location_when_unset():
    parsed = _parsed(loc="Gurgaon, India")
    out = ingest_resume.profile_dict_from_model(parsed, {})
    assert out["identity"]["city"] == "Gurgaon, India"


def test_profile_dict_never_overrides_a_manually_set_city():
    existing = {"identity": {"city": "Bengaluru"}}
    parsed = _parsed(loc="Gurgaon, India")
    out = ingest_resume.profile_dict_from_model(parsed, existing)
    assert out["identity"]["city"] == "Bengaluru"


def test_parse_resume_merges_llm_and_deterministic_extraction(monkeypatch):
    """The LLM path is monkeypatched out (no network/codex call in a unit
    test) -- this exercises the merge glue between it and the deterministic
    fallback parser only."""
    llm_result = C(n="Alex Candidate", s="", skills=[S(n="Python", cat="language")], exp=[], projects=[],
                    certifications=[], education=[], achievements=[])
    monkeypatch.setattr("profile.ingestor.run", lambda txt: llm_result)

    txt = "Alex Candidate\nSkills: Python, AWS, Docker\n"
    parsed = ingest_resume.parse_resume(txt)

    assert parsed.n == "Alex Candidate"  # LLM's own field wins
    names = {skill.n for skill in parsed.skills}
    assert "Python" in names  # present in both sources
    assert "AWS" in names  # the deterministic fallback fills in what the LLM (mock) missed
