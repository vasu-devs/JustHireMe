"""Feedback scoring: prebuilt-model reuse + no signal_reason suffix stacking."""

from __future__ import annotations

from ranking.feedback_ranker import apply_feedback_learning, build_model, score_with_model


def test_score_with_model_matches_apply():
    examples = [{"feedback": "good", "platform": "greenhouse", "kind": "job"}]
    lead = {"platform": "greenhouse", "kind": "job", "signal_score": 40}
    model = build_model(examples)
    assert score_with_model(lead, model)["signal_score"] == apply_feedback_learning(lead, examples)["signal_score"]


def test_reason_does_not_stack_on_rescore():
    examples = [{"feedback": "good", "platform": "greenhouse", "kind": "job"}]
    model = build_model(examples)
    lead = {"platform": "greenhouse", "kind": "job", "signal_score": 40, "signal_reason": "quality signal"}

    r1 = score_with_model(lead, model)
    assert "feedback learning" in r1["signal_reason"]

    # Re-score the already-scored lead (as recompute does) — the suffix must be
    # REPLACED, not appended a second time.
    r2 = score_with_model(r1, model)
    assert r2["signal_reason"].count("feedback learning") == 1, r2["signal_reason"]
    assert r2["signal_reason"].startswith("quality signal")


def test_empty_model_clears_stale_suffix():
    # No feedback -> empty model -> a previously-suffixed reason is cleaned, not kept.
    lead = {"signal_score": 40, "signal_reason": "quality signal; feedback learning +5"}
    out = score_with_model(lead, {})
    assert out["learning_delta"] == 0
    assert "feedback learning" not in out["signal_reason"]
    assert out["signal_reason"] == "quality signal"


def test_delta_rounds_to_zero_clears_learning_meta():
    # Contributions exist but net/round to 0 -> no boost/penalty; must clear the
    # learning metadata (not write a contradictory 'penalty +0.4 / delta:0' block).
    lead = {
        "signal_score": 47,
        "location": "berlin",
        "source_meta": {"learning": {"base_signal_score": 40, "delta": 7, "reason": "old"}},
    }
    # A single "good" example sharing the location feature: 1.0 * 0.2 * 2.0 = 0.4 -> rounds to 0.
    model = build_model([{"feedback": "good", "location": "berlin"}])
    out = score_with_model(lead, model)
    assert out["learning_delta"] == 0
    assert out["learning_reason"] == ""
    assert "learning" not in (out.get("source_meta") or {}), out.get("source_meta")


def test_demotion_clears_stale_learning_meta():
    # A previously-boosted lead re-scored with a model that no longer matches it
    # (delta -> 0) must not keep a contradictory source_meta.learning block.
    lead = {
        "signal_score": 47,
        "platform": "greenhouse",
        "source_meta": {"learning": {"base_signal_score": 40, "delta": 7, "reason": "Feedback boost"}},
    }
    # Model that shares no feature with the lead -> no contribution -> delta 0.
    model = {"platform:other": {"sum": 1.0, "count": 1}}
    out = score_with_model(lead, model)
    assert out["learning_delta"] == 0
    assert "learning" not in (out.get("source_meta") or {}), out.get("source_meta")
