"""Shared primitives and graph/vector I/O wrappers for the profile layer.

This module holds the helpers and constants used across the profile
read/write/deletion/vector/correlation modules: ID hashing, the bulk-import
context flag, profile-shape normalization, small key/entry utilities, and the
low-level Kùzu query wrappers (_safe_execute / _query_rows / _upsert_node).

It must not import any of the profile_* sibling modules, so it sits at the
base of the dependency graph (everything else may import from here).
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import re
from collections.abc import Iterable
from urllib.parse import unquote

from core.logging import get_logger
from data.graph.connection import execute_query
from data.vector import connection as vector_connection

_log = get_logger(__name__)

PROFILE_SNAPSHOT_KEY = "profile_snapshot_json"
PROFILE_DELETIONS_KEY = "profile_deleted_items_json"
IDENTITY_KEYS = ("email", "phone", "linkedin_url", "github_url", "website_url", "city")
PROFILE_DELETE_KEYS = ("skills", "projects", "exp", "education", "certifications", "achievements")
_BULK_IMPORT_DEPTH: contextvars.ContextVar[int] = contextvars.ContextVar("profile_bulk_import_depth", default=0)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")


def _vec():
    return vector_connection.vec


def hash_id(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


@contextlib.contextmanager
def bulk_profile_import():
    token = _BULK_IMPORT_DEPTH.set(_BULK_IMPORT_DEPTH.get() + 1)
    try:
        yield
    finally:
        _BULK_IMPORT_DEPTH.reset(token)


def _bulk_import_active() -> bool:
    return _BULK_IMPORT_DEPTH.get() > 0


def stack_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


# Field-agnostic: a project's skills can arrive under any of these keys depending
# on the source (resume parser, LinkedIn export, portfolio scrape, manual JSON).
# Linking only off `stack` left projects whose skills came in under `skills` /
# `technologies` / `tools` disconnected in the knowledge graph.
PROJECT_SKILL_FIELDS = ("stack", "s", "skills", "tech", "technologies", "tools", "tech_stack")


def project_stack_list(item: dict) -> list[str]:
    """Flatten a project's skills across every recognised skill field.

    De-duplicates case-insensitively while preserving first-seen order so a
    project links to its skills no matter which field the source populated.
    """
    out: list[str] = []
    seen: set[str] = set()
    for field in PROJECT_SKILL_FIELDS:
        for token in stack_list(item.get(field)):
            key = token.lower()
            if key and key not in seen:
                seen.add(key)
                out.append(token)
    return out


def clean_profile_summary(value: str) -> str:
    lines: list[str] = []
    for raw in str(value or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        lower = line.lower().strip(" :-")
        if not line:
            continue
        if lower.startswith(("email", "phone", "mobile", "links", "linkedin", "github", "portfolio", "website", "contact", "targeting ")):
            continue
        line = _URL_RE.sub("", line)
        line = _EMAIL_RE.sub("", line)
        line = _PHONE_RE.sub("", line)
        line = re.sub(r"\s+", " ", line).strip(" .;|-")
        if line:
            lines.append(line)
    clean = re.sub(r"\s+", " ", " ".join(lines)).strip()
    marker_count = sum(1 for marker in ("email", "phone", "links", "linkedin", "github", "http") if marker in clean.lower())
    return "" if marker_count >= 2 else clean


def profile_has_data(profile: dict | None) -> bool:
    if not isinstance(profile, dict):
        return False
    return bool(
        str(profile.get("n") or "").strip()
        or str(profile.get("s") or "").strip()
        or profile.get("skills")
        or profile.get("projects")
        or profile.get("exp")
        or profile.get("certifications")
        or profile.get("education")
        or profile.get("achievements")
        or any(str(value or "").strip() for value in (profile.get("identity") or {}).values())
    )


def profile_has_structured_data(profile: dict | None) -> bool:
    if not isinstance(profile, dict):
        return False
    profile = normal_profile(profile)
    return bool(
        profile.get("skills")
        or profile.get("projects")
        or profile.get("exp")
        or profile.get("certifications")
        or profile.get("education")
        or profile.get("achievements")
    )


def empty_profile() -> dict:
    return {
        "n": "",
        "s": "",
        "skills": [],
        "projects": [],
        "exp": [],
        "certifications": [],
        "education": [],
        "achievements": [],
        "identity": {key: "" for key in IDENTITY_KEYS},
    }


def normal_profile(profile: dict | None) -> dict:
    profile = profile if isinstance(profile, dict) else {}
    identity: dict = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    return {
        "n": str(profile.get("n") or ""),
        "s": clean_profile_summary(str(profile.get("s") or "")),
        "skills": list(profile.get("skills") or []),
        "projects": list(profile.get("projects") or []),
        "exp": list(profile.get("exp") or []),
        "certifications": list(profile.get("certifications") or profile.get("certs") or []),
        "education": list(profile.get("education") or []),
        "achievements": list(profile.get("achievements") or profile.get("awards") or []),
        "identity": {key: str(identity.get(key) or profile.get(key) or "") for key in IDENTITY_KEYS},
    }


def _entry_text(value) -> str:
    if isinstance(value, dict):
        return str(value.get("title") or "").strip()
    return str(value or "").strip()


def _entry_key(value) -> str:
    return re.sub(r"\s+", " ", _entry_text(value)).strip().lower()


def _norm_key(value) -> str:
    return re.sub(r"[^a-z0-9]+", "", unquote(str(value or "")).strip().lower())


def _dedupe_ids(ids: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(item or "").strip() for item in ids if str(item or "").strip()))


def _safe_execute(query: str, params: dict | None = None):
    try:
        return execute_query(query, params)
    except Exception as exc:
        _log.warning("graph query skipped: %s", exc)
        return None


def _query_rows(query: str, params: dict | None = None, *, require_result: bool = False) -> list[list]:
    rows: list[list] = []
    result = _safe_execute(query, params)
    if result is None and require_result:
        raise RuntimeError("graph query unavailable")
    while result is not None and result.has_next():
        rows.append(result.get_next())
    return rows


def _upsert_node(label: str, props: dict) -> bool:
    pk = next(iter(props))
    pk_params = {pk: props[pk]}
    try:
        result = execute_query(f"MATCH (n:{label}) WHERE n.{pk} = ${pk} RETURN n.{pk} LIMIT 1", pk_params)
        if result is not None and result.has_next():
            if len(props) > 1:
                sets = ", ".join(f"n.{key} = ${key}" for key in props if key != pk)
                execute_query(f"MATCH (n:{label}) WHERE n.{pk} = ${pk} SET {sets}", props)
            return True
        cols = ", ".join(f"{key}: ${key}" for key in props)
        execute_query(f"CREATE (:{label} {{{cols}}})", props)
        return True
    except Exception as exc:
        if "duplicated primary key" in str(exc).lower() and len(props) > 1:
            sets = ", ".join(f"n.{key} = ${key}" for key in props if key != pk)
            _safe_execute(f"MATCH (n:{label}) WHERE n.{pk} = ${pk} SET {sets}", props)
            return True
        _log.warning("graph node upsert skipped: %s", exc)
        return False
