"""Data maintenance: destructive local-data reset.

`reset_all_data` clears the CRM/leads, the profile knowledge graph, the vector
tables, and generated documents — leaving the schemas intact so the app keeps
working and lands back in a clean, first-run-like state. (The non-destructive
stored-lead repair lives in ``discovery.maintenance`` — it re-runs discovery's
parsers, and ``data`` must not import ``discovery``.)

By default it PRESERVES settings (LLM provider, API keys, preferences) and
saved resume templates, so a reset leaves the app immediately usable. Pass
``clear_settings=True`` for a full factory reset that also wipes those.

Everything is local and per-store best-effort: a failure clearing one store is
recorded in the summary and never aborts the others.
"""

from __future__ import annotations

import os

from core.logging import get_logger
from core.paths import app_data_path

_log = get_logger(__name__)

# Node tables created by data/graph/connection.py. Cleared with DETACH DELETE so
# their relationships go too, while the table schema itself stays.
_GRAPH_NODE_TABLES = (
    "Candidate",
    "Skill",
    "Project",
    "Experience",
    "Certification",
    "Education",
    "Achievement",
    "JobLead",
)

# SQLite tables that hold schema/config rather than user data.
_SQLITE_ALWAYS_PRESERVE = {"schema_migrations", "sqlite_sequence"}
# Preserved on a data-only reset; cleared on a full (clear_settings) reset.
_SQLITE_SETTINGS_TABLES = {"settings", "resume_templates"}


def _reset_sqlite(summary: dict, *, clear_settings: bool) -> None:
    from data.sqlite.connection import get_connection

    preserve = set(_SQLITE_ALWAYS_PRESERVE)
    if not clear_settings:
        preserve |= _SQLITE_SETTINGS_TABLES

    conn = get_connection()
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    except Exception as exc:
        summary["errors"].append(f"sqlite list tables: {exc}")
        return
    for row in rows:
        name = row["name"] if hasattr(row, "keys") else row[0]
        if name in preserve or str(name).startswith("sqlite_"):
            continue
        try:
            conn.execute(f"DELETE FROM {name}")  # noqa: S608 - name is from sqlite_master, not user input
            summary["sqlite_cleared"].append(name)
        except Exception as exc:
            summary["errors"].append(f"sqlite {name}: {exc}")

    # The profile snapshot + identity fields live in the `settings` table but are
    # profile DATA, not preferences. They MUST be cleared even on a data-only reset
    # (settings preserved) — otherwise get_profile() returns the cached snapshot and
    # the profile still shows full. (On a full reset the whole table is gone already.)
    if "settings" in preserve:
        try:
            from data.graph.profile_base import IDENTITY_KEYS, PROFILE_SNAPSHOT_KEY

            profile_keys = (PROFILE_SNAPSHOT_KEY, *IDENTITY_KEYS)
            placeholders = ",".join("?" for _ in profile_keys)
            conn.execute(f"DELETE FROM settings WHERE key IN ({placeholders})", profile_keys)
            summary["sqlite_cleared"].append("settings:profile")
        except Exception as exc:
            summary["errors"].append(f"sqlite profile keys: {exc}")

    try:
        conn.commit()
    except Exception as exc:
        summary["errors"].append(f"sqlite commit: {exc}")


def _reset_graph(summary: dict) -> None:
    try:
        from data.graph.connection import execute_query, init_graph
    except Exception as exc:
        summary["errors"].append(f"graph import: {exc}")
        return
    for table in _GRAPH_NODE_TABLES:
        try:
            execute_query(f"MATCH (n:{table}) DETACH DELETE n")
            summary["graph_cleared"].append(table)
        except Exception as exc:
            # A not-yet-created table simply has nothing to clear.
            summary["errors"].append(f"graph {table}: {exc}")
    try:
        init_graph()  # re-ensure the (now empty) schema exists
    except Exception as exc:
        summary["errors"].append(f"graph init: {exc}")


def _reset_vectors(summary: dict) -> None:
    try:
        # Use the canonical helper, not vec.list_tables() directly: lancedb returns
        # a ListTablesResponse object that iterates into (key, value) tuples rather
        # than table-name strings. vec_table_names() normalizes it to list[str].
        from data.graph.profile_vectors import vec_table_names
        from data.vector.connection import vec

        for name in list(vec_table_names() or []):
            try:
                vec.drop_table(name)
                summary["vectors_dropped"].append(name)
            except Exception as exc:
                summary["errors"].append(f"vector {name}: {exc}")
    except Exception as exc:
        # NullVectorStore / unavailable runtime — nothing persisted, nothing to do.
        summary["errors"].append(f"vector store: {exc}")


def _reset_assets(summary: dict) -> None:
    assets_dir = str(app_data_path("assets"))
    if not os.path.isdir(assets_dir):
        return
    for entry in os.listdir(assets_dir):
        path = os.path.join(assets_dir, entry)
        try:
            if os.path.isfile(path):
                os.remove(path)
                summary["assets_removed"] += 1
        except Exception as exc:
            summary["errors"].append(f"asset {entry}: {exc}")


def reset_all_data(*, clear_settings: bool = False) -> dict:
    """Wipe local user data. Returns a per-store summary of what was cleared."""
    summary: dict = {
        "sqlite_cleared": [],
        "graph_cleared": [],
        "vectors_dropped": [],
        "assets_removed": 0,
        "settings_cleared": clear_settings,
        "errors": [],
    }

    _reset_sqlite(summary, clear_settings=clear_settings)
    _reset_graph(summary)
    _reset_vectors(summary)
    _reset_assets(summary)

    _log.info(
        "data reset: sqlite=%s graph=%s vectors=%s assets=%s settings_cleared=%s errors=%s",
        len(summary["sqlite_cleared"]),
        len(summary["graph_cleared"]),
        len(summary["vectors_dropped"]),
        summary["assets_removed"],
        clear_settings,
        len(summary["errors"]),
    )
    return summary
