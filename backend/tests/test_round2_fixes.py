"""Round-2 audit fixes: honest keyword coverage + hoisted settings read."""

from __future__ import annotations

import asyncio

from generation.generators.keywords import _keyword_coverage
from ranking.service import RankingService


def test_non_tech_coverage_pct_is_none_not_fake_100():
    # The JD extractor is software-only; a non-tech role has no known JD terms, so
    # coverage must be None (unknown), not a fabricated 100%.
    lead = {"title": "Structural Welder", "company": "SteelCo", "description": "MIG/TIG welding from blueprints"}
    out = _keyword_coverage({"skills": []}, lead)
    assert out["jd_terms"] == []
    assert out["coverage_pct"] is None


def test_evaluate_lead_uses_provided_settings(monkeypatch):
    # The loop call sites pass cfg so evaluate_lead must NOT re-read settings per lead.
    rs = RankingService()

    def boom():
        raise AssertionError("_load_settings must not be called when settings are provided")

    captured = {}

    def fake_score(jd, profile, settings, use_llm=True):
        captured["settings"] = settings
        captured["use_llm"] = use_llm
        return {"score": 50}

    monkeypatch.setattr(rs, "_load_settings", boom)
    monkeypatch.setattr(rs.evaluator, "score", fake_score)

    out = asyncio.run(rs.evaluate_lead({"title": "x"}, {}, {"llm_provider": "ollama"}))
    assert out["score"] == 50
    assert captured["settings"] == {"llm_provider": "ollama"}
