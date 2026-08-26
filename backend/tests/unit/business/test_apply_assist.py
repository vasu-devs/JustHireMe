"""scripts/apply_assist.py -- queue ordering (score-descending over
draft_ready/approved, --force widens the pool to include applied), the
--field clipboard-selection logic (cover_letter.md/resume.txt/answers.md
section parsing plus the profile-identity fields), and the done-transition
(chains draft_ready->approved->applied through review.py's OWN state
machine, since review.TRANSITIONS has no direct draft_ready->applied edge --
same isolated-JHM_APP_DATA_DIR subprocess pattern as
test_review_transitions.py for the one part that needs a real DB).
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

import apply_assist  # noqa: E402

_PROFILE = {
    "identity": {
        "portfolio_url": "https://candidate.example.test",
        "email": "alex.candidate@example.test",
        "phone": "+1 555 010 0000",
    }
}


def _lead(job_id: str, score: int, status: str) -> dict:
    return {"job_id": job_id, "score": score, "status": status, "title": "x", "company": "y"}


# ---------------------------------------------------------------------------
# Queue ordering
# ---------------------------------------------------------------------------

def test_queue_sorts_by_score_descending_over_actionable_statuses_only(monkeypatch):
    leads = [
        _lead("a", 50, "draft_ready"),
        _lead("b", 90, "approved"),
        _lead("c", 70, "discovered"),  # not actionable through this tool -- excluded
        _lead("d", 80, "applied"),  # already applied -- excluded by default
    ]
    monkeypatch.setattr(apply_assist, "get_all_leads", lambda db_path: leads)
    queue = apply_assist._queue("ignored")
    assert [lead["job_id"] for lead in queue] == ["b", "a"]


def test_queue_force_widens_the_pool_to_include_applied_leads(monkeypatch):
    leads = [_lead("a", 50, "draft_ready"), _lead("d", 80, "applied")]
    monkeypatch.setattr(apply_assist, "get_all_leads", lambda db_path: leads)
    queue = apply_assist._queue("ignored", include_applied=True)
    assert [lead["job_id"] for lead in queue] == ["d", "a"]


def test_queue_is_empty_when_nothing_is_actionable(monkeypatch):
    monkeypatch.setattr(apply_assist, "get_all_leads", lambda db_path: [_lead("c", 70, "discovered")])
    assert apply_assist._queue("ignored") == []


# ---------------------------------------------------------------------------
# --field selection
# ---------------------------------------------------------------------------

def test_field_selection_reads_cover_letter_and_resume_text_verbatim(tmp_path):
    (tmp_path / "cover_letter.md").write_text("Dear team,\n\nBody text.\n", encoding="utf-8")
    (tmp_path / "resume.txt").write_text("RESUME PLAIN TEXT\n", encoding="utf-8")
    assert apply_assist._field_text("cover_letter", tmp_path, _PROFILE) == "Dear team,\n\nBody text.\n"
    assert apply_assist._field_text("resume_text", tmp_path, _PROFILE) == "RESUME PLAIN TEXT\n"


def test_field_selection_parses_why_and_work_auth_out_of_answers_md(tmp_path):
    (tmp_path / "answers.md").write_text(
        "# heading\n\n## Work authorization\nIndian citizen, no sponsorship needed.\n\n"
        "## Why Acme Corp\nAcme's data-governance problem is exactly AegisQuery's domain.\n",
        encoding="utf-8",
    )
    assert apply_assist._field_text("work_auth", tmp_path, _PROFILE) == "Indian citizen, no sponsorship needed."
    assert (
        apply_assist._field_text("why_company", tmp_path, _PROFILE)
        == "Acme's data-governance problem is exactly AegisQuery's domain."
    )


def test_field_selection_reads_identity_fields_straight_from_the_profile(tmp_path):
    # portfolio/email/phone are candidate-level, not lead-specific -- no
    # packet folder needed at all (None must not raise).
    assert apply_assist._field_text("portfolio", None, _PROFILE) == "https://candidate.example.test"
    assert apply_assist._field_text("email", None, _PROFILE) == "alex.candidate@example.test"
    assert apply_assist._field_text("phone", None, _PROFILE) == "+1 555 010 0000"


def test_field_selection_degrades_to_empty_string_when_file_is_missing(tmp_path):
    assert apply_assist._field_text("cover_letter", tmp_path, _PROFILE) == ""
    assert apply_assist._field_text("why_company", tmp_path, _PROFILE) == ""


def test_md_sections_splits_on_h2_headers_case_insensitively():
    sections = apply_assist._md_sections("## Alpha\nline one\nline two\n\n## Beta\nother\n")
    assert sections["alpha"] == "line one\nline two"
    assert sections["beta"] == "other"


# ---------------------------------------------------------------------------
# done-transition (real DB, isolated app-data dir, subprocess -- see
# test_harness_quirks: regression_support.py globally fakes sqlite3, so any
# real-SQLite assertion must run out-of-process)
# ---------------------------------------------------------------------------

def _run(script: str, tmp_path, *argv: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, JHM_APP_DATA_DIR=str(tmp_path))
    return subprocess.run(
        [sys.executable, "-c", script, *argv],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=180,
    )


_DONE_CHAINS_DRAFT_READY_THROUGH_APPROVED_TO_APPLIED = """
import argparse, sqlite3, sys
sys.path.insert(0, "backend")
sys.path.insert(0, "backend/scripts")
from pathlib import Path

