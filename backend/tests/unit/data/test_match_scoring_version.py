from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from core.scoring_version import MATCH_SCORING_VERSION, is_match_score_stale
from data.sqlite import leads


_REPO_ROOT = Path(__file__).resolve().parents[3]

_REAL_SQLITE_UPGRADE = r"""
import json
import os

from core.scoring_version import MATCH_SCORING_VERSION
from data.sqlite.connection import get_connection, init_sql
from data.sqlite.leads import get_lead_by_id, save_lead, update_lead_score

db_path = os.path.join(os.environ["JHM_APP_DATA_DIR"], "crm.db")
init_sql(db_path)
save_lead({
    "job_id": "legacy-score",
    "title": "Senior Account Based Marketing Manager",
    "company": "Dropbox",
    "url": "https://example.test/dropbox-abm",
    "platform": "greenhouse",
    "description": "Own account based marketing campaigns and pipeline. 6+ years required.",
    "kind": "job",
    "signal_score": 100,
    "signal_reason": "high-confidence source",
    "source_meta": {"quality": 100, "freshness": "assumed"},
}, db_path)

conn = get_connection(db_path)
conn.execute(
    "UPDATE leads SET status='tailoring',score=68,reason='legacy fit',"
    "match_points='[\"legacy point\"]',gaps='[\"legacy gap\"]' WHERE job_id=?",
    ("legacy-score",),
)
conn.commit()
conn.close()

stale = get_lead_by_id("legacy-score", db_path)
assert stale["score"] == 0
assert stale["score_stale"] is True
assert stale["signal_score"] == 100
assert stale["source_meta"]["quality"] == 100
assert stale["match_points"] == [] and stale["gaps"] == []

update_lead_score(
    "legacy-score", 15, "fresh candidate-relative fit", [],
    ["wrong-field cap: different occupation"], scored_by="deterministic",
    db_path=db_path,
)
fresh = get_lead_by_id("legacy-score", db_path)
assert fresh["score"] == 15
assert fresh["score_stale"] is False
assert fresh["status"] == "discarded"
assert fresh["source_meta"]["match_scoring_version"] == MATCH_SCORING_VERSION
assert fresh["source_meta"]["quality"] == 100
assert fresh["source_meta"]["scored_by"] == "deterministic"
print(json.dumps({
    "stale_visible_score": stale["score"],
    "source_signal_preserved": stale["signal_score"],
    "fresh_score": fresh["score"],
    "fresh_status": fresh["status"],
    "scoring_version": fresh["source_meta"]["match_scoring_version"],
}, sort_keys=True))
"""


def _row(*, score: int, version: int | None) -> dict:
    row = {name: "" for name in leads.LEAD_COLUMN_NAMES}
    row.update({
        "job_id": "j1",
        "title": "Engineer",
        "company": "Acme",
        "url": "https://example.com/job",
        "platform": "manual",
        "status": "tailoring",
        "kind": "job",
        "score": score,
        "reason": "old reasoning",
        "match_points": '["old point"]',
        "gaps": '["old gap"]',
        "source_meta": json.dumps({} if version is None else {"match_scoring_version": version}),
    })
    return row


def test_stale_match_scores_are_hidden_without_mutating_discovery_metadata():
    mapped = leads.lead_row_dict(_row(score=68, version=None))

    assert mapped["score"] == 0
    assert mapped["score_stale"] is True
    assert mapped["match_points"] == []
    assert mapped["gaps"] == []
    assert "re-evaluation" in mapped["reason"]


def test_current_and_unscored_rows_are_not_stale():
    current = leads.lead_row_dict(_row(score=82, version=MATCH_SCORING_VERSION))
    unscored = leads.lead_row_dict(_row(score=0, version=None))

    assert current["score"] == 82 and current["score_stale"] is False
    assert current["match_points"] == ["old point"]
    assert unscored["score"] == 0 and unscored["score_stale"] is False
    assert is_match_score_stale(90, {"match_scoring_version": "invalid"}) is True


def test_update_lead_score_stamps_current_algorithm_version(monkeypatch):
    calls: list[tuple[str, tuple]] = []

    class Result:
        def fetchone(self):
            return {"kind": "job", "status": "discovered", "source_meta": "{}"}

    class Connection:
        def execute(self, sql, params=()):
            calls.append((sql, tuple(params)))
            return Result()

        def commit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(leads, "get_connection", lambda _path: Connection())
    monkeypatch.setattr(leads, "_score_threshold", lambda _path, key, default: default)

    leads.update_lead_score("j1", 82, "current", ["match"], [], db_path="memory")

    update = next((params for sql, params in calls if sql.lstrip().startswith("UPDATE leads SET status=")), None)
    assert update is not None
    source_meta = json.loads(update[5])
    assert source_meta["match_scoring_version"] == MATCH_SCORING_VERSION


def test_real_sqlite_upgrade_hides_legacy_score_then_persists_fresh_score(tmp_path):
    env = dict(os.environ, JHM_APP_DATA_DIR=str(tmp_path))
    result = subprocess.run(
        [sys.executable, "-c", _REAL_SQLITE_UPGRADE],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report == {
        "fresh_score": 15,
        "fresh_status": "discarded",
        "scoring_version": MATCH_SCORING_VERSION,
        "source_signal_preserved": 100,
        "stale_visible_score": 0,
    }
