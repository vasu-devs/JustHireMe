from __future__ import annotations

import os
import sqlite3
import threading
import weakref
from pathlib import Path
from typing import Any, cast

from core.logging import get_logger
from core.paths import app_data_dir

_log = get_logger(__name__)


def default_base_dir() -> str:
    return str(app_data_dir())


def default_db_path() -> str:
    return os.path.join(default_base_dir(), "crm.db")


BASE_DIR = default_base_dir()
DEFAULT_DB_PATH = default_db_path()
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_POOL_LOCK = threading.RLock()

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


def _resolve_db_path(db_path: str | None = None) -> str:
    if not db_path or db_path == DEFAULT_DB_PATH:
        return default_db_path()
    return db_path


def _ensure_parent(db_path: str) -> None:
    parent = os.path.dirname(db_path)
    if parent:
        Path(parent).mkdir(parents=True, exist_ok=True)


def _configure_connection(conn) -> None:
    row_factory = getattr(sqlite3, "Row", None)
    if row_factory is not None:
        conn.row_factory = row_factory
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")


def _sqlite_connect(db_path: str, *, pooled: bool = False):
    kwargs = {"check_same_thread": False}
    if pooled and hasattr(sqlite3, "Connection"):
        kwargs["factory"] = _PooledConnection
    try:
        return sqlite3.connect(db_path, **kwargs)
    except TypeError:
        return sqlite3.connect(db_path)


class _PooledConnection(sqlite3.Connection if hasattr(sqlite3, "Connection") else object):
    def close(self) -> None:  # type: ignore[override]
        # Repository functions historically call close() in finally blocks.
        # Pooled connections stay open until close_all(), but an open write
        # transaction at close() time means the caller bailed before commit
        # (e.g. raised between execute and commit). Roll it back: otherwise the
        # WAL write lock stays held by this thread and a later unrelated commit
        # on the same pooled connection would persist the half-written changes.
        try:
            if self.in_transaction:
                self.rollback()
        except sqlite3.Error as exc:
            _log.warning("rollback of abandoned sqlite transaction failed: %s", exc)
        return None

    def close_for_pool(self) -> None:
        super().close()


def connect(db_path: str | None = None):
    db_path = _resolve_db_path(db_path)
    _ensure_parent(db_path)
    conn = _sqlite_connect(db_path)
    _configure_connection(conn)
    return conn


class ConnectionPool:
    """One SQLite connection per thread and database path."""

    def __init__(self) -> None:
        self._local = threading.local()
        self._connections: set[Any] = set()
        # Bumped by close_all(). A thread whose cached connections predate the
        # current generation must drop them — otherwise it would hand back a
        # connection close_all() already closed (ProgrammingError).
        self._generation = 0

    def get_connection(self, db_path: str | None = None):
        resolved = _resolve_db_path(db_path)
        _ensure_parent(resolved)
        if getattr(self._local, "generation", None) != self._generation:
            # close_all() ran since this thread last cached anything; its
            # thread-local handles are now closed. Start fresh.
            self._local.connections = {}
            self._local.generation = self._generation
        connections = getattr(self._local, "connections", None)
        if connections is None:
            connections = {}
            self._local.connections = connections
        conn = connections.get(resolved)
        if conn is not None:
            return conn
        conn = _sqlite_connect(resolved, pooled=True)
        _configure_connection(conn)
        connections[resolved] = conn
        with _POOL_LOCK:
            self._connections.add(conn)
        # Reap this connection once its owning thread is gone, so a long-running
        # process doesn't accumulate SQLite handles from dead worker threads.
        # (check_same_thread=False makes the cross-thread close safe.)
        weakref.finalize(threading.current_thread(), self._reap, conn)
        return conn

    def _reap(self, conn) -> None:
        with _POOL_LOCK:
            self._connections.discard(conn)
        try:
            close_for_pool = getattr(conn, "close_for_pool", None)
            (close_for_pool or conn.close)()
        except Exception as exc:
            _log.debug("sqlite pooled connection reap failed: %s", exc)

    def close_all(self) -> None:
        with _POOL_LOCK:
            connections = list(self._connections)
            self._connections.clear()
            # Invalidate every thread's cache: the next get_connection on any
            # thread sees a newer generation and rebuilds instead of returning a
            # now-closed handle.
            self._generation += 1
        for conn in connections:
            try:
                close_for_pool = getattr(conn, "close_for_pool", None)
                if callable(close_for_pool):
                    close_for_pool()
                else:
                    conn.close()
            except Exception as exc:
                _log.debug("sqlite pooled connection close failed: %s", exc)
        if hasattr(self._local, "connections"):
            self._local.connections = {}


_POOL = ConnectionPool()


def get_connection(db_path: str | None = None):
    return _POOL.get_connection(db_path)


def close_all() -> None:
    _POOL.close_all()
    # Tests (and resets) close everything and may swap the database file out
    # from under us; forget the migration memo so init_sql re-checks.
    with _MIGRATED_LOCK:
        _MIGRATED_PATHS.clear()


