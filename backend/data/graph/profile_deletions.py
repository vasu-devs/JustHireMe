"""Profile soft-delete tombstones and read-path deletion filtering.

Deleting a profile item records a tombstone in SQLite settings rather than
mutating the graph immediately; every read path (Profile snapshot, Knowledge
graph snapshot, embedding space) filters against the same tombstone tokens so
a deleted item never reappears. The hard purge that actually removes nodes
from the graph/vector stores lives in profile.py (it depends on the graph and
vector mutation helpers).

Depends only on profile_base + the SQLite settings store, so it sits just
above the base layer with no dependency on the read/vector/mutation modules.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from urllib.parse import unquote

from data.graph.profile_base import (
    PROFILE_DELETE_KEYS,
    PROFILE_DELETIONS_KEY,
    _entry_text,
    _norm_key,
    hash_id,
    normal_profile,
    stack_list,
)
from data.sqlite.settings import get_setting, save_settings


def _load_profile_deletions(db_path: str | None = None) -> dict[str, list[str]]:
    try:
        raw = get_setting(PROFILE_DELETIONS_KEY, "", db_path) if db_path else get_setting(PROFILE_DELETIONS_KEY, "")
        data = json.loads(raw or "{}")
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/data/graph/profile.py:_load_profile_deletions: %s', log_exc)
        data = {}
    return {
        key: sorted({
            _norm_key(token)
            for token in (data.get(key) if isinstance(data, dict) else []) or []
            if _norm_key(token)
        })
        for key in PROFILE_DELETE_KEYS
    }


def _save_profile_deletions(deletions: dict[str, list[str]], db_path: str | None = None) -> None:
    clean = {key: sorted({_norm_key(token) for token in deletions.get(key, []) if _norm_key(token)}) for key in PROFILE_DELETE_KEYS}
    try:
        payload = {PROFILE_DELETIONS_KEY: json.dumps(clean, ensure_ascii=False)}
        if db_path:
            save_settings(payload, db_path)
        else:
            save_settings(payload)
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/data/graph/profile.py:_save_profile_deletions: %s', log_exc)
        pass


def _delete_tokens(*values) -> set[str]:
    out: set[str] = set()
    for value in values:
        if isinstance(value, (list, tuple, set)):
            out.update(_delete_tokens(*value))
            continue
        text = str(value or "").strip()
        if not text:
            continue
        out.add(text)
        out.add(unquote(text))
        out.add(hash_id(unquote(text)))
    return {_norm_key(item) for item in out if _norm_key(item)}


def _remember_profile_deletion(key: str, values: Iterable, db_path: str | None = None) -> None:
    if key not in PROFILE_DELETE_KEYS:
        return
    deletions = _load_profile_deletions(db_path)
    deletions[key] = sorted(set(deletions.get(key, [])) | _delete_tokens(values))
    _save_profile_deletions(deletions, db_path)


def _forget_profile_deletion(key: str, values: Iterable, db_path: str | None = None) -> None:
    if key not in PROFILE_DELETE_KEYS:
        return
    tokens = _delete_tokens(values)
    if not tokens:
        return
    deletions = _load_profile_deletions(db_path)
    deletions[key] = [token for token in deletions.get(key, []) if token not in tokens]
    _save_profile_deletions(deletions, db_path)


def forget_profile_deletions_for_profile(profile: dict | None, db_path: str | None = None) -> None:
    profile = normal_profile(profile)
    for item in profile.get("skills", []) or []:
        if isinstance(item, dict):
            _forget_profile_deletion("skills", [item.get("id"), item.get("n"), item.get("name"), item.get("title")], db_path)
    for item in profile.get("projects", []) or []:
        if isinstance(item, dict):
            _forget_profile_deletion("projects", [item.get("id"), item.get("title"), item.get("name")], db_path)
    for item in profile.get("exp", []) or []:
        if isinstance(item, dict):
            role = str(item.get("role") or "")
            company = str(item.get("co") or item.get("company") or "")
            _forget_profile_deletion("exp", [item.get("id"), role, company, role + company, " at ".join(part for part in [role, company] if part)], db_path)
    for key in ["education", "certifications", "achievements"]:
        for item in profile.get(key, []) or []:
            text = _entry_text(item)
            _forget_profile_deletion(key, [text, hash_id(text)], db_path)


def _is_deleted(key: str, *values, db_path: str | None = None) -> bool:
    tokens = _delete_tokens(values)
    if not tokens:
        return False
    return bool(tokens.intersection(_load_profile_deletions(db_path).get(key, [])))


def apply_profile_deletions(profile: dict | None, db_path: str | None = None) -> dict:
    profile = normal_profile(profile)
    profile["skills"] = [
        item for item in profile.get("skills", [])
        if not (isinstance(item, dict) and _is_deleted("skills", item.get("id"), item.get("n"), item.get("name"), item.get("title"), db_path=db_path))
    ]
    profile["projects"] = [
        item for item in profile.get("projects", [])
        if not (isinstance(item, dict) and _is_deleted("projects", item.get("id"), item.get("title"), item.get("name"), db_path=db_path))
    ]
    profile["exp"] = [
        item for item in profile.get("exp", [])
        if not (
            isinstance(item, dict)
            and _is_deleted(
                "exp",
                item.get("id"),
                item.get("role"),
                item.get("co"),
                str(item.get("role") or "") + str(item.get("co") or ""),
                " at ".join(part for part in [item.get("role"), item.get("co")] if part),
                " - ".join(part for part in [item.get("role"), item.get("co")] if part),
                db_path=db_path,
            )
        )
    ]
    for key in ["education", "certifications", "achievements"]:
        profile[key] = [item for item in profile.get(key, []) if not _is_deleted(key, _entry_text(item), hash_id(_entry_text(item)), db_path=db_path)]
    return _prune_orphan_project_stack_skills(profile)


def _prune_orphan_project_stack_skills(profile: dict) -> dict:
    project_stack_terms: set[str] = set()
    for project in profile.get("projects", []) or []:
        if not isinstance(project, dict):
            continue
        for term in stack_list(project.get("stack")):
            key = _norm_key(term)
            if key:
                project_stack_terms.add(key)

    skills = []
    for item in profile.get("skills", []) or []:
        if not isinstance(item, dict):
            skills.append(item)
            continue
        category = str(item.get("cat") or item.get("category") or "").strip().lower()
        name = str(item.get("n") or item.get("name") or item.get("title") or "").strip()
        if category == "project_stack" and _norm_key(name) not in project_stack_terms:
            continue
        skills.append(item)
    profile["skills"] = skills
    return profile


# --- Deletion filtering for the graph-stats read path -----------------------
# The Knowledge page reads /api/v1/graph, whose `graph` (raw Kùzu snapshot) and
# `embedding` (raw LanceDB rows) fields previously bypassed the deletion
# tombstones that the Profile page applies via apply_profile_deletions(). That
# asymmetry let a deleted item linger on the Knowledge page and resurrect the
# profile on the next repair sync. These helpers reuse the SAME tombstone token
# logic (_is_deleted) so every read path agrees on what is deleted.

_CREDENTIAL_SUBTITLE_KEYS = {
    "education": "education",
    "certification": "certifications",
    "certifications": "certifications",
    "achievement": "achievements",
    "achievements": "achievements",
}

_EMBEDDING_SOURCE_KEYS = {
    "skills": ["skills"],
    "projects": ["projects"],
    "experiences": ["exp"],
    "credentials": ["education", "certifications", "achievements"],
}


def _strip_node_prefix(node_id) -> str:
    text = str(node_id or "")
    return text.split(":", 1)[1] if ":" in text else text


def _graph_node_is_deleted(node, db_path: str | None = None) -> bool:
    if not isinstance(node, dict):
        return False
    node_type = str(node.get("type") or "").strip().lower()
    raw_id = _strip_node_prefix(node.get("id"))
    label = node.get("label")
    subtitle = node.get("subtitle")
    if node_type == "skill":
        return _is_deleted("skills", raw_id, label, db_path=db_path)
    if node_type == "project":
        return _is_deleted("projects", raw_id, label, db_path=db_path)
    if node_type == "experience":
        role = str(label or "")
        company = str(subtitle or "")
        joined = " at ".join(part for part in [role, company] if part)
        return _is_deleted("exp", raw_id, role, company, role + company, joined, db_path=db_path)
    if node_type == "credential":
        key = _CREDENTIAL_SUBTITLE_KEYS.get(str(subtitle or "").strip().lower())
        keys = [key] if key else ["education", "certifications", "achievements"]
        return any(_is_deleted(item, raw_id, label, db_path=db_path) for item in keys)
    return False


def filter_graph_deletions(graph: dict | None, db_path: str | None = None) -> dict:
    """Drop tombstoned nodes (and edges that reference them) from a graph snapshot."""
    if not isinstance(graph, dict):
        return graph or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    kept_nodes = [node for node in nodes if not _graph_node_is_deleted(node, db_path)]
    if len(kept_nodes) == len(nodes):
        return graph
    kept_ids = {str(node.get("id")) for node in kept_nodes if isinstance(node, dict)}
    kept_edges = [
        edge for edge in edges
        if isinstance(edge, dict) and str(edge.get("source")) in kept_ids and str(edge.get("target")) in kept_ids
    ]
    return {**graph, "nodes": kept_nodes, "edges": kept_edges}


def filter_embedding_deletions(embedding: dict | None, db_path: str | None = None) -> dict:
    """Drop tombstoned points from an embedding-space payload."""
    if not isinstance(embedding, dict):
        return embedding or {}
    points = embedding.get("points") or []
    kept = []
    for point in points:
        if not isinstance(point, dict):
            kept.append(point)
            continue
        keys = _EMBEDDING_SOURCE_KEYS.get(str(point.get("source") or "").strip().lower())
        if keys and any(_is_deleted(key, point.get("id"), point.get("label"), db_path=db_path) for key in keys):
            continue
        kept.append(point)
    if len(kept) == len(points):
        return embedding
    return {**embedding, "points": kept, "available": bool(kept)}
