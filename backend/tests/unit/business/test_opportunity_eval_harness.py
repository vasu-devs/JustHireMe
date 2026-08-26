from __future__ import annotations

import pytest

from evals.opportunity_contracts import OpportunityCase, corpus_readiness, load_opportunity_cases
from evals.opportunity_harness import format_readiness


def test_seed_opportunity_corpus_is_valid_and_adversarial() -> None:
    cases = load_opportunity_cases()
    assert len(cases) >= 12
    assert len({case.id for case in cases}) == len(cases)
    assert {case.expected["decision"] for case in cases} >= {"apply_now", "needs_review", "skip"}
    assert {case.category for case in cases} >= {
        "india_internship",
        "india_early_career",
        "remote_india_eligible",
        "remote_india_ineligible",
        "seniority_trap",
        "non_technical",
        "closed_or_ambiguous",
        "unsafe",
        "duplicate",
    }
    assert sum(case.invariant for case in cases) >= 10


def test_seed_corpus_reports_not_ready_instead_of_claiming_phase_zero_complete() -> None:
    report = corpus_readiness(load_opportunity_cases())
    assert report.ready is False
    assert report.total < 300
    assert any("public snapshots" in gap for gap in report.gaps)
    rendered = format_readiness()
    assert "Status: NOT READY" in rendered
    assert "Opportunity corpus:" in rendered


def test_remote_unknown_requires_boolean_india_eligibility() -> None:
    raw = {
        "id": "bad",
        "category": "remote_india_eligible",
        "posting": {
            "title": "Intern",
            "company": "Acme",
            "url": "https://example.test/1",
            "source": "synthetic",
            "description": "Remote software internship worldwide.",
            "location": "Remote",
            "observed_at": "2026-08-24T00:00:00Z",
        },
        "expected": {
            "decision": "apply_now",
            "live_status": "active",
            "opportunity_type": "internship",
            "technical_track": "software",
            "workplace_scope": "worldwide_remote",
            "india_eligible": "yes",
            "paid_status": "paid",
            "hard_blockers": [],
            "safety_blockers": [],
        },
        "provenance": {
            "fixture_kind": "synthetic",
            "review_status": "single_review",
            "captured_at": "2026-08-24T00:00:00Z",
        },
    }
    with pytest.raises(ValueError, match="india_eligible must be boolean"):
        OpportunityCase.from_raw(raw, source="unit")
