from __future__ import annotations
import logging

import os
import threading

from core.logging import get_logger

_log = get_logger(__name__)

try:
    import lancedb
except Exception as exc:
    logging.getLogger(__name__).warning('suppressed exception in backend/data/vector/connection.py:<module>: %s', exc)
    lancedb = None
    _LANCEDB_IMPORT_ERROR = str(exc)
else:
    _LANCEDB_IMPORT_ERROR = ""

def default_base_dir() -> str:
    root = os.environ.get("JHM_APP_DATA_DIR") or os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    return os.path.join(root, "JustHireMe")


def default_vector_dir() -> str:
    return os.path.join(default_base_dir(), "vector")


BASE_DIR = default_base_dir()
VECTOR_DIR = default_vector_dir()
# STABILITY: thread-safe vector store reconnect/status
_vector_lock = threading.RLock()


class NullVectorStore:
    """No-op vector store so profile CRUD never fails because embeddings are unavailable."""

    available = False

    def __init__(self, reason: str = ""):
        self.reason = reason

    def list_tables(self):
        return []

    def create_table(self, *_args, **_kwargs):
        return None

    def open_table(self, *_args, **_kwargs):
        return self

    def add(self, *_args, **_kwargs):
        return None


def _connect_vector_store():
    global BASE_DIR, VECTOR_DIR
    with _vector_lock:
        BASE_DIR = default_base_dir()
        VECTOR_DIR = default_vector_dir()
        os.makedirs(VECTOR_DIR, exist_ok=True)
        if lancedb is None:
            raise RuntimeError(_LANCEDB_IMPORT_ERROR or "LanceDB is not available")
        return lancedb.connect(VECTOR_DIR)


def vector_status() -> dict:
    with _vector_lock:
        if getattr(vec, "available", True) is False:
            return {
                "status": "unavailable",
                "error": getattr(vec, "reason", "") or "vector store is unavailable",
                "tables": [],
            }
        try:
            return {"status": "ok", "tables": list(vec.list_tables() or [])}
        except Exception as exc:
            _log.warning("vector store status check failed: %s", exc)
            return {"status": "degraded", "error": str(exc), "tables": []}


try:
    vec = _connect_vector_store()
except Exception as exc:
    if lancedb is None:
        _log.info("vector store disabled: %s", exc)
    else:
        _log.warning("vector store disabled: %s", exc)
    vec = NullVectorStore(str(exc))
