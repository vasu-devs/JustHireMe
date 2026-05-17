from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_record_error_aggregates_recent_duplicates(tmp_path):
    script = (
        "import os, sys;"
        "sys.path.insert(0, 'backend');"
        f"os.environ['JHM_APP_DATA_DIR'] = {str(tmp_path)!r};"
        f"os.environ['LOCALAPPDATA'] = {str(tmp_path)!r};"
        "from core.telemetry import get_error_count, get_top_errors, record_error;"
        "from data.sqlite.connection import close_all, init_sql;"
        "init_sql();"
        "record_error('llm_timeout', 'timeout one', 'ranking.evaluator');"
        "record_error('llm_timeout', 'timeout two', 'ranking.evaluator');"
        "rows = get_top_errors();"
        "assert rows and rows[0]['error_type'] == 'llm_timeout';"
        "assert rows[0]['count'] == 2;"
        "assert get_error_count(24) >= 2;"
        "close_all();"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
