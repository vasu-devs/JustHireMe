"""scripts/watch_jobs.py -- the recurring scrape/score loop. The whole point of
a background watcher is that ONE bad cycle (a dead board, a locked DB, a
transient network blip) must never stop tomorrow's cycle from running. These
tests mock ``run_cycle`` (the scrape+ingest+score unit) so they exercise only
the loop's own control flow -- no network, no real DB.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import watch_jobs  # noqa: E402


def _ok_stats(**kw) -> dict:
    base = {"duration_s": 0.1, "leads_before": 0, "leads_after": 1, "targets": 1,
            "scraped": 1, "written": 1, "added": 1, "unscored": 1, "scored": 1, "failed": 0}
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_a_failed_cycle_is_logged_and_the_loop_continues_to_the_next_one():
    stop = watch_jobs._Stop()
    calls = {"sleeps": 0}

    async def fake_sleep(_seconds, s):
        # Let cycle 2 run, then stop -- verifies the loop survives cycle 1's
        # exception rather than exiting after it.
        calls["sleeps"] += 1
        if calls["sleeps"] >= 2:
            s.requested = True

    run_cycle_mock = mock.AsyncMock(side_effect=[RuntimeError("board down"), _ok_stats()])

    with mock.patch.object(watch_jobs, "run_cycle", run_cycle_mock), \
         mock.patch.object(watch_jobs, "_sleep_interruptibly", fake_sleep), \
         mock.patch.object(watch_jobs, "record_error") as record_error_mock:
        cycles = await watch_jobs.watch({}, "unused.db", interval_hours=0.001, once=False, stop=stop)

    assert cycles == 2
    assert run_cycle_mock.await_count == 2
    # A stable error code was recorded for the failed cycle -- this repo's
    # logging convention (see core/telemetry.record_error usage elsewhere).
    record_error_mock.assert_called_once()
    assert record_error_mock.call_args[0][0] == "watch_cycle_failed"


@pytest.mark.asyncio
async def test_every_cycle_failing_never_raises_out_of_watch():
    """A watcher that only ever hits dead boards must still not crash the
    process -- it just keeps logging and looping until told to stop."""
    stop = watch_jobs._Stop()

    async def fake_sleep(_seconds, s):
        s.requested = True  # stop after the first (failing) cycle

    with mock.patch.object(watch_jobs, "run_cycle", mock.AsyncMock(side_effect=RuntimeError("boom"))), \
         mock.patch.object(watch_jobs, "_sleep_interruptibly", fake_sleep), \
         mock.patch.object(watch_jobs, "record_error"):
        cycles = await watch_jobs.watch({}, "unused.db", interval_hours=0.001, once=False, stop=stop)

    assert cycles == 1  # ran, failed, logged, stopped cleanly -- no exception escaped


@pytest.mark.asyncio
async def test_once_flag_runs_exactly_one_cycle_and_never_sleeps():
    sleep_mock = mock.AsyncMock()
    with mock.patch.object(watch_jobs, "run_cycle", mock.AsyncMock(return_value=_ok_stats())) as run_cycle_mock, \
         mock.patch.object(watch_jobs, "_sleep_interruptibly", sleep_mock):
        cycles = await watch_jobs.watch({}, "unused.db", interval_hours=6.0, once=True)

    assert cycles == 1
    run_cycle_mock.assert_awaited_once()
    sleep_mock.assert_not_called()


@pytest.mark.asyncio
async def test_stop_flag_set_before_the_next_cycle_ends_the_loop():
    stop = watch_jobs._Stop()
    stop.requested = True  # simulates Ctrl-C arriving mid-cycle
    with mock.patch.object(watch_jobs, "run_cycle", mock.AsyncMock(return_value=_ok_stats())) as run_cycle_mock, \
         mock.patch.object(watch_jobs, "_sleep_interruptibly", mock.AsyncMock()) as sleep_mock:
        cycles = await watch_jobs.watch({}, "unused.db", interval_hours=6.0, once=False, stop=stop)

    assert cycles == 1  # the in-flight cycle still completes, then it stops
    run_cycle_mock.assert_awaited_once()
    sleep_mock.assert_not_called()


@pytest.mark.asyncio
async def test_sleep_interruptibly_stops_after_the_slice_where_shutdown_was_requested(monkeypatch):
    """A 6h interval must not block Ctrl-C for 6 hours: it sleeps in <=30s
    slices and re-checks the stop flag between them. Mocks asyncio.sleep so
    the assertion is on slicing behaviour, not real wall-clock time."""
    stop = watch_jobs._Stop()
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        if len(slept) == 2:
            stop.requested = True  # e.g. Ctrl-C arrives during the 2nd slice

    monkeypatch.setattr(watch_jobs.asyncio, "sleep", fake_sleep)
    # Uninterrupted, 3600s / 30s-per-slice would be 120 slices.
    await watch_jobs._sleep_interruptibly(3600, stop)

    assert slept == [30.0, 30.0]  # stopped after slice 2, not all 120
