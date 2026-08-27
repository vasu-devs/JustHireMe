"""The unscoped-query gate — Stage 2's first and most important test.

One missed scope check leaks one candidate's CV to another. That is a
confidentiality bug, not a correctness bug, so it gets a build-breaking gate
*before* the migration starts rather than a code review after it.

**How this works as a ratchet.** Every SQL statement in ``data/`` that touches a
tenant-owned table is either *scoped* (carries a ``tenant_id`` predicate) or not.
Today none are, because the columns do not exist yet. ``BASELINE`` records the
current per-file count of unscoped statements. The test fails if:

  * any file's unscoped count **grows** (a regression, blocked immediately), or
  * a **new** file starts issuing unscoped queries, or
  * a file's count **drops below** its baseline without the baseline being
    tightened (keeps the ratchet honest instead of quietly slack).

So the number can only go down, and it must reach zero before the hosted build
ships. See ``docs/LAYERS.md`` and ``private/WEB_MIGRATION_LLD.md`` §A1.
"""

from __future__ import annotations

import ast
import re

from paths import BACKEND_ROOT

#: Tables owned by a tenant. `schema_migrations` is deliberately absent: schema
#: version is global infrastructure, not user data.
TENANT_TABLES = frozenset({
    "leads",
    "events",
    "settings",
    "metrics",
    "error_log",
    "resume_templates",
    "gateway_jobs",
})

GLOBAL_TABLES = frozenset({"schema_migrations"})

#: Unscoped statements per file, as of the Stage 2 starting line.
#: **This dict may only ever shrink.**
BASELINE: dict[str, int] = {
    # data/sqlite/events.py reached 0 via SqliteEventStore - the reference pattern.
    "data/sqlite/leads.py": 37,
    "data/sqlite/resume_templates.py": 14,
    "data/sqlite/connection.py": 3,
    "data/sqlite/settings.py": 3,
    "data/maintenance.py": 1,
}

_STATEMENT_RE = re.compile(r"\b(select|insert|update|delete)\b", re.I)
_TABLE_RE = re.compile(r"\b(?:from|into|update|join)\s+([a-z_]+)", re.I)
#: What counts as scoping: the predicate or the column, in any casing.
_SCOPED_RE = re.compile(r"\btenant_id\b", re.I)


def _sql_literals(path) -> list[str]:
    """Every string literal in the module that looks like SQL."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _STATEMENT_RE.search(node.value)
    ]


def _tenant_tables_in(sql: str) -> set[str]:
    return {match.group(1).lower() for match in _TABLE_RE.finditer(sql)} & TENANT_TABLES


def _unscoped_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted((BACKEND_ROOT / "data").rglob("*.py")):
        rel = path.relative_to(BACKEND_ROOT).as_posix()
        unscoped = sum(
            1
            for sql in _sql_literals(path)
            if _tenant_tables_in(sql) and not _SCOPED_RE.search(sql)
        )
        if unscoped:
            counts[rel] = unscoped
    return counts


def test_no_new_unscoped_queries_are_introduced():
    """The ratchet. Adding an unscoped query to a tenant table fails the build."""
    actual = _unscoped_counts()

    regressions = [
        f"{path}: {count} unscoped (baseline {BASELINE.get(path, 0)})"
        for path, count in sorted(actual.items())
        if count > BASELINE.get(path, 0)
    ]

    assert not regressions, (
        "new unscoped queries against tenant-owned tables:\n  "
        + "\n  ".join(regressions)
        + "\n\nScope the query by tenant_id, or route it through a tenant-scoped "
          "repository. Do NOT raise the baseline."
    )


def test_the_baseline_is_tightened_as_queries_get_scoped():
    """Stops the ratchet going slack once the migration starts paying off."""
    actual = _unscoped_counts()
    stale = [
        f"{path}: baseline says {baseline}, actual is {actual.get(path, 0)}"
        for path, baseline in sorted(BASELINE.items())
        if actual.get(path, 0) < baseline
    ]

    assert not stale, (
        "these files have fewer unscoped queries than the baseline claims - "
        "lower BASELINE to lock the win in:\n  " + "\n  ".join(stale)
    )


def test_the_baseline_only_lists_files_that_still_need_work():
    unknown = sorted(set(BASELINE) - set(_unscoped_counts()))
    assert not unknown, (
        f"these files are fully scoped now - remove them from BASELINE: {unknown}"
    )


def test_global_tables_are_not_treated_as_tenant_owned():
    """schema_migrations must stay global; scoping it would break migrations."""
    assert not (TENANT_TABLES & GLOBAL_TABLES)


def test_the_detector_recognises_a_scoped_statement():
    """Guards the gate itself: a detector that never fires protects nothing."""
    assert _tenant_tables_in("SELECT * FROM leads WHERE job_id = ?") == {"leads"}
    assert _SCOPED_RE.search("SELECT * FROM leads WHERE tenant_id = ? AND job_id = ?")
    assert not _SCOPED_RE.search("SELECT * FROM leads WHERE job_id = ?")


def test_the_detector_ignores_global_tables():
    assert _tenant_tables_in("SELECT version FROM schema_migrations") == set()
