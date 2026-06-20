# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs
"""Regression: projects must link to their skills (PROJ_UTILIZES) on ingest.

Bug: the knowledge graph showed Project nodes with no skill edges -- projects
"hung there" disconnected even though the profile had both projects and skills.
Root cause: the import / snapshot-materialize paths only read a project's skills
from the `stack` field. When the source supplied them under an alternative,
equally common field (`skills`, `technologies`, `tools`, `tech`, ...) the stack
was empty, sync_profile_relationships found nothing to link via `stack`, and the
text scan only matched skill names that happened to appear in the project
title/impact -- so non-tech projects (nurse/welder) stayed disconnected.

These run in a subprocess against a REAL Kuzu DB: the in-process suite installs
a global kuzu/sqlite fake, which would otherwise make edge counts meaningless.
"""
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]

# A non-tech (nurse) profile. Skills appear ONLY in the project's skill field
# and NOT in the title/impact text, so the only way the edge can exist is if the
# ingest path reads that field. None of these skills are in SKILL_CANONICAL.
_NURSE_SKILLS = ["IV Therapy", "ACLS", "Patient Assessment", "Wound Care"]


def _run(field: str, entrypoint: str, tmp_path: Path) -> subprocess.CompletedProcess:
    data_dir = (tmp_path / "appdata").as_posix()
    script = f"""
import os, sys, asyncio
os.environ["JHM_APP_DATA_DIR"] = {data_dir!r}
os.environ["LOCALAPPDATA"] = {data_dir!r}
sys.path.insert(0, "backend")

FIELD = {field!r}
SKILLS = {_NURSE_SKILLS!r}
PROJECTS = [
    {{"title": "ICU Sepsis Protocol Rollout",
      "impact": "Led bedside team adopting an early-warning sepsis bundle.",
      FIELD: ["IV Therapy", "ACLS", "Patient Assessment"]}},
    {{"title": "Ward Standardization Program",
      "impact": "Standardized dressing protocols across the surgical ward.",
      FIELD: ["Wound Care", "Patient Assessment"]}},
]

def ingest_json_import():
    from profile.service import ProfileService
    body = {{
        "candidate": {{"name": "Nora Nightingale", "summary": "Registered Nurse, ICU"}},
        "skills": [{{"name": s, "category": "clinical"}} for s in SKILLS],
        "projects": PROJECTS,
    }}
    asyncio.run(ProfileService().import_profile_data(body))

def ingest_materialize():
    from data.graph.profile_mutations import materialize_profile_snapshot
    profile = {{
        "n": "Nora Nightingale", "s": "Registered Nurse, ICU",
        "skills": [{{"n": s, "cat": "clinical"}} for s in SKILLS],
        "projects": PROJECTS,
    }}
    materialize_profile_snapshot(profile)

{{"json_import": ingest_json_import, "materialize": ingest_materialize}}[{entrypoint!r}]()

from data.graph import connection as c
edges = c._query_rows(
    "MATCH (:Project)-[r:PROJ_UTILIZES]->(:Skill) RETURN count(r)"
)[0][0]
linked_projects = {{r[0] for r in c._query_rows(
    "MATCH (p:Project)-[:PROJ_UTILIZES]->(:Skill) RETURN p.title"
)}}
view = c.graph_snapshot()
view_edges = [e for e in view["edges"] if e["type"] == "PROJ_UTILIZES"]

assert edges == 5, f"expected 5 PROJ_UTILIZES edges, got {{edges}}"
assert "ICU Sepsis Protocol Rollout" in linked_projects, (
    "project with skills only in a non-stack field is disconnected: "
    f"{{sorted(linked_projects)}}"
)
assert len(view_edges) == 5, f"graph view shows {{len(view_edges)}} PROJ_UTILIZES edges"
print("OK")
"""
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_json_import_links_project_skills_from_skills_field(tmp_path):
    result = _run("skills", "json_import", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_json_import_links_project_skills_from_technologies_field(tmp_path):
    result = _run("technologies", "json_import", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_json_import_links_project_skills_from_stack_field(tmp_path):
    # The original-working field must keep working (no regression).
    result = _run("stack", "json_import", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_materialize_snapshot_links_project_skills_from_skills_field(tmp_path):
    result = _run("skills", "materialize", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
