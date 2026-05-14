from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import re
from collections.abc import Iterable

from core.logging import get_logger
from data.graph.connection import execute_query
from data.sqlite.settings import get_setting, save_settings
from data.vector.connection import vec
from graph_service.helpers import is_bad_vector_label

_log = get_logger(__name__)

PROFILE_SNAPSHOT_KEY = "profile_snapshot_json"
IDENTITY_KEYS = ("email", "phone", "linkedin_url", "github_url", "website_url", "city")
_BULK_IMPORT_DEPTH: contextvars.ContextVar[int] = contextvars.ContextVar("profile_bulk_import_depth", default=0)


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


def stack_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


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
        "s": str(profile.get("s") or ""),
        "skills": list(profile.get("skills") or []),
        "projects": list(profile.get("projects") or []),
        "exp": list(profile.get("exp") or []),
        "certifications": list(profile.get("certifications") or profile.get("certs") or []),
        "education": list(profile.get("education") or []),
        "achievements": list(profile.get("achievements") or profile.get("awards") or []),
        "identity": {key: str(identity.get(key) or profile.get(key) or "") for key in IDENTITY_KEYS},
    }


def load_profile_snapshot(db_path: str | None = None) -> dict:
    try:
        raw = get_setting(PROFILE_SNAPSHOT_KEY, "", db_path) if db_path else get_setting(PROFILE_SNAPSHOT_KEY)
        if not raw:
            return {}
        profile = normal_profile(json.loads(raw or "{}"))
        return profile if profile_has_data(profile) else {}
    except Exception:
        return {}


def save_profile_snapshot(profile: dict, db_path: str | None = None) -> None:
    profile = normal_profile(profile)
    if not profile_has_data(profile):
        return
    try:
        payload = {PROFILE_SNAPSHOT_KEY: json.dumps(profile, ensure_ascii=False)}
        if db_path:
            save_settings(payload, db_path)
        else:
            save_settings(payload)
    except Exception:
        pass


def read_profile_from_graph() -> dict:
    result = execute_query("MATCH (n:Candidate) RETURN n.id, n.n, n.s")
    if result is None:
        return empty_profile()
    candidates = []
    while result.has_next():
        candidates.append(result.get_next())
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

    result = execute_query("MATCH (n:Skill) RETURN n.id, n.n, n.cat")
    skills = []
    while result.has_next():
        row = result.get_next()
        skills.append({"id": row[0], "n": row[1], "cat": row[2]})

    result = execute_query("MATCH (n:Project) RETURN n.id, n.title, n.stack, n.repo, n.impact")
    projects = []
    while result.has_next():
        row = result.get_next()
        projects.append({"id": row[0], "title": row[1], "stack": stack_list(row[2]), "repo": row[3], "impact": row[4]})

    result = execute_query("MATCH (n:Experience) RETURN n.id, n.role, n.co, n.period, n.d")
    experience = []
    while result.has_next():
        row = result.get_next()
        experience.append({"id": row[0], "role": row[1], "co": row[2], "period": row[3], "d": row[4]})

    def read_text_nodes(label: str) -> list[str]:
        try:
            rows = execute_query(f"MATCH (n:{label}) RETURN n.title")
        except Exception:
            return []
        items: list[str] = []
        while rows.has_next():
            row = rows.get_next()
            text = str(row[0] or "").strip()
            if text:
                items.append(text)
        return items

    return {
        "n": candidate[1],
        "s": candidate[2],
        "skills": skills,
        "projects": projects,
        "exp": experience,
        "certifications": read_text_nodes("Certification"),
        "education": read_text_nodes("Education"),
        "achievements": read_text_nodes("Achievement"),
        "identity": {key: get_setting(key, "") for key in IDENTITY_KEYS},
    }


def get_profile(db_path: str | None = None) -> dict:
    snapshot = load_profile_snapshot(db_path)
    try:
        profile = normal_profile(read_profile_from_graph())
    except Exception as exc:
        if snapshot:
            return snapshot
        _log.error("profile read failed: %s", exc)
        return empty_profile()

    if profile_has_data(profile):
        save_profile_snapshot(profile, db_path)
        return profile
    return snapshot or profile


def refresh_profile_snapshot(db_path: str | None = None) -> None:
    try:
        save_profile_snapshot(read_profile_from_graph(), db_path)
    except Exception:
        pass


