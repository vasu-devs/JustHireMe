"""scripts/review.py -- status-transition legality + the outcome-to-feedback
mapping that closes the loop (recorded application outcomes must feed back
into ranking, not just get stored).

Pure-logic tests for the transition table + mapping function; one subprocess
integration test (same isolated-``JHM_APP_DATA_DIR`` pattern as
test_feedback_recompute.py) proving the NEW "interview"/"offer"/"app_rejected"
feedback labels actually move ranking through the EXISTING feedback-learning
model, not just parse without error.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from paths import REPO_ROOT  # noqa: E402

import review  # noqa: E402


def test_legal_forward_transitions_pass():
    for current, targets in review.TRANSITIONS.items():
        for target in targets:
            assert review._validate(current, target, force=False) is None


def test_illegal_jump_is_rejected():
    assert review._validate("draft_ready", "offer", force=False) is not None


def test_discarded_is_always_a_legal_exit():
    assert review._validate("applied", "discarded", force=False) is None
    assert review._validate("interviewing", "discarded", force=False) is None


def test_force_bypasses_the_transition_check():
    assert review._validate("draft_ready", "offer", force=True) is None


def test_outcome_feedback_maps_each_stage():
    assert review.outcome_feedback_for("applied", "approved", "") == "already_contacted"
    assert review.outcome_feedback_for("interviewing", "applied", "") == "interview"
    assert review.outcome_feedback_for("offer", "interviewing", "interview") == "offer"


def test_rejection_without_ever_reaching_interview_is_negative_signal():
    assert review.outcome_feedback_for("rejected", "applied", "") == "app_rejected"


def test_rejection_after_reaching_interview_keeps_the_positive_signal_instead():
    # Rejected straight from "interviewing" (or after an "offer" outcome was
    # already recorded) -- the interview itself is already positive evidence;
    # a later process rejection at that stage must not overwrite it with a
    # negative label.
    assert review.outcome_feedback_for("rejected", "interviewing", "interview") is None
    assert review.outcome_feedback_for("rejected", "applied", "offer") is None


def test_approved_and_accepted_carry_no_new_feedback_signal():
    # These stages restate what draft_ready (already shortlisted + verified)
    # or an earlier outcome already said -- no feedback row needed for them.
    assert review.outcome_feedback_for("approved", "draft_ready", "") is None
    assert review.outcome_feedback_for("accepted", "offer", "offer") is None


def _run(script: str, tmp_path) -> subprocess.CompletedProcess:
    env = dict(os.environ, JHM_APP_DATA_DIR=str(tmp_path))
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=180,
    )


_INTERVIEW_BOOST = """
import sys
sys.path.insert(0, "backend")
from data.sqlite.connection import init_sql
init_sql()
from data.sqlite.leads import save_lead, save_lead_feedback, get_lead_by_id
from ranking.service import RankingService

# Lead A reached an interview -- the outcome scripts/review.py would record.
save_lead({"job_id": "a", "title": "Registered Nurse", "company": "Mercy", "platform": "greenhouse",
           "url": "https://x/a", "signal_score": 50, "kind": "job", "status": "interviewing"})
save_lead_feedback("a", "interview", "reached final round")

# Lead B is an open, similarly-shaped lead with no feedback yet.
save_lead({"job_id": "b", "title": "Staff Nurse", "company": "Grace", "platform": "greenhouse",
           "url": "https://x/b", "signal_score": 40, "kind": "job", "status": "matched"})

RankingService()._recompute_feedback_signals(500)
b = get_lead_by_id("b")
assert b["signal_score"] > 40, b
assert int(b.get("learning_delta") or 0) > 0, b
print("INTERVIEW_BOOST_OK")
"""

_APP_REJECTED_PENALTY = """
import sys
sys.path.insert(0, "backend")
from data.sqlite.connection import init_sql
init_sql()
from data.sqlite.leads import save_lead, save_lead_feedback, get_lead_by_id
from ranking.service import RankingService

save_lead({"job_id": "a", "title": "Registered Nurse", "company": "Mercy", "platform": "lever",
           "url": "https://x/a", "signal_score": 50, "kind": "job", "status": "rejected"})
save_lead_feedback("a", "app_rejected", "no interview offered")

save_lead({"job_id": "b", "title": "Staff Nurse", "company": "Grace", "platform": "lever",
           "url": "https://x/b", "signal_score": 40, "kind": "job", "status": "matched"})

RankingService()._recompute_feedback_signals(500)
b = get_lead_by_id("b")
assert b["signal_score"] < 40, b
assert int(b.get("learning_delta") or 0) < 0, b
print("APP_REJECTED_PENALTY_OK")
"""


def test_interview_outcome_boosts_similar_leads(tmp_path):
    result = _run(_INTERVIEW_BOOST, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "INTERVIEW_BOOST_OK" in result.stdout


def test_app_rejected_outcome_penalizes_similar_leads(tmp_path):
    result = _run(_APP_REJECTED_PENALTY, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "APP_REJECTED_PENALTY_OK" in result.stdout
