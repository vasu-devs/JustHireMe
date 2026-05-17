from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from data.sqlite.settings import validate_setting


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_script(script: str):
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_invalid_integer_setting_rejects_text():
    ok, message = validate_setting("x_max_requests_per_scan", "banana")
    assert not ok
    assert "must be a number" in message


def test_invalid_integer_setting_rejects_out_of_range():
    ok, message = validate_setting("x_max_requests_per_scan", "999")
    assert not ok
    assert "between 1 and 50" in message


def test_valid_integer_setting_saves(tmp_path):
    db_path = str(tmp_path / "settings.db")
    run_script(
        "import sys;"
        "sys.path.insert(0, 'backend');"
        "from data.sqlite.connection import close_all;"
        "from data.sqlite.settings import get_settings, save_settings;"
        f"db_path = {db_path!r};"
        "save_settings({'x_max_requests_per_scan': '10'}, db_path);"
        "assert get_settings(db_path)['x_max_requests_per_scan'] == '10';"
        "close_all();"
    )


def test_unknown_setting_keys_remain_forward_compatible(tmp_path):
    db_path = str(tmp_path / "settings.db")
    run_script(
        "import sys;"
        "sys.path.insert(0, 'backend');"
        "from data.sqlite.connection import close_all;"
        "from data.sqlite.settings import get_settings, save_settings;"
        f"db_path = {db_path!r};"
        "save_settings({'future_setting': 'anything'}, db_path);"
        "assert get_settings(db_path)['future_setting'] == 'anything';"
        "close_all();"
    )


def test_invalid_setting_payload_raises(tmp_path):
    db_path = str(tmp_path / "settings.db")
    script = (
        "import sys;"
        "sys.path.insert(0, 'backend');"
        "from data.sqlite.settings import save_settings;"
        f"db_path = {db_path!r};"
        "save_settings({'board_scan_batch_size': '99'}, db_path);"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "between 1 and 12" in result.stderr
