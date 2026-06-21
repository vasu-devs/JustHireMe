# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs
"""Regression tests for resume-ingestion accuracy fixes:

- one job extracted multiple times must collapse to a single experience
- education entries differing only in spacing/punctuation must de-duplicate
- a genuine project (repo / real stack / substantial impact) must not be
  absorbed into the previous project or dropped for a detail-like title
"""

from profile import normalization as norm
from profile import service as svc


def test_normalize_experiences_collapses_duplicate_job():
    rows = [
        {"role": "Freelance Engineer", "company": "Self-employed", "period": "2024", "description": "Built a platform."},
        {"role": "Freelance Engineer ", "company": "Self-employed", "period": "", "description": "Built a production-grade finance platform end to end."},
        {"role": "freelance  engineer", "company": "self-employed", "period": "2024", "description": "Built a platform."},
    ]
    out = norm.normalize_experiences(rows)
    assert len(out) == 1
    # keeps the richest (longest) description
    assert "production-grade" in out[0]["description"]
    assert out[0]["period"] == "2024"


def test_normalize_candidate_model_dedupes_experiences():
    from models.schema import C, E

    model = C(
        n="Jane Doe",
        s="Engineer",
        exp=[
            E(role="Freelance Engineer", co="Self-employed", period="2024", d="Built a platform.", s=[]),
            E(role="Freelance Engineer", co="Self-employed", period="2024", d="Built a platform.", s=[]),
            E(role="Freelance Engineer", co="Self-employed", period="2024", d="Built a platform.", s=[]),
        ],
    )
    cleaned = norm.normalize_candidate_model(model)
    assert len(cleaned.exp) == 1


def test_dedupe_text_items_ignores_punctuation_and_spacing():
    items = [
        "B.Tech Computer Science - IIT Delhi, 2020",
        "B.Tech Computer Science  -  IIT Delhi 2020",
        "B.Tech Computer Science – IIT Delhi, 2020",
    ]
    assert len(svc._dedupe_text_items(items)) == 1


def test_dedupe_dict_items_collapses_same_job_with_different_ids():
    items = [
        {"id": "hash-aaa", "role": "Freelance Engineer", "co": "Self-employed", "period": "2024", "d": "x"},
        {"id": "hash-bbb", "role": "Freelance Engineer", "co": "Self-employed", "period": "", "d": "x"},
    ]
    assert len(svc._dedupe_dict_items(items, "id")) == 1


def test_same_project_named_two_ways_merges_into_one():
    """A project listed once as a plain name and again with a repo / GitHub
    annotation is ONE project — they must collapse to a single entry that keeps
    the repo and the richest stack/impact, not two near-duplicate nodes."""
    projects = [
        {"title": "Vaani", "stack": "Python", "impact": "A voice assistant.", "repo": ""},
        {"title": "Vaani (github.com/vasu/vaani)", "stack": "Python, FastAPI", "impact": "A real-time multilingual voice assistant with streaming ASR.", "repo": "https://github.com/vasu/vaani"},
    ]
    out = norm.normalize_projects(projects)
    assert len(out) == 1, f"expected one merged project, got {[p['title'] for p in out]}"
    merged = out[0]
    assert merged["title"] == "Vaani"  # source annotation stripped
    assert "github.com/vasu/vaani" in merged["repo"]  # repo salvaged from the richer mention
    assert "FastAPI" in merged["stack"]  # stacks unioned
    assert "streaming ASR" in merged["impact"]  # longer impact kept


def test_source_annotation_does_not_merge_distinct_projects():
    """Two genuinely different projects must stay separate even when one carries
    a (GitHub) annotation — dedup is by cleaned title, not by stripping suffixes."""
    projects = [
        {"title": "Vaani (GitHub)", "stack": "Python", "impact": "Voice assistant.", "repo": "https://github.com/u/vaani"},
        {"title": "BranchGPT", "stack": "TypeScript", "impact": "Git workflow copilot.", "repo": "https://github.com/u/branchgpt"},
    ]
    out = norm.normalize_projects(projects)
    titles = sorted(p["title"] for p in out)
    assert titles == ["BranchGPT", "Vaani"], titles


def test_project_with_repo_is_not_absorbed_despite_detail_like_title():
    projects = [
        {"title": "Acme Dashboard", "stack": "React, TypeScript", "impact": "Internal ops console.", "repo": ""},
        # detail-like title but has a real repo + stack -> a standalone project
        {"title": "Built a real-time analytics pipeline", "stack": "Python, Kafka", "impact": "Streams events.", "repo": "https://github.com/u/analytics"},
    ]
    out = norm.normalize_projects(projects)
    titles = [p["title"] for p in out]
    assert len(out) == 2, f"expected both projects kept, got {titles}"
    # the analytics project survives with a salvaged/usable title and its repo
    assert any("analytics" in t.lower() for t in titles)
