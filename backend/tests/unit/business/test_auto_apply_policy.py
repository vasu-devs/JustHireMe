from __future__ import annotations

from datetime import datetime, timezone

from automation.policy import assess_auto_apply


def _candidate(**overrides):
    return {
        "consent_confirmed_at": "2026-09-01T00:00:00Z",
        "auto_apply_enabled": True,
        "auto_apply_confirmed_at": "2026-09-01T00:00:00Z",
        "auto_apply_minimum_fit_score": 80,
        "auto_apply_daily_limit": 5,
        "auto_apply_allow_strong_stretch": False,
        "allow_unpaid": False,
        **overrides,
    }


def _opportunity(status="active"):
    return {
        "opportunity_id": "opp_1",
        "canonical_apply_url": "https://example.test/apply",
        "lifecycle": {"status": status},
    }


def _applicability(**overrides):
    return {
        "decision": "apply_now",
        "eligibility": "eligible",
        "paid_status": "paid",
        "candidate_fit_score": 91,
        "hard_blockers": [],
        "safety_blockers": [],
        "safety_warnings": [],
        "unknowns": [],
        "candidate_evidence_missing": False,
        **overrides,
    }


def test_auto_apply_policy_allows_only_fully_verified_candidate_fit():
    decision = assess_auto_apply(
        _candidate(), _opportunity(), _applicability(), [], application_profile_ready=True
    )
    assert decision.allowed is True
    assert decision.blockers == ()


def test_auto_apply_policy_blocks_unknowns_duplicates_and_unconfirmed_consent():
    events = [{
        "event_type": "application_submitted",
        "opportunity_id": "opp_1",
        "occurred_at": "2026-09-01T01:00:00Z",
    }]
    decision = assess_auto_apply(
        _candidate(auto_apply_confirmed_at=None),
        _opportunity(),
        _applicability(unknowns=["work authorization unknown"]),
        events,
        application_profile_ready=True,
    )
    assert decision.allowed is False
    assert any("confirmation" in item for item in decision.blockers)
    assert any("unresolved" in item for item in decision.blockers)
    assert any("already" in item for item in decision.blockers)


def test_auto_apply_policy_enforces_fit_lifecycle_and_daily_limit():
    events = [
        {
            "event_type": "application_submitted",
            "opportunity_id": f"other_{index}",
            "occurred_at": "2026-09-01T01:00:00Z",
        }
        for index in range(2)
    ]
    decision = assess_auto_apply(
        _candidate(auto_apply_daily_limit=2),
        _opportunity("unknown"),
        _applicability(candidate_fit_score=79),
        events,
        application_profile_ready=True,
        now=datetime(2026, 9, 1, 12, tzinfo=timezone.utc),
    )
    assert decision.allowed is False
    assert any("verified active" in item for item in decision.blockers)
    assert any("fit 79" in item for item in decision.blockers)
    assert any("daily" in item for item in decision.blockers)


def test_strong_stretch_is_explicitly_opt_in():
    blocked = assess_auto_apply(
        _candidate(), _opportunity(), _applicability(decision="strong_stretch"), [],
        application_profile_ready=True,
    )
    allowed = assess_auto_apply(
        _candidate(auto_apply_allow_strong_stretch=True), _opportunity(),
        _applicability(decision="strong_stretch"), [], application_profile_ready=True,
    )
    assert blocked.allowed is False
    assert allowed.allowed is True


def test_auto_apply_requires_verified_paid_status_and_direct_url():
    decision = assess_auto_apply(
        _candidate(),
        _opportunity() | {"canonical_apply_url": ""},
        _applicability(paid_status="unknown"),
        [],
        application_profile_ready=True,
    )
    assert decision.allowed is False
    assert any("direct application URL" in item for item in decision.blockers)
    assert any("verified paid" in item for item in decision.blockers)
