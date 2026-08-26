"""Round-3 audit fixes: query_gen fallback, PDF accents, cold-email line structure."""

from __future__ import annotations

import discovery.query_gen as qg
from generation.generators.cover_letter import _shorten_words
from generation.pdf_renderer import _clean


def test_query_gen_deterministic_fallback_when_llm_empty(monkeypatch):
    # LLM returns no queries (e.g. provider needs a key it doesn't have -> call_llm
    # returns an empty result, not an exception). Board site: targets must still get
    # deterministic queries, not be silently dropped.
    monkeypatch.setattr("llm.call_llm", lambda *a, **k: qg._Plan(queries=[]))
    profile = {"s": "Registered Nurse", "skills": [{"n": "IV Therapy"}]}
    out = qg.generate(profile, ["site:jobs.lever.co", "site:boards.greenhouse.io"], "global")
    assert any("site:jobs.lever.co" in q for q in out), out
    assert any("site:boards.greenhouse.io" in q for q in out), out


def test_pdf_clean_preserves_latin_accents():
    assert _clean("José García") == "José García"
    assert _clean("Müller François Renée Zoë") == "Müller François Renée Zoë"
    # Truly non-latin-1 (CJK/emoji) is still stripped, and it must not crash.
    cleaned = _clean("Zoë 李伟 🚀 test")
    assert "Zoë" in cleaned and "test" in cleaned


def test_shorten_words_preserves_line_structure():
    body = " ".join(["word"] * 300)
    email = f"Subject: Senior Engineer at Acme\n\nHi team,\n\n{body}\n\nBest,\nJane"
    out = _shorten_words(email, 20)
    assert "\n" in out, "line structure (Subject / body) must survive truncation"
    assert out.startswith("Subject: Senior Engineer at Acme")
    assert len(out.split()) <= 20
