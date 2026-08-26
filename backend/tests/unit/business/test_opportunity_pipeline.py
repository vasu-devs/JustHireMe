from __future__ import annotations

from datetime import datetime, timedelta, timezone

from opportunities.canonicalize import source_record_from_lead
from opportunities.deduplicate import canonicalize_observations
from opportunities.eligibility import CandidateConstraints, Decision
from opportunities.models import LiveStatus
from opportunities.pipeline import _primary_observation, process_leads
from opportunities.taxonomy import WorkplaceScope


NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
CANDIDATE = CandidateConstraints(candidate_id="friend-1", graduation_year=2027, currently_enrolled=True)


def _lead(url: str, **overrides) -> dict:
    return {
        "title": "Software Engineering Intern",
        "company": "Acme",
        "url": url,
        "platform": "greenhouse",
        "location": "Bengaluru, India",
        "description": "Paid software internship for 2027 graduates building Python APIs.",
        **overrides,
    }


def test_direct_ats_observations_flow_to_one_active_apply_now_opportunity() -> None:
    result = process_leads(
        [
            _lead("https://boards.greenhouse.io/acme/jobs/123?gh_src=one"),
            _lead("https://job-boards.greenhouse.io/acme/jobs/123?gh_jid=123"),
        ],
        candidate=CANDIDATE,
        observed_at=NOW,
    )
    assert len(result.source_records) == 2
    assert len(result.opportunities) == 1
    item = result.opportunities[0]
    assert item.opportunity.lifecycle.status == LiveStatus.ACTIVE
    assert len(item.opportunity.observations) == 2
    assert item.applicability.decision == Decision.APPLY_NOW
    assert result.decision_counts == {"apply_now": 1}


def test_pipeline_never_promotes_restricted_remote_role() -> None:
    result = process_leads(
        [_lead(
            "https://boards.greenhouse.io/acme/jobs/456",
            location="Remote — United States only",
            description="Remote role. Must reside in the United States with unrestricted US work authorization.",
        )],
        candidate=CANDIDATE,
        observed_at=NOW,
    )
    assert result.opportunities[0].applicability.decision == Decision.SKIP


def test_pipeline_uses_structured_workplace_when_description_omits_remote() -> None:
    result = process_leads(
        [_lead(
            "https://boards.greenhouse.io/acme/jobs/457",
            workplace="remote",
            description="Paid software internship building Python APIs.",
        )],
        candidate=CANDIDATE,
        observed_at=NOW,
    )

    assert result.opportunities[0].applicability.workplace_scope == WorkplaceScope.INDIA_REMOTE


def test_bad_lead_is_reported_without_aborting_valid_records() -> None:
    result = process_leads(
        [{"title": "Missing URL"}, _lead("https://boards.greenhouse.io/acme/jobs/789")],
        candidate=CANDIDATE,
        observed_at=NOW,
    )
    assert len(result.conversion_errors) == 1
    assert len(result.opportunities) == 1


def test_newest_near_complete_scan_wins_within_same_source_identity() -> None:
    older = source_record_from_lead(
        _lead(
            "https://boards.greenhouse.io/acme/jobs/901",
            description="Paid software internship. Compensation: INR 15,000.",
        ),
        observed_at=NOW,
    )
    newer = source_record_from_lead(
        _lead(
            "https://boards.greenhouse.io/acme/jobs/901",
            description="Paid software internship. Salary: INR 15,000.",
        ),
        observed_at=NOW + timedelta(hours=1),
    )
    opportunity = canonicalize_observations([older, newer])[0]

    assert _primary_observation(opportunity).source_record_id == newer.source_record_id


def test_short_latest_fallback_does_not_displace_full_detail() -> None:
    older = source_record_from_lead(
        _lead(
            "https://boards.greenhouse.io/acme/jobs/902",
            description=(
                "Paid software internship building production Python APIs with mentorship, "
                "testing, deployment, database design, and code reviews."
            ),
        ),
        observed_at=NOW,
    )
    fallback = source_record_from_lead(
        _lead(
            "https://boards.greenhouse.io/acme/jobs/902",
            description="Software Engineering Intern",
        ),
        observed_at=NOW + timedelta(hours=1),
    )
    opportunity = canonicalize_observations([older, fallback])[0]

    assert _primary_observation(opportunity).source_record_id == older.source_record_id
