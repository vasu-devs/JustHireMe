"""Audit-report queries — business layer behind ``api/routers/dashboard.py``
and ``scripts/dashboard.py`` (the standalone HTML report).

Every number here comes from a real SQL query against the live database (or,
for "the answers that were submitted", a real file on disk) — nothing here
fabricates or estimates. These were originally CLI-script-only; moved here so
the web dashboard and the CLI report render off the exact same tested queries
instead of two copies that could drift.

Package name is ``reporting``, not ``dashboard``: ``scripts/dashboard.py`` is
already a top-level module name on ``sys.path`` in CLI contexts, and a
business package literally named ``dashboard`` would shadow-collide with it.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from data.repository import Repository
from data.sqlite.connection import checkpoint_wal, get_connection
from leads.shortlist import classify_geo, is_ai_relevant

# Same default the CLI script has always used: backend/scripts/drafts, written
# by build_packet.py / apply_assist.py. Not user-configurable from the API —
# single-tenant desktop install, one drafts folder.
DEFAULT_DRAFTS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "drafts"

# A lead counts as "ever applied" either because its CURRENT status is
# applied-or-later in the review.py state machine, or because feedback was
# recorded directly (save_lead_feedback's already_contacted/interview/offer/
# app_rejected path, which sets status too but doesn't always go through
# review.py). Shared between the headline metric and the applications table
# so the two numbers can never silently disagree.
_APPLIED_STATUSES = ("applied", "interviewing", "offer", "accepted", "rejected")
_APPLIED_FEEDBACK = ("already_contacted", "interview", "offer", "app_rejected")
_APPLIED_SQL = (
    f"(status IN ({','.join('?' * len(_APPLIED_STATUSES))}) "
    f"OR feedback IN ({','.join('?' * len(_APPLIED_FEEDBACK))}))"
)
_APPLIED_PARAMS = (*_APPLIED_STATUSES, *_APPLIED_FEEDBACK)


# ---------------------------------------------------------------------------
# Queries -- each takes a live connection and returns plain data.
# ---------------------------------------------------------------------------

def headline_metrics(conn) -> dict:
    row = conn.execute(
        f"""
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN verify_status='CONFIRMED' THEN 1 ELSE 0 END) AS verified_confirmed,
          SUM(CASE WHEN status IN ('draft_ready','approved') THEN 1 ELSE 0 END) AS in_apply_queue,
          SUM(CASE WHEN {_APPLIED_SQL} THEN 1 ELSE 0 END) AS applied,
          SUM(CASE WHEN feedback IN ('interview','offer') THEN 1 ELSE 0 END) AS interviews,
          SUM(CASE WHEN feedback='offer' THEN 1 ELSE 0 END) AS offers,
          SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) AS rejections
        FROM leads
        """,
        _APPLIED_PARAMS,
    ).fetchone()
    # sqlite3.Row iteration yields values; `.keys()` is required for named access.
    return {key: int(row[key] or 0) for key in row.keys()}  # noqa: SIM118


FUNNEL_LABELS = ("Scraped", "Shortlisted", "Verified", "Drafted", "Applied", "Interview")

# Bands leads.shortlist.filtered_ranked_leads keeps -- kept in sync by hand
# since that function is the source of truth for which leads actually get
# verified/drafted; this only needs the same predicate as a fast COUNT.
_SHORTLIST_BANDS = ("A", "B", "C")


def _classify_pending_leads(conn) -> None:
    """Persist ai_relevant/geo_band for any lead that doesn't have them yet
    (newly scraped, or predating migration 007) -- an O(n) regex classify is
    fine once per lead, not once per dashboard request. Both are pure
    functions of title/location/description: those are set at insert time and
    (barring discovery.maintenance's text-repair pass, which recomputes them
    itself) never change after, so caching them in a column never goes stale.

    Unbounded on purpose: capping this to a per-request batch would make the
    "Shortlisted" count quietly wrong (undercounted) for however many requests
    it takes a large historical backlog to finish backfilling. Uncapped, the
    cost is paid once -- the first request after this ships classifies the
    whole existing table (same cost the old per-request scan paid on EVERY
    request); every request after that only classifies the handful of leads
    the last scrape cycle added, which is fast."""
    rows = conn.execute(
        "SELECT job_id, title, location, description FROM leads WHERE geo_band IS NULL"
    ).fetchall()
    if not rows:
        return
    updates = []
    for row in rows:
        lead = {"title": row["title"], "location": row["location"], "description": row["description"]}
        band, _evidence = classify_geo(lead)
        updates.append((int(is_ai_relevant(lead)), band, row["job_id"]))
    conn.executemany("UPDATE leads SET ai_relevant = ?, geo_band = ? WHERE job_id = ?", updates)
    conn.commit()


def funnel_stages(conn, db_path: str | None = None) -> list[dict]:
    # db_path is accepted (unused) only for call-site/back-compat -- funnel
    # counts now come entirely from `conn`, never a second get_all_leads() scan.
    _classify_pending_leads(conn)
    scraped = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    placeholders = ",".join("?" * len(_SHORTLIST_BANDS))
    shortlisted = conn.execute(
        f"SELECT COUNT(*) FROM leads WHERE ai_relevant=1 AND geo_band IN ({placeholders}) "
        "AND status NOT IN ('discarded','rejected')",
        _SHORTLIST_BANDS,
    ).fetchone()[0]
    verified = conn.execute("SELECT COUNT(*) FROM leads WHERE verify_checked_at != ''").fetchone()[0]
    # "Drafted" reaches into the event log (not the current status column) on
    # purpose: a lead drafted and later discarded still WAS drafted, and only
    # the audit trail remembers that once its status has moved on.
    drafted = conn.execute(
        "SELECT COUNT(DISTINCT job_id) FROM events WHERE action LIKE 'status_changed=draft_ready%'"
    ).fetchone()[0]
    applied = conn.execute(f"SELECT COUNT(*) FROM leads WHERE {_APPLIED_SQL}", _APPLIED_PARAMS).fetchone()[0]
    interview = conn.execute("SELECT COUNT(*) FROM leads WHERE feedback IN ('interview','offer')").fetchone()[0]

    counts = [scraped, shortlisted, verified, drafted, applied, interview]
    stages, prev = [], None
    for label, count in zip(FUNNEL_LABELS, counts, strict=True):
        dropoff = round((1 - count / prev) * 100) if prev else None
        stages.append({"label": label, "count": int(count), "dropoff_pct": dropoff})
        prev = count
    return stages


def source_breakdown(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT platform,
               COUNT(*) AS total,
               SUM(CASE WHEN verify_checked_at != '' THEN 1 ELSE 0 END) AS verified,
               SUM(CASE WHEN verify_status='CONFIRMED' THEN 1 ELSE 0 END) AS confirmed
        FROM leads
        GROUP BY platform
        ORDER BY confirmed DESC, verified DESC, total DESC
        """
    ).fetchall()
    out = []
    for row in rows:
        verified, confirmed = int(row["verified"] or 0), int(row["confirmed"] or 0)
        out.append({
            "platform": row["platform"] or "unknown",
            "total": int(row["total"] or 0),
            "verified": verified,
            "confirmed": confirmed,
            "confirm_rate": round(confirmed / verified * 100, 1) if verified else None,
        })
    return out


