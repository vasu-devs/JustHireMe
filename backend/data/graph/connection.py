from __future__ import annotations

import os
import re
import threading
from datetime import datetime, timezone
from hashlib import md5
from itertools import combinations

from core.logging import get_logger

_log = get_logger(__name__)

try:
    import kuzu
except Exception as exc:
    kuzu = None
    _KUZU_IMPORT_ERROR = str(exc)
else:
    _KUZU_IMPORT_ERROR = ""

BASE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "JustHireMe")
GRAPH_PATH = os.path.join(BASE_DIR, "graph.kuzu")

_GRAPH_ERROR = ""
_GRAPH_DIR_READY = False
_graph_lock = threading.RLock()
db = None
conn = None

try:
    os.makedirs(BASE_DIR, exist_ok=True)
    _GRAPH_DIR_READY = True
except Exception as exc:
    _GRAPH_ERROR = str(exc)
    _log.warning("graph store path unavailable: %s", exc)

def _ensure_connection() -> bool:
    global db, conn, _GRAPH_ERROR
    if db is not None and conn is not None:
        return True
    with _graph_lock:
        if db is not None and conn is not None:
            return True
        try:
            if not _GRAPH_DIR_READY:
                raise RuntimeError(_GRAPH_ERROR or "Graph directory is not available")
            if kuzu is None:
                raise RuntimeError(_KUZU_IMPORT_ERROR or "Kuzu is not available")
            db = kuzu.Database(GRAPH_PATH)
            conn = kuzu.Connection(db)
            _GRAPH_ERROR = ""
            _init_graph_unlocked()
            return True
        except Exception as exc:
            db = None
            conn = None
            _GRAPH_ERROR = str(exc)
            _log.warning("graph store disabled: %s", exc)
            return False


def init_graph() -> None:
    _ensure_connection()


def _init_graph_unlocked() -> None:
    if conn is None:
        return
    for statement in [
        "CREATE NODE TABLE IF NOT EXISTS Candidate(id STRING, n STRING, s STRING, PRIMARY KEY(id))",
        "CREATE NODE TABLE IF NOT EXISTS Skill(id STRING, n STRING, cat STRING, PRIMARY KEY(id))",
        "CREATE NODE TABLE IF NOT EXISTS Project(id STRING, title STRING, stack STRING, repo STRING, impact STRING, PRIMARY KEY(id))",
        "CREATE NODE TABLE IF NOT EXISTS Experience(id STRING, role STRING, co STRING, period STRING, d STRING, PRIMARY KEY(id))",
        "CREATE NODE TABLE IF NOT EXISTS Certification(id STRING, title STRING, PRIMARY KEY(id))",
        "CREATE NODE TABLE IF NOT EXISTS Education(id STRING, title STRING, PRIMARY KEY(id))",
        "CREATE NODE TABLE IF NOT EXISTS Achievement(id STRING, title STRING, PRIMARY KEY(id))",
        "CREATE NODE TABLE IF NOT EXISTS JobLead(job_id STRING, title STRING, co STRING, url STRING, platform STRING, PRIMARY KEY(job_id))",
        "CREATE REL TABLE IF NOT EXISTS WORKED_AS(FROM Candidate TO Experience)",
        "CREATE REL TABLE IF NOT EXISTS BUILT(FROM Candidate TO Project)",
        "CREATE REL TABLE IF NOT EXISTS HAS_CERTIFICATION(FROM Candidate TO Certification)",
        "CREATE REL TABLE IF NOT EXISTS HAS_EDUCATION(FROM Candidate TO Education)",
        "CREATE REL TABLE IF NOT EXISTS HAS_ACHIEVEMENT(FROM Candidate TO Achievement)",
        "CREATE REL TABLE IF NOT EXISTS HAS_SKILL(FROM Candidate TO Skill)",
        "CREATE REL TABLE IF NOT EXISTS EXP_UTILIZES(FROM Experience TO Skill)",
        "CREATE REL TABLE IF NOT EXISTS PROJ_UTILIZES(FROM Project TO Skill)",
        "CREATE REL TABLE IF NOT EXISTS CERTIFIES(FROM Certification TO Skill)",
        "CREATE REL TABLE IF NOT EXISTS EDUCATES(FROM Education TO Skill)",
        "CREATE REL TABLE IF NOT EXISTS ACHIEVEMENT_USES(FROM Achievement TO Skill)",
        "CREATE REL TABLE IF NOT EXISTS RELATED_SKILL(FROM Skill TO Skill)",
        "CREATE REL TABLE IF NOT EXISTS SIMILAR_PROJECT(FROM Project TO Project)",
        "CREATE REL TABLE IF NOT EXISTS PROJECT_SUPPORTS_EXPERIENCE(FROM Project TO Experience)",
        "CREATE REL TABLE IF NOT EXISTS REQUIRES(FROM JobLead TO Skill)",
    ]:
        execute_query(statement)


