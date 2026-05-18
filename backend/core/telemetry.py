from __future__ import annotations

import json
import os
import re
import time
import traceback
from pathlib import Path
from collections.abc import Mapping


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
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "JustHireMe"
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
    except Exception:
        return


def _rotate_error_log(max_lines: int = 500) -> None:
    try:
        path_obj = errors_path()
        lines = path_obj.read_text(encoding="utf-8").splitlines(True)
        if len(lines) > max_lines:
            path_obj.write_text("".join(lines[-max_lines:]), encoding="utf-8")
    except Exception:
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
    except Exception:
        return
