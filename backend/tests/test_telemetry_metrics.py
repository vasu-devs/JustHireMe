"""Metrics telemetry round-trips through a real SQLite DB.

These assert against real ``data.sqlite`` behavior, so they run in a subprocess
with an isolated ``JHM_APP_DATA_DIR`` — the test suite's global ``sqlite3`` fake
(``regression_support``) would otherwise poison the connection. See
``test_sqlite_settings.py`` for the same pattern.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(script: str, tmp_path) -> subprocess.CompletedProcess:
    env = dict(os.environ, JHM_APP_DATA_DIR=str(tmp_path))
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_counters_and_state_roundtrip(tmp_path):
    script = (
        "import sys; sys.path.insert(0, 'backend');"
        "from core.telemetry import record_metric, incr_metrics, set_metric_state, get_metrics, get_metric_state;"
        "record_metric('scans_run');"
        "record_metric('scans_run', 2);"                      # counters accumulate
        "incr_metrics({'leads_found': 5, 'leads_saved': 3});"  # batch increment
        "set_metric_state('last_scan', {'new_leads': 3, 'by_source': {'hn': 2}});"
        "m = get_metrics();"
        "assert m.get('scans_run') == 3, m;"
        "assert m.get('leads_found') == 5, m;"
        "assert m.get('leads_saved') == 3, m;"
        "s = get_metric_state('last_scan');"
        "assert s['new_leads'] == 3, s;"
        "assert s['by_source'] == {'hn': 2}, s;"
        "print('ROUNDTRIP_OK')"
    )
    result = _run(script, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "ROUNDTRIP_OK" in result.stdout


def test_state_snapshot_is_redacted(tmp_path):
    # A scan summary carries URLs/company text; a stray secret must not persist.
    script = (
        "import sys; sys.path.insert(0, 'backend');"
        "from core.telemetry import set_metric_state, get_metric_state;"
        "set_metric_state('leak', {'note': 'token=sk-abcdefghijklmnop1234567890'});"
        "s = get_metric_state('leak');"
        "assert 'sk-abcdefghijklmnop' not in s['note'], s;"
        "print('REDACT_OK')"
    )
    result = _run(script, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "REDACT_OK" in result.stdout


def test_empty_on_fresh_db(tmp_path):
    script = (
        "import sys; sys.path.insert(0, 'backend');"
        "from core.telemetry import get_metrics, get_metric_state;"
        "assert get_metrics() == {}, get_metrics();"
        "assert get_metric_state('nope') == {}, get_metric_state('nope');"
        "print('EMPTY_OK')"
    )
    result = _run(script, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "EMPTY_OK" in result.stdout
