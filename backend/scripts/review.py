#!/usr/bin/env python
"""Review queue CLI -- the human gate the closed loop ends at.

job_loop.py generates tailored drafts for CONFIRMED roles and leaves them at
status ``draft_ready``. This script is how a human works the queue: read a
draft, decide, and record what actually happened. It never submits anything
anywhere -- the human applies themselves, on the employer's own site.

Status transitions (persisted to the existing ``leads.status`` column --
``events`` already timestamps every change, and ``leads.feedback_note`` already
holds free text, so no new migration is needed for this):

    draft_ready -> approved -> applied -> interviewing -> offer -> accepted
                        \\-> discarded          \\-> rejected    \\-> rejected

Marking an outcome (applied/interviewing/offer/rejected) also feeds
ranking/feedback_ranker.py's existing feedback-learning model (the SAME model
manual lead-quality tags use, via ``leads.feedback`` + ``save_lead_feedback``)
and immediately re-ranks the rest of the dataset -- this is the loop's
feedback step: roles like ones that reached an interview rank higher from here
on, roles like ones rejected before interview rank lower.

    python scripts/review.py                        # list drafts pending review
    python scripts/review.py list --status applied   # list any other stage
    python scripts/review.py show <job_id>            # print a draft + metadata
    python scripts/review.py mark <job_id> approved
    python scripts/review.py mark <job_id> applied
    python scripts/review.py mark <job_id> interviewing
    python scripts/review.py mark <job_id> offer --note "45L base, decide by Fri"
    python scripts/review.py mark <job_id> rejected
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import run_scrape  # noqa: E402  sibling script, for resolve_db()
from build_packet import _verify_info, build_packet  # noqa: E402  sibling script -- the application-packet builder
from core.logging import get_logger  # noqa: E402
from data.sqlite.leads import (  # noqa: E402
    get_all_leads,
    get_lead_by_id,
    save_lead_feedback,
    update_lead_status,
)

_log = get_logger("scripts.review")

DEFAULT_DRAFTS_DIR = Path(__file__).resolve().parent / "drafts"
DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent / "candidate_profile.json"

# Legal forward transitions. A lead can also be dropped to "discarded" from
# draft_ready/approved (the human decides not to pursue it after all) -- kept
# out of this table and allowed unconditionally in _validate below, same as
# "rejected" is always a legal exit from applied/interviewing/offer.
TRANSITIONS: dict[str, set[str]] = {
    "draft_ready": {"approved", "discarded"},
    "approved": {"applied", "discarded"},
    "applied": {"interviewing", "rejected"},
    "interviewing": {"offer", "rejected"},
    "offer": {"accepted", "rejected"},
}

# Outcome -> the feedback label that teaches ranking/feedback_ranker.py.
# "approved"/"discarded"/"accepted" carry no NEW market signal beyond what
# draft_ready (already shortlisted+verified) or the outcomes below say, so
# they don't write a feedback row.
_OUTCOME_FEEDBACK = {"applied": "already_contacted", "interviewing": "interview", "offer": "offer"}


def _validate(current: str, target: str, *, force: bool) -> str | None:
    """None if the transition is fine; else a human-readable error."""
    if force:
        return None
    if target == "discarded":
        return None  # always a legal exit -- the human can drop anything
    allowed = TRANSITIONS.get(current)
    if allowed is None:
        return f"lead is at status {current!r}, which this queue doesn't manage -- use --force to override"
    if target not in allowed:
        return f"illegal transition {current!r} -> {target!r} (allowed: {sorted(allowed)}); use --force to override"
    return None


def outcome_feedback_for(new_status: str, prior_status: str, prior_feedback: str) -> str | None:
    """Feedback label to write for this transition, or None if this stage
    carries no additional ranking signal beyond what's already recorded.

    A rejection AFTER reaching an interview keeps the positive "interview"
    signal (getting an interview is the harder-to-fake evidence of fit; a
    downstream rejection there is mostly process/headcount, not a fit
    mismatch) -- only a rejection with NO interview ever recorded is treated
    as a negative pattern.
    """
    if new_status == "rejected":
        reached_interview = prior_status == "interviewing" or prior_feedback in ("interview", "offer")
        return None if reached_interview else "app_rejected"
    return _OUTCOME_FEEDBACK.get(new_status)


def cmd_list(args) -> int:
    db_path = run_scrape.resolve_db(args.db)
    leads = [lead for lead in get_all_leads(db_path) if str(lead.get("status") or "") == args.status]
    leads.sort(key=lambda lead: -int(lead.get("score") or 0))
    if not leads:
        print(f"\n  nothing at status={args.status!r}\n")
        return 0
    print(f"\n  {len(leads)} lead(s) at status={args.status!r}\n")
    for lead in leads:
        score = int(lead.get("score") or 0)
        job_id = str(lead.get("job_id") or "")
        title = str(lead.get("title") or "?")[:45]
        company = str(lead.get("company") or "?")[:22]
        band = _verify_info(job_id, db_path)[0] or "unverified"
        print(f"  [{score:>3}] ({band:<10}) {title:<45} @ {company:<22} {job_id[:10]}  {lead.get('url', '')}")
    print()
    return 0


def cmd_show(args) -> int:
    db_path = run_scrape.resolve_db(args.db)
    lead = get_lead_by_id(args.job_id, db_path)
    if not lead:
        print(f"  ! no lead with job_id={args.job_id!r}")
        return 2
    verify_status, verify_evidence = _verify_info(args.job_id, db_path)
    print(f"\n  {lead.get('title')} @ {lead.get('company')}  ({lead.get('url')})")
    print(f"  status={lead.get('status')} score={lead.get('score')} verify_status={verify_status}")
    print(f"  verify_evidence: {verify_evidence}\n")

    draft_dir = Path(args.drafts_dir)
    matches = [p for p in draft_dir.glob(f"*-{str(args.job_id)[:8]}")] if draft_dir.exists() else []
    if not matches:
        print("  (no draft folder found -- run job_loop.py or generate_drafts.py first)\n")
        return 0
    folder = matches[0]
    for name in ("resume_summary.md", "cover_letter.md"):
        path = folder / name
        if path.exists():
            print(f"  --- {name} ---")
            print(path.read_text(encoding="utf-8"))
            print()
    return 0


def cmd_open(args) -> int:
    """Build (if not already built) and print the FULL application packet --
    tailored resume, cover letter, and pre-filled answers -- plus the apply
    URL, so applying is: read this, paste, submit. The one-command substitute
    for the auto-submit step this project deliberately never builds (see
    backend/CLOSED_LOOP.md)."""
    db_path = run_scrape.resolve_db(args.db)
    lead = get_lead_by_id(args.job_id, db_path)
    if not lead:
        print(f"  ! no lead with job_id={args.job_id!r}")
        return 2

    folder = build_packet(
        args.job_id, profile_path=Path(args.profile), db_path=db_path, drafts_dir=Path(args.drafts_dir),
    )
    verify_status, verify_evidence = _verify_info(args.job_id, db_path)
    print(f"\n  {lead.get('title')} @ {lead.get('company')}")
    print(f"  status={lead.get('status')} score={lead.get('score')} verify_status={verify_status}")
    if verify_evidence:
        print(f"  verify_evidence: {verify_evidence}")
    print(f"\n  APPLY HERE: {lead.get('url')}\n")

    for name in ("resume.md", "resume.txt", "cover_letter.md", "answers.md"):
        path = folder / name
        if path.exists():
            print(f"  --- {name} ---")
            print(path.read_text(encoding="utf-8"))
            print()
    print(f"  packet folder: {folder}\n")
    return 0


def cmd_mark(args) -> int:
    db_path = run_scrape.resolve_db(args.db)
    lead = get_lead_by_id(args.job_id, db_path)
    if not lead:
        print(f"  ! no lead with job_id={args.job_id!r}")
        return 2

    current = str(lead.get("status") or "")
    error = _validate(current, args.new_status, force=args.force)
    if error:
        print(f"  ! {error}")
        return 2

    update_lead_status(args.job_id, args.new_status, db_path)

    if args.new_status == "approved":
        # The packet is what makes "approved" actually actionable -- build it
        # right away rather than making the human remember a second command.
        try:
            folder = build_packet(
                args.job_id, profile_path=Path(args.profile), db_path=db_path, drafts_dir=Path(args.drafts_dir),
            )
            print(f"  packet ready: {folder}  (see `review.py open {args.job_id}`)")
        except Exception as exc:
            _log.warning("packet build failed for %s: %s", args.job_id, exc)
            print(f"  ! packet build failed: {exc}")

    feedback = outcome_feedback_for(args.new_status, current, str(lead.get("feedback") or ""))
    if feedback:
        save_lead_feedback(args.job_id, feedback, note=args.note or "", db_path=db_path)
        _log.info("outcome feedback recorded: job_id=%s feedback=%s", args.job_id, feedback)
        # Immediate re-rank: this IS the feedback loop closing -- the rest of
        # the dataset reflects this outcome right away, not on the next scan.
        from ranking.service import RankingService

        changed = asyncio.run(RankingService().recompute_feedback_signals())
        print(f"  {args.job_id} -> {args.new_status} (feedback={feedback}); "
              f"{len(changed)} other lead(s) re-ranked")
    else:
        print(f"  {args.job_id} -> {args.new_status}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=None, help="database file (defaults to the installed app's)")
    parser.add_argument("--drafts-dir", default=str(DEFAULT_DRAFTS_DIR), help="drafts output directory")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE_PATH), help="candidate profile JSON path")
    sub = parser.add_subparsers(dest="cmd")

    p_list = sub.add_parser("list", help="list leads at a given status (default draft_ready)")
    p_list.add_argument("--status", default="draft_ready")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="print a draft's resume summary + cover letter")
    p_show.add_argument("job_id")
    p_show.set_defaults(func=cmd_show)

    p_open = sub.add_parser("open", help="build (if needed) + print the full application packet and apply URL")
    p_open.add_argument("job_id")
    p_open.set_defaults(func=cmd_open)

    p_mark = sub.add_parser("mark", help="record a status transition")
    p_mark.add_argument("job_id")
    p_mark.add_argument("new_status", choices=["approved", "applied", "interviewing", "offer", "accepted", "rejected", "discarded"])
    p_mark.add_argument("--note", default="", help="free-text outcome note (comp offered, feedback received, ...)")
    p_mark.add_argument("--force", action="store_true", help="skip the transition-legality check")
    p_mark.set_defaults(func=cmd_mark)

    args = parser.parse_args()
    if not args.cmd:
        args.status = "draft_ready"
        return cmd_list(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
