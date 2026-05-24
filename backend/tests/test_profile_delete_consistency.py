# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs
"""Regression tests for the profile delete-consistency fix.

The Profile page (/api/v1/profile) applies deletion tombstones, but the
Knowledge page (/api/v1/graph) previously read the raw Kùzu snapshot and raw
LanceDB embedding points without filtering. That asymmetry let a deleted item
linger on the Knowledge page and resurrect the profile on the next repair sync.

These tests lock in that the graph snapshot and embedding payloads are now
filtered through the SAME tombstone tokens, and that the graph-stats endpoint
is wired to apply that filtering.
"""

import ast
from pathlib import Path

from data.graph import profile, profile_deletions

BACKEND = Path(__file__).resolve().parents[1]


def _deletions(**kw):
    base = {key: [] for key in profile.PROFILE_DELETE_KEYS}
    for key, values in kw.items():
        base[key] = sorted(profile._delete_tokens(values))
    return base


def test_filter_graph_deletions_removes_skill_and_orphan_edges(monkeypatch):
    monkeypatch.setattr(profile_deletions, "_load_profile_deletions", lambda db_path=None: _deletions(skills=["React"]))
    graph = {
        "nodes": [
            {"id": "skill:abc", "label": "React", "type": "Skill", "subtitle": "frontend"},
            {"id": "skill:xyz", "label": "Python", "type": "Skill", "subtitle": "backend"},
            {"id": "project:p1", "label": "App", "type": "Project"},
        ],
        "edges": [
            {"source": "project:p1", "target": "skill:abc", "type": "PROJ_UTILIZES"},
            {"source": "project:p1", "target": "skill:xyz", "type": "PROJ_UTILIZES"},
        ],
        "available": True,
    }
    out = profile.filter_graph_deletions(graph)
    labels = {node["label"] for node in out["nodes"]}
    assert "React" not in labels
    assert "Python" in labels
    # The edge that pointed at the deleted skill must be gone; the other stays.
    assert all(edge["target"] != "skill:abc" for edge in out["edges"])
    assert any(edge["target"] == "skill:xyz" for edge in out["edges"])


def test_filter_graph_deletions_matches_by_node_id(monkeypatch):
    # Tombstone recorded by node id (the common delete-by-id path).
    monkeypatch.setattr(profile_deletions, "_load_profile_deletions", lambda db_path=None: _deletions(projects=["p1"]))
    graph = {
        "nodes": [{"id": "project:p1", "label": "Renamed Title", "type": "Project"}],
        "edges": [],
        "available": True,
    }
    out = profile.filter_graph_deletions(graph)
    assert out["nodes"] == []


def test_filter_graph_deletions_handles_experience_and_credentials(monkeypatch):
    monkeypatch.setattr(
        profile_deletions,
        "_load_profile_deletions",
        lambda db_path=None: _deletions(exp=["Engineer at Acme"], certifications=["AWS Cert"]),
    )
    graph = {
        "nodes": [
            {"id": "experience:e1", "label": "Engineer", "type": "Experience", "subtitle": "Acme"},
            {"id": "experience:e2", "label": "Designer", "type": "Experience", "subtitle": "Globex"},
            {"id": "credential:c1", "label": "AWS Cert", "type": "Credential", "subtitle": "Certification"},
            {"id": "credential:c2", "label": "BSc CS", "type": "Credential", "subtitle": "Education"},
        ],
        "edges": [],
        "available": True,
    }
    out = profile.filter_graph_deletions(graph)
    labels = {node["label"] for node in out["nodes"]}
    assert "Engineer" not in labels
    assert "AWS Cert" not in labels
    assert {"Designer", "BSc CS"} <= labels


def test_filter_embedding_deletions_removes_point(monkeypatch):
    monkeypatch.setattr(profile_deletions, "_load_profile_deletions", lambda db_path=None: _deletions(skills=["React"]))
    embedding = {
        "available": True,
        "error": "",
        "points": [
            {"id": "s1", "label": "React", "source": "skills", "type": "Skill"},
            {"id": "s2", "label": "Python", "source": "skills", "type": "Skill"},
            {"id": "cand", "label": "Jane", "source": "candidates", "type": "Candidate"},
        ],
    }
    out = profile.filter_embedding_deletions(embedding)
    labels = {point["label"] for point in out["points"]}
    assert "React" not in labels
    assert {"Python", "Jane"} <= labels


def test_filters_are_noop_without_tombstones(monkeypatch):
    monkeypatch.setattr(profile_deletions, "_load_profile_deletions", lambda db_path=None: _deletions())
    graph = {"nodes": [{"id": "skill:a", "label": "Go", "type": "Skill"}], "edges": [], "available": True}
    embedding = {"available": True, "points": [{"id": "a", "label": "Go", "source": "skills"}], "error": ""}
    # No tombstones → returns the exact same objects (cheap identity short-circuit).
    assert profile.filter_graph_deletions(graph) is graph
    assert profile.filter_embedding_deletions(embedding) is embedding


def test_graph_stats_endpoint_is_wired_to_apply_deletions():
    """misc.graph_stats must run the snapshot + embedding through the filters."""
    src = (BACKEND / "api" / "routers" / "misc.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "graph_stats"
    )
    called = {
        node.func.id
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_apply_graph_deletions" in called
    assert "_apply_embedding_deletions" in called
