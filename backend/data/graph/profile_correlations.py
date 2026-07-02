"""Bulk graph/vector maintenance for the profile layer.

- purge_profile_deletion_tombstones: hard-delete tombstoned nodes from the
  Kùzu graph + vector tables (the read paths only soft-filter).
- sync_vectors_from_graph: rebuild the LanceDB embedding tables from the graph.
- rebuild_profile_correlations: re-derive correlation edges (via
  sync_profile_relationships) and re-embed in one pass after an ingest.

Sits above base/deletions/vectors/read; the per-item edge-linking helpers used
during mutations live with the mutation code, not here.
"""

from __future__ import annotations

import logging

from data.graph.connection import execute_query, sync_profile_relationships
from data.graph.profile_base import _query_rows, _safe_execute, _vec, hash_id
from data.graph.profile_deletions import _delete_tokens, _load_profile_deletions
from data.graph.profile_read import refresh_profile_snapshot
from data.graph.profile_vectors import (
    add_profile_vec,
    credential_text,
    current_embedding_dim,
    delete_vec_id_from_all,
    drop_vec_table,
    embed_rows,
    experience_text,
    profile_text,
    project_text,
    prune_bad_vector_rows,
    skill_text,
    vec_table_dim,
)
from graph_service.helpers import is_bad_vector_label


def purge_profile_deletion_tombstones(db_path: str | None = None) -> dict:
    deletions = _load_profile_deletions(db_path)
    purged = 0

    def deleted(key: str, *values) -> bool:
        # key-aware tokens (free-text uses _entry_key) — must match how the tombstone
        # was stored, else purge would miss (or, before this, over-match) free-text.
        tokens = _delete_tokens(key, values)
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
    store = _vec()
    if getattr(store, "available", True) is False:
        return {
            "status": "disabled",
            "synced": 0,
            "error": getattr(store, "reason", "") or "vector store is unavailable",
        }
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
        logging.getLogger(__name__).warning('suppressed exception in backend/data/graph/profile.py:sync_vectors_from_graph: %s', exc)
        return {"status": "error", "synced": 0, "error": str(exc)}

    synced = 0
    profile_parts: list[str] = []

    # Build each vector table in ONE batched embed + write instead of a per-item
    # round-trip. embed_rows() embeds the whole list in a single embed_texts call
    # and writes it in one LanceDB operation, so 75 skills cost 1 embed + 1 write
    # instead of 75 + 75 (the old add_*_vec-per-item loop was the ingest hot spot).
    cand_rows: list[dict] = []
    cand_texts: list[str] = []
    for candidate_id, name, summary in candidates:
        if is_bad_vector_label(name) and is_bad_vector_label(summary):
            continue
        text = profile_text(str(name or ""), str(summary or ""))
        cand_rows.append({"id": str(candidate_id), "label": str(name or "") or "Candidate", "kind": "candidate", "n": str(name or ""), "summary": str(summary or "")})
        cand_texts.append(text)
        profile_parts.append(text)
    if cand_rows:
        embed_rows("candidates", cand_rows, cand_texts, allow_recreate=True)
        synced += len(cand_rows)

    skill_rows: list[dict] = []
    skill_texts: list[str] = []
    for skill_id, name, category in skills:
        if is_bad_vector_label(name):
            continue
        text = skill_text(str(name), str(category or "general"))
        skill_rows.append({"id": str(skill_id), "label": str(name), "kind": "skill", "n": str(name), "cat": str(category or "general")})
        skill_texts.append(text)
        profile_parts.append(text)
    if skill_rows:
        embed_rows("skills", skill_rows, skill_texts, allow_recreate=True)
        synced += len(skill_rows)

    proj_rows: list[dict] = []
    proj_texts: list[str] = []
    for project_id, title, stack, impact in projects:
        if is_bad_vector_label(title):
            continue
        text = project_text(str(title), str(stack or ""), str(impact or ""))
        proj_rows.append({"id": str(project_id), "label": str(title), "kind": "project", "title": str(title), "stack": str(stack or ""), "impact": str(impact or "")})
        proj_texts.append(text)
        profile_parts.append(text)
    if proj_rows:
        embed_rows("projects", proj_rows, proj_texts, allow_recreate=True)
        synced += len(proj_rows)

    exp_rows: list[dict] = []
    exp_texts: list[str] = []
    for experience_id, role, company, period, description in experiences:
        if is_bad_vector_label(role) and is_bad_vector_label(company):
            continue
        label = " - ".join(part for part in [str(role or ""), str(company or "")] if part) or "Experience"
        text = experience_text(str(role or ""), str(company or ""), str(period or ""), str(description or ""))
        exp_rows.append({"id": str(experience_id), "label": label, "kind": "experience", "role": str(role or ""), "company": str(company or ""), "period": str(period or ""), "description": str(description or "")})
        exp_texts.append(text)
        profile_parts.append(text)
    if exp_rows:
        embed_rows("experiences", exp_rows, exp_texts, allow_recreate=True)
        synced += len(exp_rows)

    cred_rows: list[dict] = []
    cred_texts: list[str] = []
    for credential_id, title, kind in credentials:
        if is_bad_vector_label(title):
            continue
        text = credential_text(str(title), str(kind))
        cred_rows.append({"id": str(credential_id), "label": str(title), "kind": str(kind).lower(), "title": str(title)})
        cred_texts.append(text)
        profile_parts.append(text)
    if cred_rows:
        embed_rows("credentials", cred_rows, cred_texts, allow_recreate=True)
        synced += len(cred_rows)

    if profile_parts:
        # Rebuild the aggregate 'profile' table at the new dim too, exactly like the
        # five sibling tables above — otherwise a provider/dim switch strands
        # profile:default at the old dimension (dim-guard skips a partial write).
        add_profile_vec("profile:default", "Complete profile", "\n".join(profile_parts), allow_recreate=True)
        synced += 1

    # A table can be stranded at the OLD embedding dimension after a provider switch
    # in two ways this rebuild does NOT overwrite: (a) it produced zero rows (all
    # items deleted / none of a kind), or (b) every row was rejected by embed_rows'
    # stricter bad-label filter, so embed_rows wrote nothing and never recreated it.
    # In both cases the old-dim table survives and later single-item writes to it are
    # silently skipped by the dim-guard. Keying off the pre-embed row lists misses
    # case (b), so drop any expected table whose STORED dim != the current dim — the
    # next add_* then recreates it at the right dimension.
    target_dim = current_embedding_dim()
    if target_dim:
        for table_name in ("candidates", "skills", "projects", "experiences", "credentials", "profile"):
            existing_dim = vec_table_dim(table_name)
            if existing_dim is not None and existing_dim != target_dim:
                drop_vec_table(table_name)

    return {"status": "ok", "synced": synced, "deleted_bad_rows": deleted_bad_rows}


def rebuild_profile_correlations(db_path: str | None = None) -> dict:
    """Rebuild derived graph correlations and re-embed the profile.

    Ingest paths create direct edges per item (HAS_SKILL / PROJ_UTILIZES /
    EXP_UTILIZES) but NOT the derived correlation edges (RELATED_SKILL,
    SIMILAR_PROJECT, PROJECT_SUPPORTS_EXPERIENCE, credential->skill). Those are
    only produced by sync_profile_relationships(). Run this after an ingest so
    correlations and vector tables reflect the freshly imported profile in one
    pass, instead of waiting for a manual Knowledge-page repair sync.
    """
    relationships = sync_profile_relationships()
    vectors = sync_vectors_from_graph()
    return {"status": "ok", "relationships": relationships, "vectors": vectors}
