from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from catalog.source_registry import DirectScanRun, ScanStatus, SourceHealth, SourceTarget
from opportunities import orchestrator
from opportunities.eligibility import CandidateConstraints
from opportunities.pipeline import process_leads


class FakeStore:
    def __init__(self) -> None:
        self.finished: dict = {}
        self.saved = 0

    def create_scan_run(self, candidate_id: str, *, target_count: int) -> str:
        assert candidate_id == "friend-1"
        assert target_count == 1
        return "opscan_test"

    def save_pipeline_result(self, result, *, candidate_id: str) -> dict:
        self.saved += 1
        return {"source_records": len(result.source_records), "opportunities": len(result.opportunities), "decisions": len(result.opportunities)}

    def finish_scan_run(self, run_id: str, candidate_id: str, *, status: str, payload: dict, source_health=None) -> None:
        self.finished = {"run_id": run_id, "candidate_id": candidate_id, "status": status, "payload": payload, "health": source_health or []}

    def get_latest_scan_run(self, candidate_id: str) -> dict:
        return self.finished.get("payload") or {"candidate_id": candidate_id, "status": "idle"}

    def reconcile_missing_direct_opportunities(self, **_payload) -> list[str]:
        return []


def test_background_opportunity_scan_persists_result_and_progress(monkeypatch) -> None:
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    target = SourceTarget(target_id="greenhouse:acme", provider="greenhouse", scan_target="ats:greenhouse:acme")
    candidate = CandidateConstraints(candidate_id="friend-1", graduation_year=2027)
    pipeline = process_leads([{
        "title": "Software Engineering Intern",
        "company": "Acme",
        "url": "https://job-boards.greenhouse.io/acme/jobs/123",
        "platform": "greenhouse",
        "location": "Bengaluru, India",
        "description": "Paid software internship for 2027 graduates.",
        "source_meta": {"job_id": "123"},
    }], candidate=candidate, observed_at=now)
    health = SourceHealth(
        target_id=target.target_id,
        provider="greenhouse",
        scan_target=target.scan_target,
        status=ScanStatus.SUCCESS,
        attempted_at=now,
        duration_ms=5,
        raw_rows=1,
        accepted_source_records=1,
        conversion_errors=0,
    )

    monkeypatch.setattr(orchestrator, "production_market_targets", lambda company_limit: [target])

    async def fake_scan(_targets, *, candidate, scraper, max_concurrency, on_target_complete):
        await on_target_complete(health)
        return DirectScanRun(started_at=now, completed_at=now, source_health=[health], pipeline=pipeline)

    monkeypatch.setattr(orchestrator, "run_direct_scan", fake_scan)
    monkeypatch.setattr(orchestrator, "rescore_existing", lambda _repo, _candidate: {
        "apply_now": 1,
        "opportunities": 1,
        "invalid_canonical": 0,
    })
    store = FakeStore()
    repo = SimpleNamespace(opportunities=store)
    registry = orchestrator.OpportunityScanRegistry()

    async def scenario():
        started = await registry.start(repo=repo, candidate=candidate, target_limit=1)
        assert started["started"] is True
        assert (await registry.status(candidate_id="friend-1", repo=repo))["status"] == "running"
        # Wait on the registry's completion primitive. A fixed number of
        # sleep(0) polls is scheduler-dependent when the shared thread pool is
        # busy during the full suite and made this otherwise-correct test flaky.
        return await registry.wait()

    status = asyncio.run(scenario())
    assert status["status"] == "completed"
    assert status["targets_completed"] == 1
    assert status["decision_counts"] == {"apply_now": 1}
    assert store.saved == 1
    assert store.finished["status"] == "completed"
    assert len(store.finished["health"]) == 1
