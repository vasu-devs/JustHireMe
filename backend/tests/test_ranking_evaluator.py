from unittest import mock

from ranking.evaluator import Evaluator
from ranking.feedback_ranker import FeedbackRanker
from ranking.semantic import SemanticMatcher


def test_evaluator_facade_calls_score_function():
    expected = {"score": 81, "reason": "ok", "match_points": [], "gaps": []}

    with mock.patch("ranking.evaluator.score", return_value=expected) as score:
        result = Evaluator().score("Job Title: Role", {"skills": []})

    assert result == expected
    # settings default to None and use_llm defaults to True (the token gate is opt-in
    # per lead by the caller).
    score.assert_called_once_with("Job Title: Role", {"skills": []}, None, True)


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