def sync_vectors_from_graph() -> dict:
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
    try:
        result = execute_query("MATCH (c:Candidate) RETURN c.id LIMIT 1")
        return result.get_next()[0] if result.has_next() else None
    except Exception:
        return None


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
    try:
        result = execute_query("MATCH (s:Skill) RETURN s.id, s.n")
        while result and result.has_next():
            row = result.get_next()
            name = str(row[1] or "").strip().lower()
            if name:
                rows[name] = str(row[0] or "")
    except Exception:
        pass
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
    try:
        execute_query("CREATE (:Skill {id: $id, n: $n, cat: $cat})", {"id": skill_id, "n": name, "cat": category})
    except Exception:
        execute_query(
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
    return {"id": skill_id, "n": name, "cat": category}


def update_skill(skill_id: str, name: str, category: str, db_path: str | None = None) -> dict:
    name = str(name or "").strip()
    category = str(category or "general").strip() or "general"
    execute_query(
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
    return {"id": skill_id, "n": name, "cat": category}


def delete_skill(skill_id: str, db_path: str | None = None) -> None:
    delete_vec_rows("skills", [skill_id])
    delete_vec_id_from_all(skill_id)
    execute_query("MATCH (s:Skill) WHERE s.id = $id DETACH DELETE s", {"id": skill_id})
    _refresh_after_write(db_path)


def add_experience(role: str, company: str, period: str, description: str, db_path: str | None = None) -> dict:
    role = str(role or "").strip()
    company = str(company or "").strip()
    period = str(period or "").strip()
    description = str(description or "").strip()
    experience_id = hash_id(role + company)
    try:
        execute_query(
            "CREATE (:Experience {id: $id, role: $role, co: $co, period: $period, d: $d})",
            {"id": experience_id, "role": role, "co": company, "period": period, "d": description},
        )
    except Exception:
        execute_query(
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
    return {"id": experience_id, "role": role, "co": company, "period": period, "d": description}


def update_experience(experience_id: str, role: str, company: str, period: str, description: str, db_path: str | None = None) -> dict:
    role = str(role or "").strip()
    company = str(company or "").strip()
    period = str(period or "").strip()
    description = str(description or "").strip()
    execute_query(
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
    return {"id": experience_id, "role": role, "co": company, "period": period, "d": description}


def delete_experience(experience_id: str, db_path: str | None = None) -> None:
    _refresh_after_write(db_path)
    delete_vec_rows("experiences", [experience_id])
    delete_vec_id_from_all(experience_id)
    execute_query("MATCH (e:Experience) WHERE e.id = $id DETACH DELETE e", {"id": experience_id})
    _refresh_after_write(db_path)


def add_project(title: str, stack: str, repo: str, impact: str, db_path: str | None = None) -> dict:
    title = str(title or "").strip()
    stack = str(stack or "").strip()
    repo = str(repo or "").strip()
    impact = str(impact or "").strip()
    project_id = hash_id(title)
    try:
        execute_query(
            "CREATE (:Project {id: $id, title: $title, stack: $stack, repo: $repo, impact: $impact})",
            {"id": project_id, "title": title, "stack": stack, "repo": repo, "impact": impact},
        )
    except Exception:
        execute_query(
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
    return {"id": project_id, "title": title, "stack": stack.split(",") if stack else [], "repo": repo, "impact": impact}


def update_project(project_id: str, title: str, stack: str, repo: str, impact: str, db_path: str | None = None) -> dict:
    title = str(title or "").strip()
    stack = str(stack or "").strip()
    repo = str(repo or "").strip()
    impact = str(impact or "").strip()
    execute_query(
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
    return {"id": project_id, "title": title, "stack": stack.split(",") if stack else [], "repo": repo, "impact": impact}


def delete_project(project_id: str, db_path: str | None = None) -> None:
    delete_vec_rows("projects", [project_id])
    delete_vec_id_from_all(project_id)
    execute_query("MATCH (p:Project) WHERE p.id = $id DETACH DELETE p", {"id": project_id})
    _refresh_after_write(db_path)


def _add_text_node(label: str, rel: str, title: str, db_path: str | None = None) -> dict:
    title = str(title or "").strip()
    node_id = hash_id(title)
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
    return {"id": node_id, "title": title}


def add_education(title: str, db_path: str | None = None) -> dict:
    return _add_text_node("Education", "HAS_EDUCATION", title, db_path)


def add_certification(title: str, db_path: str | None = None) -> dict:
    return _add_text_node("Certification", "HAS_CERTIFICATION", title, db_path)


def add_achievement(title: str, db_path: str | None = None) -> dict:
    return _add_text_node("Achievement", "HAS_ACHIEVEMENT", title, db_path)


def update_identity(identity: dict, db_path: str | None = None) -> dict:
    clean = {key: str(identity.get(key) or "").strip() for key in IDENTITY_KEYS if key in identity}
    if clean:
        save_settings(clean, db_path) if db_path else save_settings(clean)
    try:
        snapshot = normal_profile(load_profile_snapshot(db_path) or read_profile_from_graph())
    except Exception:
        snapshot = empty_profile()
    snapshot["identity"] = {**snapshot.get("identity", {}), **clean}
    save_profile_snapshot(snapshot, db_path)
    return {key: str(snapshot["identity"].get(key) or "") for key in IDENTITY_KEYS}


def update_candidate(name: str, summary: str, db_path: str | None = None) -> dict:
    name = str(name or "").strip()
    summary = str(summary or "").strip()
    _refresh_after_write(db_path)
    result = execute_query("MATCH (n:Candidate) RETURN n.id LIMIT 1")
    if result.has_next():
        candidate_id = result.get_next()[0]
        execute_query(
            "MATCH (n:Candidate {id: $id}) SET n.n = $n, n.s = $s",
            {"id": candidate_id, "n": name, "s": summary},
        )
    else:
        candidate_id = hash_id(name)
        try:
            execute_query(
                "CREATE (:Candidate {id: $id, n: $n, s: $s})",
                {"id": candidate_id, "n": name, "s": summary},
            )
        except Exception:
            pass
    if not _bulk_import_active():
        try:
            add_candidate_vec(candidate_id, name, summary)
        except Exception:
            pass
    _refresh_after_write(db_path)
    return {"n": name, "s": summary}
