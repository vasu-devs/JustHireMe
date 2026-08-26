"""Back-compat shim over the tenant-scoped event store.

The SQL now lives in ``event_store.SqliteEventStore``, which carries a
``TenantContext``. These module functions remain so the desktop build (single
tenant) and existing call sites keep working unchanged; they resolve to the
local tenant. The hosted build constructs the store with a real tenant instead
and never comes through here.
"""

from __future__ import annotations

from core.tenancy import LOCAL_TENANT
from data.sqlite.connection import DEFAULT_DB_PATH
from data.sqlite.event_store import SqliteEventStore, create_event_store

__all__ = ["SqliteEventStore", "create_event_store", "get_events", "record_event"]


def record_event(job_id: str | None, action: str, db_path: str = DEFAULT_DB_PATH) -> None:
    SqliteEventStore(LOCAL_TENANT, db_path).record_event(job_id, action)


def get_events(limit: int = 50, job_id: str | None = None, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    return SqliteEventStore(LOCAL_TENANT, db_path).get_events(limit, job_id)
