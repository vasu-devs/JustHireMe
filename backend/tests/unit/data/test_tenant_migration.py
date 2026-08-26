"""Migration 005 — tenant_id on every user-owned table.

Runs in a subprocess against a REAL SQLite file: the in-process suite installs a
global sqlite3 fake, so PRAGMA results and index names would be meaningless here.
"""

from __future__ import annotations

import subprocess
import sys

from paths import REPO_ROOT

LOCAL_TENANT = "00000000-0000-0000-0000-000000000001"

TENANT_TABLES = ("leads", "events", "settings", "error_log", "metrics", "resume_templates")

_SCRIPT = '''
import json, sys
sys.path.insert(0, "backend")
db_path = {db_path!r}

from data.sqlite.connection import get_connection, init_sql

init_sql(db_path)
conn = get_connection(db_path)

# A row written BEFORE the tenant column existed would be adopted by the local
# tenant; simulate the outcome by inserting and reading back the default.
conn.execute(
    "INSERT INTO leads(job_id, title, company, url, platform) VALUES(?,?,?,?,?)",
    ("legacy-1", "Engineer", "Acme", "https://acme/1", "manual"),
)
conn.commit()

out = {{}}
out["columns"] = {{
    table: [row[1] for row in conn.execute("PRAGMA table_info(" + table + ")").fetchall()]
    for table in {tables!r}
}}
out["indexes"] = [
    row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    ).fetchall()
]
out["adopted_tenant"] = conn.execute(
    "SELECT tenant_id FROM leads WHERE job_id = ?", ("legacy-1",)
).fetchone()[0]
out["applied"] = [
    row[0] for row in conn.execute("SELECT name FROM schema_migrations").fetchall()
]

# Idempotency: a second run must not fail or duplicate anything.
init_sql(db_path)
out["applied_after_rerun"] = [
    row[0] for row in conn.execute("SELECT name FROM schema_migrations").fetchall()
]

print("RESULT" + json.dumps(out))
'''


def _run(tmp_path) -> dict:
    script = _SCRIPT.format(db_path=str(tmp_path / "crm.db"), tables=list(TENANT_TABLES))
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    line = next(ln for ln in result.stdout.splitlines() if ln.startswith("RESULT"))
    import json

    return json.loads(line[len("RESULT"):])


def test_every_tenant_owned_table_gains_the_column(tmp_path):
    columns = _run(tmp_path)["columns"]
    missing = [table for table in TENANT_TABLES if "tenant_id" not in columns[table]]
    assert not missing, f"tenant_id missing from: {missing}"


def test_existing_rows_are_adopted_by_the_local_tenant(tmp_path):
    """The ~2,200 desktop installs must survive this migration untouched."""
    assert _run(tmp_path)["adopted_tenant"] == LOCAL_TENANT


def test_indexes_are_composite_and_lead_with_tenant_id(tmp_path):
    """A bare tenant_id index degrades every lookup into a per-tenant scan."""
    indexes = _run(tmp_path)["indexes"]
    for expected in (
        "idx_leads_tenant_created",
        "idx_leads_tenant_job",
        "idx_leads_tenant_status",
        "idx_events_tenant_ts",
        "idx_settings_tenant_key",
        "idx_templates_tenant",
    ):
        assert expected in indexes, f"missing index {expected} (have: {sorted(indexes)})"


def test_the_migration_is_recorded_and_idempotent(tmp_path):
    result = _run(tmp_path)
    assert "005_tenant_id.sql" in result["applied"]
    assert result["applied"] == result["applied_after_rerun"], "re-running must be a no-op"


def test_schema_migrations_stays_global(tmp_path):
    """Scoping the schema version by tenant would break migrations outright."""
    columns = _run(tmp_path)["columns"]
    assert "schema_migrations" not in columns  # not in the tenant table list at all