def execute_query(query: str, params: dict | None = None):
    if not _ensure_connection() or conn is None:
        return None
    with _graph_lock:
        if params:
            return conn.execute(query, params)
        return conn.execute(query)


def graph_available() -> bool:
    return _ensure_connection() and db is not None and conn is not None


def graph_error() -> str:
    return friendly_graph_error(_GRAPH_ERROR)


def friendly_graph_error(error: str) -> str:
    text = str(error or "")
    lower = text.lower()
    if "could not set lock" in lower or "concurrency" in lower or "lock on file" in lower:
        return (
            "Kuzu graph is locked by another JustHireMe backend process. "
            "Close extra JustHireMe/Tauri windows or stop stale backend Python processes, then restart the app. "
            f"Raw error: {text}"
        )
    return text


def graph_counts() -> dict:
    out = {key: 0 for key in ["candidate", "skill", "project", "experience", "joblead"]}
    if not _ensure_connection() or conn is None:
        return out
    for table in ["Candidate", "Skill", "Project", "Experience", "JobLead"]:
        try:
            result = execute_query(f"MATCH (n:{table}) RETURN count(n)")
            out[table.lower()] = result.get_next()[0] if result.has_next() else 0
        except Exception as exc:
            _log.warning("graph count failed for %s: %s", table, exc)
    return out


