from unittest import mock

import pytest

from core.types import ScoreResult
from ranking import evaluator as ev
from ranking.evaluator import Evaluator
from ranking.feedback_ranker import FeedbackRanker
from ranking.semantic import SemanticMatcher


def test_evaluator_facade_calls_score_function():
    expected = {"score": 81, "reason": "ok", "match_points": [], "gaps": []}

    with mock.patch("ranking.evaluator.score", return_value=expected) as score:
        result = Evaluator().score("Job Title: Role", {"skills": []})

    assert result == expected
    # settings default to None and use_llm defaults to True (the token gate is opt-in
    # per lead by the caller); baseline is the opt-in precomputed-rubric contract.
    score.assert_called_once_with("Job Title: Role", {"skills": []}, None, True, baseline=None)


def _baseline_result(score: int = 55, **kwargs) -> ScoreResult:
    defaults = dict(
        score=score,
        reason="deterministic baseline",
        match_points=["Stack overlap 80/100"],
        gaps=["Missing or weak evidence for: docker"],
        criteria=[],
    )
    defaults.update(kwargs)
    return ScoreResult(**defaults)


def test_score_uses_precomputed_baseline_without_recomputing():
    with mock.patch(
        "ranking.evaluator.score_job_lead",
        side_effect=AssertionError("baseline must not be recomputed"),
    ):
        out = ev.score("Job Title: Role", {"skills": []}, None, use_llm=False, baseline=_baseline_result(61))

    assert out["score"] == 61
    assert out["scored_by"] == "deterministic"


def test_llm_reply_omitting_score_falls_back_to_baseline_score():
    raw = ev._Score(reason="solid match", match_points=["proof"])  # no score field sent
    with mock.patch("ranking.evaluator.record_error") as rec:
        out = ev._normalize_llm_result(raw, _baseline_result(58).as_dict())

    assert out["score"] == 58, "omitted score must fall back to the baseline, not persist as 0"
    assert out["scored_by"] == "llm_score_fallback"
    assert any("omitted a score" in gap for gap in out["gaps"])
    rec.assert_called_once()


def test_llm_reply_with_explicit_zero_score_is_kept():
    raw = ev._Score(score=0, reason="terrible fit")
    out = ev._normalize_llm_result(raw, _baseline_result(58).as_dict())
    assert out["score"] == 0
    assert "scored_by" not in out


def test_parse_fallback_empty_reply_still_raises_and_triggers_deterministic_fallback(monkeypatch):
    # Keyless providers return _parse_fallback's empty-but-valid _Score; that must
    # keep raising ValueError (not silently score 0) so score() falls back.
    from llm.client import _parse_fallback

    empty = _parse_fallback("ignored", ev._Score)
    with pytest.raises(ValueError):
        ev._normalize_llm_result(empty, _baseline_result().as_dict())

    monkeypatch.setattr(ev, "_evaluator_llm_requested", lambda settings=None: True)
    monkeypatch.setattr(ev, "record_error", lambda *a, **k: None)
    with mock.patch("llm.call_llm", return_value=empty):
        out = ev.score("Job Title: Role", {"skills": []}, {"llm_provider": "groq"})
    assert out["scored_by"] == "deterministic_fallback"


def test_hard_cap_reads_cap_kinds_even_when_gap_note_is_truncated_out():
    # The display gaps list is truncated to 8; the seniority note can be cut while
    # the cap still applies. Structural cap_kinds must keep enforcing it.
    baseline = _baseline_result(
        42,
        gaps=[f"filler gap {i}" for i in range(8)],  # no 'seniority cap' text at all
        applied_cap=42,
        cap_kinds=["seniority", "stack"],
    ).as_dict()
    raw = ev._Score(score=90, reason="LLM overshoot", match_points=["x"])

    out = ev._normalize_llm_result(raw, baseline)

    assert out["score"] == 42, "seniority cap must hold even without its gap note"
    assert any("Guardrail cap applied" in gap for gap in out["gaps"])


def test_hard_cap_is_soft_for_stack_and_confidence_kinds():
    baseline = _baseline_result(42, applied_cap=42, cap_kinds=["stack"]).as_dict()
    raw = ev._Score(score=88, reason="evidence justifies more")
    out = ev._normalize_llm_result(raw, baseline)
    assert out["score"] == 88, "stack cap is deliberately soft for the LLM"


def test_evaluator_llm_requested_requires_a_provider():
    with mock.patch("ranking.evaluator.record_error") as rec:
        assert ev._evaluator_llm_requested({"evaluator_provider": "codex_cli"}) is True
        assert ev._evaluator_llm_requested({"llm_provider": "groq"}) is True
        assert ev._evaluator_llm_requested({}) is False
        rec.assert_not_called()
        # Key/model alone is not a route: it would dead-end in localhost ollama
        # retries. Deterministic + one telemetry record naming the miss.
        assert ev._evaluator_llm_requested({"evaluator_api_key": "sk-x"}) is False
        assert ev._evaluator_llm_requested({"evaluator_model": "gpt-x"}) is False
    assert rec.call_count == 2
    assert rec.call_args[0][0] == "evaluator_provider_missing"


def test_off_field_prefilter_reason_fits_store_limit():
    long_reason = "x" * 600
    baseline = _baseline_result(15, reason=long_reason, cap_kinds=["wrong-field"], applied_cap=15)
    with mock.patch.object(ev, "_evaluator_llm_requested", return_value=True):
        out = ev.score("Job Title: Registered Nurse\nDescription: ICU nurse needed.",
                       {"skills": [{"n": "Python"}]}, {"llm_provider": "groq"}, baseline=baseline)
    assert out["scored_by"] == "prefiltered_off_field"
    assert len(out["reason"]) <= 500
    assert out["reason"].startswith("Off-field for your profile")


def test_semantic_matcher_facade_calls_semantic_fit():
    expected = {"score": 55}

    with mock.patch("ranking.semantic.semantic_fit", return_value=expected) as semantic_fit:
        result = SemanticMatcher().match("Job Title: Role", candidate_data={"skills": []})

    assert result == expected
    semantic_fit.assert_called_once_with("Job Title: Role", candidate_data={"skills": []}, top_skills=6, top_projects=3)


def test_feedback_ranker_facade_calls_apply_feedback_learning():
    expected = {"signal_score": 61}

    with mock.patch("ranking.feedback_ranker.apply_feedback_learning", return_value=expected) as apply:
        result = FeedbackRanker().apply({"signal_score": 60}, [{"feedback": "good"}])

    assert result == expected
    apply.assert_called_once_with({"signal_score": 60}, [{"feedback": "good"}], max_delta=18)
