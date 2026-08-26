# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs
"""Regression tests for C4/M2: graph connection locking.

execute_query must hold _graph_lock for the *entire* connection-check + execute
so concurrent callers are serialized and conn cannot be reset mid-query. M2 adds
_execute_query_unlocked for callers that already hold the lock.
"""

import threading
import time

import pytest

from data.graph import connection as gc


class _FakeConn:
    """Records the maximum number of concurrent execute() calls."""

    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.calls = 0
        self._lock = threading.Lock()

    def execute(self, query, params=None):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls += 1
        time.sleep(0.01)  # widen the window for a race to be observable
        with self._lock:
            self.active -= 1
        return f"result:{query}"


@pytest.fixture
def fake_graph(monkeypatch):
    fake = _FakeConn()
    # Pretend a connection already exists and the path is ready, so
    # _ensure_connection_unlocked is a no-op that won't null our fake.
    monkeypatch.setattr(gc, "conn", fake, raising=False)
    monkeypatch.setattr(gc, "db", object(), raising=False)
    monkeypatch.setattr(gc, "_GRAPH_DIR_READY", True, raising=False)
    monkeypatch.setattr(gc, "_prepare_graph_path", lambda: True)
    return fake


def test_execute_query_serializes_concurrent_calls(fake_graph):
    def worker():
        for _ in range(5):
            gc.execute_query("MATCH (n) RETURN n")

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert fake_graph.calls == 30
    # The lock must prevent any two executes from overlapping.
    assert fake_graph.max_active == 1


def test_execute_query_unlocked_runs_under_held_lock(fake_graph):
    with gc._graph_lock:
        result = gc._execute_query_unlocked("MATCH (n) RETURN n")
    assert result == "result:MATCH (n) RETURN n"


def test_execute_query_raises_graph_busy_when_lock_unavailable(monkeypatch, fake_graph):
    # Hold the lock from another thread so the main thread's timed acquire fails.
    monkeypatch.setattr(gc, "_GRAPH_LOCK_TIMEOUT_SECONDS", 0.05)
    held = threading.Event()
    release = threading.Event()

    def hog():
        with gc._graph_lock:
            held.set()
            release.wait(timeout=2)

    t = threading.Thread(target=hog)
    t.start()
    try:
        assert held.wait(timeout=2)
        with pytest.raises(gc.GraphBusyError):
            gc.execute_query("MATCH (n) RETURN n")
    finally:
        release.set()
        t.join()


def test_ensure_connection_acquires_lock(fake_graph):
    # _ensure_connection must succeed when a connection already exists, and it
    # must do so while holding the lock (no exception, returns True).
    assert gc._ensure_connection() is True


def test_graph_lock_timeout_is_generous_enough_for_rapid_deletes():
    # Rapid sequential profile deletes each hold the graph lock for a heavy
    # operation (Kuzu DETACH DELETE + vector cleanup + snapshot rewrite). The
    # old 1.5s timeout starved later deletes — they hit GraphBusyError, which
    # _safe_execute swallowed, so the node was never actually removed.
    assert gc._GRAPH_LOCK_TIMEOUT_SECONDS >= 10


@pytest.mark.parametrize(
    "raw",
    [
        "Could not set lock on file: graph.kuzu",
        "RuntimeError: IO exception: Could not set lock on file",
        "concurrency error opening database",
        "failed to acquire lock on file",
    ],
)
def test_friendly_graph_error_explains_lock_contention(raw):
    # Lock/concurrency errors are the common multi-process failure; the user-facing
    # message must give remediation (close extra windows / stop stale backends) and
    # still preserve the raw error for debugging.
    msg = gc.friendly_graph_error(raw)
    assert "locked by another JustHireMe backend process" in msg
    assert "restart the app" in msg
    assert raw in msg  # raw error preserved


def test_friendly_graph_error_passes_through_non_lock_errors():
    assert gc.friendly_graph_error("table does not exist") == "table does not exist"
    assert gc.friendly_graph_error("") == ""
    assert gc.friendly_graph_error(None) == ""
