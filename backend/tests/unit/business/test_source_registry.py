from __future__ import annotations

import asyncio

from catalog.source_registry import ScanStatus, SourceTarget, _opportunity_projection, run_direct_scan
from discovery.sources.common import text_lead
from opportunities.eligibility import CandidateConstraints


CANDIDATE = CandidateConstraints(candidate_id="friend-1", graduation_year=2027)


def _target(provider: str, slug: str) -> SourceTarget:
    return SourceTarget(
        target_id=f"{provider}:{slug}",
        company_id=f"company:{slug}",
        provider=provider,
        scan_target=f"ats:{provider}:{slug}",
    )


def _lead(provider: str, slug: str, job_id: str) -> dict:
    return {
        "title": "Software Engineering Intern",
        "company": slug,
        "url": f"https://jobs.example.test/{slug}/{job_id}",
        "platform": provider,
        "location": "Bengaluru, India",
        "description": "Paid internship for 2027 graduates building software.",
        "source_meta": {"job_id": job_id},
    }


def test_source_health_distinguishes_success_zero_and_failure() -> None:
    targets = [_target("greenhouse", "ok"), _target("lever", "empty"), _target("ashby", "broken")]

    async def fake_scraper(scan_target: str) -> list[dict]:
        if "broken" in scan_target:
            raise RuntimeError("board unavailable")
        if "empty" in scan_target:
            return []
        return [_lead("greenhouse", "ok", "123")]

    run = asyncio.run(run_direct_scan(targets, candidate=CANDIDATE, scraper=fake_scraper))
    statuses = {health.target_id: health.status for health in run.source_health}
    assert statuses == {
        "greenhouse:ok": ScanStatus.SUCCESS,
        "lever:empty": ScanStatus.ZERO_RESULT,
        "ashby:broken": ScanStatus.FAILURE,
    }
    assert len(run.pipeline.opportunities) == 1
    assert run.pipeline.decision_counts == {"apply_now": 1}


def test_malformed_adapter_row_is_counted_without_aborting_scan() -> None:
    async def fake_scraper(_scan_target: str) -> list[dict]:
        return [_lead("greenhouse", "ok", "123"), "bad-row"]  # type: ignore[list-item]

    run = asyncio.run(
        run_direct_scan([_target("greenhouse", "ok")], candidate=CANDIDATE, scraper=fake_scraper)
    )
    health = run.source_health[0]
    assert health.status == ScanStatus.SUCCESS
    assert health.raw_rows == 2
    assert health.conversion_errors == 1
    assert len(run.pipeline.opportunities) == 1


def test_scan_reports_each_target_completion() -> None:
    completed: list[str] = []

    async def fake_scraper(scan_target: str) -> list[dict]:
        slug = scan_target.rsplit(":", 1)[-1]
        return [_lead("greenhouse", slug, "123")]

    async def on_complete(health) -> None:
        completed.append(health.target_id)

    targets = [_target("greenhouse", "one"), _target("greenhouse", "two")]
    asyncio.run(run_direct_scan(
        targets,
        candidate=CANDIDATE,
        scraper=fake_scraper,
        on_target_complete=on_complete,
    ))
    assert set(completed) == {"greenhouse:one", "greenhouse:two"}


def test_opportunity_projection_drops_discovery_only_generated_copy() -> None:
    row = {
        **_lead("greenhouse", "ok", "123"),
        "outreach_email": "large generated draft",
        "followup_sequence": ["one", "two"],
        "proposal_draft": "another generated draft",
    }
    projected = _opportunity_projection(row, target_id="greenhouse:ok")
    assert projected["title"] == row["title"]
    assert projected["description"] == row["description"]
    assert projected["source_meta"]["source_target_id"] == "greenhouse:ok"
    assert "outreach_email" not in projected
    assert "followup_sequence" not in projected
    assert "proposal_draft" not in projected


def test_source_timeout_is_recorded_as_failure() -> None:
    async def slow_scraper(_scan_target: str) -> list[dict]:
        await asyncio.sleep(0.05)
        return []

    run = asyncio.run(run_direct_scan(
        [_target("greenhouse", "slow")],
        candidate=CANDIDATE,
        scraper=slow_scraper,
        target_timeout_seconds=0.01,
    ))
    assert run.source_health[0].status == ScanStatus.FAILURE
    assert run.source_health[0].error_type == "TimeoutError"


def test_direct_scan_skips_legacy_outreach_enrichment_inside_source_adapters() -> None:
    observed: list[dict] = []

    async def adapter(_scan_target: str) -> list[dict]:
        lead = text_lead(_lead("greenhouse", "lean", "123"))
        observed.append(lead)
        return [lead]

    run = asyncio.run(run_direct_scan(
        [_target("greenhouse", "lean")],
        candidate=CANDIDATE,
        scraper=adapter,
    ))
    assert len(run.pipeline.opportunities) == 1
    assert "signal_score" not in observed[0]
    assert "outreach_email" not in observed[0]
    assert observed[0]["kind"] == "job"