def sync_profile_relationships() -> dict:
    if not _ensure_connection() or conn is None:
        return {"status": "disabled", "linked": 0, "error": graph_error()}
    linked = 0
    try:
        _clear_derived_profile_edges()
        candidates = _query_rows("MATCH (c:Candidate) RETURN c.id LIMIT 1")
        candidate_id = candidates[0][0] if candidates else _ensure_candidate_for_profile()
        for row in _query_rows("MATCH (p:Project) RETURN p.id"):
            execute_query(
                "MATCH (c:Candidate {id: $candidate_id}), (p:Project {id: $project_id}) MERGE (c)-[:BUILT]->(p)",
                {"candidate_id": candidate_id, "project_id": row[0]},
            )
            linked += 1
        for row in _query_rows("MATCH (e:Experience) RETURN e.id"):
            execute_query(
                "MATCH (c:Candidate {id: $candidate_id}), (e:Experience {id: $experience_id}) MERGE (c)-[:WORKED_AS]->(e)",
                {"candidate_id": candidate_id, "experience_id": row[0]},
            )
            linked += 1
        skill_rows = _query_rows("MATCH (s:Skill) RETURN s.id, s.n")
        skills_by_name = {str(row[1] or "").strip().lower(): str(row[0] or "") for row in skill_rows if str(row[1] or "").strip()}
        for row in _query_rows("MATCH (p:Project) RETURN p.stack"):
            for skill_name in _split_terms(row[0]):
                key = str(skill_name or "").strip().lower()
                if key and key not in skills_by_name:
                    skills_by_name[key] = _ensure_skill(skill_name, "project_stack")
        skill_rows = [[skill_id, skill_name] for skill_name, skill_id in skills_by_name.items()]
        for skill_id, _name in skill_rows:
            execute_query(
                "MATCH (c:Candidate {id: $candidate_id}), (s:Skill {id: $skill_id}) MERGE (c)-[:HAS_SKILL]->(s)",
                {"candidate_id": candidate_id, "skill_id": skill_id},
            )
            linked += 1

        credential_specs = [
            ("Certification", "HAS_CERTIFICATION", "CERTIFIES"),
            ("Education", "HAS_EDUCATION", "EDUCATES"),
            ("Achievement", "HAS_ACHIEVEMENT", "ACHIEVEMENT_USES"),
        ]
        for label, candidate_rel, skill_rel in credential_specs:
            for row in _query_rows(f"MATCH (n:{label}) RETURN n.id, n.title"):
                node_id = row[0]
                execute_query(
                    f"MATCH (c:Candidate {{id: $candidate_id}}), (n:{label} {{id: $node_id}}) MERGE (c)-[:{candidate_rel}]->(n)",
                    {"candidate_id": candidate_id, "node_id": node_id},
                )
                linked += 1
                for skill_id in _skill_ids_in_text(row[1], skills_by_name):
                    execute_query(
                        f"MATCH (n:{label} {{id: $node_id}}), (s:Skill {{id: $skill_id}}) MERGE (n)-[:{skill_rel}]->(s)",
                        {"node_id": node_id, "skill_id": skill_id},
                    )
                    linked += 1

        project_skills: dict[str, set[str]] = {}
        for row in _query_rows("MATCH (p:Project) RETURN p.id, p.title, p.stack, p.impact"):
            project_id = row[0]
            skill_ids = set()
            for skill_name in _split_terms(row[2]):
                skill_id = skills_by_name.get(str(skill_name or "").lower())
                if skill_id:
                    skill_ids.add(skill_id)
            skill_ids.update(_skill_ids_in_text(" ".join(str(item or "") for item in row[1:]), skills_by_name))
            project_skills[project_id] = skill_ids
            for skill_id in skill_ids:
                execute_query(
                    "MATCH (p:Project {id: $project_id}), (s:Skill {id: $skill_id}) MERGE (p)-[:PROJ_UTILIZES]->(s)",
                    {"project_id": project_id, "skill_id": skill_id},
                )
                linked += 1

        experience_skills: dict[str, set[str]] = {}
        for row in _query_rows("MATCH (e:Experience) RETURN e.id, e.role, e.co, e.period, e.d"):
            experience_id = row[0]
            skill_ids = set(_skill_ids_in_text(" ".join(str(item or "") for item in row[1:]), skills_by_name))
            experience_skills[experience_id] = skill_ids
            for skill_id in skill_ids:
                execute_query(
                    "MATCH (e:Experience {id: $experience_id}), (s:Skill {id: $skill_id}) MERGE (e)-[:EXP_UTILIZES]->(s)",
                    {"experience_id": experience_id, "skill_id": skill_id},
                )
                linked += 1

        for skill_ids in [*project_skills.values(), *experience_skills.values()]:
            for source_id, target_id in combinations(sorted(skill_ids), 2):
                execute_query(
                    "MATCH (a:Skill {id: $source_id}), (b:Skill {id: $target_id}) MERGE (a)-[:RELATED_SKILL]->(b)",
                    {"source_id": source_id, "target_id": target_id},
                )
                linked += 1

        for (project_a, skills_a), (project_b, skills_b) in combinations(project_skills.items(), 2):
            if not skills_a.intersection(skills_b):
                continue
            execute_query(
                "MATCH (a:Project {id: $project_a}), (b:Project {id: $project_b}) MERGE (a)-[:SIMILAR_PROJECT]->(b)",
                {"project_a": project_a, "project_b": project_b},
            )
            linked += 1

        for project_id, skill_ids in project_skills.items():
            for experience_id, exp_skill_ids in experience_skills.items():
                if not skill_ids.intersection(exp_skill_ids):
                    continue
                execute_query(
                    "MATCH (p:Project {id: $project_id}), (e:Experience {id: $experience_id}) MERGE (p)-[:PROJECT_SUPPORTS_EXPERIENCE]->(e)",
                    {"project_id": project_id, "experience_id": experience_id},
                )
                linked += 1
    except Exception as exc:
        _log.warning("graph profile relationship sync failed: %s", exc)
        return {"status": "error", "linked": linked, "error": str(exc)}
    return {"status": "ok", "linked": linked}


def _ensure_candidate_for_profile() -> str:
    has_profile_evidence = any(
        _query_rows(query)
        for query in [
            "MATCH (s:Skill) RETURN s.id LIMIT 1",
            "MATCH (p:Project) RETURN p.id LIMIT 1",
            "MATCH (e:Experience) RETURN e.id LIMIT 1",
            "MATCH (c:Certification) RETURN c.id LIMIT 1",
            "MATCH (e:Education) RETURN e.id LIMIT 1",
            "MATCH (a:Achievement) RETURN a.id LIMIT 1",
        ]
    )
    candidate_id = "profile-default"
    if has_profile_evidence:
        execute_query(
            "CREATE (:Candidate {id: $id, n: $n, s: $s})",
            {"id": candidate_id, "n": "Profile", "s": "Local profile evidence root"},
        )
    return candidate_id


def _ensure_skill(name: str, category: str) -> str:
    clean = str(name or "").strip()
    skill_id = md5(clean.encode()).hexdigest()[:12]
    try:
        execute_query(
            "CREATE (:Skill {id: $id, n: $n, cat: $cat})",
            {"id": skill_id, "n": clean, "cat": category},
        )
    except Exception:
        try:
            execute_query(
                "MATCH (s:Skill {id: $id}) SET s.n = $n, s.cat = $cat",
                {"id": skill_id, "n": clean, "cat": category},
            )
        except Exception:
            pass
    return skill_id


