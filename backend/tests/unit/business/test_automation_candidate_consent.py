from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from automation.service import AutomationService, get_lead_for_fire_sync
from core.errors import ConflictError


def _candidate_lead() -> dict:
    return {
        "job_id": "lead-1",
        "title": "Software Intern",
        "url": "https://example.test/apply",
        "source_meta": {"candidate_id": "friend-1", "opportunity_id": "opp_1"},
    }


def test_candidate_fire_uses_candidate_snapshot_not_shared_profile() -> None:
    candidate_profile = {
        "n": "Friend Candidate",
        "s": "Backend engineer",
        "projects": [],
        "identity": {
            "email": "friend@example.test",
            "phone": "+91 98765 43210",
            "city": "Bengaluru",
        },
    }
    repo = SimpleNamespace(
        leads=SimpleNamespace(get_lead_for_fire=lambda _job_id: (_candidate_lead(), "")),
        opportunities=SimpleNamespace(
            get_candidate_application_profile=lambda _candidate_id: candidate_profile
        ),
        profile=SimpleNamespace(
            get_profile=lambda: (_ for _ in ()).throw(
                AssertionError("shared profile must not be read")
            )
        ),
        settings=SimpleNamespace(
            get_settings=lambda: (_ for _ in ()).throw(
                AssertionError("shared identity settings must not be read")
            )
        ),
    )

    lead, _asset = get_lead_for_fire_sync("lead-1", repo)

    assert lead["name"] == "Friend Candidate"
    assert lead["email"] == "friend@example.test"
    assert lead["phone"] == "+91 98765 43210"
    assert lead["city"] == "Bengaluru"


@pytest.mark.parametrize(
    ("consent", "ready", "message"),
    [
        (None, True, "consent"),
        ("2026-08-25T00:00:00Z", False, "(?i)candidate-specific application profile"),
    ],
)
def test_candidate_submit_boundary_requires_consent_and_contact_profile(
    consent: str | None,
    ready: bool,
    message: str,
) -> None:
    repo = SimpleNamespace(opportunities=SimpleNamespace(
        get_candidate_profile=lambda _candidate_id: {
            "candidate_id": "friend-1",
            "consent_confirmed_at": consent,
        },
        candidate_application_profile_status=lambda _candidate_id: {"ready": ready},
    ))
    service = AutomationService(repo)

    with pytest.raises(ConflictError, match=message):
        asyncio.run(service._require_candidate_submission_ready(_candidate_lead()))


def test_generic_personal_lead_does_not_require_pilot_candidate_profile() -> None:
    service = AutomationService(SimpleNamespace())
    asyncio.run(service._require_candidate_submission_ready({"job_id": "legacy"}))
