from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from core.logging import get_logger

_log = get_logger(__name__)

BASE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "JustHireMe")
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "crm.db")
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_LEGACY_LEAD_COLUMNS = [
    ("score", "INTEGER DEFAULT 0"),
    ("reason", "TEXT DEFAULT ''"),
    ("match_points", "TEXT DEFAULT ''"),
    ("asset_path", "TEXT DEFAULT ''"),
    ("cover_letter_path", "TEXT DEFAULT ''"),
    ("selected_projects", "TEXT DEFAULT ''"),
    ("description", "TEXT DEFAULT ''"),
    ("gaps", "TEXT DEFAULT ''"),
    ("kind", "TEXT DEFAULT 'job'"),
    ("budget", "TEXT DEFAULT ''"),
    ("signal_score", "INTEGER DEFAULT 0"),
    ("signal_reason", "TEXT DEFAULT ''"),
    ("signal_tags", "TEXT DEFAULT ''"),
    ("outreach_reply", "TEXT DEFAULT ''"),
    ("outreach_dm", "TEXT DEFAULT ''"),
    ("source_meta", "TEXT DEFAULT ''"),
    ("feedback", "TEXT DEFAULT ''"),
    ("feedback_note", "TEXT DEFAULT ''"),
    ("followup_due_at", "TEXT DEFAULT ''"),
    ("last_contacted_at", "TEXT DEFAULT ''"),
    ("outreach_email", "TEXT DEFAULT ''"),
    ("proposal_draft", "TEXT DEFAULT ''"),
    ("fit_bullets", "TEXT DEFAULT ''"),
    ("followup_sequence", "TEXT DEFAULT ''"),
    ("proof_snippet", "TEXT DEFAULT ''"),
    ("tech_stack", "TEXT DEFAULT ''"),
    ("location", "TEXT DEFAULT ''"),
    ("urgency", "TEXT DEFAULT ''"),
    ("base_signal_score", "INTEGER DEFAULT 0"),
    ("learning_delta", "INTEGER DEFAULT 0"),
    ("learning_reason", "TEXT DEFAULT ''"),
    ("resume_version", "INTEGER DEFAULT 0"),
]


def connect(db_path: str = DEFAULT_DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_parent(db_path: str) -> None:
    parent = os.path.dirname(db_path)
    if parent:
        Path(parent).mkdir(parents=True, exist_ok=True)


def _migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def _split_sql_script(script: str) -> list[str]:
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def _apply_migration(conn, name: str, script: str) -> None:
    try:
        conn.executescript(script)
        return
    except Exception as exc:
        if "duplicate column name" not in str(exc).lower():
            raise

    for statement in _split_sql_script(script):
        try:
            conn.execute(statement)
        except Exception as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
            _log.debug("migration %s skipped duplicate column in: %s", name, statement)


def _lock_file(lock_file) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(lock_file, fcntl.LOCK_EX)


def _unlock_file(lock_file) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(lock_file, fcntl.LOCK_UN)


def _run_migrations_inner(db_path: str = DEFAULT_DB_PATH) -> None:
    conn = connect(db_path)
    try:
        _ensure_core_tables(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations(
                name TEXT PRIMARY KEY,
                applied_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        rows = conn.execute("SELECT name FROM schema_migrations").fetchall()
        applied = {row[0] for row in rows}

        for path in _migration_files():
            if path.name in applied:
                continue
            _apply_migration(conn, path.name, path.read_text(encoding="utf-8"))
            conn.execute("INSERT OR REPLACE INTO schema_migrations(name) VALUES(?)", (path.name,))

        _ensure_legacy_columns(conn)
        conn.commit()
    finally:
        conn.close()


def _ensure_core_tables(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS leads(
            job_id TEXT PRIMARY KEY,
            title TEXT,
            company TEXT,
            url TEXT,
            platform TEXT,
            status TEXT DEFAULT 'discovered',
            score INTEGER DEFAULT 0,
            reason TEXT DEFAULT '',
            match_points TEXT DEFAULT '',
            asset_path TEXT DEFAULT '',
            cover_letter_path TEXT DEFAULT '',
            selected_projects TEXT DEFAULT '',
            description TEXT DEFAULT '',
            gaps TEXT DEFAULT '',
            resume_version INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT,
            action TEXT,
            ts TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            val TEXT
        );
        """
    )


def run_migrations(db_path: str = DEFAULT_DB_PATH) -> None:
    _ensure_parent(db_path)
    lock_path = db_path + ".migration.lock"
    Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        try:
            _lock_file(lock_file)
            _run_migrations_inner(db_path)
        finally:
            _unlock_file(lock_file)


def _ensure_legacy_columns(conn) -> None:
    for col, definition in _LEGACY_LEAD_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {col} {definition}")
        except Exception as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def init_sql(db_path: str = DEFAULT_DB_PATH) -> None:
    run_migrations(db_path)
