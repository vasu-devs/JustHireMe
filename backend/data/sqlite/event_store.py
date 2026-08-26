"""Tenant-scoped SQLite adapter for the activity log.

**This is the reference implementation for Stage 2.** Every other store follows
this shape:

  * the tenant arrives in ``__init__`` and is stored on the instance, so no
    method takes it and no caller can supply a different one;
  * every statement carries ``tenant_id = ?`` and every write supplies it;
  * the module-level functions stay as a thin back-compat shim so the desktop
    app and the existing tests keep working while the migration proceeds.

Postgres RLS will make the predicate redundant later. It stays anyway: RLS is
the backstop for when this layer has a bug, not a replacement for it.
"""

from __future__ import annotations

from core.tenancy import LOCAL_TENANT, TenantContext
from data.sqlite.connection import DEFAULT_DB_PATH, get_connection


class SqliteEventStore:
    """Implements ``ports.EventStore`` for one tenant."""

    def __init__(self, tenant: TenantContext = LOCAL_TENANT, db_path: str = DEFAULT_DB_PATH) -> None:
        self._tenant = tenant
        self._db_path = db_path

    def record_event(self, job_id: str | None, action: str) -> None:
        conn = get_connection(self._db_path)
        try:
            conn.execute(
                "INSERT INTO events(tenant_id, job_id, action) VALUES(?,?,?)",
                (
                    self._tenant.tenant_id,
                    (job_id or "__system__")[:160],
                    str(action or "")[:1000],
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_events(self, limit: int = 50, job_id: str | None = None) -> list[dict]:
        conn = get_connection(self._db_path)
        try:
            if job_id:
                rows = conn.execute(
                    "SELECT job_id, action, ts FROM events "
                    "WHERE tenant_id = ? AND job_id = ? ORDER BY ts DESC LIMIT ?",
                    (self._tenant.tenant_id, job_id, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT job_id, action, ts FROM events "
                    "WHERE tenant_id = ? ORDER BY ts DESC LIMIT ?",
                    (self._tenant.tenant_id, int(limit)),
                ).fetchall()
        finally:
            conn.close()
        return [{"job_id": row["job_id"], "action": row["action"], "ts": row["ts"]} for row in rows]


def create_event_store(
    tenant: TenantContext = LOCAL_TENANT, db_path: str = DEFAULT_DB_PATH
) -> SqliteEventStore:
    return SqliteEventStore(tenant, db_path)
