"""scripts/job_loop.py -- the full closed-loop orchestrator. Mirrors
test_watch_jobs_loop.py's approach: mock each stage function so these tests
exercise stage-level crash-tolerance and cycle wiring, not real network/DB/LLM
calls. The point of a per-stage try/except (stronger than watch_jobs.py's
per-CYCLE one) is that a dead verify-fetch or one bad draft must never cost
the rest of that same cycle's work.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import job_loop  # noqa: E402


def _lead(job_id: str, score: int = 80, status: str = "matched") -> dict:
    return {
        "job_id": job_id, "title": f"Role {job_id}", "company": "Acme",
        "url": f"https://x/{job_id}", "score": score, "status": status,
    }


def test_select_newly_confirmed_skips_already_actioned_and_respects_cap():
    shortlist = [_lead("a"), _lead("b", status="draft_ready"), _lead("c"), _lead("d")]
    verify_cache = {jid: {"verdict": "CONFIRMED"} for jid in ("a", "b", "c", "d")}
    out = job_loop._select_newly_confirmed(shortlist, verify_cache, cap=2)
    ids = [lead["job_id"] for lead in out]
    assert "b" not in ids  # already draft_ready -- never re-drafted
    assert ids == ["a", "c"]  # cap=2, shortlist order (already score-sorted upstream)


def test_select_newly_confirmed_only_takes_confirmed_verdicts():
    shortlist = [_lead("a"), _lead("b")]
    verify_cache = {"a": {"verdict": "REJECTED"}, "b": {"verdict": "CONFIRMED"}}
    out = job_loop._select_newly_confirmed(shortlist, verify_cache, cap=10)
    assert [lead["job_id"] for lead in out] == ["b"]


@pytest.mark.asyncio
async def test_a_failed_stage_never_kills_the_rest_of_the_cycle(monkeypatch, tmp_path):
    """The shortlist stage raises; verify/draft must gracefully no-op (they're
    gated on the prior stage producing a non-empty shortlist) instead of
    crashing, and the cycle still returns a complete stats dict."""
    monkeypatch.setattr(job_loop.run_scrape, "run_once", mock.AsyncMock(return_value={"added": 0}))
    monkeypatch.setattr(job_loop.watch_jobs, "score_unscored_leads", mock.AsyncMock(return_value={}))
    monkeypatch.setattr(job_loop.watch_jobs, "_load_cfg", lambda db_path: {})
    monkeypatch.setattr(job_loop, "get_all_leads", mock.Mock(return_value=[]))
    monkeypatch.setattr(job_loop.shortlist_global, "filtered_ranked_leads", mock.Mock(side_effect=RuntimeError("db locked")))
    record_error_mock = mock.Mock()
    monkeypatch.setattr(job_loop, "record_error", record_error_mock)

    stats = await job_loop.run_cycle({}, "unused.db", drafts_dir=tmp_path)

    assert "shortlist" in stats["errors"]
    assert stats["shortlist_size"] == 0
    assert stats["verify"] == {}
    assert stats["drafted"] == 0
    assert stats["draft_failed"] == 0
    assert (tmp_path / "review_queue.json").exists()  # the review-queue stage still ran
    assert record_error_mock.call_args_list[0].args[0] == "job_loop_shortlist_failed"


@pytest.mark.asyncio
async def test_verify_and_draft_stages_run_for_a_newly_confirmed_role(monkeypatch, tmp_path):
    lead = _lead("a", score=90)
    monkeypatch.setattr(job_loop.run_scrape, "run_once", mock.AsyncMock(return_value={"added": 1}))
    monkeypatch.setattr(job_loop.watch_jobs, "score_unscored_leads", mock.AsyncMock(return_value={}))
    monkeypatch.setattr(job_loop.watch_jobs, "_load_cfg", lambda db_path: {})
    monkeypatch.setattr(job_loop, "get_all_leads", mock.Mock(return_value=[lead]))
    monkeypatch.setattr(job_loop.shortlist_global, "filtered_ranked_leads", lambda leads: [lead])
    monkeypatch.setattr(job_loop.verify_shortlist, "run", mock.AsyncMock(return_value={"a": {"verdict": "CONFIRMED"}}))
    draft_calls: list[str] = []
    monkeypatch.setattr(
        job_loop.generate_drafts, "generate_draft",
        lambda profile, ld, out_dir, db_path: draft_calls.append(ld["job_id"]) or {"mode": "deterministic"},
    )
    status_calls: list[tuple] = []
    monkeypatch.setattr(job_loop, "update_lead_status", lambda job_id, status, db_path: status_calls.append((job_id, status)))

    stats = await job_loop.run_cycle({}, "unused.db", drafts_dir=tmp_path)

    assert draft_calls == ["a"]
    assert status_calls == [("a", "draft_ready")]
    assert stats["drafted"] == 1
    assert stats["verify"] == {"CONFIRMED": 1}


@pytest.mark.asyncio
async def test_a_failed_draft_is_logged_and_does_not_block_the_others(monkeypatch, tmp_path):
    lead_a, lead_b = _lead("a"), _lead("b")
    monkeypatch.setattr(job_loop.run_scrape, "run_once", mock.AsyncMock(return_value={"added": 0}))
    monkeypatch.setattr(job_loop.watch_jobs, "score_unscored_leads", mock.AsyncMock(return_value={}))
    monkeypatch.setattr(job_loop.watch_jobs, "_load_cfg", lambda db_path: {})
    monkeypatch.setattr(job_loop, "get_all_leads", mock.Mock(return_value=[lead_a, lead_b]))
    monkeypatch.setattr(job_loop.shortlist_global, "filtered_ranked_leads", lambda leads: [lead_a, lead_b])
    monkeypatch.setattr(
        job_loop.verify_shortlist, "run",
        mock.AsyncMock(return_value={"a": {"verdict": "CONFIRMED"}, "b": {"verdict": "CONFIRMED"}}),
    )
    monkeypatch.setattr(
        job_loop.generate_drafts, "generate_draft",
        mock.Mock(side_effect=[RuntimeError("codex down"), {"mode": "deterministic"}]),
    )
    update_mock = mock.Mock()
    monkeypatch.setattr(job_loop, "update_lead_status", update_mock)
    record_error_mock = mock.Mock()
    monkeypatch.setattr(job_loop, "record_error", record_error_mock)

    stats = await job_loop.run_cycle({}, "unused.db", drafts_dir=tmp_path)

    assert stats["drafted"] == 1
    assert stats["draft_failed"] == 1
    update_mock.assert_called_once()  # only the surviving draft advanced status
    assert any(call.args[0] == "job_loop_draft_failed" for call in record_error_mock.call_args_list)


@pytest.mark.asyncio
async def test_watch_once_flag_runs_exactly_one_cycle_and_never_sleeps(monkeypatch):
    sleep_mock = mock.AsyncMock()
    run_cycle_mock = mock.AsyncMock(return_value={"errors": [], "scrape": {"added": 0}, "shortlist_size": 0, "verify": {}, "drafted": 0})
    monkeypatch.setattr(job_loop, "run_cycle", run_cycle_mock)
    monkeypatch.setattr(job_loop.watch_jobs, "_sleep_interruptibly", sleep_mock)

    cycles = await job_loop.watch(
        {}, "unused.db", interval_hours=6.0, once=True,
        draft_cap=20, drafts_dir=Path("."), verify_concurrency=9,
    )

    assert cycles == 1
    run_cycle_mock.assert_awaited_once()
    sleep_mock.assert_not_called()


@pytest.mark.asyncio
async def test_watch_survives_a_cycle_that_raises_out_of_run_cycle(monkeypatch):
    """Belt-and-suspenders: even if run_cycle itself somehow raised (every
    stage inside it already catches its own exceptions), the outer loop must
    not propagate it -- mirrors watch_jobs.py's equivalent guarantee."""
    stop = job_loop.watch_jobs._Stop()

    async def fake_sleep(_seconds, s):
        s.requested = True

    monkeypatch.setattr(job_loop, "run_cycle", mock.AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(job_loop.watch_jobs, "_sleep_interruptibly", fake_sleep)
    record_error_mock = mock.Mock()
    monkeypatch.setattr(job_loop, "record_error", record_error_mock)

    cycles = await job_loop.watch(
        {}, "unused.db", interval_hours=0.001, once=False,
        draft_cap=20, drafts_dir=Path("."), verify_concurrency=9, stop=stop,
    )

    assert cycles == 1
    record_error_mock.assert_called_once()
    assert record_error_mock.call_args[0][0] == "job_loop_cycle_failed"


@pytest.mark.asyncio
async def test_watch_times_out_a_stalled_cycle_and_keeps_the_loop_alive(monkeypatch):
    """A slow board must not prevent the recurring worker from reaching its
    next cycle. The timeout is recorded as a distinct, auditable error."""

    async def stalled_cycle(*_args, **_kwargs):
        await __import__("asyncio").sleep(1)

    monkeypatch.setattr(job_loop, "run_cycle", stalled_cycle)
    record_error_mock = mock.Mock()
    monkeypatch.setattr(job_loop, "record_error", record_error_mock)

    cycles = await job_loop.watch(
        {}, "unused.db", interval_hours=6.0, once=True,
        draft_cap=20, drafts_dir=Path("."), verify_concurrency=9,
        cycle_timeout_s=0.001,
    )

    assert cycles == 1
    record_error_mock.assert_called_once()
    assert record_error_mock.call_args[0][0] == "job_loop_cycle_timeout"
