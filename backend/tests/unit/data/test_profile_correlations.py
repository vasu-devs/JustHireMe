# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs
"""Regression tests for post-ingest correlation rebuilding.

Ingest paths create direct edges per item but not the derived correlation
edges (RELATED_SKILL / SIMILAR_PROJECT / PROJECT_SUPPORTS_EXPERIENCE /
credential->skill). rebuild_profile_correlations() runs sync_profile_relationships
then sync_vectors_from_graph, and every ingest service path must await it so the
knowledge graph and vectors reflect the freshly imported profile before the UI refreshes.
"""

import ast
from pathlib import Path
from paths import BACKEND_ROOT

BACKEND = BACKEND_ROOT


def test_rebuild_profile_correlations_runs_relationships_then_vectors(monkeypatch):
    from data.graph import profile as graph_profile
    from data.graph import profile_correlations

    order = []
    monkeypatch.setattr(profile_correlations, "sync_profile_relationships", lambda: order.append("rel") or {"status": "ok"})
    monkeypatch.setattr(profile_correlations, "sync_vectors_from_graph", lambda: order.append("vec") or {"status": "ok"})

    out = graph_profile.rebuild_profile_correlations()

    assert order == ["rel", "vec"], "relationships must be rebuilt before re-embedding"
    assert out["status"] == "ok"
    assert out["relationships"] == {"status": "ok"}
    assert out["vectors"] == {"status": "ok"}


def test_every_ingest_path_awaits_post_ingest_sync():
    """resume / github / linkedin / json-import must await the correlation rebuild."""
    src = (BACKEND / "profile" / "service.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    service = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "ProfileService"
    )
    methods = {
        node.name: node
        for node in service.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    def awaits_sync(method) -> bool:
        return any(
            isinstance(node, ast.Await)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "_run_post_ingest_sync"
            for node in ast.walk(method)
        )

    for name in ["ingest_resume", "ingest_github", "ingest_linkedin", "import_profile_data"]:
        assert name in methods, f"{name} missing from ProfileService"
        assert awaits_sync(methods[name]), f"{name} must await self._run_post_ingest_sync()"


def test_post_ingest_sync_targets_rebuild_correlations():
    src = (BACKEND / "profile" / "service.py").read_text(encoding="utf-8")
    assert "graph_profile.rebuild_profile_correlations" in src
