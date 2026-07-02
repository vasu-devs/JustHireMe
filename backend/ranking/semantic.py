"""Semantic similarity between a JD and the candidate's embedded profile.

The profile stores per-skill and per-project embeddings in LanceDB (see
``agents.ingestor._vectors``).  This module embeds the incoming JD with the
active embedding provider (ONNX local, OpenAI API, or hash fallback — see
``data.vector.embeddings``) and runs cosine search over those tables.

When the Kuzu graph is available, the candidate profile is *enriched* before
embedding: skills carry evidence scores from project/experience edges, related
skills are expanded, and industry domains are inferred.  This lets the semantic
signal capture "React — proven across 3 projects" rather than just "React".

Searches are scoped to the candidate profile passed into the evaluator, so stale
vector rows cannot win just because they are close to the JD.  The result is
exposed as a 0-100 ``Semantic fit`` signal that the deterministic scoring engine
blends with its keyword-based criteria.

Everything here is wrapped to fail soft.  When LanceDB, the embedding model,
or the graph is unavailable the pipeline cascades gracefully: graph enrichment
→ flat profile, ONNX → hash, vector store → local hashed embedding.
"""
from __future__ import annotations
import logging

import hashlib
import math
from core.logging import get_logger

_log = get_logger(__name__)


def _h(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()[:12]


def _embed_jd(text: str) -> list[float] | None:
    """Embed a JD string into a 384-dim vector. Returns None on any failure."""
    if not (text or "").strip():
        return None
    try:
        from data.vector.embeddings import embed_texts
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/ranking/semantic.py:_embed_jd: %s', log_exc)
        return None
    try:
        vecs = embed_texts([text])
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/ranking/semantic.py:_embed_jd: %s', log_exc)
        return None
    if not vecs:
        return None
    try:
        first = vecs[0]
    except (IndexError, TypeError):
        return None
    if first is None:
        return None
    try:
        return [float(x) for x in first]
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/ranking/semantic.py:_embed_jd: %s', log_exc)
        return None


def _embedding_mode() -> str:
    try:
        from data.vector.embeddings import embedding_status
        status = embedding_status()
        return str(status.get("mode") or "")
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/ranking/semantic.py:_embedding_mode: %s', log_exc)
        return ""


def _is_semantic_provider(mode: str) -> bool:
    """Return True if the active provider produces real semantic vectors."""
    return mode in {"onnx", "openai", "sentence-transformer"}


def _vec_store():
    try:
        from data.vector.connection import vec
        return vec
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/ranking/semantic.py:_vec_store: %s', log_exc)
        return None


def _available_tables(store) -> set[str]:
    if store is None:
        return set()
    try:
        return set(_normalize_table_names(store.list_tables()))
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/ranking/semantic.py:_available_tables: %s', log_exc)
        return set()


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
        logging.getLogger(__name__).debug(
            "table name pair normalization skipped in backend/ranking/semantic.py:_normalize_table_names: %s",
            log_exc,
        )
    try:
        return [str(item) for item in raw]
    except TypeError:
        return []


def _profile_scope(candidate_data: dict | None) -> dict[str, set[str]] | None:
    """Return LanceDB row ids belonging to the current profile.

    Passing ``None`` means "unscoped legacy search". Passing a profile with no
    usable ids means "do not use semantic search"; this prevents stale vectors
    from a previous profile from influencing an otherwise empty/current profile.
    """
    if candidate_data is None:
        return None

    skill_ids: set[str] = set()
    for skill in candidate_data.get("skills", []) or []:
        sid = str(skill.get("id") or "").strip()
        name = str(skill.get("n") or "").strip()
        if sid:
            skill_ids.add(sid)
        elif name:
            skill_ids.add(_h(name))

    project_ids: set[str] = set()
    for project in candidate_data.get("projects", []) or []:
        pid = str(project.get("id") or "").strip()
        title = str(project.get("title") or "").strip()
        if pid:
            project_ids.add(pid)
        elif title:
            project_ids.add(_h(title))

    experience_ids: set[str] = set()
    for exp in candidate_data.get("exp", []) or []:
        eid = str(exp.get("id") or "").strip()
        role = str(exp.get("role") or "").strip()
        company = str(exp.get("co") or "").strip()
        if eid:
            experience_ids.add(eid)
        elif role or company:
            experience_ids.add(_h(role + company))

    credential_ids: set[str] = set()
    for key in ("education", "certifications", "certs", "achievements", "awards"):
        for item in candidate_data.get(key, []) or []:
            title = _entry_title(item)
            if title:
                credential_ids.add(_h(title))

    return {
        "skills": skill_ids,
        "projects": project_ids,
        "experiences": experience_ids,
        "credentials": credential_ids,
    }


def _scope_has_ids(scope: dict[str, set[str]] | None) -> bool:
    return scope is None or any(scope.get(key) for key in ("skills", "projects", "experiences", "credentials"))


def _ids_where_clause(ids: set[str]) -> str:
    quoted = ["'" + str(item).replace("'", "''") + "'" for item in sorted(ids)]
    return "id IN (" + ", ".join(quoted) + ")"


def _filter_rows(rows: list[dict], allowed_ids: set[str] | None, limit: int) -> list[dict]:
    if allowed_ids is None:
        return rows[:limit]
    if not allowed_ids:
        return []
    return [row for row in rows if str(row.get("id") or "") in allowed_ids][:limit]


def _table_search(
    table_name: str,
    query: list[float],
    limit: int,
    *,
    allowed_ids: set[str] | None = None,
    store=None,
    available_tables: set[str] | None = None,
) -> list[dict]:
    if allowed_ids is not None and not allowed_ids:
        return []
    store = store if store is not None else _vec_store()
    if store is None:
        return []
    tables = available_tables if available_tables is not None else _available_tables(store)
    if table_name not in tables:
        return []
    try:
        table = store.open_table(table_name)
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/ranking/semantic.py:_table_search: %s', log_exc)
        return []
    try:
        # LanceDB returns rows ordered by similarity. Prefer cosine when supported.
        try:
            search = table.search(query).metric("cosine")
        except Exception as log_exc:
            logging.getLogger(__name__).warning('suppressed exception in backend/ranking/semantic.py:_table_search: %s', log_exc)
            search = table.search(query)
        server_filtered = False
        if allowed_ids:
            try:
                search = search.where(_ids_where_clause(allowed_ids), prefilter=True)
                server_filtered = True
            except Exception as log_exc:
                logging.getLogger(__name__).warning('suppressed exception in backend/ranking/semantic.py:_table_search: %s', log_exc)
                server_filtered = False
        if server_filtered or allowed_ids is None:
            request_limit = limit
        else:
            request_limit = max(limit, min(200, len(allowed_ids) + limit * 8))
        results = search.limit(request_limit).to_list()
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/ranking/semantic.py:_table_search: %s', log_exc)
        return []
    return _filter_rows(list(results or []), allowed_ids, limit)


def _row_label(row: dict, fallback: str) -> str:
    for key in ("label", "title", "n", "role", "id"):
        v = row.get(key)
        if v:
            return str(v)
    return fallback


def _row_similarity(row: dict) -> float:
    """Convert LanceDB output (cosine distance or score) to similarity in [0,1]."""
    distance = row.get("_distance")
    if distance is None:
        sim = row.get("_score")
        try:
            return max(0.0, min(1.0, float(sim))) if sim is not None else 0.0
        except (TypeError, ValueError):
            return 0.0
    try:
        d = float(distance)
    except (TypeError, ValueError):
        return 0.0
    # Cosine distance is in [0,2]; similarity = 1 - d, clamped.
    sim = 1.0 - d
    if sim < 0:
        sim = 0.0
    if sim > 1:
        sim = 1.0
    return sim


def _stack_text(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _entry_title(value) -> str:
    if isinstance(value, dict):
        return str(value.get("title") or value.get("name") or value.get("n") or "").strip()
    return str(value or "").strip()


def _try_graph_enrich(candidate_data: dict) -> dict:
    """Attempt graph enrichment; return original data on failure."""
    try:
        from ranking.graph_enrichment import graph_enriched_profile
        enriched = graph_enriched_profile(candidate_data)
        if enriched.get("_graph_enriched"):
            return enriched
    except Exception as exc:
        _log.debug("graph enrichment skipped in semantic pipeline: %s", exc)
    return candidate_data


def _local_profile_rows(candidate_data: dict | None) -> list[dict]:
    if not isinstance(candidate_data, dict):
        return []

    # Try graph enrichment for richer skill/domain context
    data = _try_graph_enrich(candidate_data)

    rows: list[dict] = []
    summary_parts = [
        str(data.get("n") or "").strip(),
        str(data.get("s") or "").strip(),
        str(data.get("desired_position") or "").strip(),
    ]
    # Append domain context if available from graph enrichment
    domain_text = str(data.get("_domain_text") or "").strip()
    if domain_text:
        summary_parts.append(domain_text)

    summary = "\n".join(part for part in summary_parts if part)
    if summary:
        rows.append({
            "kind": "profile",
            "id": "profile:local",
            "label": "Profile summary",
            "text": f"Candidate profile\n{summary}",
        })

    for skill in data.get("skills", []) or []:
        if isinstance(skill, dict):
            name = str(skill.get("n") or skill.get("name") or "").strip()
            category = str(skill.get("cat") or skill.get("category") or "general").strip() or "general"
            row_id = str(skill.get("id") or "").strip() or _h(name)
            # Include evidence context in the text for better semantic matching
            evidence_sources = skill.get("evidence_sources", [])
            evidence_text = ""
            if evidence_sources:
                evidence_text = "\nEvidence: " + "; ".join(evidence_sources[:3])
        else:
            name = str(skill or "").strip()
            category = "general"
            row_id = _h(name)
            evidence_text = ""
        if name:
            rows.append({
                "kind": "skill",
                "id": row_id,
                "label": name,
                "text": f"Skill: {name}\nCategory: {category}{evidence_text}",
                "_evidence_score": skill.get("evidence_score", 0.3) if isinstance(skill, dict) else 0.3,
            })

    for project in data.get("projects", []) or []:
        if not isinstance(project, dict):
            continue
        title = str(project.get("title") or project.get("name") or "").strip()
        stack = _stack_text(project.get("stack") or project.get("s"))
        impact = str(project.get("impact") or project.get("description") or "").strip()
        row_id = str(project.get("id") or "").strip() or _h(title)
        text = f"Project: {title}\nStack: {stack}\nImpact: {impact}".strip()
        if title or stack or impact:
            rows.append({"kind": "project", "id": row_id, "label": title or "Project", "text": text})

    for exp in data.get("exp", []) or []:
        if not isinstance(exp, dict):
            continue
        role = str(exp.get("role") or "").strip()
        company = str(exp.get("co") or exp.get("company") or "").strip()
        period = str(exp.get("period") or "").strip()
        stack = _stack_text(exp.get("s") or exp.get("stack"))
        desc = str(exp.get("d") or exp.get("description") or "").strip()
        label = " at ".join(part for part in [role, company] if part) or "Experience"
        row_id = str(exp.get("id") or "").strip() or _h(role + company)
        text = f"Experience: {role}\nCompany: {company}\nPeriod: {period}\nStack: {stack}\nDescription: {desc}".strip()
        if role or company or desc or stack:
            rows.append({"kind": "experience", "id": row_id, "label": label, "text": text})

    for key, kind in (
        ("education", "credential"),
        ("certifications", "credential"),
        ("certs", "credential"),
        ("achievements", "credential"),
        ("awards", "credential"),
    ):
        for item in data.get(key, []) or []:
            title = _entry_title(item)
            if title:
                rows.append({
                    "kind": kind,
                    "id": _h(title),
                    "label": title,
                    "text": f"{key}: {title}",
                })
    return rows


def _hash_embedding(text: str) -> list[float] | None:
    try:
        from data.vector.embeddings import hash_embedding
        return [float(x) for x in hash_embedding(text)]
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/ranking/semantic.py:_hash_embedding: %s', log_exc)
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(size))
    na = math.sqrt(sum(a[i] * a[i] for i in range(size))) or 1.0
    nb = math.sqrt(sum(b[i] * b[i] for i in range(size))) or 1.0
    return max(0.0, min(1.0, dot / (na * nb)))


def _local_rows_by_similarity(jd_text: str, candidate_data: dict | None) -> list[dict]:
    query = _hash_embedding(jd_text)
    if query is None:
        return []
    rows: list[dict] = []
    for row in _local_profile_rows(candidate_data):
        vector = _hash_embedding(str(row.get("text") or ""))
        if vector is None:
            continue
        rows.append({**row, "_score": _cosine(query, vector)})
    return sorted(rows, key=lambda item: item.get("_score", 0), reverse=True)


def _matches(rows: list[dict], kind: str, limit: int, fallback: str) -> list[tuple[str, float]]:
    out = [
        (_row_label(row, fallback), _row_similarity(row))
        for row in rows
        if row.get("kind") == kind and _row_similarity(row) > 0.01
    ]
    return out[:limit]


def _semantic_result(
    *,
    skill_matches: list[tuple[str, float]],
    project_matches: list[tuple[str, float]],
    experience_matches: list[tuple[str, float]],
    credential_matches: list[tuple[str, float]],
    profile_matches: list[tuple[str, float]],
    source: str,
) -> dict | None:
    groups = [
        ("skills", skill_matches, 0.22),
        ("projects", project_matches, 0.34),
        ("experiences", experience_matches, 0.26),
        ("credentials", credential_matches, 0.10),
        ("profile", profile_matches, 0.08),
    ]
    active = [(name, values, weight) for name, values, weight in groups if values]
    if not active:
        return None

    weight_total = sum(weight for _name, _values, weight in active) or 1.0
    avgs = {name: sum(score for _label, score in values) / len(values) for name, values, _weight in active}
    maxes = {name: max(score for _label, score in values) for name, values, _weight in active}
    avg_signal = sum(avgs[name] * weight for name, _values, weight in active) / weight_total
    peak_signal = sum(maxes[name] * weight for name, _values, weight in active) / weight_total

    combined = 0.60 * avg_signal + 0.40 * peak_signal

    # Score stretching depends on the embedding provider. Real semantic models
    # (ONNX/OpenAI) produce higher cosine similarity for matching content than
    # the hash embedder, so their stretch windows differ.
    mode = _embedding_mode()
    if source == "local-profile":
        # The local-profile fallback ALWAYS computes its similarities with the hash
        # embedder (_local_rows_by_similarity -> _hash_embedding), never the semantic
        # model — so it must use the hash window regardless of which provider is
        # active for the (here unavailable/empty) vector store. Gating this on the
        # provider mode collapsed genuine matches (~score 95 -> ~27) whenever ONNX or
        # OpenAI was active but LanceDB had no tables.
        stretched = (combined - 0.06) / 0.30
    elif _is_semantic_provider(mode):
        # ONNX or OpenAI: real semantic similarity, wider range
        stretched = (combined - 0.20) / 0.55
    else:
        # Vector store with hash embeddings (legacy path)
        stretched = (combined - 0.15) / 0.55
    score = max(0, min(100, round(stretched * 100)))

    raw = {
        **{f"{name}_avg": round(avgs.get(name, 0.0), 3) for name, _values, _weight in groups},
        **{f"{name}_max": round(maxes.get(name, 0.0), 3) for name, _values, _weight in groups},
        "combined": round(combined, 3),
        "source": source,
        # Surface the embedding provider so scores are interpretable: a
        # hash-fallback score means the local runtime pack isn't installed and
        # matching is degraded, not that the candidate is a poor fit.
        "mode": mode,
    }

    return {
        "score": score,
        "skill_matches": skill_matches,
        "project_matches": project_matches,
        "experience_matches": experience_matches,
        "credential_matches": credential_matches,
        "profile_matches": profile_matches,
        "raw": raw,
        "source": source,
        "mode": mode,
    }


def _local_profile_result(
    jd_text: str,
    candidate_data: dict | None,
    *,
    top_skills: int,
    top_projects: int,
) -> dict | None:
    local_rows = _local_rows_by_similarity(jd_text, candidate_data)
    return _semantic_result(
        skill_matches=_matches(local_rows, "skill", top_skills, "skill"),
        project_matches=_matches(local_rows, "project", top_projects, "project"),
        experience_matches=_matches(local_rows, "experience", 3, "experience"),
        credential_matches=_matches(local_rows, "credential", 3, "credential"),
        profile_matches=_matches(local_rows, "profile", 1, "profile"),
        source="local-profile",
    )


def _prefer_local_result(
    vector_result: dict | None,
    local_result: dict | None,
    *,
    embedding_mode: str,
) -> bool:
    if vector_result is None:
        return local_result is not None
    if local_result is None:
        return False

    vector_score = int(vector_result.get("score") or 0)
    local_score = int(local_result.get("score") or 0)
    degraded_embeddings = not _is_semantic_provider(embedding_mode)

    if degraded_embeddings and local_score >= vector_score:
        return True
    return vector_score < 45 and local_score >= vector_score + 10


def semantic_fit(
    jd_text: str,
    *,
    candidate_data: dict | None = None,
    top_skills: int = 6,
    top_projects: int = 3,
) -> dict | None:
    """Compute a 0-100 semantic-fit score for a JD against the stored profile.

    Prefers scoped LanceDB rows when available, then falls back to a local hashed
    embedding over the current profile payload. Returns ``None`` only when there
    is no usable profile evidence.
    """
    scope = _profile_scope(candidate_data)
    if scope is not None and not _scope_has_ids(scope) and not _local_profile_rows(candidate_data):
        return None

    local_result = _local_profile_result(
        jd_text,
        candidate_data,
        top_skills=top_skills,
        top_projects=top_projects,
    )
    store = _vec_store()
    tables = _available_tables(store)
    vector_tables = {"skills", "projects", "experiences", "credentials"} & tables
    if vector_tables:
        query = _embed_jd(jd_text)
        if query is not None:
            embedding_mode = _embedding_mode()
            skill_rows = _table_search(
                "skills",
                query,
                top_skills,
                allowed_ids=None if scope is None else scope["skills"],
                store=store,
                available_tables=tables,
            )
            project_rows = _table_search(
                "projects",
                query,
                top_projects,
                allowed_ids=None if scope is None else scope["projects"],
                store=store,
                available_tables=tables,
            )
            experience_rows = _table_search(
                "experiences",
                query,
                3,
                allowed_ids=None if scope is None else scope["experiences"],
                store=store,
                available_tables=tables,
            )
            credential_rows = _table_search(
                "credentials",
                query,
                3,
                allowed_ids=None if scope is None else scope["credentials"],
                store=store,
                available_tables=tables,
            )
            vector_result = _semantic_result(
                skill_matches=[(_row_label(r, "skill"), _row_similarity(r)) for r in skill_rows],
                project_matches=[(_row_label(r, "project"), _row_similarity(r)) for r in project_rows],
                experience_matches=[(_row_label(r, "experience"), _row_similarity(r)) for r in experience_rows],
                credential_matches=[(_row_label(r, "credential"), _row_similarity(r)) for r in credential_rows],
                profile_matches=[],
                source="vector-store",
            )
            if vector_result is not None:
                if _prefer_local_result(vector_result, local_result, embedding_mode=embedding_mode):
                    return local_result
                return vector_result

    return local_result


class SemanticMatcher:
    def match(
        self,
        jd_text: str,
        *,
        candidate_data: dict | None = None,
        top_skills: int = 6,
        top_projects: int = 3,
    ) -> dict | None:
        return semantic_fit(
            jd_text,
            candidate_data=candidate_data,
            top_skills=top_skills,
            top_projects=top_projects,
        )
