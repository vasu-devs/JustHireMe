from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any

from data.graph.connection import run_graph
from data.repository import Repository
from graph_service.helpers import embedding_space, sync_vectors_from_graph

_log = logging.getLogger(__name__)


def _hash_id(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()[:12]


def _split_terms(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value or "").replace(";", ",").replace("|", ",").split(",") if part.strip()]


def _contains_term(text: str, term: str) -> bool:
    if not text or not term:
        return False
    return bool(re.search(r"(?<![a-z0-9+#.-])" + re.escape(term.lower()) + r"(?![a-z0-9+#.-])", text.lower()))


def profile_snapshot_graph(profile: dict) -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []

    def add_node(node_id: str, label: str, node_type: str, subtitle: str = "") -> None:
        if node_id and label and not any(node["id"] == node_id for node in nodes):
            nodes.append({"id": node_id, "label": label, "type": node_type, "subtitle": subtitle})

    def add_edge(source: str, target: str, edge_type: str) -> None:
        if source and target and source != target and not any(edge["source"] == source and edge["target"] == target and edge["type"] == edge_type for edge in edges):
            edges.append({"source": source, "target": target, "type": edge_type})

    candidate_id = "candidate:profile-snapshot"
    if profile.get("n") or profile.get("s") or profile.get("skills") or profile.get("projects"):
        add_node(candidate_id, str(profile.get("n") or "Profile"), "Candidate", str(profile.get("s") or "Local profile snapshot"))

    skill_ids: dict[str, str] = {}
    for skill in profile.get("skills", []) or []:
        if isinstance(skill, dict):
            name = str(skill.get("n") or skill.get("name") or "").strip()
            category = str(skill.get("cat") or skill.get("category") or "general")
            raw_id = str(skill.get("id") or _hash_id(name))
        else:
            name = str(skill or "").strip()
            category = "general"
            raw_id = _hash_id(name)
        if not name:
            continue
        node_id = f"skill:{raw_id}"
        skill_ids[name.lower()] = node_id
        add_node(node_id, name, "Skill", category)
        add_edge(candidate_id, node_id, "HAS_SKILL")

    for project in profile.get("projects", []) or []:
        if not isinstance(project, dict):
            continue
        title = str(project.get("title") or "").strip()
        if not title:
            continue
        stack = project.get("stack", [])
        stack_terms = _split_terms(stack)
        impact = str(project.get("impact") or "")
        node_id = f"project:{project.get('id') or _hash_id(title)}"
        add_node(node_id, title, "Project", ", ".join(stack_terms))
        add_edge(candidate_id, node_id, "BUILT")
        for term in stack_terms:
            skill_id = skill_ids.get(term.lower())
            if not skill_id:
                skill_id = f"skill:{_hash_id(term)}"
                skill_ids[term.lower()] = skill_id
                add_node(skill_id, term, "Skill", "project_stack")
                add_edge(candidate_id, skill_id, "HAS_SKILL")
            add_edge(node_id, skill_id, "PROJ_UTILIZES")
        text = f"{title} {impact}"
        for term, skill_id in skill_ids.items():
            if _contains_term(text, term):
                add_edge(node_id, skill_id, "PROJ_UTILIZES")

    return {"nodes": nodes, "edges": edges, "available": bool(nodes), "error": ""}


def merge_graphs(primary: dict, fallback: dict) -> dict:
    merged: dict[str, Any] = {
        "nodes": list(primary.get("nodes") or []),
        "edges": list(primary.get("edges") or []),
        "available": bool(primary.get("available") or fallback.get("available")),
        "error": primary.get("error") or fallback.get("error") or "",
    }
    node_ids = {node.get("id") for node in merged["nodes"]}
    for node in fallback.get("nodes") or []:
        if node.get("id") not in node_ids:
            merged["nodes"].append(node)
            node_ids.add(node.get("id"))
    edge_keys = {(edge.get("source"), edge.get("target"), edge.get("type")) for edge in merged["edges"]}
    for edge in fallback.get("edges") or []:
        key = (edge.get("source"), edge.get("target"), edge.get("type"))
        if key not in edge_keys and edge.get("source") in node_ids and edge.get("target") in node_ids:
            merged["edges"].append(edge)
            edge_keys.add(key)
    return merged


def filter_stale_profile_nodes(graph: dict, profile_graph: dict) -> dict:
    allowed_profile_ids = {str(node.get("id") or "") for node in profile_graph.get("nodes") or []}
    candidate_owned_ids = {
        str(edge.get("target") or "")
        for edge in graph.get("edges") or []
        if str(edge.get("source") or "").startswith("candidate:")
        and str(edge.get("type") or "") in {"HAS_SKILL", "BUILT"}
    }
    remove_ids: set[str] = set()
    for node in graph.get("nodes") or []:
        node_id = str(node.get("id") or "")
        node_type = str(node.get("type") or "")
        subtitle = str(node.get("subtitle") or "").strip().lower()
        if (node_id in candidate_owned_ids and node_type in {"Skill", "Project"} and node_id not in allowed_profile_ids) or (node_type == "Skill" and subtitle == "project_stack" and node_id not in allowed_profile_ids):
            remove_ids.add(node_id)
    if not remove_ids:
        return graph
    nodes = [node for node in graph.get("nodes") or [] if str(node.get("id") or "") not in remove_ids]
    edges = [
        edge
        for edge in graph.get("edges") or []
        if str(edge.get("source") or "") not in remove_ids and str(edge.get("target") or "") not in remove_ids
    ]
    return {**graph, "nodes": nodes, "edges": edges}


