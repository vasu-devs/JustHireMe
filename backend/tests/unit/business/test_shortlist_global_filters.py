"""scripts/shortlist_global.py -- the corrected hireability classifier
(A/B/C/D/U) and the ranking it drives. Pure functions, no DB, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import shortlist_global as sg  # noqa: E402


def _lead(**kw) -> dict:
    base = {"job_id": "j1", "title": "Engineer", "company": "Acme", "score": 50,
            "signal_score": 0, "status": "discovered", "location": "", "description": "", "url": "https://x/1"}
    base.update(kw)
    return base


def test_band_a_global_remote_phrases():
    assert sg.classify_geo(_lead(description="We hire from anywhere, any timezone."))[0] == "A"
    assert sg.classify_geo(_lead(description="Fully remote, globally distributed team."))[0] == "A"


def test_band_b_india_entity_signal():
    assert sg.classify_geo(_lead(location="Gurgaon, India"))[0] == "B"
    assert sg.classify_geo(_lead(description="Our Bengaluru office is hiring."))[0] == "B"


def test_band_c_eor_and_contractor_signals():
    assert sg.classify_geo(_lead(description="Engaged via Deel as an EOR."))[0] == "C"
    assert sg.classify_geo(_lead(description="This is a B2B contractor engagement."))[0] == "C"


def test_band_d_strong_region_lock_overrides_incidental_remote():
    lead = _lead(location="Remote", description="Must be based in the U.S. Us citizens only.")
    assert sg.classify_geo(lead)[0] == "D"


def test_band_d_weak_only_fires_without_a_positive_signal():
    # bare "hybrid" with nothing else -> excluded (D, weak).
    assert sg.classify_geo(_lead(description="Hybrid role, 3 days in office."))[0] == "D"
    # "hybrid" mentioned but company also explicitly offers anywhere-remote -> A wins.
    lead = _lead(description="Remote-first; work from anywhere. Optional hybrid office for those nearby.")
    assert sg.classify_geo(lead)[0] == "A"


def test_band_u_when_no_signal_either_way():
    assert sg.classify_geo(_lead(location="", description="Great team, great mission."))[0] == "U"


def test_filtered_ranked_leads_keeps_only_ai_and_abc_bands_then_sorts_by_score():
    leads = [
        _lead(job_id="a", title="Applied AI Engineer", description="Work from anywhere, any timezone.", score=70),
        _lead(job_id="b", title="LLM Platform Engineer", location="Bengaluru, India", score=95),
        _lead(job_id="c", title="Forklift Operator", description="Work from anywhere.", score=99),  # off-field
        _lead(job_id="d", title="AI Engineer", description="Must be based in the US. US citizens only.", score=90),  # band D
        _lead(job_id="e", title="RAG Engineer", description="Great mission, join us.", score=85),  # band U, no signal
        _lead(job_id="f", title="AI Engineer", description="Hired via Deel, contractor B2B.", score=60, status="discarded"),
    ]
    result = sg.filtered_ranked_leads(leads)
    assert [lead["job_id"] for lead in result] == ["b", "a"]
    assert result[0]["geo_band"] == "B"
    assert result[1]["geo_band"] == "A"


def test_filtered_ranked_leads_respects_limit():
    leads = [_lead(job_id=str(i), title="AI Engineer", description="hire from anywhere", score=i) for i in range(10)]
    result = sg.filtered_ranked_leads(leads, limit=3)
    assert len(result) == 3
    assert [lead["job_id"] for lead in result] == ["9", "8", "7"]
