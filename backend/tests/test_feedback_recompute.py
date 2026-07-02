"""Feedback learning actually reshapes ranking (the 'gets better with use' promise).

Runs in a subprocess with an isolated ``JHM_APP_DATA_DIR`` — the recompute path
touches real ``data.sqlite`` (feedback examples, leads-for-learning, learning-score
update), which the suite's global ``sqlite3`` fake would poison. See
``test_telemetry_metrics.py`` for the same pattern.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(script: str, tmp_path) -> subprocess.CompletedProcess:
    env = dict(os.environ, JHM_APP_DATA_DIR=str(tmp_path))
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


_RERANK = """
import sys
sys.path.insert(0, "backend")
from data.sqlite.connection import init_sql
init_sql()
from data.sqlite.leads import save_lead, save_lead_feedback, get_lead_by_id
from ranking.service import RankingService

# Lead A is marked "good" and lives on greenhouse.
save_lead({"job_id": "a", "title": "Registered Nurse", "company": "Mercy",
           "platform": "greenhouse", "url": "https://x/a", "signal_score": 50,
           "kind": "job", "status": "matched"})
save_lead_feedback("a", "good", "")

# Leads B and C have no feedback yet but share the greenhouse platform.
# Two of them force the batch writer (update_learning_scores) to persist >1 row
# in a single executemany/commit.
save_lead({"job_id": "b", "title": "Staff Nurse", "company": "Grace",
           "platform": "greenhouse", "url": "https://x/b", "signal_score": 40,
           "kind": "job", "status": "matched"})
save_lead({"job_id": "c", "title": "ICU Nurse", "company": "Hope",
           "platform": "greenhouse", "url": "https://x/c", "signal_score": 42,
           "kind": "job", "status": "matched"})

rs = RankingService()
changed = rs._recompute_feedback_signals(500)
b = get_lead_by_id("b")
c = get_lead_by_id("c")
assert b["signal_score"] > 40, b                       # boosted by learned preference
assert c["signal_score"] > 42, c                       # second row in the same batch
assert int(b.get("learning_delta") or 0) > 0, b
assert int(c.get("learning_delta") or 0) > 0, c
assert any(x.get("job_id") == "b" for x in changed), changed
assert any(x.get("job_id") == "c" for x in changed), changed

# Idempotent: a second recompute must not stack the delta.
first_delta = int(b["learning_delta"])
rs._recompute_feedback_signals(500)
b2 = get_lead_by_id("b")
assert int(b2["learning_delta"]) == first_delta, (first_delta, b2)
print("RELEARN_OK")
"""


_NOOP = """
import sys
sys.path.insert(0, "backend")
from data.sqlite.connection import init_sql
init_sql()
from data.sqlite.leads import save_lead
from ranking.service import RankingService

save_lead({"job_id": "x", "title": "Welder", "platform": "lever",
           "url": "https://x/x", "signal_score": 40, "kind": "job", "status": "matched"})
# No feedback anywhere => nothing learned => no re-ranking.
assert RankingService()._recompute_feedback_signals(500) == []
print("NOOP_OK")
"""


_MATCH_RERANK = """
import sys
sys.path.insert(0, "backend")
from unittest import mock
from data.sqlite.connection import init_sql
init_sql()
from data.sqlite.leads import save_lead, save_lead_feedback, update_lead_score, get_lead_by_id
from ranking.service import RankingService

save_lead({"job_id": "a", "title": "Registered Nurse", "platform": "greenhouse",
           "url": "https://x/a", "signal_score": 50, "kind": "job", "status": "matched"})
save_lead_feedback("a", "good", "")
save_lead({"job_id": "b", "title": "Staff Nurse", "platform": "greenhouse",
           "url": "https://x/b", "signal_score": 40, "kind": "job", "status": "matched"})
update_lead_score("b", 50, "base match", [], [], preserve_status=True)   # base MATCH score = 50, keep status

rs = RankingService()
# Force a deterministic +10 match delta for b (bypasses the embedding model).
with mock.patch("ranking.feedback_semantic.preference_deltas", return_value={"b": 10, "a": 10}):
    rs._recompute_feedback_signals(500)
    first = int(get_lead_by_id("b")["score"])
    rs._recompute_feedback_signals(500)   # repeat -> must re-apply from base, not stack
    second = int(get_lead_by_id("b")["score"])
assert first == 60, first            # 50 base + 10 preference
assert second == 60, (first, second) # idempotent, NOT 70
print("MATCH_RERANK_OK")
"""


_MATCH_ZERO = """
import sys
sys.path.insert(0, "backend")
from unittest import mock
from data.sqlite.connection import init_sql
init_sql()
from data.sqlite.leads import save_lead, save_lead_feedback, update_lead_score, get_lead_by_id
from ranking.service import RankingService

save_lead({"job_id": "a", "title": "Registered Nurse", "platform": "greenhouse",
           "url": "https://x/a", "signal_score": 50, "kind": "job", "status": "matched"})
save_lead_feedback("a", "not_relevant", "")   # an example must exist or recompute no-ops
save_lead({"job_id": "b", "title": "Line Cook", "platform": "greenhouse",
           "url": "https://x/b", "signal_score": 40, "kind": "job", "status": "matched"})
update_lead_score("b", 10, "weak base match", [], [], preserve_status=True)  # low base match = 10

rs = RankingService()
# Strong negative preference delta drives b's match score to exactly 0.
with mock.patch("ranking.feedback_semantic.preference_deltas", return_value={"b": -10, "a": -10}):
    rs._recompute_feedback_signals(500)
persisted = int(get_lead_by_id("b")["score"])
# The regression: `0 or base_score` used to short-circuit and persist the base (10);
# a legitimately-computed match score of exactly 0 must survive as 0.
assert persisted == 0, persisted
print("MATCH_ZERO_OK")
"""


def test_feedback_recompute_reranks_open_leads(tmp_path):
    result = _run(_RERANK, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "RELEARN_OK" in result.stdout


def test_feedback_reranks_match_score_idempotently(tmp_path):
    result = _run(_MATCH_RERANK, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "MATCH_RERANK_OK" in result.stdout


def test_feedback_reranks_match_score_to_exactly_zero(tmp_path):
    result = _run(_MATCH_ZERO, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "MATCH_ZERO_OK" in result.stdout


def test_recompute_is_noop_without_feedback(tmp_path):
    result = _run(_NOOP, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "NOOP_OK" in result.stdout
