"""Regression: graph_snapshot must return EVERY project, not a skills-starved few.

The knowledge-graph snapshot once applied a single global node cap in type order
with skills added before projects. A skill-heavy profile (100+ skills) consumed
the whole budget, so a profile with 19 projects rendered as ~5. The snapshot must
mirror the database: all structural nodes (projects, experience, credentials) are
returned; only high-cardinality skills / job leads are capped.

These tests drive graph_snapshot with controlled query rows (no real Kùzu needed),
so they assert the budgeting logic directly and deterministically.
"""

from __future__ import annotations

from unittest import mock

from data.graph import connection


def _fake_rows_factory(*, projects: int, skills: int, experiences: int = 0, jobleads: int = 0):
    def fake_query_rows(query: str):
        if "(n:Candidate)" in query:
            return [("c1", "Me", "summary")]
        if "(n:Project)" in query:
            return [(f"p{i}", f"Project {i}", "React, FastAPI") for i in range(projects)]
        if "(n:Experience)" in query:
            return [(f"e{i}", f"Role {i}", "Co") for i in range(experiences)]
        if "(n:Skill)" in query:
            return [(f"s{i}", f"Skill {i}", "language") for i in range(skills)]
        if "(n:JobLead)" in query:
            return [(f"j{i}", f"Job {i}", "Co") for i in range(jobleads)]
        # Certification / Education / Achievement / all edge queries -> none.
        return []

    return fake_query_rows


def _snapshot(**kwargs):
    with mock.patch.object(connection, "_ensure_connection", return_value=True), \
         mock.patch.object(connection, "conn", object()), \
         mock.patch.object(connection, "_query_rows", side_effect=_fake_rows_factory(**kwargs)):
        return connection.graph_snapshot()


def _types(snap, node_type):
    return [n for n in snap["nodes"] if n["type"] == node_type]


def test_all_projects_survive_a_skill_heavy_profile():
    snap = _snapshot(projects=19, skills=300)
    assert len(_types(snap, "Project")) == 19, "every project must be in the snapshot"
    # Skills are the capped, high-cardinality type — they do NOT crowd out projects.
    assert len(_types(snap, "Skill")) == 200


def test_structural_nodes_are_never_capped():
    snap = _snapshot(projects=40, skills=50, experiences=12)
    assert len(_types(snap, "Project")) == 40
    assert len(_types(snap, "Experience")) == 12
    assert len(_types(snap, "Candidate")) == 1


def test_built_edges_present_because_candidate_and_projects_coexist():
    # The candidate node and all project nodes are both emitted, so candidate->project
    # BUILT edges can resolve (both endpoints exist in the snapshot).
    def fake_query_rows(query: str):
        if "(n:Candidate)" in query:
            return [("c1", "Me", "summary")]
        if "(n:Project)" in query:
            return [(f"p{i}", f"Project {i}", "React") for i in range(5)]
        if "(a:Candidate)-[:BUILT]->(b:Project)" in query:
            return [("c1", f"p{i}") for i in range(5)]
        return []

    with mock.patch.object(connection, "_ensure_connection", return_value=True), \
         mock.patch.object(connection, "conn", object()), \
         mock.patch.object(connection, "_query_rows", side_effect=fake_query_rows):
        snap = connection.graph_snapshot()

    built = [e for e in snap["edges"] if e["type"] == "BUILT"]
    assert len(built) == 5, "candidate->project BUILT edges must resolve for all projects"
