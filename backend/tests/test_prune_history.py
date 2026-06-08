"""History retention prune for the append-only telemetry tables (audit C5)."""
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", script], cwd=str(_REPO),
        capture_output=True, text=True, timeout=30,
    )


def test_prune_caps_events_and_keeps_active_jobs(tmp_path):
    db = str(tmp_path / "p" / "crm.db")
    script = (
        "import sys; sys.path.insert(0, 'backend')\n"
        "from data.sqlite.connection import init_sql, get_connection, prune_history\n"
        "from gateway.jobs import JobStore\n"
        f"db = {db!r}\n"
        "init_sql(db)\n"
        "c = get_connection(db)\n"
        # 20 events; prune to 5 -> keep the most recent (highest id)
        "c.executemany('INSERT INTO events(job_id, action) VALUES(?, ?)', [('j', str(i)) for i in range(20)]); c.commit()\n"
        # 8 terminal jobs + 1 still running
        "store = JobStore(db_path=db)\n"
        "for _ in range(8):\n"
        "    j = store.create('scan'); store.update(j.job_id, status='succeeded')\n"
        "run = store.create('scan'); store.update(run.job_id, status='running')\n"
        "prune_history(db, max_events=5, max_jobs=3, max_errors=5)\n"
        # events capped to the 5 newest
        "assert c.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 5\n"
        "kept = [r[0] for r in c.execute('SELECT action FROM events ORDER BY id').fetchall()]\n"
        "assert kept == ['15','16','17','18','19'], kept\n"
        # 3 most-recent terminal jobs + the running one survive (4 total)
        "assert c.execute('SELECT COUNT(*) FROM gateway_jobs').fetchone()[0] == 4\n"
        "assert store.get(run.job_id) is not None\n"
        "print('OK')\n"
    )
    r = _run(script)
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout
