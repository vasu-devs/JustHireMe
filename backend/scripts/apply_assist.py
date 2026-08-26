#!/usr/bin/env python
"""Turn an approved/draft-ready lead into ~30 seconds of human work: open the
posting in the default browser, put the tailored cover letter on the
clipboard, and print every pre-filled answer ready to paste. The human reads,
pastes, and submits -- this NEVER fills a form field, clicks apply, or drives
the employer's page in any way (see backend/CLOSED_LOOP.md's "What's
deliberately manual" section for why that's a boundary, not a gap).

Reuses build_packet.py for the packet itself (built on demand if missing --
never fails just because it hasn't run yet for this lead), review.py's own
status-transition + feedback-learning logic for `done` (the SAME state
machine `review.py mark` uses, not a second copy), and
generation.generators.resume._rank_projects for "why this fits" when a
lead's own draft meta.json isn't available.

    python scripts/apply_assist.py next                    # open + copy + print everything
    python scripts/apply_assist.py next --field work_auth  # re-copy one field, no browser re-open
    python scripts/apply_assist.py list                     # the queue, in apply order
    python scripts/apply_assist.py done <job_id>             # mark applied, offer the next role
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import webbrowser
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

import review  # noqa: E402  sibling script -- delegate transition/feedback logic to it, don't duplicate
import run_scrape  # noqa: E402  sibling script, for resolve_db()
from build_packet import DEFAULT_PROFILE_PATH, _verify_info, build_packet  # noqa: E402
from core.logging import get_logger  # noqa: E402
from data.sqlite.events import record_event  # noqa: E402
from data.sqlite.leads import get_all_leads, get_lead_by_id  # noqa: E402
from generation.generators.resume import _rank_projects  # noqa: E402  reuse the existing project matcher

_log = get_logger("scripts.apply_assist")

DEFAULT_DRAFTS_DIR = Path(__file__).resolve().parent / "drafts"

# Leads actionable through this tool -- applied/interviewing/etc. are past
# the "apply" step and belong to review.py, not this queue.
QUEUE_STATUSES = ("draft_ready", "approved")

# Fields answers.md/the packet folder can serve -- vs. FIELDS below.
_FOLDER_FIELDS = ("cover_letter", "resume_text", "why_company", "work_auth")
FIELDS = (*_FOLDER_FIELDS, "portfolio", "email", "phone")


def _queue(db_path: str, *, include_applied: bool = False) -> list[dict]:
    """Highest-ranked first -- same score-descending order review.py's own
    `list` uses. `include_applied` is the --force escape hatch: normally an
    already-`applied` lead can never be re-selected as "next" (resumable /
    safe-to-rerun by construction), --force widens the pool to allow
    deliberately reopening one anyway (e.g. to re-copy a field for a
    follow-up)."""
    statuses = QUEUE_STATUSES + (("applied",) if include_applied else ())
    leads = [lead for lead in get_all_leads(db_path) if str(lead.get("status") or "") in statuses]
    leads.sort(key=lambda lead: -int(lead.get("score") or 0))
    return leads


def _copy_to_clipboard(text: str) -> bool:
    """Windows `clip` via subprocess -- stdlib, no new dependency. UTF-16LE is
    the clipboard's own native text encoding (CF_UNICODETEXT); piping UTF-8
    into `clip` mangles em dashes/curly quotes the LLM drafts routinely use,
    UTF-16LE round-trips them correctly (verified with a live clipboard
    read-back)."""
    try:
        subprocess.run(["clip"], input=text.encode("utf-16-le"), check=True, timeout=10)
        return True
    except Exception as exc:
        _log.warning("clipboard copy failed: %s", exc)
        return False


def _md_sections(md_text: str) -> dict[str, str]:
    """``## Header`` -> body text, so a single answer can be pulled out of
    answers.md without a second copy of build_packet.py's own section-writing
    logic."""
    sections: dict[str, str] = {}
    header, buf = None, []
    for line in md_text.splitlines():
        if line.startswith("## "):
            if header is not None:
                sections[header] = "\n".join(buf).strip()
            header, buf = line[3:].strip().lower(), []
        elif header is not None:
            buf.append(line)
    if header is not None:
        sections[header] = "\n".join(buf).strip()
    return sections


def _ensure_packet(job_id: str, db_path: str, profile_path: Path, drafts_dir: Path) -> Path:
    """The packet folder, building it on demand if answers.md is missing --
    per the task, never fail just because build_packet.py hasn't run for this
    lead yet. Uses the SAME folder-lookup build_packet._draft_folder does, so
    a lead drafted by generate_drafts.py keeps its meta.json alongside."""
    matches = list(drafts_dir.glob(f"*-{job_id[:8]}")) if drafts_dir.exists() else []
    folder = matches[0] if matches else None
    if folder is None or not (folder / "answers.md").exists():
        folder = build_packet(job_id, profile_path=profile_path, db_path=db_path, drafts_dir=drafts_dir)
    return folder


def _why_this_fits(lead: dict, folder: Path, profile: dict) -> str:
    """The named project this pitch leads with. Prefers generate_drafts.py's
    own meta.json when this lead went through the normal draft stage --
    that's the EXACT ranking the cover letter was written from -- and only
    re-ranks live (same matcher, `_rank_projects`) for a lead approved
    without ever drafting, so this is never a guess."""
    meta_path = folder / "meta.json"
    if meta_path.exists():
        try:
            matched = json.loads(meta_path.read_text(encoding="utf-8")).get("matched_projects") or []
            if matched:
                return str(matched[0])
        except (ValueError, OSError):
            pass
    ranked = _rank_projects(profile, lead, limit=1)
    return str(ranked[0]["title"]) if ranked else "(no closely-matching project -- see full portfolio)"


def _field_text(field: str, folder: Path | None, profile: dict) -> str:
    if field == "cover_letter":
        p = folder / "cover_letter.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""
    if field == "resume_text":
        p = folder / "resume.txt"
        return p.read_text(encoding="utf-8") if p.exists() else ""
    if field in ("why_company", "work_auth"):
        p = folder / "answers.md"
        sections = _md_sections(p.read_text(encoding="utf-8")) if p.exists() else {}
        if field == "work_auth":
            return sections.get("work authorization", "")
        return next((body for header, body in sections.items() if header.startswith("why ")), "")
    identity = profile.get("identity") or {}
    key = "portfolio_url" if field == "portfolio" else field  # email/phone match identity's own keys
    return str(identity.get(key) or "")


def _print_card(lead: dict, folder: Path, profile: dict, db_path: str) -> None:
    verify_status, verify_evidence = _verify_info(lead["job_id"], db_path)
    print(f"\n  {lead.get('title')} @ {lead.get('company')}")
    print(f"  band={verify_status or 'unverified'}  score={int(lead.get('score') or 0)}  status={lead.get('status')}")
    print(f"  lead with: {_why_this_fits(lead, folder, profile)}")
    if verify_evidence:
        print(f"  verified: {verify_evidence}")
    print(f"  apply: {lead.get('url')}\n")


def _print_answers(folder: Path) -> None:
    answers_path = folder / "answers.md"
    if not answers_path.exists():
        return
    sections = _md_sections(answers_path.read_text(encoding="utf-8"))
    print("  --- answers (paste into the application form) ---")
    for i, (header, body) in enumerate(sections.items(), 1):
        flag = "  [NEEDS YOUR INPUT]" if "TODO" in body else ""
        print(f"  {i}. {header.title()}{flag}")
        for line in (body.splitlines() or [""]):
            print(f"     {line}")
        print()


def cmd_next(args) -> int:
    db_path = run_scrape.resolve_db(args.db)
    profile_path = Path(args.profile)
    drafts_dir = Path(args.drafts_dir)

    queue = _queue(db_path, include_applied=args.force)
    if not queue:
        print("\n  queue is empty -- nothing at draft_ready/approved\n")
        return 0
    lead = queue[0]
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    folder = None
    if not args.field or args.field in _FOLDER_FIELDS:
        folder = _ensure_packet(lead["job_id"], db_path, profile_path, drafts_dir)

    if args.field:
        text = _field_text(args.field, folder, profile)
        copied = _copy_to_clipboard(text)
        preview = (text[:70] + "...") if len(text) > 70 else text
        preview = preview.replace("\n", " ")
        status = "copied" if copied else "! clipboard copy FAILED for"
        print(f"  {status} {args.field} ({len(text)} chars) -- {lead.get('title')} @ {lead.get('company')}")
        print(f"     {preview!r}")
        return 0

    webbrowser.open(lead["url"])
    record_event(lead["job_id"], "apply_opened", db_path)
    _print_card(lead, folder, profile, db_path)

    cover_path = folder / "cover_letter.md"
    cover_text = cover_path.read_text(encoding="utf-8") if cover_path.exists() else ""
    copied = _copy_to_clipboard(cover_text)
    print(f"  {'cover letter copied to clipboard' if copied else '! clipboard copy FAILED'}\n")

    _print_answers(folder)
    print(f"  record the outcome: python scripts/apply_assist.py done {lead['job_id']}\n")
    return 0


def cmd_list(args) -> int:
    db_path = run_scrape.resolve_db(args.db)
    queue = _queue(db_path)
    if not queue:
        print("\n  queue is empty -- nothing at draft_ready/approved\n")
        return 0
    print(f"\n  {len(queue)} lead(s) in apply order\n")
    for i, lead in enumerate(queue, 1):
        job_id = str(lead.get("job_id") or "")
        band = _verify_info(job_id, db_path)[0] or "unverified"
        title = str(lead.get("title") or "?")[:45]
        company = str(lead.get("company") or "?")[:22]
        score = int(lead.get("score") or 0)
        print(f"  {i:>2}. [{score:>3}] ({band:<10}) {title:<45} @ {company:<22} {job_id[:10]}  status={lead.get('status')}")
    print()
    return 0


def cmd_done(args) -> int:
    # Delegate entirely to review.py's own transition-legality + outcome-
    # feedback logic -- the SAME state machine `review.py mark <id> ...` runs,
    # not a second copy of it. review.TRANSITIONS has no direct
    # draft_ready->applied edge (only draft_ready->approved->applied), but
    # "done" is the human's single "I applied" action regardless of which of
    # the two actionable states the lead was in -- so step through BOTH legal
    # transitions via review.cmd_mark when starting from draft_ready, instead
    # of forcing straight to applied.
    db_path = run_scrape.resolve_db(args.db)
    lead = get_lead_by_id(args.job_id, db_path)
    if lead and str(lead.get("status") or "") == "draft_ready" and not args.force:
        rc = review.cmd_mark(argparse.Namespace(
            job_id=args.job_id, new_status="approved", note="", force=False,
            db=args.db, drafts_dir=args.drafts_dir, profile=args.profile,
        ))
        if rc != 0:
            return rc

    mark_args = argparse.Namespace(
        job_id=args.job_id, new_status="applied", note=args.note, force=args.force,
        db=args.db, drafts_dir=args.drafts_dir, profile=args.profile,
    )
    rc = review.cmd_mark(mark_args)
    if rc != 0:
        return rc
    print("\n  -- offering the next role --")
    next_args = argparse.Namespace(db=args.db, drafts_dir=args.drafts_dir, profile=args.profile, field=None, force=False)
    return cmd_next(next_args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=None, help="database file (defaults to the installed app's)")
    parser.add_argument("--drafts-dir", default=str(DEFAULT_DRAFTS_DIR), help="drafts output directory")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE_PATH), help="candidate profile JSON path")
    sub = parser.add_subparsers(dest="cmd")

    p_next = sub.add_parser("next", help="open the top lead, copy the cover letter, print everything to paste")
    p_next.add_argument("--field", choices=FIELDS, default=None, help="re-copy one field instead of opening the browser again")
    p_next.add_argument("--force", action="store_true", help="also consider leads already marked applied")
    p_next.set_defaults(func=cmd_next)

    p_list = sub.add_parser("list", help="the queue, in apply order")
    p_list.set_defaults(func=cmd_list)

    p_done = sub.add_parser("done", help="mark applied and immediately offer the next role")
    p_done.add_argument("job_id")
    p_done.add_argument("--note", default="", help="free-text note (same as review.py mark --note)")
    p_done.add_argument("--force", action="store_true", help="skip the transition-legality check")
    p_done.set_defaults(func=cmd_done)

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
