"""scripts/dashboard.py -- the metric/funnel/source SQL queries and the small
pure formatting helpers.

The pure helpers (``_humanize_action``, ``_short_ts``, ``_kv``, ``_tag_tone``)
run in-process -- they never touch a database. Everything that calls
``get_connection()`` runs in a **subprocess** instead: ``tests/unit/service/
test_api.py`` permanently rebinds ``data.sqlite.connection``'s own ``sqlite3``
name to a fake connection at import time (``sys.modules["sqlite3"] =
fake_sqlite`` with no teardown -- see its ``_install_storage_fakes()``), and
that leaks into every other test in the same pytest session once that module
is collected. A real SQLite file in a subprocess sidesteps it entirely, same
pattern as test_event_store_isolation.py / test_prune_history.py.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from paths import REPO_ROOT

SCRIPTS_DIR = REPO_ROOT / "backend" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import dashboard  # noqa: E402  pure-function tests only; DB tests import it fresh inside the subprocess


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", script], cwd=str(REPO_ROOT),
        capture_output=True, text=True, timeout=60,
    )


_PRELUDE = """
import sys, tempfile, os
sys.path.insert(0, 'backend')
sys.path.insert(0, 'backend/scripts')
import dashboard
from data.sqlite.connection import get_connection, run_migrations
from data.sqlite.leads import save_lead, save_lead_feedback, update_lead_status, update_lead_score
from data.sqlite.events import record_event

tmp = tempfile.mkdtemp(prefix='jhm-dashboard-test-')
db = os.path.join(tmp, 'crm.db')
run_migrations(db)
conn = get_connection(db)

def lead(job_id, platform='greenhouse', **extra):
    base = {'job_id': job_id, 'title': f'Role {job_id}', 'company': 'Acme', 'url': f'https://x/{job_id}', 'platform': platform}
    base.update(extra)
    return base
"""


def _assert_ok(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# headline_metrics
# ---------------------------------------------------------------------------

def test_headline_metrics_on_an_empty_db_is_all_zero():
    script = _PRELUDE + """
metrics = dashboard.headline_metrics(conn)
assert metrics == {
    "total": 0, "verified_confirmed": 0, "in_apply_queue": 0,
    "applied": 0, "interviews": 0, "offers": 0, "rejections": 0,
}, metrics
print("OK")
"""
    _assert_ok(_run(script))


def test_headline_metrics_counts_each_bucket_independently():
    script = _PRELUDE + """
for jid in ("a", "b", "c", "d"):
    save_lead(lead(jid), db)
conn.execute("UPDATE leads SET verify_status='CONFIRMED' WHERE job_id IN ('a','b')")
conn.commit()
update_lead_status("a", "draft_ready", db)
update_lead_status("b", "draft_ready", db)
update_lead_status("b", "approved", db)
update_lead_status("c", "draft_ready", db)
update_lead_status("c", "approved", db)
update_lead_status("c", "applied", db)
update_lead_status("c", "interviewing", db)
save_lead_feedback("c", "interview", db_path=db)  # what review.py's cmd_mark actually does on this transition
update_lead_status("d", "draft_ready", db)
update_lead_status("d", "approved", db)
update_lead_status("d", "applied", db)
save_lead_feedback("d", "app_rejected", db_path=db)
update_lead_status("d", "rejected", db)

metrics = dashboard.headline_metrics(conn)
assert metrics["total"] == 4, metrics
assert metrics["verified_confirmed"] == 2, metrics  # a, b
assert metrics["in_apply_queue"] == 2, metrics  # a (draft_ready) and b (approved), neither advanced further
assert metrics["applied"] == 2, metrics  # c, d both reached applied-or-later
assert metrics["interviews"] == 1, metrics  # c only
assert metrics["rejections"] == 1, metrics  # d
print("OK")
"""
    _assert_ok(_run(script))


# ---------------------------------------------------------------------------
# funnel_stages
# ---------------------------------------------------------------------------

def test_funnel_stages_dropoff_never_divides_by_zero():
    script = _PRELUDE + """
stages = dashboard.funnel_stages(conn, db)
assert [s["count"] for s in stages] == [0, 0, 0, 0, 0, 0], stages
assert all(s["dropoff_pct"] is None for s in stages), stages
print("OK")
"""
    _assert_ok(_run(script))


def test_funnel_stages_reflects_real_counts_and_computes_dropoff():
    script = _PRELUDE + """
for jid in ("a", "b", "c"):
    save_lead(lead(jid, description="Applied AI Engineer, Python, LangChain, remote India"), db)
