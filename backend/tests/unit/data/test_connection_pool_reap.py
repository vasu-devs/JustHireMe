"""SQLite pool reaps connections from dead threads (Tier-2 leak fix).

Previously every connection ever created stayed in the global pool set until
close_all(), so a long-running process leaked a SQLite handle per worker thread.
A weakref.finalize on the owning thread now releases it when the thread is gone.
"""
import gc
import threading

from data.sqlite import connection as conn_mod


def _run_workers(pool, n):
    # Kept in its own scope so no loop variable lingers holding a Thread alive.
    threads = [threading.Thread(target=lambda: pool.get_connection(":memory:")) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def test_pool_reaps_connections_from_dead_threads():
    pool = conn_mod.ConnectionPool()
    _run_workers(pool, 6)
    # Worker threads have exited and all references to them are gone.
    gc.collect()
    gc.collect()
    assert len(pool._connections) == 0  # every dead thread's connection was reaped


def test_same_thread_reuses_one_connection():
    pool = conn_mod.ConnectionPool()
    a = pool.get_connection(":memory:")
    b = pool.get_connection(":memory:")
    assert a is b
    assert len(pool._connections) == 1
