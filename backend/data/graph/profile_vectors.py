"""LanceDB vector-store access for the profile graph layer.

Reads the profile back out of the embedding tables, writes/embeds rows, prunes
bad-label rows, and builds the per-entity embedding text. Sits above the base
+ deletions layers (read_profile_from_vectors applies deletion tombstones) and
is consumed by the read, correlation, and mutation modules.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from core.logging import get_logger
from data.graph.profile_base import (
    _vec,
    clean_profile_summary,
    empty_profile,
    hash_id,
    stack_list,
)
from data.graph.profile_deletions import apply_profile_deletions
from graph_service.helpers import is_bad_vector_label

_log = get_logger(__name__)


def _vector_rows(table_name: str, limit: int = 500) -> list[dict]:
    try:
        if table_name not in vec_table_names():
            return []
        table = _vec().open_table(table_name)
        if hasattr(table, "to_arrow"):
            rows = table.to_arrow().to_pylist()
        elif hasattr(table, "to_pandas"):
            rows = table.to_pandas().to_dict("records")
        else:
            rows = []
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/data/graph/profile.py:_vector_rows: %s', log_exc)
        return []
    return [row for row in rows[:limit] if isinstance(row, dict)]


def _first_text(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, (list, tuple, set)):
            value = ", ".join(str(item).strip() for item in value if str(item).strip())
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _vector_id(row: dict, fallback: str) -> str:
    return _first_text(row, "id") or hash_id(fallback)


def read_profile_from_vectors(db_path: str | None = None) -> dict:
    profile = empty_profile()

    for row in [*_vector_rows("candidates"), *_vector_rows("profile")]:
        name = _first_text(row, "n", "name", "label")
        summary = _first_text(row, "s", "summary", "text")
        if name.lower() in {"complete profile", "profile", "candidate"}:
            name = ""
        if name and not is_bad_vector_label(name) and not profile["n"]:
            profile["n"] = name
        if summary and not is_bad_vector_label(summary) and not profile["s"]:
            profile["s"] = clean_profile_summary(summary)
        if profile["n"] and profile["s"]:
            break

    for row in _vector_rows("skills"):
        name = _first_text(row, "n", "name", "label", "title")
        if not name or is_bad_vector_label(name):
            continue
        profile["skills"].append({
            "id": _vector_id(row, name),
            "n": name,
            "cat": _first_text(row, "cat", "category", "kind") or "vector",
        })

    for row in _vector_rows("projects"):
        title = _first_text(row, "title", "name", "label", "n")
        if not title or is_bad_vector_label(title):
            continue
        profile["projects"].append({
            "id": _vector_id(row, title),
            "title": title,
            "stack": stack_list(row.get("stack") or row.get("tags") or ""),
            "repo": _first_text(row, "repo", "url"),
            "impact": _first_text(row, "impact", "description", "text", "summary"),
        })

    for row in _vector_rows("experiences"):
        role = _first_text(row, "role", "title", "label", "name")
        company = _first_text(row, "co", "company", "org", "subtitle")
        if (not role and not company) or (is_bad_vector_label(role) and is_bad_vector_label(company)):
            continue
        profile["exp"].append({
            "id": _vector_id(row, role + company),
            "role": role,
            "co": company,
            "period": _first_text(row, "period", "dates", "range"),
            "d": _first_text(row, "d", "description", "text", "summary"),
        })

    credential_keys = {
        "education": "education",
        "certification": "certifications",
        "achievement": "achievements",
    }
    for row in _vector_rows("credentials"):
        title = _first_text(row, "title", "label", "name", "n")
        if not title or is_bad_vector_label(title):
            continue
        kind = _first_text(row, "kind", "type", "category").lower()
        key = credential_keys.get(kind)
        if key:
            profile[key].append(title)
        else:
            profile["certifications"].append(title)

    return apply_profile_deletions(profile, db_path)


def delete_vec_rows(table_name: str, ids: list[str]) -> None:
    ids = [str(item or "").strip() for item in ids if str(item or "").strip()]
    if not ids:
        return
    try:
        if table_name not in vec_table_names():
            return
        _delete_vec_ids(_vec().open_table(table_name), ids)
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/data/graph/profile.py:delete_vec_rows: %s', log_exc)
        pass


def _delete_vec_ids(table, ids: list[str]) -> None:
    quoted = ["'" + item.replace("'", "''") + "'" for item in ids]
    table.delete("id IN (" + ", ".join(quoted) + ")")


def delete_vec_id_from_all(row_id: str) -> None:
    for table_name in ["profile", "candidates", "skills", "projects", "experiences", "credentials"]:
        delete_vec_rows(table_name, [row_id])


def drop_profile_aggregate_vector() -> None:
    delete_vec_rows("profile", ["profile:default"])


def prune_bad_vector_rows() -> int:
    deleted = 0
    for table_name in ["profile", "candidates", "skills", "projects", "experiences", "credentials"]:
        try:
            if table_name not in vec_table_names():
                continue
            table = _vec().open_table(table_name)
            if hasattr(table, "to_arrow"):
                rows = table.to_arrow().to_pylist()
            elif hasattr(table, "to_pandas"):
                rows = table.to_pandas().to_dict("records")
            else:
                rows = []
            bad_ids = []
            for row in rows:
                label = row.get("label") or row.get("title") or row.get("n") or row.get("role") or row.get("id")
                text = row.get("text") or ""
                if is_bad_vector_label(label) or is_bad_vector_label(text):
                    row_id = str(row.get("id") or "").strip()
                    if row_id:
                        bad_ids.append(row_id)
            if bad_ids:
                delete_vec_rows(table_name, bad_ids)
                deleted += len(set(bad_ids))
        except Exception as log_exc:
            logging.getLogger(__name__).warning('suppressed exception in backend/data/graph/profile.py:prune_bad_vector_rows: %s', log_exc)
            continue
    return deleted


def vec_table_names() -> list[str]:
    store = _vec()
    if getattr(store, "available", True) is False:
        return []
    raw = store.list_tables()
    names = _normalize_table_names(raw)
    if names:
        return names
    return []


def _normalize_table_names(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                value = item.get("name") or item.get("table") or item.get("table_name")
                if value:
                    out.append(str(value))
            elif isinstance(item, (list, tuple)) and item:
                out.append(str(item[0]))
            elif item is not None:
                out.append(str(item))
        return out
    if hasattr(raw, "tables"):
        return _normalize_table_names(raw.tables)
    if isinstance(raw, dict):
        tables = raw.get("tables", raw)
        if tables is not raw:
            return _normalize_table_names(tables)
    try:
        pairs = dict(raw)
        tables = pairs.get("tables", [])
        if tables:
            return _normalize_table_names(tables)
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/data/graph/profile.py:vec_table_names: %s', log_exc)
    try:
        return [str(item) for item in raw]
    except TypeError:
        return []


def _incoming_vector_dim(rows: list[dict]) -> int | None:
    for row in rows:
        vec = row.get("vector")
        if vec is not None:
            try:
                return len(vec)
            except TypeError:
                return None
    return None


def _existing_vector_dim(store, table_name: str) -> int | None:
    try:
        schema = store.open_table(table_name).to_arrow().schema
        return getattr(schema.field("vector").type, "list_size", None)
    except Exception:
        return None


def _upsert_rows(table, ids: list[str], rows: list[dict]) -> None:
    """Replace rows by id atomically.

    The previous delete-then-add ordering lost the old embeddings whenever the
    add failed (the delete had already committed). merge_insert performs the
    replace as a single operation; if it's unavailable we fall back to the old
    best-effort ordering.
    """
    try:
        (
            table.merge_insert("id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(rows)
        )
    except (AttributeError, NotImplementedError):
        _delete_vec_ids(table, ids)
        table.add(rows)


def put_vec_rows(table_name: str, rows: list[dict]) -> None:
    if not rows:
        return
    store = _vec()
    if getattr(store, "available", True) is False:
        return
    ids = [str(row.get("id") or "").strip() for row in rows if str(row.get("id") or "").strip()]
    try:
        if table_name in vec_table_names():
            # If the embedding dimensionality changed (e.g. the user switched
            # embedding provider, 1536<->384), the old table is in a different
            # vector space and incompatible. Recreate it rather than letting the
            # add silently fail and drop every new vector.
            want_dim = _incoming_vector_dim(rows)
            have_dim = _existing_vector_dim(store, table_name)
            if want_dim and have_dim and want_dim != have_dim:
                _log.warning("vector dim for %s changed %s->%s; recreating table", table_name, have_dim, want_dim)
                store.drop_table(table_name)
                store.create_table(table_name, data=rows)
                return
            rows = _rows_for_existing_table(table_name, rows)
            _upsert_rows(store.open_table(table_name), ids, rows)
        else:
            try:
                store.create_table(table_name, data=rows)
            except Exception as exc:
                if "already exists" not in str(exc).lower():
                    raise
                rows = _rows_for_existing_table(table_name, rows)
                _upsert_rows(store.open_table(table_name), ids, rows)
    except Exception as exc:
        _log.warning("vector write failed for %s: %s", table_name, exc)


def _rows_for_existing_table(table_name: str, rows: list[dict]) -> list[dict]:
    try:
        table = _vec().open_table(table_name)
        schema = table.to_arrow().schema
        field_names = set(schema.names)
        if not field_names:
            return rows
        return [{key: value for key, value in row.items() if key in field_names} for row in rows]
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/data/graph/profile.py:_rows_for_existing_table: %s', log_exc)
        return rows


def embed_rows(table_name: str, rows: list[dict], texts: Iterable[str]) -> None:
    try:
        from data.vector.embeddings import embed_texts

        pairs = [
            (row, str(text or "").strip())
            for row, text in zip(rows, texts, strict=False)
            if not is_bad_vector_label(row.get("label") or row.get("title") or row.get("n") or row.get("role") or row.get("id"))
            and not is_bad_vector_label(text)
        ]
        if not pairs:
            return
        clean_rows = [row for row, _text in pairs]
        clean_texts = [text for _row, text in pairs]
        vectors = embed_texts(clean_texts)
        if not vectors:
            return
        put_vec_rows(table_name, [
            {**row, "text": text, "vector": vector}
            for row, text, vector in zip(clean_rows, clean_texts, vectors, strict=False)
        ])
    except Exception as exc:
        _log.warning("embedding write failed for %s: %s", table_name, exc)


def profile_text(name: str, summary: str) -> str:
    return f"Candidate profile\nName: {name}\nSummary: {summary}".strip()


def skill_text(name: str, category: str) -> str:
    return f"Skill: {name}\nCategory: {category}".strip()


def project_text(title: str, stack: str | list, impact: str) -> str:
    stack_value = ", ".join(stack) if isinstance(stack, list) else str(stack or "")
    return f"Project: {title}\nStack: {stack_value}\nImpact: {impact}".strip()


def experience_text(role: str, company: str, period: str, description: str) -> str:
    return f"Experience: {role}\nCompany: {company}\nPeriod: {period}\nDescription: {description}".strip()


def credential_text(title: str, kind: str) -> str:
    return f"{kind}: {title}".strip()


def add_candidate_vec(candidate_id: str, name: str, summary: str) -> None:
    row = {"id": candidate_id, "label": name or "Candidate", "kind": "candidate", "n": name, "summary": summary}
    embed_rows("candidates", [row], [profile_text(name, summary)])


def add_profile_vec(profile_id: str, label: str, text: str) -> None:
    embed_rows("profile", [{"id": profile_id, "label": label, "kind": "profile"}], [text])


def add_skill_vec(skill_id: str, name: str, category: str) -> None:
    row = {"id": skill_id, "label": name, "kind": "skill", "n": name, "cat": category}
    embed_rows("skills", [row], [skill_text(name, category)])


def add_project_vec(project_id: str, title: str, stack: str, impact: str) -> None:
    row = {"id": project_id, "label": title, "kind": "project", "title": title, "stack": stack, "impact": impact}
    embed_rows("projects", [row], [project_text(title, stack, impact)])


def add_experience_vec(experience_id: str, role: str, company: str, period: str, description: str) -> None:
    label = " - ".join(part for part in [role, company] if part) or "Experience"
    row = {"id": experience_id, "label": label, "kind": "experience", "role": role, "company": company, "period": period, "description": description}
    embed_rows("experiences", [row], [experience_text(role, company, period, description)])


def add_credential_vec(node_id: str, title: str, kind: str) -> None:
    row = {"id": node_id, "label": title, "kind": kind.lower(), "title": title}
    embed_rows("credentials", [row], [credential_text(title, kind)])