def prune_history(db_path: str | None = None, *, max_events: int = 5000, max_jobs: int = 500, max_errors: int = 1000) -> None:
    """Cap the append-only telemetry tables to their most recent rows so a
    long-lived local install doesn't accumulate events/jobs/errors forever.
    Each delete is guarded so a not-yet-created table (e.g. gateway_jobs) is
    simply skipped. Active jobs are never pruned."""
    conn = get_connection(db_path)
    prunes = [
        ("DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT ?)", (max_events,)),
        (
            "DELETE FROM gateway_jobs WHERE status IN ('succeeded','failed','cancelled') "
            "AND rowid NOT IN (SELECT rowid FROM gateway_jobs WHERE status IN ('succeeded','failed','cancelled') "
            "ORDER BY created_at DESC LIMIT ?)",
            (max_jobs,),
        ),
        ("DELETE FROM error_log WHERE rowid NOT IN (SELECT rowid FROM error_log ORDER BY last_seen DESC LIMIT ?)", (max_errors,)),
    ]
    for sql, params in prunes:
        try:
            conn.execute(sql, params)
        except Exception as exc:
            _log.debug("history prune skipped: %s", exc)
    conn.commit()


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
            # Only the idempotent re-application of an ALTER ... ADD COLUMN may be
            # safely skipped. Any other failure (incl. a duplicate-column error on
            # a non-ADD-COLUMN statement) is a real migration bug and must surface,
            # rather than being silently masked and the migration marked applied.
            if not ("add column" in statement.lower() and "duplicate column name" in str(exc).lower()):
                raise
            _log.debug("migration %s skipped duplicate column in: %s", name, statement)


def _lock_file(lock_file) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt_module = cast(Any, msvcrt)
        # H2: the lock file is opened "a+", so the cursor sits at EOF. msvcrt
        # locks `nbytes` from the *current* position, so without seek(0) two
        # processes lock different byte offsets and never actually exclude each
        # other. Always lock byte 0.
        lock_file.seek(0)
        msvcrt_module.locking(lock_file.fileno(), msvcrt_module.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(lock_file, fcntl.LOCK_EX)  # type: ignore[attr-defined]


def _unlock_file(lock_file) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt_module = cast(Any, msvcrt)
        # H2: unlock the same byte 0 region that _lock_file locked.
        lock_file.seek(0)
        msvcrt_module.locking(lock_file.fileno(), msvcrt_module.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(lock_file, fcntl.LOCK_UN)  # type: ignore[attr-defined]


def _run_migrations_inner(db_path: str | None = None) -> None:
    db_path = _resolve_db_path(db_path)
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
        applied = {row["name"] if hasattr(row, "keys") else next(iter(row)) for row in rows}

        for path in _migration_files():
            if path.name in applied:
                continue
            _apply_migration(conn, path.name, path.read_text(encoding="utf-8"))
            conn.execute("INSERT OR REPLACE INTO schema_migrations(name) VALUES(?)", (path.name,))

        _ensure_legacy_columns(conn)
        _ensure_indexes(conn)
        conn.commit()
    finally:
        conn.close()


def _ensure_indexes(conn) -> None:
    # Run after _ensure_legacy_columns so kind/feedback/followup_due_at exist.
    # Indexes for the hot lead/event query paths — before this the only index in
    # the schema was on resume_templates, so every filtered/ordered leads query
    # and every per-lead events lookup was a full table scan. All IF NOT EXISTS.
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at);
        CREATE INDEX IF NOT EXISTS idx_leads_status_kind ON leads(status, kind);
        CREATE INDEX IF NOT EXISTS idx_leads_followup_due_at ON leads(followup_due_at);
        CREATE INDEX IF NOT EXISTS idx_leads_feedback ON leads(feedback);
        CREATE INDEX IF NOT EXISTS idx_events_job_id ON events(job_id);
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
        """
    )


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

        CREATE TABLE IF NOT EXISTS error_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            error_type TEXT NOT NULL,
            error_message TEXT,
            source TEXT,
            count INTEGER DEFAULT 1,
            first_seen TEXT DEFAULT (datetime('now')),
            last_seen TEXT DEFAULT (datetime('now'))
        );
        """
    )


def run_migrations(db_path: str | None = None) -> None:
    db_path = _resolve_db_path(db_path)
    _ensure_parent(db_path)
    lock_path = db_path + ".migration.lock"
    Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        locked = False
        try:
            _lock_file(lock_file)
            locked = True
            _run_migrations_inner(db_path)
        finally:
            # Only unlock when the lock was actually acquired: on Windows,
            # unlocking an unheld region raises PermissionError, which would
            # replace the real lock-timeout error.
            if locked:
                _unlock_file(lock_file)


def _ensure_legacy_columns(conn) -> None:
    for col, definition in _LEGACY_LEAD_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {col} {definition}")
        except Exception as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


_MIGRATED_PATHS: set[str] = set()
_MIGRATED_LOCK = threading.Lock()


def init_sql(db_path: str | None = None) -> None:
    # Settings/profile helpers call init_sql on every read; replaying the full
    # migration pass (file lock + 33 ALTER TABLE attempts) each time is pure
    # overhead and widens lock-contention windows. Run once per db path.
    resolved = _resolve_db_path(db_path)
    with _MIGRATED_LOCK:
        if resolved in _MIGRATED_PATHS:
            return
    run_migrations(resolved)
    with _MIGRATED_LOCK:
        _MIGRATED_PATHS.add(resolved)
