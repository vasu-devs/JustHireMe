from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import re
import functools
import threading
from urllib.parse import unquote
from collections.abc import Iterable

from core.logging import get_logger
from data.graph.connection import execute_query
from data.sqlite.settings import get_setting, save_settings
from data.vector.connection import vec
from graph_service.helpers import is_bad_vector_label

_log = get_logger(__name__)

PROFILE_SNAPSHOT_KEY = "profile_snapshot_json"
PROFILE_DELETIONS_KEY = "profile_deleted_items_json"
IDENTITY_KEYS = ("email", "phone", "linkedin_url", "github_url", "website_url", "city")
PROFILE_DELETE_KEYS = ("skills", "projects", "exp", "education", "certifications", "achievements")
_BULK_IMPORT_DEPTH: contextvars.ContextVar[int] = contextvars.ContextVar("profile_bulk_import_depth", default=0)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")

_profile_write_lock = threading.RLock()


def _profile_write_locked(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with _profile_write_lock:
            return func(*args, **kwargs)
    return wrapper


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


def _refresh_after_write(db_path: str | None = None) -> None:
    if not _bulk_import_active():
        refresh_profile_snapshot(db_path)


def _save_profile_patch(patch: dict, db_path: str | None = None) -> None:
    if _bulk_import_active():
        return
    try:
        base = load_profile_snapshot(db_path)
        try:
            graph = read_profile_from_graph()
            if profile_has_data(graph):
                base = merge_profiles(base, graph)
        except Exception:
            pass
        save_profile_snapshot(merge_profiles(base, patch), db_path)
    except Exception:
        pass


def stack_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


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
    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
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


def _load_profile_deletions(db_path: str | None = None) -> dict[str, list[str]]:
    try:
        raw = get_setting(PROFILE_DELETIONS_KEY, "", db_path) if db_path else get_setting(PROFILE_DELETIONS_KEY, "")
        data = json.loads(raw or "{}")
    except Exception:
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
    except Exception:
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


@_profile_write_locked
def _remember_profile_deletion(key: str, values: Iterable, db_path: str | None = None) -> None:
    if key not in PROFILE_DELETE_KEYS:
        return
    deletions = _load_profile_deletions(db_path)
    deletions[key] = sorted(set(deletions.get(key, [])) | _delete_tokens(values))
    _save_profile_deletions(deletions, db_path)


@_profile_write_locked
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


def load_profile_snapshot(db_path: str | None = None) -> dict:
    try:
        raw = get_setting(PROFILE_SNAPSHOT_KEY, "", db_path) if db_path else get_setting(PROFILE_SNAPSHOT_KEY)
        if not raw:
            return {}
        profile = apply_profile_deletions(json.loads(raw or "{}"), db_path)
        return profile if profile_has_data(profile) else {}
    except Exception:
        return {}


@_profile_write_locked
def save_profile_snapshot(profile: dict, db_path: str | None = None, *, allow_empty: bool = False) -> None:
    profile = apply_profile_deletions(profile, db_path)
    if not allow_empty and not profile_has_data(profile):
        return
    try:
        payload = {PROFILE_SNAPSHOT_KEY: json.dumps(profile, ensure_ascii=False)}
        if db_path:
            save_settings(payload, db_path)
        else:
            save_settings(payload)
    except Exception:
        pass


def _safe_execute(query: str, params: dict | None = None):
    try:
        return execute_query(query, params)
    except Exception as exc:
        _log.warning("graph query skipped: %s", exc)
        return None


def _query_rows(query: str, params: dict | None = None) -> list[list]:
    rows: list[list] = []
    result = _safe_execute(query, params)
    while result is not None and result.has_next():
        rows.append(result.get_next())
    return rows


def read_profile_from_graph() -> dict:
    candidates = _query_rows("MATCH (n:Candidate) RETURN n.id, n.n, n.s")
    if candidates:
        candidates.sort(
            key=lambda row: (
                0 if str(row[1] or "").strip().lower() in {"", "unknown", "candidate"} else 1,
                len(str(row[1] or "")) + len(str(row[2] or "")),
            ),
            reverse=True,
        )
        candidate = candidates[0]
    else:
        candidate = ["", "", ""]

    skills = []
    for row in _query_rows("MATCH (n:Skill) RETURN n.id, n.n, n.cat"):
        skills.append({"id": row[0], "n": row[1], "cat": row[2]})

    projects = []
    for row in _query_rows("MATCH (n:Project) RETURN n.id, n.title, n.stack, n.repo, n.impact"):
        projects.append({"id": row[0], "title": row[1], "stack": stack_list(row[2]), "repo": row[3], "impact": row[4]})

    experience = []
    for row in _query_rows("MATCH (n:Experience) RETURN n.id, n.role, n.co, n.period, n.d"):
        experience.append({"id": row[0], "role": row[1], "co": row[2], "period": row[3], "d": row[4]})

    def read_text_nodes(label: str) -> list[str]:
        items: list[str] = []
        for row in _query_rows(f"MATCH (n:{label}) RETURN n.title"):
            text = str(row[0] or "").strip()
            if text:
                items.append(text)
        return items

    return apply_profile_deletions({
        "n": candidate[1],
        "s": candidate[2],
        "skills": skills,
        "projects": projects,
        "exp": experience,
        "certifications": read_text_nodes("Certification"),
        "education": read_text_nodes("Education"),
        "achievements": read_text_nodes("Achievement"),
        "identity": {key: get_setting(key, "") for key in IDENTITY_KEYS},
    })


def get_profile(db_path: str | None = None, *, prefer_snapshot: bool = True) -> dict:
    snapshot = load_profile_snapshot(db_path)
    if prefer_snapshot and profile_has_data(snapshot):
        return snapshot
    try:
        profile = normal_profile(read_profile_from_graph())
    except Exception as exc:
        if snapshot:
            return snapshot
        _log.error("profile read failed: %s", exc)
        return empty_profile()

    if profile_has_data(profile):
        if snapshot:
            profile = merge_profiles(snapshot, profile)
        save_profile_snapshot(profile, db_path)
        return profile
    return snapshot or profile


def merge_profiles(base: dict | None, incoming: dict | None) -> dict:
    merged = normal_profile(base)
    incoming = normal_profile(incoming)
    if str(incoming.get("n") or "").strip().lower() not in {"", "unknown", "candidate"}:
        merged["n"] = incoming.get("n", "")
    if str(incoming.get("s") or "").strip():
        merged["s"] = incoming.get("s", "")
    merged["identity"] = {**(merged.get("identity") or {}), **{k: v for k, v in (incoming.get("identity") or {}).items() if v}}
    for key, id_key in [("skills", "id"), ("projects", "id"), ("exp", "id")]:
        seen: set[str] = set()
        rows: list[dict] = []
        for item in [*(merged.get(key) or []), *(incoming.get(key) or [])]:
            if not isinstance(item, dict):
                continue
            marker = str(item.get(id_key) or item.get("n") or item.get("title") or item.get("role") or "").strip().lower()
            if not marker or marker in seen:
                continue
            seen.add(marker)
            rows.append(item)
        merged[key] = rows
    for key in ["education", "certifications", "achievements"]:
        seen_text: set[str] = set()
        values: list[str] = []
        for item in [*(merged.get(key) or []), *(incoming.get(key) or [])]:
            text = str(item.get("title") if isinstance(item, dict) else item or "").strip()
            marker = text.lower()
            if text and marker not in seen_text:
                seen_text.add(marker)
                values.append(text)
        merged[key] = values
    return merged


def refresh_profile_snapshot(db_path: str | None = None) -> None:
    try:
        save_profile_snapshot(read_profile_from_graph(), db_path)
    except Exception:
        pass


def purge_profile_deletion_tombstones(db_path: str | None = None) -> dict:
    deletions = _load_profile_deletions(db_path)
    purged = 0

    def deleted(key: str, *values) -> bool:
        tokens = _delete_tokens(values)
        return bool(tokens.intersection(deletions.get(key, [])))

    for row in _query_rows("MATCH (s:Skill) RETURN s.id, s.n"):
        node_id, name = str(row[0] or ""), str(row[1] or "")
        if deleted("skills", node_id, name, hash_id(name)):
            delete_vec_id_from_all(node_id)
            _safe_execute("MATCH (s:Skill) WHERE s.id = $id DETACH DELETE s", {"id": node_id})
            purged += 1

    for row in _query_rows("MATCH (p:Project) RETURN p.id, p.title"):
        node_id, title = str(row[0] or ""), str(row[1] or "")
        if deleted("projects", node_id, title, hash_id(title)):
            delete_vec_id_from_all(node_id)
            _safe_execute("MATCH (p:Project) WHERE p.id = $id DETACH DELETE p", {"id": node_id})
            purged += 1

    for row in _query_rows("MATCH (e:Experience) RETURN e.id, e.role, e.co"):
        node_id = str(row[0] or "")
        role = str(row[1] or "")
        company = str(row[2] or "")
        if deleted("exp", node_id, role, company, role + company, " at ".join(part for part in [role, company] if part), " - ".join(part for part in [role, company] if part)):
            delete_vec_id_from_all(node_id)
            _safe_execute("MATCH (e:Experience) WHERE e.id = $id DETACH DELETE e", {"id": node_id})
            purged += 1

    for label, key in [("Education", "education"), ("Certification", "certifications"), ("Achievement", "achievements")]:
        for row in _query_rows(f"MATCH (n:{label}) RETURN n.id, n.title"):
            node_id, title = str(row[0] or ""), str(row[1] or "")
            if deleted(key, node_id, title, hash_id(title)):
                delete_vec_id_from_all(node_id)
                _safe_execute(f"MATCH (n:{label}) WHERE n.id = $id DETACH DELETE n", {"id": node_id})
                purged += 1

    if purged:
        refresh_profile_snapshot(db_path)
    return {"status": "ok", "purged": purged}


def sync_vectors_from_graph() -> dict:
    purge_profile_deletion_tombstones()
    deleted_bad_rows = prune_bad_vector_rows()
    candidates = []
    skills = []
    projects = []
    experiences = []
    credentials = []
    try:
        result = execute_query("MATCH (c:Candidate) RETURN c.id, c.n, c.s")
        while result and result.has_next():
            candidates.append(result.get_next())
        result = execute_query("MATCH (s:Skill) RETURN s.id, s.n, s.cat")
        while result and result.has_next():
            skills.append(result.get_next())
        result = execute_query("MATCH (p:Project) RETURN p.id, p.title, p.stack, p.impact")
        while result and result.has_next():
            projects.append(result.get_next())
        result = execute_query("MATCH (e:Experience) RETURN e.id, e.role, e.co, e.period, e.d")
        while result and result.has_next():
            experiences.append(result.get_next())
        for label in ["Certification", "Education", "Achievement"]:
            result = execute_query(f"MATCH (n:{label}) RETURN n.id, n.title")
            while result and result.has_next():
                row = result.get_next()
                credentials.append([row[0], row[1], label])
    except Exception as exc:
        return {"status": "error", "synced": 0, "error": str(exc)}

    synced = 0
    profile_parts: list[str] = []
    for candidate_id, name, summary in candidates:
        if is_bad_vector_label(name) and is_bad_vector_label(summary):
            continue
        add_candidate_vec(str(candidate_id), str(name or ""), str(summary or ""))
        profile_parts.append(profile_text(name, summary))
        synced += 1
    for skill_id, name, category in skills:
        if is_bad_vector_label(name):
            continue
        add_skill_vec(str(skill_id), str(name), str(category or "general"))
        profile_parts.append(skill_text(name, category))
        synced += 1
    for project_id, title, stack, impact in projects:
        if is_bad_vector_label(title):
            continue
        add_project_vec(str(project_id), str(title), str(stack or ""), str(impact or ""))
        profile_parts.append(project_text(title, stack, impact))
        synced += 1
    for experience_id, role, company, period, description in experiences:
        if is_bad_vector_label(role) and is_bad_vector_label(company):
            continue
        add_experience_vec(str(experience_id), str(role or ""), str(company or ""), str(period or ""), str(description or ""))
        profile_parts.append(experience_text(role, company, period, description))
        synced += 1
    for credential_id, title, kind in credentials:
        if is_bad_vector_label(title):
            continue
        add_credential_vec(str(credential_id), str(title), str(kind))
        profile_parts.append(credential_text(title, kind))
        synced += 1
    if profile_parts:
        add_profile_vec("profile:default", "Complete profile", "\n".join(profile_parts))
        synced += 1
    return {"status": "ok", "synced": synced, "deleted_bad_rows": deleted_bad_rows}


def _candidate_id() -> str | None:
    rows = _query_rows("MATCH (c:Candidate) RETURN c.id LIMIT 1")
    return rows[0][0] if rows else None


def _link_to_candidate(label: str, node_id: str, rel: str) -> None:
    candidate_id = _candidate_id()
    if not candidate_id:
        return
    try:
        execute_query(
            f"MATCH (a:Candidate {{id: $s}}), (b:{label} {{id: $d}}) MERGE (a)-[:{rel}]->(b)",
            {"s": candidate_id, "d": node_id},
        )
    except Exception:
        pass


def _unlink_outgoing(label: str, node_id: str, rel: str) -> None:
    try:
        execute_query(f"MATCH (n:{label} {{id: $id}})-[r:{rel}]->() DELETE r", {"id": node_id})
    except Exception:
        pass


def _skill_rows_by_name() -> dict[str, str]:
    rows: dict[str, str] = {}
    for row in _query_rows("MATCH (s:Skill) RETURN s.id, s.n"):
        name = str(row[1] or "").strip().lower()
        if name:
            rows[name] = str(row[0] or "")
    return rows


def _link_project_skills(project_id: str, stack: str, db_path: str | None = None, replace: bool = False) -> None:
    if replace:
        _unlink_outgoing("Project", project_id, "PROJ_UTILIZES")
    for skill_name in stack_list(stack):
        skill = add_skill(skill_name, "project_stack", db_path)
        try:
            execute_query(
                "MATCH (p:Project {id: $project_id}), (s:Skill {id: $skill_id}) MERGE (p)-[:PROJ_UTILIZES]->(s)",
                {"project_id": project_id, "skill_id": skill["id"]},
            )
        except Exception:
            pass


def _link_experience_skills(experience_id: str, text: str, replace: bool = False) -> None:
    if replace:
        _unlink_outgoing("Experience", experience_id, "EXP_UTILIZES")
    lower_text = str(text or "").lower()
    if not lower_text:
        return
    for skill_name, skill_id in _skill_rows_by_name().items():
        if len(skill_name) < 2:
            continue
        pattern = r"(?<![a-z0-9+#.-])" + re.escape(skill_name) + r"(?![a-z0-9+#.-])"
        if re.search(pattern, lower_text):
            try:
                execute_query(
                    "MATCH (e:Experience {id: $experience_id}), (s:Skill {id: $skill_id}) MERGE (e)-[:EXP_UTILIZES]->(s)",
                    {"experience_id": experience_id, "skill_id": skill_id},
                )
            except Exception:
                pass


def delete_vec_rows(table_name: str, ids: list[str]) -> None:
    ids = [str(item or "").strip() for item in ids if str(item or "").strip()]
    if not ids:
        return
    try:
        if table_name not in vec_table_names():
            return
        quoted = ["'" + item.replace("'", "''") + "'" for item in ids]
        vec.open_table(table_name).delete("id IN (" + ", ".join(quoted) + ")")
    except Exception:
        pass


def delete_vec_id_from_all(row_id: str) -> None:
    for table_name in ["profile", "candidates", "skills", "projects", "experiences", "credentials"]:
        delete_vec_rows(table_name, [row_id])


def prune_bad_vector_rows() -> int:
    deleted = 0
    for table_name in ["profile", "candidates", "skills", "projects", "experiences", "credentials"]:
        try:
            if table_name not in vec_table_names():
                continue
            table = vec.open_table(table_name)
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
        except Exception:
            continue
    return deleted


def vec_table_names() -> list[str]:
    raw = vec.list_tables()
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if hasattr(raw, "tables"):
        return [str(item) for item in raw.tables]
    if isinstance(raw, dict):
        tables = raw.get("tables", raw)
        if isinstance(tables, list):
            return [str(item) for item in tables]
    try:
        pairs = dict(raw)
        tables = pairs.get("tables", [])
        if isinstance(tables, list):
            return [str(item) for item in tables]
    except Exception:
        pass
    return [str(item) for item in raw]


def put_vec_rows(table_name: str, rows: list[dict]) -> None:
    if not rows:
        return
    ids = [str(row.get("id") or "").strip() for row in rows if str(row.get("id") or "").strip()]
    try:
        if table_name in vec_table_names():
            rows = _rows_for_existing_table(table_name, rows)
            delete_vec_rows(table_name, ids)
            vec.open_table(table_name).add(rows)
        else:
            vec.create_table(table_name, data=rows)
    except Exception as exc:
        _log.warning("vector write failed for %s: %s", table_name, exc)


def _rows_for_existing_table(table_name: str, rows: list[dict]) -> list[dict]:
    try:
        table = vec.open_table(table_name)
        schema = table.to_arrow().schema
        field_names = set(schema.names)
        if not field_names:
            return rows
        return [{key: value for key, value in row.items() if key in field_names} for row in rows]
    except Exception:
        return rows


def embed_rows(table_name: str, rows: list[dict], texts: Iterable[str]) -> None:
    try:
        from data.vector.embeddings import embed_texts

        pairs = [
            (row, str(text or "").strip())
            for row, text in zip(rows, texts)
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
        put_vec_rows(table_name, [{**row, "text": text, "vector": vector} for row, text, vector in zip(clean_rows, clean_texts, vectors)])
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


def add_skill(name: str, category: str, db_path: str | None = None) -> dict:
    name = str(name or "").strip()
    category = str(category or "general").strip() or "general"
    skill_id = hash_id(name)
    _forget_profile_deletion("skills", [skill_id, name], db_path)
    try:
        execute_query("CREATE (:Skill {id: $id, n: $n, cat: $cat})", {"id": skill_id, "n": name, "cat": category})
    except Exception:
        _safe_execute(
            "MATCH (s:Skill) WHERE s.id = $id SET s.n = $n, s.cat = $cat",
            {"id": skill_id, "n": name, "cat": category},
        )
    if not _bulk_import_active():
        try:
            add_skill_vec(skill_id, name, category)
        except Exception:
            pass
    _link_to_candidate("Skill", skill_id, "HAS_SKILL")
    _refresh_after_write(db_path)
    _save_profile_patch({"skills": [{"id": skill_id, "n": name, "cat": category}]}, db_path)
    return {"id": skill_id, "n": name, "cat": category}


def update_skill(skill_id: str, name: str, category: str, db_path: str | None = None) -> dict:
    name = str(name or "").strip()
    category = str(category or "general").strip() or "general"
    _forget_profile_deletion("skills", [skill_id, name, hash_id(name)], db_path)
    _safe_execute(
        "MATCH (s:Skill) WHERE s.id = $id SET s.n = $n, s.cat = $cat",
        {"id": skill_id, "n": name, "cat": category},
    )
    if not _bulk_import_active():
        try:
            add_skill_vec(skill_id, name, category)
        except Exception:
            pass
    _link_to_candidate("Skill", skill_id, "HAS_SKILL")
    _refresh_after_write(db_path)
    snapshot = load_profile_snapshot(db_path)
    skills = []
    for item in snapshot.get("skills", []) or []:
        if isinstance(item, dict) and str(item.get("id") or "") == str(skill_id):
            skills.append({"id": skill_id, "n": name, "cat": category})
        else:
            skills.append(item)
    if not any(isinstance(item, dict) and str(item.get("id") or "") == str(skill_id) for item in skills):
        skills.append({"id": skill_id, "n": name, "cat": category})
    save_profile_snapshot({**normal_profile(snapshot), "skills": skills}, db_path)
    return {"id": skill_id, "n": name, "cat": category}


@_profile_write_locked
def delete_skill(skill_id: str, db_path: str | None = None) -> None:
    value = unquote(str(skill_id or "")).strip()
    delete_ids = _skill_delete_ids(value)
    _remember_profile_deletion("skills", [value, *delete_ids], db_path)
    delete_vec_rows("skills", delete_ids)
    for node_id in delete_ids:
        delete_vec_id_from_all(node_id)
        _safe_execute("MATCH (s:Skill) WHERE s.id = $id DETACH DELETE s", {"id": node_id})
    snapshot = normal_profile(load_profile_snapshot(db_path))
    delete_id_set = set(delete_ids)
    delete_key = _norm_key(value)
    snapshot["skills"] = [
        item
        for item in snapshot.get("skills", [])
        if not (
            isinstance(item, dict)
            and (
                str(item.get("id") or "") in delete_id_set
                or hash_id(str(item.get("n") or "").strip()) in delete_id_set
                or _norm_key(item.get("n")) == delete_key
            )
        )
    ]
    save_profile_snapshot(snapshot, db_path, allow_empty=True)


def add_experience(role: str, company: str, period: str, description: str, db_path: str | None = None) -> dict:
    role = str(role or "").strip()
    company = str(company or "").strip()
    period = str(period or "").strip()
    description = str(description or "").strip()
    experience_id = hash_id(role + company)
    _forget_profile_deletion("exp", [experience_id, role, company, role + company, " at ".join(part for part in [role, company] if part)], db_path)
    try:
        execute_query(
            "CREATE (:Experience {id: $id, role: $role, co: $co, period: $period, d: $d})",
            {"id": experience_id, "role": role, "co": company, "period": period, "d": description},
        )
    except Exception:
        _safe_execute(
            "MATCH (e:Experience) WHERE e.id = $id SET e.role = $role, e.co = $co, e.period = $period, e.d = $d",
            {"id": experience_id, "role": role, "co": company, "period": period, "d": description},
        )
    _link_to_candidate("Experience", experience_id, "WORKED_AS")
    _link_experience_skills(experience_id, f"{role} {company} {description}")
    if not _bulk_import_active():
        try:
            add_experience_vec(experience_id, role, company, period, description)
        except Exception:
            pass
    _refresh_after_write(db_path)
    _save_profile_patch({"exp": [{"id": experience_id, "role": role, "co": company, "period": period, "d": description}]}, db_path)
    return {"id": experience_id, "role": role, "co": company, "period": period, "d": description}


def update_experience(experience_id: str, role: str, company: str, period: str, description: str, db_path: str | None = None) -> dict:
    role = str(role or "").strip()
    company = str(company or "").strip()
    period = str(period or "").strip()
    description = str(description or "").strip()
    _forget_profile_deletion("exp", [experience_id, role, company, role + company, " at ".join(part for part in [role, company] if part)], db_path)
    _safe_execute(
        "MATCH (e:Experience) WHERE e.id = $id SET e.role = $role, e.co = $co, e.period = $period, e.d = $d",
        {"id": experience_id, "role": role, "co": company, "period": period, "d": description},
    )
    _link_to_candidate("Experience", experience_id, "WORKED_AS")
    _link_experience_skills(experience_id, f"{role} {company} {description}", replace=True)
    if not _bulk_import_active():
        try:
            add_experience_vec(experience_id, role, company, period, description)
        except Exception:
            pass
    _refresh_after_write(db_path)
    snapshot = normal_profile(load_profile_snapshot(db_path))
    row = {"id": experience_id, "role": role, "co": company, "period": period, "d": description}
    snapshot["exp"] = [row if isinstance(item, dict) and str(item.get("id") or "") == str(experience_id) else item for item in snapshot.get("exp", [])]
    if not any(isinstance(item, dict) and str(item.get("id") or "") == str(experience_id) for item in snapshot["exp"]):
        snapshot["exp"].append(row)
    save_profile_snapshot(snapshot, db_path)
    return {"id": experience_id, "role": role, "co": company, "period": period, "d": description}


def delete_experience(experience_id: str, db_path: str | None = None) -> None:
    value = unquote(str(experience_id or "")).strip()
    delete_ids = _experience_delete_ids(value)
    _remember_profile_deletion("exp", [value, *delete_ids], db_path)
    delete_vec_rows("experiences", delete_ids)
    for node_id in delete_ids:
        delete_vec_id_from_all(node_id)
        _safe_execute("MATCH (e:Experience) WHERE e.id = $id DETACH DELETE e", {"id": node_id})
    snapshot = normal_profile(load_profile_snapshot(db_path))
    delete_id_set = set(delete_ids)
    delete_key = _norm_key(value)
    snapshot["exp"] = [
        item
        for item in snapshot.get("exp", [])
        if not (
            isinstance(item, dict)
            and (
                str(item.get("id") or "") in delete_id_set
                or hash_id(str(item.get("role") or "") + str(item.get("co") or "")) in delete_id_set
                or _norm_key(" at ".join(part for part in [item.get("role"), item.get("co")] if part)) == delete_key
            )
        )
    ]
    save_profile_snapshot(snapshot, db_path, allow_empty=True)


def add_project(title: str, stack: str, repo: str, impact: str, db_path: str | None = None) -> dict:
    title = str(title or "").strip()
    stack = str(stack or "").strip()
    repo = str(repo or "").strip()
    impact = str(impact or "").strip()
    project_id = hash_id(title)
    _forget_profile_deletion("projects", [project_id, title], db_path)
    try:
        execute_query(
            "CREATE (:Project {id: $id, title: $title, stack: $stack, repo: $repo, impact: $impact})",
            {"id": project_id, "title": title, "stack": stack, "repo": repo, "impact": impact},
        )
    except Exception:
        _safe_execute(
            "MATCH (p:Project) WHERE p.id = $id SET p.title = $title, p.stack = $stack, p.repo = $repo, p.impact = $impact",
            {"id": project_id, "title": title, "stack": stack, "repo": repo, "impact": impact},
        )
    _link_to_candidate("Project", project_id, "BUILT")
    _link_project_skills(project_id, stack, db_path)
    if not _bulk_import_active():
        try:
            add_project_vec(project_id, title, stack, impact)
        except Exception:
            pass
    _refresh_after_write(db_path)
    _save_profile_patch({"projects": [{"id": project_id, "title": title, "stack": stack_list(stack), "repo": repo, "impact": impact}]}, db_path)
    return {"id": project_id, "title": title, "stack": stack.split(",") if stack else [], "repo": repo, "impact": impact}


def update_project(project_id: str, title: str, stack: str, repo: str, impact: str, db_path: str | None = None) -> dict:
    title = str(title or "").strip()
    stack = str(stack or "").strip()
    repo = str(repo or "").strip()
    impact = str(impact or "").strip()
    _forget_profile_deletion("projects", [project_id, title, hash_id(title)], db_path)
    _safe_execute(
        "MATCH (p:Project) WHERE p.id = $id SET p.title = $title, p.stack = $stack, p.repo = $repo, p.impact = $impact",
        {"id": project_id, "title": title, "stack": stack, "repo": repo, "impact": impact},
    )
    _link_to_candidate("Project", project_id, "BUILT")
    _link_project_skills(project_id, stack, db_path, replace=True)
    if not _bulk_import_active():
        try:
            add_project_vec(project_id, title, stack, impact)
        except Exception:
            pass
    _refresh_after_write(db_path)
    snapshot = normal_profile(load_profile_snapshot(db_path))
    row = {"id": project_id, "title": title, "stack": stack_list(stack), "repo": repo, "impact": impact}
    snapshot["projects"] = [row if isinstance(item, dict) and str(item.get("id") or "") == str(project_id) else item for item in snapshot.get("projects", [])]
    if not any(isinstance(item, dict) and str(item.get("id") or "") == str(project_id) for item in snapshot["projects"]):
        snapshot["projects"].append(row)
    save_profile_snapshot(snapshot, db_path)
    return {"id": project_id, "title": title, "stack": stack.split(",") if stack else [], "repo": repo, "impact": impact}


def delete_project(project_id: str, db_path: str | None = None) -> None:
    value = unquote(str(project_id or "")).strip()
    delete_ids = _project_delete_ids(value)
    _remember_profile_deletion("projects", [value, *delete_ids], db_path)
    delete_vec_rows("projects", delete_ids)
    for node_id in delete_ids:
        delete_vec_id_from_all(node_id)
        _safe_execute("MATCH (p:Project) WHERE p.id = $id DETACH DELETE p", {"id": node_id})
    snapshot = normal_profile(load_profile_snapshot(db_path))
    delete_id_set = set(delete_ids)
    delete_key = _norm_key(value)
    snapshot["projects"] = [
        item
        for item in snapshot.get("projects", [])
        if not (
            isinstance(item, dict)
            and (
                str(item.get("id") or "") in delete_id_set
                or hash_id(str(item.get("title") or "").strip()) in delete_id_set
                or _norm_key(item.get("title")) == delete_key
            )
        )
    ]
    save_profile_snapshot(snapshot, db_path, allow_empty=True)


def _add_text_node(label: str, rel: str, title: str, db_path: str | None = None) -> dict:
    title = str(title or "").strip()
    node_id = hash_id(title)
    key = {
        "Education": "education",
        "Certification": "certifications",
        "Achievement": "achievements",
    }.get(label)
    if key:
        _forget_profile_deletion(key, [node_id, title], db_path)
    try:
        execute_query(f"CREATE (:{label} {{id: $id, title: $title}})", {"id": node_id, "title": title})
    except Exception:
        pass
    _link_to_candidate(label, node_id, rel)
    if not _bulk_import_active():
        try:
            add_credential_vec(node_id, title, label)
        except Exception:
            pass
    _refresh_after_write(db_path)
    if key:
        _save_profile_patch({key: [title]}, db_path)
    return {"id": node_id, "title": title}


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


def _skill_delete_ids(skill_id_or_name: str) -> list[str]:
    value = unquote(str(skill_id_or_name or "")).strip()
    if not value:
        return []
    ids = [value, hash_id(value)]
    wanted_key = _norm_key(value)
    for row in _query_rows("MATCH (s:Skill) RETURN s.id, s.n"):
        node_id = str(row[0] or "").strip()
        name = str(row[1] or "").strip()
        if node_id in ids or _norm_key(name) == wanted_key or _norm_key(node_id) == wanted_key:
            ids.append(node_id)
    return _dedupe_ids(ids)


def _project_delete_ids(project_id_or_title: str) -> list[str]:
    value = unquote(str(project_id_or_title or "")).strip()
    if not value:
        return []
    ids = [value, hash_id(value)]
    wanted_key = _norm_key(value)
    for row in _query_rows("MATCH (p:Project) RETURN p.id, p.title"):
        node_id = str(row[0] or "").strip()
        title = str(row[1] or "").strip()
        if node_id in ids or _norm_key(title) == wanted_key or _norm_key(node_id) == wanted_key:
            ids.append(node_id)
    return _dedupe_ids(ids)


def _experience_delete_ids(experience_id_or_label: str) -> list[str]:
    value = unquote(str(experience_id_or_label or "")).strip()
    if not value:
        return []
    ids = [value, hash_id(value)]
    wanted_key = _norm_key(value)
    for row in _query_rows("MATCH (e:Experience) RETURN e.id, e.role, e.co"):
        node_id = str(row[0] or "").strip()
        role = str(row[1] or "").strip()
        company = str(row[2] or "").strip()
        labels = [
            node_id,
            role,
            company,
            role + company,
            " at ".join(part for part in [role, company] if part),
            " - ".join(part for part in [role, company] if part),
        ]
        if node_id in ids or hash_id(role + company) in ids or any(_norm_key(label) == wanted_key for label in labels):
            ids.append(node_id)
            ids.append(hash_id(role + company))
    return _dedupe_ids(ids)


def _text_node_ids(label: str, entry: str) -> list[str]:
    entry = unquote(str(entry or "")).strip()
    if not entry:
        return []
    wanted = {entry, hash_id(entry)}
    wanted_key = _entry_key(entry)
    ids: list[str] = []
    for row in _query_rows(f"MATCH (n:{label}) RETURN n.id, n.title"):
        node_id = str(row[0] or "").strip()
        title = str(row[1] or "").strip()
        if node_id in wanted or _entry_key(title) == wanted_key:
            ids.append(node_id)
    if not ids:
        ids.append(hash_id(entry))
    return list(dict.fromkeys(ids))


@_profile_write_locked
def _delete_text_node(label: str, profile_key: str, entry: str, db_path: str | None = None) -> None:
    entry = unquote(str(entry or "")).strip()
    if not entry:
        return
    delete_ids = _text_node_ids(label, entry)
    _remember_profile_deletion(profile_key, [entry, *delete_ids], db_path)
    for node_id in delete_ids:
        delete_vec_id_from_all(node_id)
        _safe_execute(f"MATCH (n:{label}) WHERE n.id = $id DETACH DELETE n", {"id": node_id})

    snapshot = normal_profile(load_profile_snapshot(db_path))
    entry_key = _entry_key(entry)
    delete_id_set = set(delete_ids)
    snapshot[profile_key] = [
        item
        for item in snapshot.get(profile_key, [])
        if _entry_key(item) != entry_key and hash_id(_entry_text(item)) not in delete_id_set
    ]
    save_profile_snapshot(snapshot, db_path, allow_empty=True)


def add_education(title: str, db_path: str | None = None) -> dict:
    return _add_text_node("Education", "HAS_EDUCATION", title, db_path)


def add_certification(title: str, db_path: str | None = None) -> dict:
    return _add_text_node("Certification", "HAS_CERTIFICATION", title, db_path)


def add_achievement(title: str, db_path: str | None = None) -> dict:
    return _add_text_node("Achievement", "HAS_ACHIEVEMENT", title, db_path)


def delete_education(entry: str, db_path: str | None = None) -> None:
    _delete_text_node("Education", "education", entry, db_path)


def delete_certification(entry: str, db_path: str | None = None) -> None:
    _delete_text_node("Certification", "certifications", entry, db_path)


def delete_achievement(entry: str, db_path: str | None = None) -> None:
    _delete_text_node("Achievement", "achievements", entry, db_path)


def update_identity(identity: dict, db_path: str | None = None) -> dict:
    clean = {key: str(identity.get(key) or "").strip() for key in IDENTITY_KEYS if key in identity}
    if clean:
        try:
            save_settings(clean, db_path) if db_path else save_settings(clean)
        except Exception as exc:
            _log.warning("identity settings save skipped: %s", exc)
    try:
        snapshot = normal_profile(load_profile_snapshot(db_path) or read_profile_from_graph())
    except Exception:
        snapshot = empty_profile()
    snapshot["identity"] = {**snapshot.get("identity", {}), **clean}
    save_profile_snapshot(snapshot, db_path)
    return {key: str(snapshot["identity"].get(key) or "") for key in IDENTITY_KEYS}


def update_candidate(name: str, summary: str, db_path: str | None = None) -> dict:
    name = str(name or "").strip()
    summary = clean_profile_summary(str(summary or "").strip())
    candidate_id = hash_id(name or "Candidate")
    _refresh_after_write(db_path)
    try:
        result = execute_query("MATCH (n:Candidate) RETURN n.id LIMIT 1")
        if result is not None and result.has_next():
            row = result.get_next()
            candidate_id = str(row[0] or candidate_id)
            execute_query(
                "MATCH (n:Candidate {id: $id}) SET n.n = $n, n.s = $s",
                {"id": candidate_id, "n": name, "s": summary},
            )
        elif result is not None:
            execute_query(
                "CREATE (:Candidate {id: $id, n: $n, s: $s})",
                {"id": candidate_id, "n": name, "s": summary},
            )
    except Exception as exc:
        _log.warning("candidate graph update skipped: %s", exc)
    if not _bulk_import_active():
        try:
            add_candidate_vec(candidate_id, name, summary)
        except Exception:
            pass
    _refresh_after_write(db_path)
    _save_profile_patch({"n": name, "s": summary}, db_path)
    return {"n": name, "s": summary}
