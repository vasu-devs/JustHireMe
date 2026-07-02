"""Accepted-LLM outreach must be truncated to the documented caps.

The LinkedIn connection note hard-caps at 300 chars; before the fix only the
deterministic fallback sliced, so an over-limit LLM note was copied verbatim.
"""

from __future__ import annotations

from generation.generators.base import _DocPackage
from generation.generators.cover_letter import _normalize_package, _shorten_chars, _shorten_words


def test_shorten_chars_word_boundary():
    assert _shorten_chars("a" * 400, 300) == "a" * 300  # no spaces -> hard cut at limit
    trimmed = _shorten_chars("word " * 100, 50)
    assert len(trimmed) <= 50
    assert not trimmed.endswith(" ")  # clean boundary


def test_shorten_words():
    assert _shorten_words("w " * 200, 10).split() == ["w"] * 10
    assert _shorten_words("short text", 10) == "short text"


def test_normalize_caps_over_limit_llm_outreach():
    pkg = _DocPackage(
        resume_markdown="# Resume\n" + ("Experienced backend engineer with Python and FastAPI. " * 12),
        cover_letter_markdown="Dear hiring team, " + ("I am excited to apply for this role. " * 12),
        founder_message="Hi there! " + ("I would be a great fit for this. " * 40),
        linkedin_note="Hello, " + ("I would love to connect with you about this role. " * 20),
        cold_email="word " * 400,
        selected_projects=[],
    )
    profile = {"n": "Test Candidate", "s": "Engineer", "skills": [], "exp": [], "projects": []}
    lead = {"title": "Backend Engineer", "company": "Acme", "url": "https://x/y"}

    out = _normalize_package(pkg, profile, lead)
    assert len(out.founder_message) <= 280
    assert len(out.linkedin_note) <= 300, len(out.linkedin_note)
    assert len(out.cold_email.split()) <= 150
