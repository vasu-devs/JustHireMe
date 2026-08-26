from __future__ import annotations

from types import SimpleNamespace

from datetime import datetime, timezone

from opportunities.eligibility import CandidateConstraints
from opportunities.rescore import rescore_existing
from opportunities.pipeline import process_leads


def test_rescore_requests_the_full_canonical_index_not_the_display_default() -> None:
    calls: list[dict] = []

    class FakeOpportunities:
        @staticmethod
        def list_canonical_opportunities(**kwargs):
            calls.append(kwargs)
            return []

    repo = SimpleNamespace(opportunities=FakeOpportunities())

    result = rescore_existing(
        repo,
        CandidateConstraints(candidate_id="candidate-1"),
        db_path="audit.sqlite3",
    )

    assert result == {}
    assert calls == [{"limit": 100_000, "db_path": "audit.sqlite3"}]


def test_rescore_persists_decisions_without_rewriting_canonical_truth() -> None:
    pipeline = process_leads(
        [{
            "title": "Software Engineering Intern",
            "company": "Acme",
            "url": "https://job-boards.greenhouse.io/acme/jobs/123",
            "platform": "greenhouse",
            "location": "Bengaluru, India",
            "description": "Paid internship building Python APIs.",
        }],
        candidate=CandidateConstraints(candidate_id="candidate-1"),
        observed_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
    )
    saved: list[tuple[object, dict]] = []

    class FakeOpportunities:
        @staticmethod
        def list_canonical_opportunities(**kwargs):
            return [pipeline.opportunities[0].opportunity.model_dump(mode="json")]

        @staticmethod
        def save_candidate_decisions(result, **kwargs):
            saved.append((result, kwargs))

        @staticmethod
        def save_pipeline_result(*args, **kwargs):
            raise AssertionError("rescore must not rewrite canonical opportunities")

    result = rescore_existing(
        SimpleNamespace(opportunities=FakeOpportunities()),
        CandidateConstraints(candidate_id="candidate-1"),
        db_path="audit.sqlite3",
    )

    assert result["opportunities"] == 1
    assert saved[0][1] == {"candidate_id": "candidate-1", "db_path": "audit.sqlite3"}
