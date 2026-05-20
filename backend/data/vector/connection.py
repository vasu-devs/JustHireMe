from __future__ import annotations
import importlib
import logging

import os
import sys
import threading

from core.logging import get_logger
from data.vector.runtime import add_vector_runtime_to_path, vector_runtime_ready, vector_runtime_roots

_log = get_logger(__name__)
lancedb = None
_LANCEDB_IMPORT_ERROR = ""
_LANCEDB_RESTART_REQUIRED = False
PYO3_RESTART_MESSAGE = "Runtime pack is installed. Restart JustHireMe to finish loading vector search."


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


def _usable_lancedb_module(module) -> bool:
    return module is not None and callable(getattr(module, "connect", None))


def _clear_lancedb_modules() -> None:
    for name in list(sys.modules):
        if name == "lancedb" or name.startswith("lancedb."):
            sys.modules.pop(name, None)


def _runtime_package_installed() -> bool:
    return any((root / "lancedb" / "__init__.py").exists() for root in vector_runtime_roots())


def _is_pyo3_reinit_error(exc: BaseException) -> bool:
    """Detect the PyO3 'may only be initialized once per interpreter process' error."""
    return "initialized once per interpreter" in str(exc).lower()


def _set_lancedb_module(module):
    global lancedb, _LANCEDB_IMPORT_ERROR, _LANCEDB_RESTART_REQUIRED
    lancedb = module
    _LANCEDB_IMPORT_ERROR = ""
    _LANCEDB_RESTART_REQUIRED = False
    return module


def _try_import_lancedb(*, log_warning: bool = True):
    global lancedb, _LANCEDB_IMPORT_ERROR, _LANCEDB_RESTART_REQUIRED
    if _usable_lancedb_module(lancedb):
        _LANCEDB_IMPORT_ERROR = ""
        _LANCEDB_RESTART_REQUIRED = False
        return lancedb
    add_vector_runtime_to_path()
    importlib.invalidate_caches()
    if getattr(sys, "frozen", False) and not _runtime_package_installed():
        _clear_lancedb_modules()
        lancedb = None
        _LANCEDB_IMPORT_ERROR = "LanceDB runtime is not installed"
        _LANCEDB_RESTART_REQUIRED = False
        return None
    if not _usable_lancedb_module(sys.modules.get("lancedb")):
        _clear_lancedb_modules()
    try:
        module = importlib.import_module("lancedb")
    except Exception as exc:
        # PyO3 native extensions can only be initialized once per process.
        # If this is a reinit error, a module may already be loaded and usable.
        cached = sys.modules.get("lancedb")
        if _is_pyo3_reinit_error(exc) and _usable_lancedb_module(cached):
            _log.info("lancedb import raised PyO3 reinit warning but the cached module is usable; continuing")
            return _set_lancedb_module(cached)
        _clear_lancedb_modules()
        if log_warning:
            logging.getLogger(__name__).warning(
                "suppressed exception in backend/data/vector/connection.py:_try_import_lancedb: %s",
                exc,
            )
        lancedb = None
        if _is_pyo3_reinit_error(exc):
            _LANCEDB_IMPORT_ERROR = PYO3_RESTART_MESSAGE
            _LANCEDB_RESTART_REQUIRED = True
        else:
            _LANCEDB_IMPORT_ERROR = str(exc)
            _LANCEDB_RESTART_REQUIRED = False
        return None
    if not _usable_lancedb_module(module):
        location = getattr(module, "__file__", "") or ",".join(map(str, getattr(module, "__path__", []))) or "unknown location"
        _clear_lancedb_modules()
        lancedb = None
        _LANCEDB_IMPORT_ERROR = f"LanceDB runtime is incomplete at {location}"
        _LANCEDB_RESTART_REQUIRED = False
        return None
    return _set_lancedb_module(module)


def _connect_vector_store():
    global BASE_DIR, VECTOR_DIR
    with _vector_lock:
        BASE_DIR = default_base_dir()
        VECTOR_DIR = default_vector_dir()
        os.makedirs(VECTOR_DIR, exist_ok=True)
        module = lancedb if _usable_lancedb_module(lancedb) else _try_import_lancedb()
        if module is None:
            raise RuntimeError(_LANCEDB_IMPORT_ERROR or "LanceDB is not available")
        return module.connect(VECTOR_DIR)


def refresh_vector_store() -> dict:
    global vec
    with _vector_lock:
        try:
            vec = _connect_vector_store()
        except Exception as exc:
            if lancedb is None:
                _log.info("vector store disabled: %s", exc)
            else:
                _log.warning("vector store disabled: %s", exc)
            vec = NullVectorStore(str(exc))
    return vector_status(refresh=False)


def vector_status(*, refresh: bool = True) -> dict:
    with _vector_lock:
        if getattr(vec, "available", True) is False:
            if refresh and not _LANCEDB_RESTART_REQUIRED and vector_runtime_ready():
                return refresh_vector_store()
            status = {
                "status": "disabled",
                "error": getattr(vec, "reason", "") or "vector store is unavailable",
                "tables": [],
            }
            if _LANCEDB_RESTART_REQUIRED:
                status["restart_required"] = True
            return status
        try:
            return {"status": "ok", "tables": list(vec.list_tables() or [])}
        except Exception as exc:
            _log.warning("vector store status check failed: %s", exc)
            return {"status": "degraded", "error": str(exc), "tables": []}


_try_import_lancedb(log_warning=False)
vec = NullVectorStore(_LANCEDB_IMPORT_ERROR or "LanceDB is not available")
refresh_vector_store()