async def _safe_graph_step(fn, label: str, errors: list[str], default=None):
    """Run one graph step on the graph executor, recording (never raising) failures."""
    try:
        return await run_graph(fn)
    except Exception as exc:
        _log.warning("suppressed exception in graph_service.stats:%s: %s", label, exc)
        errors.append(f"{label}: {exc}")
        if default is not None:
            return default
        return {"status": "error", "error": str(exc)}


def _apply_graph_deletions(graph: dict) -> dict:
    # Keep the Knowledge page (raw Kùzu snapshot) consistent with the deletion
    # tombstones the Profile page applies. Failsafe: never break the endpoint.
    try:
        from data.graph.profile import filter_graph_deletions

        return filter_graph_deletions(graph)
    except Exception as exc:
        _log.warning("suppressed exception in graph_service.stats:_apply_graph_deletions: %s", exc)
        return graph


def _apply_embedding_deletions(embedding: dict) -> dict:
    # Same as above for the raw LanceDB embedding-space points.
    try:
        from data.graph.profile import filter_embedding_deletions

        return filter_embedding_deletions(embedding)
    except Exception as exc:
        _log.warning("suppressed exception in graph_service.stats:_apply_embedding_deletions: %s", exc)
        return embedding


class GraphService:
    """Business facade for the Knowledge page, so the router holds no repo."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    async def stats(self, *, repair: bool = False) -> dict:
        return await graph_stats_payload(self._repo, repair=repair)


def create_graph_service(repo: Repository) -> GraphService:
    return GraphService(repo)


async def graph_stats_payload(repo: Repository, *, repair: bool = False) -> dict:
    """Build the Knowledge-page payload: counts, graph snapshot and embedding space.

    ``repair=True`` additionally purges deletion tombstones and re-syncs leads,
    profile relationships and vectors — expensive, so the default read path stays
    a pure read-only snapshot.
    """
    errors: list[str] = []
    profile_repo = getattr(repo, "profile", None)
    if repair:
        # The hard purge (DETACH DELETE of tombstoned nodes) is expensive and
        # only needed to physically clean the graph. Read-time filtering
        # (_apply_graph_deletions / _apply_embedding_deletions below) already
        # hides deleted items, so keep the common read path fast and purge only
        # on an explicit repair (and during ingest vector sync).
        if profile_repo and hasattr(profile_repo, "purge_profile_deletion_tombstones"):
            await _safe_graph_step(profile_repo.purge_profile_deletion_tombstones, "profile deletion purge", errors, default={"status": "skipped"})
        leads = await asyncio.to_thread(repo.leads.get_all_leads)
        sync = await _safe_graph_step(lambda: repo.graph.sync_job_leads(leads), "lead sync", errors)
        profile_sync = await _safe_graph_step(
            lambda: repo.graph.sync_profile_relationships() if hasattr(repo.graph, "sync_profile_relationships") else {"status": "skipped"},
            "profile sync",
            errors,
        )
        vector_sync = await run_graph(sync_vectors_from_graph)
        if vector_sync.get("status") == "error" and vector_sync.get("error"):
            errors.append(f"vector sync: {vector_sync['error']}")
    else:
        sync = {"status": "skipped", "reason": "read-only snapshot"}
        profile_sync = {"status": "skipped", "reason": "read-only snapshot"}
        vector_sync = {"status": "skipped", "synced": 0, "reason": "read-only snapshot"}
    counts = await _safe_graph_step(repo.graph.graph_counts, "counts", errors, default={})
    available = await _safe_graph_step(repo.graph.graph_available, "availability", errors, default=False)
    graph = await _safe_graph_step(repo.graph.graph_snapshot, "snapshot", errors, default={"nodes": [], "edges": [], "available": False})
    graph = _apply_graph_deletions(graph)
    profile_snapshot = {}
    if profile_repo:
        profile_snapshot = await _safe_graph_step(
            lambda: profile_repo.get_profile() or profile_repo.load_profile_snapshot(),
            "profile snapshot",
            errors,
            default={},
        )
    # A profile snapshot is durable even when the native graph store is empty,
    # stale, or temporarily locked. Merge it into the raw snapshot so Knowledge
    # never becomes a blank canvas while Profile visibly contains evidence.
    profile_graph = profile_snapshot_graph(profile_snapshot)
    graph = merge_graphs(filter_stale_profile_nodes(graph, profile_graph), profile_graph)
    embedding = _apply_embedding_deletions(embedding_space(repo))
    if embedding.get("error"):
        errors.append(f"embedding: {embedding['error']}")
    graph_error = "" if available else repo.graph.graph_error()
    if graph_error:
        errors.append(graph_error)
    sync_ok = sync.get("status") == "ok" if repair else True
    return {
        "candidate": 0,
        "skill": 0,
        "project": 0,
        "experience": 0,
        "joblead": 0,
        **counts,
        "available": available,
        "status": "live" if available and sync_ok and not errors else "degraded",
        "error": "; ".join(dict.fromkeys(error for error in errors if error)),
        "sync": {**sync, "profile": profile_sync, "vectors": vector_sync},
        "graph": graph,
        "embedding": embedding,
        "profile": profile_snapshot,
    }
