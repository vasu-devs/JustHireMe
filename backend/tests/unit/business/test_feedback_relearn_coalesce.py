"""The feedback relearn runner coalesces concurrent recomputes.

A burst of thumbs-up/down clicks each POST /feedback and each would otherwise spawn
a full ~500-lead recompute. ``_run_relearn`` guarantees at most one runs at a time;
overlapping calls just mark it dirty so it loops once more, covering the whole burst.
This is pure asyncio state (no DB), so it runs in-process.
"""

import asyncio

from api.routers import leads as leads_router


def test_relearn_coalesces_concurrent_calls():
    calls = {"n": 0}

    async def main():
        release = asyncio.Event()

        class FakeRS:
            async def recompute_feedback_signals(self, *a, **k):
                calls["n"] += 1
                await release.wait()  # hold the first recompute open
                return []

        class FakeMgr:
            async def broadcast(self, *a, **k):
                return None

        rs, mgr = FakeRS(), FakeMgr()
        leads_router._relearn_state["running"] = False
        leads_router._relearn_state["again"] = False

        t1 = asyncio.create_task(leads_router._run_relearn(rs, mgr))
        await asyncio.sleep(0)  # let t1 enter recompute and park on release

        # Two more clicks arrive mid-flight — must NOT start parallel recomputes.
        await leads_router._run_relearn(rs, mgr)
        await leads_router._run_relearn(rs, mgr)
        assert leads_router._relearn_state["again"] is True
        assert calls["n"] == 1  # still just the one in-flight recompute

        release.set()
        await t1

        # One in-flight + exactly one coalesced rerun for the whole burst = 2 (not 3).
        assert calls["n"] == 2, calls
        assert leads_router._relearn_state["running"] is False

    asyncio.run(main())


def test_relearn_runs_again_after_completion():
    """A call that arrives AFTER the previous run finished starts a fresh recompute."""
    calls = {"n": 0}

    async def main():
        class FakeRS:
            async def recompute_feedback_signals(self, *a, **k):
                calls["n"] += 1
                return []

        class FakeMgr:
            async def broadcast(self, *a, **k):
                return None

        rs, mgr = FakeRS(), FakeMgr()
        leads_router._relearn_state["running"] = False
        leads_router._relearn_state["again"] = False

        await leads_router._run_relearn(rs, mgr)
        await leads_router._run_relearn(rs, mgr)
        assert calls["n"] == 2, calls

    asyncio.run(main())
