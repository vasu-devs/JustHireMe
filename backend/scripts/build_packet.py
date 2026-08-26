#!/usr/bin/env python
"""Build a one-click "application packet" for an approved lead: the full
tailored resume (markdown + a plain-text version pasteable into a form), the
cover letter, and an ``answers.md`` that pre-fills the standard application
questions from the candidate's REAL profile data -- so applying is
paste-and-submit, not rewrite-from-scratch.

This is the human hand-off point the closed loop deliberately ends at (see
backend/CLOSED_LOOP.md): nothing here submits anything anywhere. Any field
that can't be filled from real data (notice period, compensation) is left as
an explicit TODO -- never invented.

Reuses ``generation.generators.resume._fallback_package`` for the actual
tailored resume/cover-letter text (the same deterministic, project-matched
generator the rest of the app uses) rather than a second resume-writer, and
``generate_drafts._slug`` for the draft-folder naming convention so a packet
lands in the SAME folder job_loop.py/generate_drafts.py already created.

    python scripts/build_packet.py <job_id>              # build/refresh one packet
    python scripts/build_packet.py --all-approved         # build for every 'approved' lead
    python scripts/build_packet.py <job_id> --force       # regenerate resume/cover letter too
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

import run_scrape  # noqa: E402  sibling script, for resolve_db()
from data.sqlite.events import record_event  # noqa: E402
from data.sqlite.leads import get_all_leads, get_lead_by_id  # noqa: E402
from generate_drafts import _slug  # noqa: E402  reuse the existing folder-naming convention
from generation.generators.resume import _fallback_package  # noqa: E402  reuse the existing tailored-resume builder
from generation.pdf_renderer import _strip_inline  # noqa: E402  reuse the existing markdown-inline stripper

DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent / "candidate_profile.json"
DEFAULT_DRAFTS_DIR = Path(__file__).resolve().parent / "drafts"

_EXP_YEARS_RE = re.compile(r"(\d+)\+?\s*years?", re.IGNORECASE)


def _years_of_experience(profile: dict) -> str:
    """Pulled from the profile's own summary text (e.g. "11+ years") rather
    than hardcoded, so this stays correct if the profile is ever updated."""
    m = _EXP_YEARS_RE.search(str(profile.get("s") or ""))
    return f"{m.group(1)}+ years" if m else "TODO -- state total years of experience"


def _markdown_to_plain(md: str) -> str:
    """Plain-text version of a resume/cover-letter markdown doc, pasteable
    into a form field that doesn't render markdown. Reuses pdf_renderer's own
    bold/italic/code/link stripper for inline markup; only heading markers
    (#/##/###) need stripping here on top of that."""
    lines = [re.sub(r"^#{1,6}\s*", "", _strip_inline(raw)) for raw in md.splitlines()]
    return "\n".join(lines).strip() + "\n"


_SIGNOFF_RE = re.compile(r"^(dear\b|sincerely|best regards|regards\b|thank(?:s| you)\b.{0,20}$)", re.IGNORECASE)


def _why_this_company(cover_letter_text: str) -> str:
    """The company/team-specific paragraph out of the tailored cover letter.

    Every observed sample (LLM and deterministic-fallback alike) puts the
    concrete "why here" reasoning in the LAST substantive paragraph -- reused
    instead of re-deriving a second "why this company" blurb from scratch,
    which would either duplicate the cover letter's own research or invent
    detail it doesn't have. The greeting ("Dear ... team,") and sign-off
    ("Sincerely,\\nName") blocks are excluded so a letter that ends with a
    signature doesn't hand back the signature as the "why" answer."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", cover_letter_text.strip()) if p.strip()]
    content = [p for p in paras if not _SIGNOFF_RE.match(p)]
    if content:
        return content[-1]
    return paras[-1] if paras else "TODO -- explain why this company/role specifically."


def _verify_info(job_id: str, db_path: str) -> tuple[str, str]:
    """(verify_status, verify_evidence) straight from the DB -- these two
    columns (migration 006) aren't part of the shared LEAD_SELECT_COLUMNS
    projection. Shared with review.py (imported from here) rather than kept
    as two copies of the same raw query."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT verify_status, verify_evidence FROM leads WHERE job_id=?", (job_id,)).fetchone()
    finally:
        conn.close()
    return (str(row[0] or ""), str(row[1] or "")) if row else ("", "")


