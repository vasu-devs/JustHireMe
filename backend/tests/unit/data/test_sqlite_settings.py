import subprocess
import sys

from paths import REPO_ROOT


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
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
