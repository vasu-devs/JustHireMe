from __future__ import annotations

import asyncio
from types import SimpleNamespace

from opportunities import scheduled


class FakeOpportunityStore:
    def __init__(self):
        self.finished = []

    def list_candidate_profiles(self):
        return [
            {"candidate_id": "pending", "graduation_year": 2027, "profile_updated_at": "newest"},
            {"candidate_id": "friend-2", "graduation_year": 2027, "consent_confirmed_at": "2026-08-25T00:00:00Z", "profile_updated_at": "now"},
            {"candidate_id": "friend-1", "graduation_year": 2026, "consent_confirmed_at": "2026-08-25T00:00:00Z", "profile_updated_at": "before"},
        ]

    def create_scan_run(self, candidate_id, *, target_count):
        return f"shared-{candidate_id}-{target_count}"

    def finish_scan_run(self, run_id, candidate_id, **payload):
        self.finished.append((run_id, candidate_id, payload))


class FakeRegistry:
    def __init__(self):
        self.starts = []

    async def start(self, **payload):
        self.starts.append(payload["candidate"].candidate_id)
        return {"started": True}

    async def wait(self):
        return {
            "status": "completed",
            "candidate_id": "friend-2",
            "target_count": 160,
            "targets_completed": 160,
            "source_failures": 2,
            "started_at": "2026-08-24T00:00:00+00:00",
        }


class FakeLogger:
    def info(self, *_args):
        return None

    def warning(self, *_args):
        return None


def test_scheduled_refresh_fetches_once_then_rescores_every_other_candidate(monkeypatch) -> None:
    store = FakeOpportunityStore()
    registry = FakeRegistry()
    rescored = []

    monkeypatch.setattr(scheduled, "OPPORTUNITY_SCANS", registry)
    monkeypatch.setattr(
        scheduled,
        "rescore_existing",
        lambda _repo, candidate: rescored.append(candidate.candidate_id) or {
            "apply_now": 3,
            "skip": 7,
            "opportunities": 10,
            "invalid_canonical": 0,
        },
    )
    tick = scheduled.create_scheduled_opportunity_tick(
        SimpleNamespace(opportunities=store),
        FakeLogger(),
    )
    asyncio.run(tick())

    assert registry.starts == ["friend-2"]
    assert rescored == ["friend-1"]
    assert store.finished[0][1] == "friend-1"
    payload = store.finished[0][2]["payload"]
    assert payload["shared_public_scan"] is True
    assert payload["decision_counts"] == {"apply_now": 3, "skip": 7}
    assert payload["opportunities"] == 10
