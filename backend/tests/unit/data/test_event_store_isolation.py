"""Two-tenant isolation for the first scoped store.

This is the shape of the Stage 2 gate ("tenant B sees zero of tenant A's rows").
It runs against a REAL SQLite file in a subprocess, because the in-process suite
installs a global sqlite3 fake and a fake cannot prove isolation.
"""

from __future__ import annotations

import json
import subprocess
import sys

from paths import REPO_ROOT

TENANT_A = "11111111-2222-3333-4444-555555555555"
TENANT_B = "99999999-8888-7777-6666-555555555555"

_SCRIPT = '''
import json, sys
sys.path.insert(0, "backend")
db_path = {db_path!r}

from core.tenancy import TenantContext
from data.sqlite.connection import init_sql
from data.sqlite.event_store import SqliteEventStore

init_sql(db_path)
a = SqliteEventStore(TenantContext({a!r}), db_path)
b = SqliteEventStore(TenantContext({b!r}), db_path)

a.record_event("job-a1", "scanned")
a.record_event("job-a2", "generated")
b.record_event("job-b1", "scanned")

out = {{
    "a_actions": sorted(e["job_id"] for e in a.get_events(limit=50)),
    "b_actions": sorted(e["job_id"] for e in b.get_events(limit=50)),
    "a_filtered_to_b_job": a.get_events(limit=50, job_id="job-b1"),
    "b_filtered_to_a_job": b.get_events(limit=50, job_id="job-a1"),
}}
print("RESULT" + json.dumps(out))
'''


def _run(tmp_path) -> dict:
    script = _SCRIPT.format(db_path=str(tmp_path / "crm.db"), a=TENANT_A, b=TENANT_B)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    line = next(ln for ln in result.stdout.splitlines() if ln.startswith("RESULT"))
    return json.loads(line[len("RESULT"):])


def test_each_tenant_sees_only_its_own_events(tmp_path):
    result = _run(tmp_path)
    assert result["a_actions"] == ["job-a1", "job-a2"]
    assert result["b_actions"] == ["job-b1"]


def test_a_tenant_cannot_reach_another_tenants_row_by_guessing_its_id(tmp_path):
    """Knowing the other tenant's job_id must not be enough."""
    result = _run(tmp_path)
    assert result["a_filtered_to_b_job"] == []
    assert result["b_filtered_to_a_job"] == []


def test_writes_are_attributed_to_the_constructing_tenant(tmp_path):
    """The tenant comes from the constructor, so a write cannot be misattributed."""
    result = _run(tmp_path)
    assert "job-b1" not in result["a_actions"]
    assert "job-a1" not in result["b_actions"]
