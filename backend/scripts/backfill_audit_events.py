#!/usr/bin/env python
"""One-shot backfill: give the audit trail (``events`` table) history for
actions that happened BEFORE this session wired up their logging.

``leads.py::save_lead`` / ``verify_shortlist.py::persist_verdict`` /
``generate_drafts.py::generate_draft`` now write a real event every time they
run -- but leads scraped, verified, and drafted before that change left no
trace beyond the columns they touched (``created_at``, ``verify_checked_at``,
the draft folder on disk). This script derives one event per lead for each of
those three actions from that existing data, so the dashboard isn't empty on
day one. Every backfilled row is tagged ``backfilled=1`` in its action string
so it's never confused with a row the loop wrote live.

Idempotent: safe to re-run, only inserts events for job_ids that don't already
have one of that action type (whether backfilled or live).

    python scripts/backfill_audit_events.py                  # run it
    python scripts/backfill_audit_events.py --db path\\to\\crm.db
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

import run_scrape  # noqa: E402  sibling script, for resolve_db()
from data.sqlite.connection import get_connection, run_migrations  # noqa: E402

DEFAULT_DRAFTS_DIR = Path(__file__).resolve().parent / "drafts"


def _already_logged(conn, action_prefix: str) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT job_id FROM events WHERE action LIKE ?", (f"{action_prefix}%",)
    ).fetchall()
    return {row[0] for row in rows if row[0]}


def backfill_discovered(conn) -> int:
    done = _already_logged(conn, "discovered")
    rows = conn.execute("SELECT job_id, platform, created_at FROM leads").fetchall()
    to_insert = [
        (job_id, f"discovered platform={platform or 'unknown'} backfilled=1", created_at)
        for job_id, platform, created_at in rows
        if job_id and job_id not in done
    ]
    if to_insert:
        conn.executemany("INSERT INTO events(job_id,action,ts) VALUES(?,?,?)", to_insert)
    return len(to_insert)


def backfill_verified(conn) -> int:
    done = _already_logged(conn, "verified")
    rows = conn.execute(
        "SELECT job_id, verify_status, verify_evidence, verify_checked_at FROM leads "
        "WHERE verify_checked_at != ''"
    ).fetchall()
    to_insert = [
        (
            job_id,
            f"verified verdict={verdict} evidence={(evidence or '')[:200]} backfilled=1",
            checked_at,
        )
        for job_id, verdict, evidence, checked_at in rows
        if job_id and job_id not in done
    ]
    if to_insert:
        conn.executemany("INSERT INTO events(job_id,action,ts) VALUES(?,?,?)", to_insert)
    return len(to_insert)


def backfill_drafted(conn, drafts_dir: Path) -> int:
    done = _already_logged(conn, "draft_generated")
    if not drafts_dir.exists():
        return 0
    to_insert = []
    for meta_path in drafts_dir.glob("*/meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        job_id = meta.get("job_id")
        if not job_id or job_id in done:
            continue
        mode = meta.get("mode", "unknown")
        generated_at = meta.get("generated_at") or ""
        to_insert.append((job_id, f"draft_generated mode={mode} backfilled=1", generated_at))
        done.add(job_id)
    if to_insert:
        conn.executemany("INSERT INTO events(job_id,action,ts) VALUES(?,?,?)", to_insert)
    return len(to_insert)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=None, help="database file (defaults to the installed app's)")
    parser.add_argument("--drafts-dir", default=str(DEFAULT_DRAFTS_DIR))
    args = parser.parse_args()

    db_path = run_scrape.resolve_db(args.db)
    print(f"  DB: {db_path}")
    run_migrations(db_path)

    conn = get_connection(db_path)
    try:
        discovered = backfill_discovered(conn)
        verified = backfill_verified(conn)
        drafted = backfill_drafted(conn, Path(args.drafts_dir))
        conn.commit()
    finally:
        conn.close()

    print(f"  backfilled: discovered={discovered} verified={verified} draft_generated={drafted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