def draft_answers(job_id: str, drafts_dir: Path) -> str:
    """The actual text of answers.md for this lead's packet, if one was ever
    built -- what the task calls "the answers that were submitted"."""
    if not job_id or not drafts_dir.exists():
        return ""
    matches = list(drafts_dir.glob(f"*-{str(job_id)[:8]}/answers.md"))
    if not matches:
        return ""
    try:
        return matches[0].read_text(encoding="utf-8")
    except OSError:
        return ""


def applications(conn, drafts_dir: Path) -> list[dict]:
    rows = conn.execute(
        f"""
        SELECT job_id, title, company, url, score, verify_status, status,
               (SELECT MIN(ts) FROM events e WHERE e.job_id = leads.job_id
                  AND e.action LIKE 'status_changed=applied%') AS applied_at
        FROM leads
        WHERE {_APPLIED_SQL}
        ORDER BY applied_at DESC, score DESC
        """,
        _APPLIED_PARAMS,
    ).fetchall()
    return [
        {
            "job_id": row["job_id"],
            "title": row["title"] or "",
            "company": row["company"] or "",
            "url": row["url"] or "",
            "score": int(row["score"] or 0),
            "band": row["verify_status"] or "unverified",
            "status": row["status"] or "",
            "applied_at": row["applied_at"] or "",
            "answers": draft_answers(row["job_id"], drafts_dir),
        }
        for row in rows
    ]


