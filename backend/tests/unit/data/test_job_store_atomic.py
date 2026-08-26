"""Atomic JobStore.update + hot-path indexes (audit B1, B3).

Run in a subprocess against a real DB — the in-process suite installs a global
sqlite3 fake (via regression_support) that would otherwise intercept these.
"""
import subprocess
import sys
from pathlib import Path
from paths import REPO_ROOT

_REPO = REPO_ROOT


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", script], cwd=str(_REPO),
        capture_output=True, text=True, timeout=30,
    )


def test_job_store_atomic_update_and_indexes(tmp_path):
    db = str(tmp_path / "jobs" / "crm.db")
    script = (
        "import sys; sys.path.insert(0, 'backend')\n"
        "from gateway.jobs import JobStore\n"
        "from data.sqlite.connection import get_connection\n"
        f"db = {db!r}\n"
        "store = JobStore(db_path=db)\n"
        # partial update preserves fields; started_at stamped on running
        "job = store.create('scan', {'x': 1})\n"
        "store.update(job.job_id, status='running', progress=10)\n"
        "r1 = store.get(job.job_id)\n"
        "assert r1.status == 'running' and r1.progress == 10 and r1.started_at\n"
        "store.update(job.job_id, progress=50)\n"  # progress only -> status preserved
        "r2 = store.get(job.job_id)\n"
        "assert r2.status == 'running' and r2.progress == 50\n"
        "store.update(job.job_id, status='succeeded', result={'ok': True})\n"
        "r3 = store.get(job.job_id)\n"
        "assert r3.status == 'succeeded' and r3.result_json == {'ok': True}\n"
        "assert r3.finished_at and r3.started_at == r1.started_at\n"
        # a cancel must survive a later progress-only update (the race fix)
        "c = store.create('scan'); store.request_cancel(c.job_id); store.update(c.job_id, progress=42)\n"
        "assert store.is_cancel_requested(c.job_id) and store.get(c.job_id).progress == 42\n"
        # update of a missing job is a no-op
        "store.update('nope', status='running'); assert store.get('nope') is None\n"
        # hot-path indexes exist
        "names = {r[0] for r in get_connection(db).execute(\"SELECT name FROM sqlite_master WHERE type='index'\").fetchall()}\n"
        "need = ('idx_leads_created_at','idx_leads_status_kind','idx_leads_followup_due_at','idx_leads_feedback','idx_events_job_id','idx_events_ts')\n"
        "assert all(n in names for n in need), sorted(names)\n"
        "print('OK')\n"
    )
    result = _run(script)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
