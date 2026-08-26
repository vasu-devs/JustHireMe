# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs
"""The semantic-fit criterion must surface the active embedding mode so a
hash-fallback (runtime pack not installed) score is interpretable as degraded
rather than a genuine poor fit.
"""

from ranking import scoring_engine


def _make_result(mode: str) -> dict:
    return {
        "score": 72,
        "skill_matches": [("Python", 0.81)],
        "project_matches": [("Agent", 0.77)],
        "experience_matches": [],
        "credential_matches": [],
        "profile_matches": [],
        "source": "vector-store",
        "mode": mode,
        "raw": {"source": "vector-store", "mode": mode},
    }


def test_semantic_criterion_flags_degraded_hash_mode(monkeypatch):
    import ranking.semantic as semantic
    monkeypatch.setattr(semantic, "semantic_fit", lambda *a, **k: _make_result("hash"))

    crit = scoring_engine._semantic_criterion("Build FastAPI agents", {"skills": [{"n": "Python"}]}, weight=15)

    assert crit is not None
    assert "hash" in crit.reason
    assert "degraded" in crit.reason.lower()


def test_semantic_criterion_does_not_flag_real_provider(monkeypatch):
    import ranking.semantic as semantic
    monkeypatch.setattr(semantic, "semantic_fit", lambda *a, **k: _make_result("onnx"))

    crit = scoring_engine._semantic_criterion("Build FastAPI agents", {"skills": [{"n": "Python"}]}, weight=15)

    assert crit is not None
    assert "onnx" in crit.reason
    assert "degraded" not in crit.reason.lower()