def build_answers_md(profile: dict, lead: dict, cover_letter_text: str, verify_evidence: str) -> str:
    identity = profile.get("identity") or {}
    title = lead.get("title") or "the role"
    company = lead.get("company") or "the company"
    portfolio = identity.get("portfolio_url") or "TODO -- add portfolio URL"
    github = identity.get("github_url") or "TODO -- add GitHub URL"
    why = _why_this_company(cover_letter_text)
    geo_note = f"\n\n*Live posting note: {verify_evidence}*" if verify_evidence else ""

    return f"""# Application answers -- {title} @ {company}

Pre-filled from the candidate's real profile and the live job posting.
Every TODO below needs a real answer before this is submitted -- nothing
here is invented.

## Years of experience
{_years_of_experience(profile)}

## Notice period
TODO -- fill in your current notice period.

## Current / expected compensation
TODO -- fill in current CTC and expected compensation.

## Work authorization
Indian citizen, based in Gurgaon; requires no work authorization for
India-based roles; open to EOR/contractor arrangements for overseas
employers.{geo_note}

## Why {company}
{why}

## Portfolio / links
- {portfolio}
- {github}

## Apply here
{lead.get('url') or 'TODO -- add the posting URL'}
"""


def _draft_folder(job_id: str, drafts_dir: Path, lead: dict) -> Path:
    """The folder generate_drafts.py/job_loop.py already write drafts into, by
    the SAME slug convention -- created on demand (never a second naming
    scheme) for a lead approved without ever going through the draft stage
    (e.g. manually marked approved)."""
    matches = list(drafts_dir.glob(f"*-{str(job_id)[:8]}")) if drafts_dir.exists() else []
    if matches:
        return matches[0]
    folder = drafts_dir / _slug(lead)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def build_packet(
    job_id: str, *, profile_path: Path = DEFAULT_PROFILE_PATH,
    db_path: str | None = None, drafts_dir: Path = DEFAULT_DRAFTS_DIR, force: bool = False,
) -> Path:
    """Write/refresh resume.md, resume.txt, cover_letter.md (if missing) and
    answers.md into the lead's draft folder. Idempotent by default: skips
    files that already exist so a re-run never clobbers a hand-edited cover
    letter; --force regenerates everything."""
    db_path = run_scrape.resolve_db(db_path)
    lead = get_lead_by_id(job_id, db_path)
    if not lead:
        raise ValueError(f"no lead with job_id={job_id!r}")
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))

    folder = _draft_folder(job_id, drafts_dir, lead)
    package = _fallback_package(profile, lead)

    resume_path = folder / "resume.md"
    if force or not resume_path.exists():
        resume_path.write_text(package.resume_markdown, encoding="utf-8")
    (folder / "resume.txt").write_text(_markdown_to_plain(resume_path.read_text(encoding="utf-8")), encoding="utf-8")

    cover_path = folder / "cover_letter.md"
    if force or not cover_path.exists():
        cover_path.write_text(package.cover_letter_markdown, encoding="utf-8")
    cover_text = cover_path.read_text(encoding="utf-8")

    _status, verify_evidence = _verify_info(job_id, db_path)
    answers_path = folder / "answers.md"
    if force or not answers_path.exists():
        answers_path.write_text(build_answers_md(profile, lead, cover_text, verify_evidence), encoding="utf-8")

    record_event(job_id, f"packet_built folder={folder.name}", db_path)
    return folder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job_id", nargs="?", help="build the packet for one lead")
    parser.add_argument("--all-approved", action="store_true", help="build for every lead at status=approved")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE_PATH))
    parser.add_argument("--db", default=None)
    parser.add_argument("--out", default=str(DEFAULT_DRAFTS_DIR))
    parser.add_argument("--force", action="store_true", help="regenerate resume/cover letter even if present")
    args = parser.parse_args()

    db_path = run_scrape.resolve_db(args.db)
    if not args.job_id and not args.all_approved:
        print("  need a job_id or --all-approved (see --help)")
        return 2

    job_ids = [args.job_id] if args.job_id else [
        lead["job_id"] for lead in get_all_leads(db_path) if str(lead.get("status") or "") == "approved"
    ]
    if not job_ids:
        print("\n  nothing at status='approved'\n")
        return 0

    for job_id in job_ids:
        folder = build_packet(
            job_id, profile_path=Path(args.profile), db_path=db_path,
            drafts_dir=Path(args.out), force=args.force,
        )
        print(f"  packet ready: {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
