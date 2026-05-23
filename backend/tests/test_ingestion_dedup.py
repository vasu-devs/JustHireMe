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
