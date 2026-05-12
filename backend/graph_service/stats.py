from __future__ import annotations

from data.repository import create_repository


def graph_stats_payload(*, repair: bool = False) -> dict:
    from api.routers.misc import _embedding_space, _safe_graph_step, _sync_vectors_from_graph

    repo = create_repository()
    errors: list[str] = []
    if repair:
        sync = _safe_graph_step(lambda: repo.graph.sync_job_leads(repo.leads.get_all_leads()), "lead sync", errors)
        profile_sync = _safe_graph_step(
            lambda: repo.graph.sync_profile_relationships() if hasattr(repo.graph, "sync_profile_relationships") else {"status": "skipped"},
            "profile sync",
            errors,
        )
        vector_sync = _sync_vectors_from_graph()
        if vector_sync.get("status") == "error" and vector_sync.get("error"):
            errors.append(f"vector sync: {vector_sync['error']}")
    else:
        sync = {"status": "skipped", "reason": "read-only snapshot"}
        profile_sync = {"status": "skipped", "reason": "read-only snapshot"}
        vector_sync = {"status": "skipped", "synced": 0, "reason": "read-only snapshot"}
    counts = _safe_graph_step(repo.graph.graph_counts, "counts", errors, default={})
    available = _safe_graph_step(repo.graph.graph_available, "availability", errors, default=False)
    graph = _safe_graph_step(repo.graph.graph_snapshot, "snapshot", errors, default={"nodes": [], "edges": [], "available": False})
    embedding = _embedding_space(repo)
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
    }
