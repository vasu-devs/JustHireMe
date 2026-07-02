"""Field-agnostic relevance: tenure stated in prose counts toward experience (no
false seniority cap), and the score bands surface genuine matches while discarding
off-field/weak ones."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ranking.scoring_engine import _total_work_months

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_work_months_reads_prose_tenure():
    # Tenure in prose only (no machine-readable period) must still count — otherwise a
    # 6-year nurse looked like a fresher and got the seniority cap.
    nurse = {"s": "Registered Nurse with 6 years of critical care experience",
             "exp": [{"role": "ICU Nurse", "d": "6 years of ICU nursing"}]}
    assert _total_work_months(nurse) >= 72
    # A dated period still works and wins when larger.
    dated = {"s": "Engineer", "exp": [{"role": "Engineer", "period": "2015 - 2024"}]}
    assert _total_work_months(dated) >= 96
    # Interns don't count.
    intern = {"exp": [{"role": "Intern", "d": "3 years"}]}
    assert _total_work_months(intern) == 0


_BANDS = """
import sys
sys.path.insert(0, "backend")
from data.sqlite.connection import init_sql
init_sql()
from data.sqlite.leads import save_lead, update_lead_score, get_lead_by_id
from data.sqlite.settings import save_settings

def classify(job_id, score):
    save_lead({"job_id": job_id, "title": "X", "url": "https://x/" + job_id, "kind": "job"})
    update_lead_score(job_id, score, "r", [], [])
    return get_lead_by_id(job_id)["status"]

# Default bands: >=76 tailoring, >=45 matched (shown), else discarded.
assert classify("strong", 80) == "tailoring"
assert classify("moderate", 59) == "matched"     # a genuine non-tech match SURVIVES
assert classify("weak", 44) == "discarded"
assert classify("offfield", 15) == "discarded"   # ranker-capped junk stays hidden

# The show band is user-configurable.
save_settings({"match_threshold": "60"})
assert classify("moderate2", 59) == "discarded"   # now below the raised bar
assert classify("strong2", 70) == "matched"
print("BANDS_OK")
"""


def test_score_bands_surface_matches_and_are_configurable(tmp_path):
    env = dict(os.environ, JHM_APP_DATA_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, "-c", _BANDS], cwd=str(REPO_ROOT),
                            env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert "BANDS_OK" in result.stdout