from data.sqlite.connection import init_sql, DEFAULT_DB_PATH
init_sql()
from data.sqlite.leads import save_lead, get_lead_by_id

# review.TRANSITIONS has no direct draft_ready->applied edge (only
# draft_ready->approved->applied) -- "done" is the human's single "I
# applied" action regardless, so it must step through both transitions.
save_lead({"job_id": "z", "title": "Security Engineer", "company": "Acme", "platform": "greenhouse",
           "url": "https://x/z", "kind": "job"})
# A second, lower-scored lead stays in the queue -- proves `done` hands back
# the NEXT-highest remaining lead, not just "the queue is now empty."
save_lead({"job_id": "y", "title": "Platform Engineer", "company": "Beta", "platform": "greenhouse",
           "url": "https://x/y", "kind": "job"})
conn = sqlite3.connect(DEFAULT_DB_PATH)
conn.execute("UPDATE leads SET status='draft_ready', score=50 WHERE job_id='z'")
conn.execute("UPDATE leads SET status='approved', score=40 WHERE job_id='y'")
conn.commit()
conn.close()

import apply_assist
apply_assist.webbrowser.open = lambda *a, **k: True         # never open a real browser tab in a test
apply_assist._copy_to_clipboard = lambda *a, **k: True        # never touch the real system clipboard

rc = apply_assist.cmd_done(argparse.Namespace(
    job_id="z", note="", force=False, db=DEFAULT_DB_PATH,
    drafts_dir=str(Path(sys.argv[1]) / "drafts"),
    profile="backend/scripts/candidate_profile.json",
))
assert rc == 0, rc

z = get_lead_by_id("z", DEFAULT_DB_PATH)
assert z["status"] == "applied", z
assert z.get("feedback") == "already_contacted", z  # outcome feedback recorded, same as review.py mark
print("DONE_CHAIN_OK")
"""


def test_done_chains_draft_ready_through_approved_to_applied_and_offers_next(tmp_path):
    result = _run(_DONE_CHAINS_DRAFT_READY_THROUGH_APPROVED_TO_APPLIED, tmp_path, str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "DONE_CHAIN_OK" in result.stdout


_DONE_REJECTS_ILLEGAL_TARGET_WITHOUT_MUTATING_STATUS = """
import argparse, sqlite3, sys
sys.path.insert(0, "backend")
sys.path.insert(0, "backend/scripts")

from data.sqlite.connection import init_sql, DEFAULT_DB_PATH
init_sql()
from data.sqlite.leads import save_lead, get_lead_by_id

save_lead({"job_id": "z", "title": "Security Engineer", "company": "Acme", "platform": "greenhouse",
           "url": "https://x/z", "kind": "job"})
conn = sqlite3.connect(DEFAULT_DB_PATH)
conn.execute("UPDATE leads SET status='discarded', score=50 WHERE job_id='z'")
conn.commit()
conn.close()

import apply_assist
rc = apply_assist.cmd_done(argparse.Namespace(
    job_id="z", note="", force=False, db=DEFAULT_DB_PATH,
    drafts_dir="backend/scripts/drafts", profile="backend/scripts/candidate_profile.json",
))
assert rc != 0, rc
z = get_lead_by_id("z", DEFAULT_DB_PATH)
assert z["status"] == "discarded", z  # rejected transition must not mutate anything
print("REJECT_OK")
"""


def test_done_on_an_illegal_source_status_is_rejected_without_mutating_the_lead(tmp_path):
    result = _run(_DONE_REJECTS_ILLEGAL_TARGET_WITHOUT_MUTATING_STATUS, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "REJECT_OK" in result.stdout
