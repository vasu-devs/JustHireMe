from data import feedback


def test_rank_lead_by_feedback_adds_safe_defaults_without_ranking_domain():
    lead = {"signal_score": 50, "platform": "github"}

    result = feedback.rank_lead_by_feedback(lead)

    assert result["base_signal_score"] == 50
    assert result["learning_delta"] == 0
    assert result["learning_reason"] == ""
