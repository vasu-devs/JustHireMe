# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs
"""Regression test for H4: run_scan must read settings/profile off the event
loop (via asyncio.to_thread), not synchronously on the loop thread."""

import asyncio
import threading
import types

import pytest

from discovery import orchestrator as discovery


class _FakeJob:
    job_id = "job-test"


class _FakeJobStore:
    def create(self, *_a, **_k):
        return _FakeJob()

    def update(self, *_a, **_k):
        return None


class _FakeManager:
    def __init__(self):
        self.events = []

    async def broadcast(self, payload):
        self.events.append(payload)


class _RecordingRepo:
    """Records which thread each DB read executed on."""

    def __init__(self, main_thread_id):
        self.main_thread_id = main_thread_id
        self.settings_thread = None
        self.profile_thread = None
        self.settings = types.SimpleNamespace(get_settings=self._get_settings)
        self.profile = types.SimpleNamespace(get_profile=self._get_profile)

    def _get_settings(self):
        self.settings_thread = threading.get_ident()
        return {}  # empty -> no explicit discovery targets

    def _get_profile(self):
        self.profile_thread = threading.get_ident()
        return {}  # empty -> no profile discovery signal


@pytest.mark.asyncio
async def test_run_scan_reads_db_off_event_loop(monkeypatch):
    monkeypatch.setattr(discovery, "get_job_store", lambda: _FakeJobStore())
    repo = _RecordingRepo(threading.get_ident())
    manager = _FakeManager()

    # Empty settings + profile => run_scan returns early after the two DB reads.
    await discovery.run_scan(
        manager,
        repo=repo,
        discovery_service=object(),
        ranking_service=object(),
    )

    main_thread = threading.get_ident()
    assert repo.settings_thread is not None
    assert repo.profile_thread is not None
    # The whole point of H4: these ran on worker threads, not the loop thread.
    assert repo.settings_thread != main_thread
    assert repo.profile_thread != main_thread
    # And it short-circuited as expected.
    assert any(e.get("event") == "scan_skipped" for e in manager.events)
