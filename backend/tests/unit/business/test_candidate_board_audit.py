from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from opportunities.eligibility import Decision
from scripts import audit_candidate_boards


@pytest.mark.asyncio
async def test_candidate_board_audit_explains_skipped_rows(monkeypatch):
    async def fake_scrape(_target: str) -> list[dict]:
        return [{"title": "Software Intern"}]

    skipped = SimpleNamespace(
        opportunity=SimpleNamespace(
            employer_name="Example",
            title="Software Intern - 2028 Batch",
            location_text="Bengaluru",
            lifecycle=SimpleNamespace(
                status="active",
                first_seen_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
                last_verified_active_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
                published_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                updated_at=None,
                deadline_at=None,
                evidence=["active_source_observation"],
            ),
            observations=[],
        ),
        applicability=SimpleNamespace(
            decision=Decision.SKIP,
            hard_blockers=["graduation_year_mismatch"],
            safety_blockers=[],
        ),
    )
    pipeline = SimpleNamespace(
        opportunities=[skipped],
        source_records=[object()],
        conversion_errors=[],
        decision_counts={"skip": 1},
    )
    monkeypatch.setattr(audit_candidate_boards, "scrape_market_target", fake_scrape)
    monkeypatch.setattr(audit_candidate_boards, "process_leads", lambda *_args, **_kwargs: pipeline)

    result = await audit_candidate_boards._audit_target(
        "ats:ashby:example",
        candidate=object(),
        semaphore=asyncio.Semaphore(1),
    )

    assert result["skip_reason_counts"] == {"graduation_year_mismatch": 1}
    assert result["freshness_counts"] == {"recent_30d": 1}
    sample = result["skip_samples"][0]
    assert sample["employer"] == "Example"
    assert sample["title"] == "Software Intern - 2028 Batch"
    assert sample["hard_blockers"] == ["graduation_year_mismatch"]
    assert sample["posting_age_days"] == 25
    assert sample["freshness_band"] == "recent_30d"
