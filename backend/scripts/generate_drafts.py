#!/usr/bin/env python
"""Generate tailored resume-summary + cover-letter DRAFTS for the top-ranked
roles in the shortlist. HUMAN-REVIEW ONLY: this writes files to disk and sets
a DB status -- nothing is emailed, posted, or submitted anywhere. A person
opens the files, edits them, and applies themselves.

Project selection reuses ``generation.generators.resume._rank_projects`` (the
same keyword-overlap matcher the rest of the app uses) so a security/infra
role surfaces AegisQuery's AST-based SQL-injection defence, an eval/quality
role surfaces evalharness, and so on -- never a generic "here's my resume".

LLM calls go through ``llm.client.call_raw(..., step="draft")``, the repo's
existing provider-agnostic adapter. It resolves ``draft_provider`` if set in
Settings, else the GLOBAL ``llm_provider`` -- which on this install is already
``codex_cli`` (the user's local Codex subscription, no API key). If Codex is
not installed / not logged in / fails, ``call_raw`` returns "" and this script
falls back to a deterministic template built straight from the matched
project's own ``impact`` text -- still specific, just not LLM-phrased. Point
this at a different local model by setting the ``draft_provider`` /
``draft_model`` settings keys in the same DB (see llm/client.py::_resolve).

    python scripts/generate_drafts.py                  # top 5 shortlisted roles
    python scripts/generate_drafts.py -n 3 --force      # regenerate top 3 even if drafted
    python scripts/generate_drafts.py --db path\\to\\crm.db --out path\\to\\drafts
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# llm.client resolves Settings (llm_provider, draft_provider/model, ...) through
# a repository whose DEFAULT_DB_PATH is core.paths.app_data_dir() -- computed
# ONCE, at import time, from a DIFFERENT default directory than the installed
# desktop app uses (see run_scrape.py's TAURI_DB / resolve_db comment). Every
# other script here sidesteps that by passing db_path explicitly everywhere,
# but llm.client's Settings lookup takes no such parameter. So: point
# app_data_dir() at the Tauri app's own data dir BEFORE any backend module is
# imported (this must run first -- app_data_dir() is memoized at import time),
# UNLESS the caller already set JHM_APP_DATA_DIR themselves. Without this, a
# --draft LLM call would silently read "llm_provider" from an empty/unrelated
# database and fall back to ollama instead of the user's configured provider.
_TAURI_APP_DATA = Path.home() / "AppData" / "Roaming" / "com.vasudev-siddh.justhireme"
if _TAURI_APP_DATA.exists() and "JHM_APP_DATA_DIR" not in os.environ:
    os.environ["JHM_APP_DATA_DIR"] = str(_TAURI_APP_DATA)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_scrape  # noqa: E402  # sibling script, for resolve_db()
import shortlist  # noqa: E402  # sibling script, for filtered_ranked_leads()
from core.logging import get_logger  # noqa: E402
from data.sqlite.events import record_event  # noqa: E402
from data.sqlite.leads import get_all_leads, update_lead_status  # noqa: E402
from generation.generators.resume import _rank_projects  # noqa: E402  # reuse the existing project matcher
from llm.client import call_raw  # noqa: E402

_log = get_logger("scripts.generate_drafts")

DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent / "candidate_profile.json"
DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "drafts"

_LLM_SYSTEM = (
    "You write concise, specific job-application drafts for a real candidate. "
    "Never invent facts not given to you (no fake metrics, no fake employers). "
    "Reference the given project(s) concretely -- what they technically did -- "
    "and connect that to what the job posting is asking for. Keep it tight: "
    "under 350 words total. Output EXACTLY this format, no extra commentary:\n"
    "RESUME SUMMARY:\n<2-3 sentence tailored resume summary>\n"
    "---COVER LETTER---\n<full cover letter, 3 short paragraphs, no letterhead>"
)


def _slug(lead: dict) -> str:
    base = f"{lead.get('company', '')}-{lead.get('title', '')}"
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()[:50]
    job_id = str(lead.get("job_id", ""))[:8]
    return f"{slug or 'role'}-{job_id}"


def _project_sentence(project: dict) -> str:
    title = str(project.get("title") or "").strip()
    impact = str(project.get("impact") or "").strip()
    if not title:
        return ""
    if impact:
        return f"{title} is directly relevant here: {impact}"
    return f"{title} is directly relevant to this role."


def _deterministic_draft(profile: dict, lead: dict, projects: list[dict]) -> dict:
    """No-LLM fallback: still specific, built straight from matched-project impact
    text rather than generic filler."""
    name = profile.get("n") or "Candidate"
    title = str(lead.get("title") or "the role").strip()
    company = str(lead.get("company") or "your company").strip()
    summary = str(profile.get("s") or "").strip()
    portfolio_url = str((profile.get("identity") or {}).get("portfolio_url") or "").strip()

    sentences = [s for s in (_project_sentence(p) for p in projects[:2]) if s]
    evidence_block = "\n".join(f"- {s}" for s in sentences) or "- (no closely-matching project found -- see full portfolio.)"

    resume_summary = summary
    if sentences:
        resume_summary = f"{summary} Most relevant: {sentences[0]}"

    body_paras = [
        f"I'm writing to apply for the {title} position at {company}. "
        f"{summary}",
    ]
    if sentences:
        body_paras.append(sentences[0])
    if len(sentences) > 1:
        body_paras.append(sentences[1])
    body_paras.append(
        "I'd welcome the chance to talk about how this maps to what your team is building."
        + (f" Portfolio: {portfolio_url}" if portfolio_url else "")
    )
    cover_letter = (
        f"Dear {company} Hiring Team,\n\n"
        + "\n\n".join(body_paras)
        + f"\n\nSincerely,\n{name}\n"
    )
    return {
        "resume_summary": resume_summary,
        "cover_letter": cover_letter,
        "evidence_block": evidence_block,
        "mode": "deterministic",
    }


def _llm_draft(profile: dict, lead: dict, projects: list[dict]) -> dict | None:
    """Try the configured LLM (default: the user's local Codex CLI) for a more
    naturally-phrased draft. Returns None on any failure/empty/malformed
    response -- caller falls back to the deterministic template."""
    project_lines = "\n".join(
        f"- {p.get('title', '')}: {p.get('impact', '')}" for p in projects[:2] if p.get("title")
    )
    user = (
        f"Candidate: {profile.get('n', '')}\n"
        f"Candidate summary: {profile.get('s', '')}\n"
        f"Most relevant projects for THIS job:\n{project_lines or '(none matched -- use the summary only)'}\n\n"
        f"Job title: {lead.get('title', '')}\n"
        f"Company: {lead.get('company', '')}\n"
        f"Job description (excerpt): {str(lead.get('description', ''))[:1200]}\n"
    )
    try:
        raw = call_raw(_LLM_SYSTEM, user, step="draft")
    except Exception as exc:
        _log.warning("draft LLM call raised for %s: %s", lead.get("job_id", "?"), exc)
        return None
    if not raw or "---COVER LETTER---" not in raw:
        return None
    summary_part, _, cover_part = raw.partition("---COVER LETTER---")
    summary = summary_part.replace("RESUME SUMMARY:", "", 1).strip()
    cover = cover_part.strip()
    if len(summary) < 20 or len(cover) < 80:
        return None
    return {"resume_summary": summary, "cover_letter": cover, "mode": "llm"}


def generate_draft(profile: dict, lead: dict, out_dir: Path, db_path: str | None = None) -> dict:
    """Write one lead's draft folder; returns the metadata written.

    ``db_path`` is optional (callers that never touch the DB, e.g. tests, can
    omit it) -- when given, records an audit-trail event with the generation
    mode (llm vs. deterministic-template), which ``status_changed=draft_ready``
    alone doesn't capture.
    """
    projects = _rank_projects(profile, lead, limit=2)
    det = _deterministic_draft(profile, lead, projects)
    llm_result = _llm_draft(profile, lead, projects)
    draft = llm_result or det

    folder = out_dir / _slug(lead)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "resume_summary.md").write_text(
        f"# Tailored resume summary -- {lead.get('title', '')} @ {lead.get('company', '')}\n\n"
        f"{draft['resume_summary']}\n",
        encoding="utf-8",
    )
    (folder / "cover_letter.md").write_text(draft["cover_letter"] + "\n", encoding="utf-8")
    meta = {
        "job_id": lead.get("job_id", ""),
        "title": lead.get("title", ""),
        "company": lead.get("company", ""),
        "url": lead.get("url", ""),
        "score": int(lead.get("score") or 0),
        "matched_projects": [p.get("title", "") for p in projects if p.get("title")],
        "mode": draft["mode"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    if db_path:
        record_event(lead.get("job_id"), f"draft_generated mode={meta['mode']}", db_path)
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-n", "--count", type=int, default=5, help="how many top roles to draft (default 5)")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE_PATH), help="candidate profile JSON path")
    parser.add_argument("--db", default=None, help="database file (defaults to the installed app's)")
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR), help="drafts output directory")
    parser.add_argument("--force", action="store_true", help="regenerate even if already draft_ready")
    args = parser.parse_args()

    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    db_path = run_scrape.resolve_db(args.db)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    leads = get_all_leads(db_path)
    candidates = shortlist.filtered_ranked_leads(leads)
    if not args.force:
        candidates = [lead for lead in candidates if lead.get("status") != "draft_ready"]
    top = candidates[: args.count]

    print(f"\n  drafting {len(top)} role(s) into {out_dir}\n")
    written = 0
    for lead in top:
        try:
            meta = generate_draft(profile, lead, out_dir, db_path)
            update_lead_status(lead["job_id"], "draft_ready", db_path)
            written += 1
            print(f"  [{meta['score']:>3}] {meta['title'][:55]:<55} @ {meta['company'][:25]:<25} ({meta['mode']})")
        except Exception as exc:
            _log.warning("draft generation failed for %s: %s", lead.get("job_id", "?"), exc)
            print(f"  ! failed: {lead.get('title', '?')} -- {exc}")
    print(f"\n  {written}/{len(top)} drafts written to {out_dir}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