conn.execute("UPDATE leads SET verify_checked_at=datetime('now') WHERE job_id IN ('a','b')")
conn.commit()
update_lead_status("a", "draft_ready", db)

stages = {s["label"]: s for s in dashboard.funnel_stages(conn, db)}
assert stages["Scraped"]["count"] == 3, stages
assert stages["Verified"]["count"] == 2, stages
assert stages["Drafted"]["count"] == 1, stages
for stage in stages.values():
    if stage["dropoff_pct"] is not None:
        assert 0 <= stage["dropoff_pct"] <= 100, stage
print("OK")
"""
    _assert_ok(_run(script))


def test_funnel_drafted_counts_a_lead_even_after_it_was_later_discarded():
    """The funnel's "Drafted" stage reads the event log, not current status --
    a lead that WAS drafted and later discarded still counts as drafted."""
    script = _PRELUDE + """
save_lead(lead("a"), db)
update_lead_status("a", "draft_ready", db)
update_lead_status("a", "discarded", db)

stages = {s["label"]: s for s in dashboard.funnel_stages(conn, db)}
assert stages["Drafted"]["count"] == 1, stages
print("OK")
"""
    _assert_ok(_run(script))


# ---------------------------------------------------------------------------
# source_breakdown
# ---------------------------------------------------------------------------

def test_source_breakdown_confirm_rate_is_none_when_nothing_verified():
    script = _PRELUDE + """
save_lead(lead("a", platform="jobicy"), db)
rows = dashboard.source_breakdown(conn)
assert len(rows) == 1, rows
assert rows[0]["platform"] == "jobicy", rows
assert rows[0]["verified"] == 0, rows
assert rows[0]["confirm_rate"] is None, rows
print("OK")
"""
    _assert_ok(_run(script))


def test_source_breakdown_computes_confirm_rate_per_platform():
    script = _PRELUDE + """
save_lead(lead("a", platform="greenhouse"), db)
save_lead(lead("b", platform="greenhouse"), db)
save_lead(lead("c", platform="ashby"), db)
conn.execute("UPDATE leads SET verify_status='CONFIRMED', verify_checked_at=datetime('now') WHERE job_id='a'")
conn.execute("UPDATE leads SET verify_status='REJECTED', verify_checked_at=datetime('now') WHERE job_id='b'")
conn.execute("UPDATE leads SET verify_status='REJECTED', verify_checked_at=datetime('now') WHERE job_id='c'")
conn.commit()

