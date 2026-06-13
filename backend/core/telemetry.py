from __future__ import annotations
import logging

import json
import os
import re
import time
import traceback
from pathlib import Path
from collections.abc import Mapping
from importlib import import_module

from .paths import app_data_path

SENSITIVE_KEY_RE = re.compile(
    r"(authorization|bearer|cookie|password|secret|token|api[_-]?key|private[_-]?key|resume|cover[_-]?letter|profile|email|phone)",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
SECRET_RE = re.compile(
    r"(ghp_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,}|Bearer\s+[A-Za-z0-9._~+/=-]{10,})"
)
ASSIGNMENT_SECRET_RE = re.compile(
    r"(?i)\b(authorization|cookie|password|secret|token|api[_-]?key|private[_-]?key)\b\s*[:=]\s*([^\s,;]+)"
)
MAX_TEXT_LEN = 2000


def telemetry_enabled() -> bool:
    return os.environ.get("JHM_LOCAL_ERROR_TELEMETRY", "").strip().lower() in {"1", "true", "yes", "on"}


def errors_path() -> Path:
    base = app_data_path()
    return Path(os.environ.get("JHM_ERRORS_JSONL", base / "errors.jsonl"))


def redact_text(value: object, *, max_len: int = MAX_TEXT_LEN) -> str:
    text = str(value)
    text = SECRET_RE.sub("[REDACTED_SECRET]", text)
    text = ASSIGNMENT_SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED_SECRET]", text)
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    if len(text) > max_len:
        text = f"{text[:max_len]}...[truncated]"
    return text


def redact_sensitive(value, *, depth: int = 0):
    if depth > 6:
        return "[REDACTED_DEPTH]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            if SENSITIVE_KEY_RE.search(key_text):
                redacted[key_text] = "[REDACTED]"
            else:
                redacted[key_text] = redact_sensitive(item, depth=depth + 1)
        return redacted
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        limited = [redact_sensitive(item, depth=depth + 1) for item in items[:50]]
        if len(items) > 50:
            limited.append("[TRUNCATED]")
        return limited
    return redact_text(value)


def record_exception(exc: BaseException, *, domain: str = "api", request_id: str = "", path: str = "") -> None:
    if not telemetry_enabled():
        return
    try:
        path_obj = errors_path()
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "domain": domain,
            "request_id": request_id,
            "path": redact_text(path, max_len=500),
            "error_type": type(exc).__name__,
            "message": redact_text(exc),
            "traceback": [redact_text(line, max_len=1000) for line in traceback.format_exception(type(exc), exc, exc.__traceback__)[-8:]],
        }
        with path_obj.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        # A recurring backend exception would otherwise grow errors.jsonl
        # unbounded; cap it the same way the frontend-error sink does.
        _rotate_error_log()
    except Exception as log_exc:
        logging.getLogger(__name__).debug('suppressed exception in backend/core/telemetry.py:record_exception: %s', log_exc)
        return


def _rotate_error_log(max_lines: int = 500) -> None:
    try:
        path_obj = errors_path()
        lines = path_obj.read_text(encoding="utf-8").splitlines(True)
        if len(lines) > max_lines:
            path_obj.write_text("".join(lines[-max_lines:]), encoding="utf-8")
    except Exception as log_exc:
        logging.getLogger(__name__).debug('suppressed exception in backend/core/telemetry.py:_rotate_error_log: %s', log_exc)
        return


def log_error(exc: BaseException | str, context: dict | None = None) -> None:
    try:
        path_obj = errors_path()
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "type": type(exc).__name__ if not isinstance(exc, str) else "FrontendError",
            "message": redact_text(exc),
            "traceback": redact_text(traceback.format_exc()) if not isinstance(exc, str) else "",
            "context": redact_sensitive(context or {}),
        }
        with path_obj.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        _rotate_error_log()
    except Exception as log_exc:
        logging.getLogger(__name__).debug('suppressed exception in backend/core/telemetry.py:log_error: %s', log_exc)
        return


def record_error(error_type: str, message: str = "", source: str = "") -> None:
    try:
        connection = import_module("data.sqlite.connection")
        connection.init_sql()
        conn = connection.get_connection()
        error_type = redact_text(error_type, max_len=120)[:120] or "unknown"
        source = redact_text(source, max_len=200)[:200]
        message = redact_text(message, max_len=1000)[:1000]
        row = conn.execute(
            """
            SELECT id FROM error_log
            WHERE error_type=? AND source=? AND last_seen >= datetime('now', '-1 hour')
            ORDER BY last_seen DESC
            LIMIT 1
            """,
            (error_type, source),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE error_log SET count=count+1, error_message=?, last_seen=datetime('now') WHERE id=?",
                (message, row["id"] if hasattr(row, "keys") else row[0]),
            )
        else:
            conn.execute(
                "INSERT INTO error_log(error_type,error_message,source) VALUES(?,?,?)",
                (error_type, message, source),
            )
        conn.commit()
    except Exception as log_exc:
        logging.getLogger(__name__).debug('suppressed exception in backend/core/telemetry.py:record_error: %s', log_exc)
        return


def get_top_errors(limit: int = 10, days: int = 7) -> list[dict]:
    try:
        connection = import_module("data.sqlite.connection")
        connection.init_sql()
        conn = connection.get_connection()
        rows = conn.execute(
            """
            SELECT error_type,error_message,source,count,first_seen,last_seen
            FROM error_log
            WHERE last_seen >= datetime('now', ?)
            ORDER BY count DESC, last_seen DESC
            LIMIT ?
            """,
            (f"-{max(1, int(days))} days", max(1, min(int(limit or 10), 100))),
        ).fetchall()
        return [
            {
                "error_type": row["error_type"],
                "error_message": row["error_message"] or "",
                "source": row["source"] or "",
                "count": row["count"] or 0,
                "first_seen": row["first_seen"] or "",
                "last_seen": row["last_seen"] or "",
            }
            for row in rows
        ]
    except Exception as log_exc:
        logging.getLogger(__name__).debug('suppressed exception in backend/core/telemetry.py:get_top_errors: %s', log_exc)
        return []


def get_error_count(hours: int = 24) -> int:
    try:
        connection = import_module("data.sqlite.connection")
        connection.init_sql()
        conn = connection.get_connection()
        row = conn.execute(
            "SELECT COALESCE(SUM(count), 0) AS total FROM error_log WHERE last_seen >= datetime('now', ?)",
            (f"-{max(1, int(hours))} hours",),
        ).fetchone()
        return int((row["total"] if hasattr(row, "keys") else row[0]) or 0)
    except Exception as log_exc:
        logging.getLogger(__name__).debug('suppressed exception in backend/core/telemetry.py:get_error_count: %s', log_exc)
        return 0
