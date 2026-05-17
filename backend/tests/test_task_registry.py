from __future__ import annotations

import asyncio

from api.routers.discovery import TaskRegistry


def test_task_registry_rejects_duplicate_running_task():
    async def scenario():
        registry = TaskRegistry()
        started = asyncio.Event()
        release = asyncio.Event()

        async def work(_stop):
            started.set()
            await release.wait()

        assert await registry.start("scan", work)
        await started.wait()
        assert not await registry.start("scan", work)
        release.set()
        await asyncio.sleep(0)

    asyncio.run(scenario())


def test_task_registry_enforces_mutex_tasks():
    async def scenario():
        registry = TaskRegistry()
        release = asyncio.Event()

        async def work(_stop):
            await release.wait()

        assert await registry.start("scan", work, mutex_with=["reevaluate"])
        assert not await registry.start("reevaluate", work, mutex_with=["scan"])
        release.set()
        await asyncio.sleep(0)

    asyncio.run(scenario())


def test_task_registry_cleans_up_after_error():
    async def scenario():
        registry = TaskRegistry()

        async def failing(_stop):
            raise RuntimeError("boom")

        assert await registry.start("scan", failing)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not await registry.is_running("scan")
        assert await registry.start("scan", failing)

    asyncio.run(scenario())


def test_task_registry_stop_sets_stop_event():
    async def scenario():
        registry = TaskRegistry()
        stopped = asyncio.Event()

        async def work(stop):
            await stop.wait()
            stopped.set()

        assert await registry.start("scan", work)
        assert await registry.stop("scan")
        await asyncio.wait_for(stopped.wait(), timeout=1)

    asyncio.run(scenario())