by_platform = {r["platform"]: r for r in dashboard.source_breakdown(conn)}
assert by_platform["greenhouse"]["confirmed"] == 1, by_platform
assert by_platform["greenhouse"]["verified"] == 2, by_platform
assert by_platform["greenhouse"]["confirm_rate"] == 50.0, by_platform
assert by_platform["ashby"]["confirm_rate"] == 0.0, by_platform
print("OK")
"""
    _assert_ok(_run(script))


# ---------------------------------------------------------------------------
# applications -- the table with the real answers.md content
# ---------------------------------------------------------------------------

def test_applications_includes_leads_reached_via_feedback_without_a_status_changed_event():
    """A lead marked applied via save_lead_feedback('already_contacted', ...)
    directly (not through review.py's update_lead_status) must still show up
    -- this is the path apply_assist.py / manual feedback tagging both use."""
    script = _PRELUDE + """
from pathlib import Path
save_lead(lead("a"), db)
save_lead_feedback("a", "already_contacted", db_path=db)
rows = dashboard.applications(conn, Path(tempfile.mkdtemp()))
assert [r["job_id"] for r in rows] == ["a"], rows
assert rows[0]["applied_at"] == "", rows  # no status_changed=applied event was ever written for this path
print("OK")
"""
    _assert_ok(_run(script))


def test_applications_reads_the_real_answers_md_off_disk():
    script = _PRELUDE + """
from pathlib import Path
job_id = "a1234567890abcdef"  # realistic 16-hex-char canonical id
save_lead(lead(job_id), db)
update_lead_status(job_id, "draft_ready", db)
update_lead_status(job_id, "approved", db)
update_lead_status(job_id, "applied", db)
drafts_dir = Path(tempfile.mkdtemp())
# matches generate_drafts._slug()'s own "<slug>-<job_id[:8]>" convention
folder = drafts_dir / f"acme-role-{job_id[:8]}"
folder.mkdir()
(folder / "answers.md").write_text("## Why Acme\\nBecause AegisQuery fits.\\n", encoding="utf-8")

rows = dashboard.applications(conn, drafts_dir)
assert len(rows) == 1, rows
assert "AegisQuery" in rows[0]["answers"], rows
print("OK")
"""
    _assert_ok(_run(script))


def test_applications_degrades_gracefully_with_no_packet_on_disk():
    script = _PRELUDE + """
from pathlib import Path
save_lead(lead("a1234567890abcdef"), db)
update_lead_status("a1234567890abcdef", "draft_ready", db)
update_lead_status("a1234567890abcdef", "approved", db)
update_lead_status("a1234567890abcdef", "applied", db)
rows = dashboard.applications(conn, Path(tempfile.mkdtemp()))  # empty drafts dir, no folder at all
assert rows[0]["answers"] == "", rows
print("OK")
"""
    _assert_ok(_run(script))


# ---------------------------------------------------------------------------
# recent_activity
# ---------------------------------------------------------------------------

def test_recent_activity_looks_up_title_and_company_for_lead_events_only():
    script = _PRELUDE + """
save_lead(lead("a", title="Staff Engineer", company="MongoDB"), db)
record_event(None, "cycle_started", db)  # a system event -- no lead to look up
record_event("a", "apply_opened", db)

rows = dashboard.recent_activity(conn, limit=10)
by_label = {r["label"]: r for r in rows}
assert by_label["opened to apply"]["title"] == "Staff Engineer", rows
assert by_label["opened to apply"]["company"] == "MongoDB", rows
assert by_label["loop cycle started"]["title"] == "", rows  # __system__ job_id, no lead
print("OK")
"""
    _assert_ok(_run(script))


# ---------------------------------------------------------------------------
# next_actions
# ---------------------------------------------------------------------------

def test_next_actions_orders_by_score_descending_and_only_the_queue_statuses():
    script = _PRELUDE + """
save_lead(lead("a"), db)
save_lead(lead("b"), db)
save_lead(lead("c"), db)
update_lead_score("a", 50, "ok", preserve_status=True, db_path=db)
update_lead_score("b", 90, "great", preserve_status=True, db_path=db)
update_lead_status("a", "draft_ready", db)
update_lead_status("b", "draft_ready", db)
update_lead_status("b", "approved", db)
# c stays at "discovered" -- not actionable, must be excluded

rows = dashboard.next_actions(conn)
assert [r["job_id"] for r in rows] == ["b", "a"], rows
assert rows[0]["command"] == "python scripts/review.py open b", rows
print("OK")
"""
    _assert_ok(_run(script))


# ---------------------------------------------------------------------------
# small pure helpers -- no DB, safe to run in-process
# ---------------------------------------------------------------------------

def test_short_ts_normalizes_both_timestamp_shapes_seen_in_this_db():
    assert dashboard._short_ts("2026-08-04 05:00:29") == "2026-08-04 05:00"
    assert dashboard._short_ts("2026-08-03T19:27:14.303043+00:00") == "2026-08-03 19:27"
    assert dashboard._short_ts("") == ""


def test_kv_extracts_a_single_token_value_stopping_at_whitespace():
    action = "verified verdict=CONFIRMED evidence=India-based onsite role -- verify directly backfilled=1"
    assert dashboard._kv(action, "verdict") == "CONFIRMED"
    assert dashboard._kv(action, "backfilled") == "1"
    assert dashboard._kv(action, "missing") == ""


def test_tag_tone_maps_verdicts_and_statuses_to_the_three_semantic_colors():
    assert dashboard._tag_tone("CONFIRMED") == "ok"
    assert dashboard._tag_tone("interviewing") == "ok"
    assert dashboard._tag_tone("REJECTED") == "bad"
    assert dashboard._tag_tone("DEAD") == "bad"
    assert dashboard._tag_tone("UNCLEAR") == "warn"
    assert dashboard._tag_tone("unverified") == ""


@pytest.mark.parametrize("action,expected_fragment", [
    ("discovered platform=greenhouse", "discovered via greenhouse"),
    ("discovered platform=ashby backfilled=1", "(backfilled)"),
    ("verified verdict=CONFIRMED evidence=India-based onsite", "verified: CONFIRMED"),
    ("draft_generated mode=llm", "draft generated (llm)"),
    ("packet_built folder=acme-role-a1", "application packet built"),
    ("apply_opened", "opened to apply"),
    ("status_changed=interviewing", "status changed to interviewing"),
    ("feedback=interview", "outcome recorded: interview"),
    ("score=74 status=preserved:discovered", "scored 74"),
    ("cycle_finished duration_s=42.3 added=4 shortlist=590 confirmed=2 drafted=1 errors=0", "finished in 42.3s"),
])
def test_humanize_action_covers_every_wired_event_type(action, expected_fragment):
    assert expected_fragment in dashboard._humanize_action(action)
