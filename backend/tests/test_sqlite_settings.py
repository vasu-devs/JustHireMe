import subprocess
import sys


def test_settings_save_bootstraps_fresh_database(tmp_path):
    db_path = str(tmp_path / "fresh" / "crm.db")
    script = (
        "import sys;"
        "sys.path.insert(0, 'backend');"
        "from data.sqlite.settings import get_settings, save_settings;"
        f"db_path = {db_path!r};"
        "save_settings({'email': 'jane@example.com'}, db_path);"
        "assert get_settings(db_path)['email'] == 'jane@example.com'"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[2]),
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
