from __future__ import annotations

import subprocess
import sys
from pathlib import Path


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


def test_get_connection_reuses_connection_in_same_thread(tmp_path):
    db_path = str(tmp_path / "pool.db")
    run_script(
        "import sys;"
        "sys.path.insert(0, 'backend');"
        "from data.sqlite.connection import close_all, get_connection, init_sql;"
        f"db_path = {db_path!r};"
        "init_sql(db_path);"
        "a = get_connection(db_path);"
        "b = get_connection(db_path);"
        "assert a is b;"
        "close_all();"
    )


def test_get_connection_uses_distinct_connections_across_threads(tmp_path):
    db_path = str(tmp_path / "pool.db")
    run_script(
        "\n".join([
            "import sys, threading",
            "sys.path.insert(0, 'backend')",
            "from data.sqlite.connection import close_all, get_connection, init_sql",
            f"db_path = {db_path!r}",
            "init_sql(db_path)",
            "seen = []",
            "def worker():",
            "    seen.append(id(get_connection(db_path)))",
            "threads = [threading.Thread(target=worker), threading.Thread(target=worker)]",
            "[t.start() for t in threads]",
            "[t.join() for t in threads]",
            "assert len(set(seen)) == 2",
            "close_all()",
        ])
    )


def test_lead_row_dict_uses_column_names_not_select_order(tmp_path):
    db_path = str(tmp_path / "leads.db")
    run_script(
        "import sys;"
        "sys.path.insert(0, 'backend');"
        "from data.sqlite.connection import close_all, get_connection, init_sql;"
        "from data.sqlite.leads import LEAD_COLUMN_NAMES, lead_row_dict, save_lead;"
        f"db_path = {db_path!r};"
        "init_sql(db_path);"
        "save_lead({'job_id':'job-1','title':'Backend Engineer','company':'Acme','url':'https://example.com/job','platform':'manual','description':'Build APIs'}, db_path);"
        "conn = get_connection(db_path);"
        "columns = list(LEAD_COLUMN_NAMES);"
        "columns[1], columns[2] = columns[2], columns[1];"
        "row = conn.execute(f\"SELECT {','.join(columns)} FROM leads WHERE job_id='job-1'\").fetchone();"
        "lead = lead_row_dict(row);"
        "assert lead['title'] == 'Backend Engineer';"
        "assert lead['company'] == 'Acme';"
        "close_all();"
    )