def _clear_derived_profile_edges() -> None:
    for query in [
        "MATCH (p:Project)-[r:PROJ_UTILIZES]->() DELETE r",
        "MATCH (e:Experience)-[r:EXP_UTILIZES]->() DELETE r",
        "MATCH (c:Certification)-[r:CERTIFIES]->() DELETE r",
        "MATCH (e:Education)-[r:EDUCATES]->() DELETE r",
        "MATCH (a:Achievement)-[r:ACHIEVEMENT_USES]->() DELETE r",
        "MATCH (s:Skill)-[r:RELATED_SKILL]->() DELETE r",
        "MATCH (p:Project)-[r:SIMILAR_PROJECT]->() DELETE r",
        "MATCH (p:Project)-[r:PROJECT_SUPPORTS_EXPERIENCE]->() DELETE r",
    ]:
        try:
            execute_query(query)
        except Exception as exc:
            _log.debug("derived edge cleanup failed: %s", exc)


def _skill_ids_in_text(text: str, skills_by_name: dict[str, str]) -> set[str]:
    text_value = str(text or "").lower()
    if not text_value:
        return set()
    out: set[str] = set()
    for skill_name, skill_id in skills_by_name.items():
        if len(skill_name) < 2:
            continue
        pattern = r"(?<![a-z0-9+#.-])" + re.escape(skill_name) + r"(?![a-z0-9+#.-])"
        if re.search(pattern, text_value):
            out.add(skill_id)
    return out


def sync_job_leads(leads: list[dict]) -> dict:
    if not _ensure_connection() or conn is None:
        return {"status": "disabled", "synced": 0, "error": graph_error()}
    job_leads = [lead for lead in leads if (lead.get("kind") or "job") == "job"]
    try:
        execute_query("MATCH (j:JobLead) DETACH DELETE j")
    except Exception as exc:
        _log.warning("graph job lead cleanup failed: %s", exc)
        return {"status": "error", "synced": 0, "error": str(exc)}

    skill_rows = _query_rows("MATCH (s:Skill) RETURN s.id, s.n")
    skills_by_name = {str(row[1] or "").strip().lower(): str(row[0] or "") for row in skill_rows if str(row[1] or "").strip()}
    synced = 0
    linked = 0
    for lead in job_leads:
        job_id = str(lead.get("job_id") or "").strip()
        if not job_id:
            continue
        try:
            execute_query(
                "CREATE (:JobLead {job_id: $job_id, title: $title, co: $co, url: $url, platform: $platform})",
                {
                    "job_id": job_id,
                    "title": str(lead.get("title") or "")[:500],
                    "co": str(lead.get("company") or "")[:240],
                    "url": str(lead.get("url") or "")[:1200],
                    "platform": str(lead.get("platform") or "")[:120],
                },
            )
            for skill_name in _lead_skill_terms(lead):
                skill_id = skills_by_name.get(skill_name.lower())
                if not skill_id:
                    continue
                try:
                    execute_query(
                        "MATCH (j:JobLead {job_id: $job_id}), (s:Skill {id: $skill_id}) MERGE (j)-[:REQUIRES]->(s)",
                        {"job_id": job_id, "skill_id": skill_id},
                    )
                    linked += 1
                except Exception as exc:
                    _log.debug("graph job skill link failed for %s/%s: %s", job_id, skill_id, exc)
            synced += 1
        except Exception as exc:
            _log.warning("graph job lead sync failed for %s: %s", job_id, exc)
    return {
        "status": "ok",
        "synced": synced,
        "linked": linked,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }


def _lead_skill_terms(lead: dict) -> list[str]:
    terms: list[str] = []
    for value in (lead.get("tech_stack"), (lead.get("source_meta") or {}).get("tech_stack"), lead.get("signal_tags")):
        if isinstance(value, list):
            terms.extend(str(item).strip() for item in value)
        elif isinstance(value, str):
            terms.extend(_split_terms(value))
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        key = term.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(term)
    return out[:24]


def _split_terms(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value or "").replace(";", ",").replace("|", ",").split(",") if part.strip()]


def _query_rows(query: str, params: dict | None = None) -> list[list]:
    result = execute_query(query, params)
    rows: list[list] = []
    if result is None:
        return rows
    while result.has_next():
        rows.append(result.get_next())
    return rows