def verification(conn, job_id: str) -> dict:
    """Verify-status + the evidence text behind it, for one lead — the
    Application Detail screen's "verification evidence" panel."""
    row = conn.execute(
        "SELECT verify_status, verify_evidence, verify_checked_at FROM leads WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        return {"verify_status": "", "verify_evidence": "", "verify_checked_at": ""}
    return {
        "verify_status": row["verify_status"] or "",
        "verify_evidence": row["verify_evidence"] or "",
        "verify_checked_at": row["verify_checked_at"] or "",
    }


def leads_per_day(conn) -> list[tuple[str, int]]:
    rows = conn.execute(
        "SELECT date(created_at) AS d, COUNT(*) AS c FROM leads WHERE created_at != '' GROUP BY d ORDER BY d"
    ).fetchall()
    return [(row["d"], int(row["c"])) for row in rows if row["d"]]


def applications_per_day(conn) -> list[tuple[str, int]]:
    rows = conn.execute(
        "SELECT date(ts) AS d, COUNT(DISTINCT job_id) AS c FROM events "
        "WHERE action LIKE 'status_changed=applied%' GROUP BY d ORDER BY d"
    ).fetchall()
    return [(row["d"], int(row["c"])) for row in rows if row["d"]]


_KV_RE_CACHE: dict[str, re.Pattern] = {}


def kv(action: str, key: str) -> str:
    pattern = _KV_RE_CACHE.setdefault(key, re.compile(rf"\b{re.escape(key)}=(\S+)"))
    match = pattern.search(action or "")
    return match.group(1) if match else ""


def humanize_action(action: str) -> str:
    """The events table's action strings are compact key=value logs (matches
    the format update_lead_score/update_lead_status already write) -- this
    turns one into the sentence the activity feed shows."""
    action = action or ""
    backfilled = " (backfilled)" if "backfilled=1" in action else ""
    if action.startswith("cycle_started"):
        return "loop cycle started"
    if action.startswith("cycle_finished"):
        dur = kv(action, "duration_s")
        added = kv(action, "added")
        confirmed = kv(action, "confirmed")
        return f"loop cycle finished in {dur}s ({added} new leads, {confirmed} confirmed)"
    if action.startswith("discovered"):
        return f"discovered via {kv(action, 'platform') or 'unknown source'}{backfilled}"
    if action.startswith("verified"):
        return f"verified: {kv(action, 'verdict') or 'unclear'}{backfilled}"
    if action.startswith("draft_generated"):
        return f"draft generated ({kv(action, 'mode') or 'unknown mode'}){backfilled}"
    if action.startswith("packet_built"):
        return "application packet built"
    if action.startswith("apply_opened"):
        return "opened to apply"
    if action.startswith("status_changed="):
        return f"status changed to {action.split('=', 1)[1]}"
    if action.startswith("feedback="):
        return f"outcome recorded: {action.split('=', 1)[1]}"
    if action.startswith("score="):
        return f"scored {kv(action, 'score')}"
    return action[:80]


def short_ts(ts: str) -> str:
    """Normalize the two timestamp shapes this DB actually contains --
    SQLite's own ``datetime('now')`` and the backfilled meta.json's
    ``isoformat()`` -- to one short, equal-width "YYYY-MM-DD HH:MM" for
    display."""
    return (ts or "").replace("T", " ")[:16]


def recent_activity(conn, limit: int = 40) -> list[dict]:
    rows = conn.execute(
        "SELECT job_id, action, ts FROM events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    job_ids = {row["job_id"] for row in rows if row["job_id"] and row["job_id"] != "__system__"}
    lookup: dict[str, tuple[str, str]] = {}
    if job_ids:
        placeholders = ",".join("?" * len(job_ids))
        for row in conn.execute(
            f"SELECT job_id, title, company FROM leads WHERE job_id IN ({placeholders})", tuple(job_ids)
        ):
            lookup[row["job_id"]] = (row["title"] or "", row["company"] or "")
    out = []
    for row in rows:
        title, company = lookup.get(row["job_id"], ("", ""))
        out.append({
            "ts": short_ts(row["ts"]), "label": humanize_action(row["action"]),
            "title": title, "company": company,
        })
    return out


def next_actions(conn, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT job_id, title, company, url, score, verify_status FROM leads "
        "WHERE status IN ('draft_ready','approved') ORDER BY score DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "job_id": row["job_id"], "title": row["title"] or "", "company": row["company"] or "",
            "url": row["url"] or "", "score": int(row["score"] or 0),
            "band": row["verify_status"] or "unverified",
            "command": f"python scripts/review.py open {row['job_id']}",
        }
        for row in rows
    ]


def tag_tone(status_or_band: str) -> str:
    value = (status_or_band or "").lower()
    if value in ("confirmed", "offer", "accepted", "interviewing", "interview"):
        return "ok"
    if value in ("rejected", "dead", "app_rejected"):
        return "bad"
    if value in ("unclear",):
        return "warn"
    return ""


def gather(conn, db_path: str, drafts_dir: Path) -> dict:
    return {
        "headline": headline_metrics(conn),
        "funnel": funnel_stages(conn, db_path),
        "sources": source_breakdown(conn),
        "applications": applications(conn, drafts_dir),
        "leads_per_day": leads_per_day(conn),
        "applications_per_day": applications_per_day(conn),
        "activity": recent_activity(conn),
        "next_actions": next_actions(conn),
    }


# ---------------------------------------------------------------------------
# Service -- the async wrapper the "/api/v1/dashboard/*" router depends on.
# ---------------------------------------------------------------------------

class ReportingService:
    def __init__(self, repo: Repository, *, drafts_dir: Path | None = None) -> None:
        self._repo = repo
        self._drafts_dir = drafts_dir or DEFAULT_DRAFTS_DIR

    def _overview_sync(self) -> dict:
        # ponytail: cheap (~10ms) PASSIVE checkpoint before the read-heavy audit
        # queries below. Confirmed on the real desktop DB that a large
        # un-checkpointed WAL (grows during a long scan/rescore session — one
        # measured at ~70MB, nearly the size of the main db) makes every one of
        # these queries 7x+ slower, because SQLite has to reconstruct current
        # pages from the whole WAL instead of the base table. The scheduled job
        # in api/scheduler.py (ensure_wal_checkpoint_job) handles steady-state
        # upkeep every 5 min; this call is insurance for the one endpoint whose
        # latency this ticket is about, independent of that cadence. Ceiling: if
        # some OTHER long-lived connection holds a read snapshot open (a stale
        # worker thread, an orphaned second backend process), PASSIVE mode can't
        # checkpoint past it — upgrade to a shorter scheduled interval or a
        # RESTART checkpoint if that shows up in practice.
        checkpoint_wal()
        conn = get_connection()
        try:
            return {
                "headline": headline_metrics(conn),
                "funnel": funnel_stages(conn),
                "sources": source_breakdown(conn),
                "leads_per_day": leads_per_day(conn),
                "applications_per_day": applications_per_day(conn),
                "activity": recent_activity(conn),
            }
        finally:
            conn.close()

    async def overview(self) -> dict:
        """Headline metrics, the funnel, source breakdown, the two daily
        timeseries, and recent activity — everything the Overview and Sources
        screens need, in one call."""
        return await asyncio.to_thread(self._overview_sync)

    def _application_detail_sync(self, job_id: str) -> dict:
        conn = get_connection()
        try:
            evidence = verification(conn, job_id)
        finally:
            conn.close()
        return {**evidence, "answers": draft_answers(job_id, self._drafts_dir)}

    async def application_detail(self, job_id: str) -> dict:
        """Verification evidence + the drafted application answers for one
        lead — empty strings when nothing has run for it yet, never an error."""
        return await asyncio.to_thread(self._application_detail_sync, job_id)


def create_reporting_service(repo: Repository) -> ReportingService:
    return ReportingService(repo)


__all__ = [
    "DEFAULT_DRAFTS_DIR",
    "FUNNEL_LABELS",
    "ReportingService",
    "applications",
    "applications_per_day",
    "create_reporting_service",
    "draft_answers",
    "funnel_stages",
    "gather",
    "headline_metrics",
    "humanize_action",
    "kv",
    "leads_per_day",
    "next_actions",
    "recent_activity",
    "short_ts",
    "source_breakdown",
    "tag_tone",
    "verification",
]
