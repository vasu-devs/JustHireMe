"""scripts/shortlist.py -- the AI/LLM relevance + remote/India/APAC geo filter
and the ranking it drives. Pure functions, no DB, no network: exactly the
filter/rank logic a human's morning shortlist depends on being correct.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import shortlist  # noqa: E402


def _lead(**kw) -> dict:
    base = {"job_id": "j1", "title": "Engineer", "company": "Acme", "score": 50,
            "status": "discovered", "location": "", "description": "", "url": "https://x/1"}
    base.update(kw)
    return base


def test_ai_relevance_matches_llm_and_ml_terms():
    assert shortlist.is_ai_relevant(_lead(title="Applied AI Engineer"))
    assert shortlist.is_ai_relevant(_lead(title="Backend Engineer", description="Build our RAG pipeline with LangChain"))
    assert shortlist.is_ai_relevant(_lead(title="MCP Platform Engineer"))
    assert not shortlist.is_ai_relevant(_lead(title="Warehouse Associate", description="Pack boxes, drive forklift"))


def test_ai_relevance_is_word_bounded_not_a_substring_match():
    # "ai" must not fire on unrelated words that merely contain the letters.
    assert not shortlist.is_ai_relevant(_lead(title="Retail Cashier", description="maintain the till and receipts"))


def test_geo_relevance_accepts_remote_and_india_apac():
    assert shortlist.is_geo_relevant(_lead(location="Remote (Global)"))
    assert shortlist.is_geo_relevant(_lead(location="Gurgaon, India"))
    assert shortlist.is_geo_relevant(_lead(location="Singapore"))
    assert not shortlist.is_geo_relevant(_lead(location="New York, NY", description="onsite, no remote"))


def test_geo_relevance_us_only_clause_overrides_incidental_remote_mention():
    lead = _lead(location="Remote", description="Must be based in the U.S. Us citizens only.")
    assert not shortlist.is_geo_relevant(lead)


def test_filtered_ranked_leads_excludes_offfield_offgeo_and_discarded_then_sorts_by_score():
    leads = [
        _lead(job_id="a", title="Applied AI Engineer", location="Remote", score=70),
        _lead(job_id="b", title="LLM Platform Engineer", location="Bengaluru, India", score=95),
        _lead(job_id="c", title="Forklift Operator", location="Remote", score=99),  # off-field
        _lead(job_id="d", title="AI Engineer", location="New York onsite only", score=90),  # off-geo
        _lead(job_id="e", title="RAG Engineer", location="Remote", score=60, status="discarded"),  # discarded
    ]
    result = shortlist.filtered_ranked_leads(leads)
    assert [lead["job_id"] for lead in result] == ["b", "a"]


def test_filtered_ranked_leads_respects_limit():
    leads = [_lead(job_id=str(i), title="AI Engineer", location="Remote", score=i) for i in range(10)]
    result = shortlist.filtered_ranked_leads(leads, limit=3)
    assert len(result) == 3
    assert [lead["job_id"] for lead in result] == ["9", "8", "7"]
