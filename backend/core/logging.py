import logging
import os
import sys
import json
import time
import functools
import re
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


def redact_text(value: object, max_len: int = 2000) -> str:
    text = str(value)
    text = SECRET_RE.sub("[REDACTED_SECRET]", text)
    text = ASSIGNMENT_SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED_SECRET]", text)
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    if len(text) > max_len:
        return f"{text[:max_len]}...[truncated]"
    return text


def redact_sensitive(value, depth: int = 0):
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
            redacted[key_text] = "[REDACTED]" if SENSITIVE_KEY_RE.search(key_text) else redact_sensitive(item, depth + 1)
        return redacted
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        out = [redact_sensitive(item, depth + 1) for item in items[:50]]
        if len(items) > 50:
            out.append("[TRUNCATED]")
        return out
    return redact_text(value)


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "module": record.name,
            "msg": redact_text(record.getMessage()),
        }
        for key in ("domain", "duration_ms", "job_id"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        context = context_payload(record)
        if context:
            entry["context"] = redact_sensitive(dict(context))
        if record.exc_info:
            entry["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level_str = os.environ.get("JHM_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    handler.setFormatter(StructuredFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def with_context(logger: logging.Logger, **context) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logger, {"jhm_context": context})


def context_payload(record: logging.LogRecord) -> Mapping:
    payload = getattr(record, "jhm_context", None)
    return payload if isinstance(payload, Mapping) else {}


def timed(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        start = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            elapsed = (time.perf_counter() - start) * 1000
            logger.info("%s completed", func.__qualname__, extra={"duration_ms": round(elapsed, 1)})
            return result
        except Exception:
            elapsed = (time.perf_counter() - start) * 1000
            logger.exception("%s failed", func.__qualname__, extra={"duration_ms": round(elapsed, 1)})
            raise

    return wrapper