def graph_snapshot(limit: int = 140) -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    if not _ensure_connection() or conn is None:
        return {"nodes": nodes, "edges": edges, "available": False, "error": graph_error()}

    def add_node(node_id: str, label: str, node_type: str, subtitle: str = "") -> None:
        if not node_id or any(node["id"] == node_id for node in nodes):
            return
        if len(nodes) >= limit:
            return
        nodes.append({"id": node_id, "label": label or node_id, "type": node_type, "subtitle": subtitle})

    def add_edge(source: str, target: str, rel: str) -> None:
        if not source or not target:
            return
        if not any(node["id"] == source for node in nodes) or not any(node["id"] == target for node in nodes):
            return
        edges.append({"source": source, "target": target, "type": rel})

    for row in _query_rows("MATCH (n:Candidate) RETURN n.id, n.n, n.s"):
        add_node(f"candidate:{row[0]}", row[1] or "Candidate", "Candidate", row[2] or "")
    for row in _query_rows("MATCH (n:Skill) RETURN n.id, n.n, n.cat"):
        add_node(f"skill:{row[0]}", row[1] or "Skill", "Skill", row[2] or "general")
    for row in _query_rows("MATCH (n:Project) RETURN n.id, n.title, n.stack"):
        add_node(f"project:{row[0]}", row[1] or "Project", "Project", row[2] or "")
    for row in _query_rows("MATCH (n:Experience) RETURN n.id, n.role, n.co"):
        add_node(f"experience:{row[0]}", row[1] or "Experience", "Experience", row[2] or "")
    for label in ["Certification", "Education", "Achievement"]:
        for row in _query_rows(f"MATCH (n:{label}) RETURN n.id, n.title"):
            add_node(f"credential:{row[0]}", row[1] or label, "Credential", label)
    for row in _query_rows("MATCH (n:JobLead) RETURN n.job_id, n.title, n.co"):
        add_node(f"job:{row[0]}", row[1] or "Job lead", "JobLead", row[2] or "")

    edge_queries = [
        ("MATCH (a:Candidate)-[:BUILT]->(b:Project) RETURN a.id, b.id", "BUILT", "candidate", "project"),
        ("MATCH (a:Candidate)-[:WORKED_AS]->(b:Experience) RETURN a.id, b.id", "WORKED_AS", "candidate", "experience"),
        ("MATCH (a:Candidate)-[:HAS_SKILL]->(b:Skill) RETURN a.id, b.id", "HAS_SKILL", "candidate", "skill"),
        ("MATCH (a:Candidate)-[:HAS_CERTIFICATION]->(b:Certification) RETURN a.id, b.id", "HAS_CERTIFICATION", "candidate", "credential"),
        ("MATCH (a:Candidate)-[:HAS_EDUCATION]->(b:Education) RETURN a.id, b.id", "HAS_EDUCATION", "candidate", "credential"),
        ("MATCH (a:Candidate)-[:HAS_ACHIEVEMENT]->(b:Achievement) RETURN a.id, b.id", "HAS_ACHIEVEMENT", "candidate", "credential"),
        ("MATCH (a:Project)-[:PROJ_UTILIZES]->(b:Skill) RETURN a.id, b.id", "PROJ_UTILIZES", "project", "skill"),
        ("MATCH (a:Experience)-[:EXP_UTILIZES]->(b:Skill) RETURN a.id, b.id", "EXP_UTILIZES", "experience", "skill"),
        ("MATCH (a:Certification)-[:CERTIFIES]->(b:Skill) RETURN a.id, b.id", "CERTIFIES", "credential", "skill"),
        ("MATCH (a:Education)-[:EDUCATES]->(b:Skill) RETURN a.id, b.id", "EDUCATES", "credential", "skill"),
        ("MATCH (a:Achievement)-[:ACHIEVEMENT_USES]->(b:Skill) RETURN a.id, b.id", "ACHIEVEMENT_USES", "credential", "skill"),
        ("MATCH (a:Skill)-[:RELATED_SKILL]->(b:Skill) RETURN a.id, b.id", "RELATED_SKILL", "skill", "skill"),
        ("MATCH (a:Project)-[:SIMILAR_PROJECT]->(b:Project) RETURN a.id, b.id", "SIMILAR_PROJECT", "project", "project"),
        ("MATCH (a:Project)-[:PROJECT_SUPPORTS_EXPERIENCE]->(b:Experience) RETURN a.id, b.id", "SUPPORTS_EXPERIENCE", "project", "experience"),
        ("MATCH (a:JobLead)-[:REQUIRES]->(b:Skill) RETURN a.job_id, b.id", "REQUIRES", "job", "skill"),
    ]
    for query, rel, source_type, target_type in edge_queries:
        try:
            for row in _query_rows(query):
                add_edge(f"{source_type}:{row[0]}", f"{target_type}:{row[1]}", rel)
        except Exception as exc:
            _log.debug("graph edge query failed for %s: %s", rel, exc)

    return {"nodes": nodes, "edges": edges, "available": True, "error": ""}
