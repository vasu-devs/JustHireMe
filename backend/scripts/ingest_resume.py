#!/usr/bin/env python
"""Resume ingest -- the closed loop's entry point.

Takes a resume file (PDF, DOCX, or markdown/text), extracts a structured
profile (name, skills, experience, projects, education) and writes it to the
flat profile JSON every scripts/ CLI consumes (run_scrape.py / watch_jobs.py /
shortlist_global.py / generate_drafts.py / job_loop.py all take
``--profile path.json``).

Reuses the SAME extraction the desktop app's resume-upload endpoint uses
(``profile.ingestor`` / ``profile.ingest_parse``): the configured LLM provider
(``codex_cli`` on this install -- the user's own ChatGPT subscription via the
local Codex CLI, no API key) with a deterministic local-parser fallback, then
merges the two so neither source's misses drop real content. It deliberately
skips ``profile.ingestor.ingest()``'s graph/vector DB writes -- those belong to
the desktop app's own live profile store (a different, already-running
system); this script only reuses the PARSER and writes the flat file the batch
pipeline reads.

Re-running this with an UPDATED resume re-ranks the ENTIRE existing lead
dataset for free: after writing the new profile, every non-discarded/rejected
lead is re-scored with the deterministic CGFE rubric (no LLM, no network, no
re-scrape) so a changed skill set/summary is reflected immediately.

    python scripts/ingest_resume.py --resume path\\to\\resume.pdf
    python scripts/ingest_resume.py --resume path\\to\\resume.md --no-rescore
    python scripts/ingest_resume.py --resume r.pdf --out other_profile.json --db path\\to\\crm.db
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import run_scrape  # noqa: E402  sibling script, for resolve_db()
from core.logging import get_logger  # noqa: E402
from data.sqlite.leads import get_all_leads, update_lead_score  # noqa: E402
from profile.ingest_documents import _document  # noqa: E402
from profile.ingest_parse import _merge_candidate_data, _parse_local  # noqa: E402
from ranking.service import create_ranking_service  # noqa: E402

_log = get_logger("scripts.ingest_resume")

DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent / "candidate_profile.json"

# Top-level keys this pipeline's profile JSON carries that a resume never
# states (hand-curated once, e.g. via the desktop Settings screen, or by
# editing the file directly) -- a re-ingest must never clobber them.
_CURATED_KEYS = ("desired_position", "identity", "_discovery_location", "_remote_preference")


def parse_resume(txt: str):
    """Structured profile (``models.schema.C``) from raw résumé text.

    Reuses the exact extraction path ``profile.ingestor.ingest()`` uses (LLM
    primary + deterministic-parser merge), minus its graph/vector DB writes --
    kept out here on purpose (see module docstring).
    """
    from profile.ingestor import run as llm_extract  # local import: pulls in the llm package

    primary = llm_extract(txt)
    try:
        primary = _merge_candidate_data(primary, _parse_local(txt))
    except Exception as exc:
        _log.warning("deterministic resume merge skipped: %s", exc)
    return primary


def profile_dict_from_model(parsed, existing: dict) -> dict:
    """Flatten the parsed C model into the scripts/ profile JSON shape, keeping
    whatever hand-curated fields (identity, desired_position, ...) the existing
    file carries -- a resume never states those, so a blind overwrite would
    silently drop them on every re-ingest."""
    out = {
        "n": parsed.n or existing.get("n", ""),
        "s": parsed.s or existing.get("s", ""),
        "skills": [s.model_dump() for s in parsed.skills] or existing.get("skills", []),
        "exp": [e.model_dump() for e in parsed.exp] or existing.get("exp", []),
        "projects": [p.model_dump() for p in parsed.projects] or existing.get("projects", []),
        "certifications": parsed.certifications or existing.get("certifications", []),
        "education": parsed.education or existing.get("education", []),
        "achievements": parsed.achievements or existing.get("achievements", []),
    }
    for key in _CURATED_KEYS:
        if key in existing:
            out[key] = existing[key]
    identity = dict(out.get("identity") or {})
    if parsed.loc and not identity.get("city"):
        identity["city"] = parsed.loc
        out["identity"] = identity
    return out


def _load_cfg(db_path: str) -> dict:
    """Same as watch_jobs._load_cfg -- read settings from the SAME database
    being re-ranked, not the resolver's own default app-data dir."""
    conn = sqlite3.connect(db_path)
    try:
        return {k: v for k, v in conn.execute("SELECT key, val FROM settings")}
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


async def rescore_all_leads(profile: dict, cfg: dict, db_path: str) -> dict:
    """Deterministic-only (no LLM, no cost) re-rank of every still-live lead
    against the NEW profile -- this is what makes a resume update propagate to
    the whole dataset without a re-scrape. Mirrors
    ``watch_jobs.score_unscored_leads``, but over every non-discarded/rejected
    lead instead of only score==0 ones: a resume change can legitimately move
    ANY lead's score, not just the never-scored ones."""
    svc = create_ranking_service()
    leads = [lead for lead in get_all_leads(db_path) if str(lead.get("status") or "") not in ("discarded", "rejected")]
    scored = 0
    failed = 0
    sem = asyncio.Semaphore(12)

    async def _one(lead: dict) -> None:
        nonlocal scored, failed
        async with sem:
            try:
                result = await svc.evaluate_lead(lead, profile, cfg, use_llm=False)
                await asyncio.to_thread(
                    update_lead_score,
                    lead["job_id"], result["score"], result.get("reason", ""),
                    result.get("match_points", []), result.get("gaps", []),
                    preserve_status=True, scored_by=result.get("scored_by", ""), db_path=db_path,
                )
                scored += 1
            except Exception as exc:
                failed += 1
                _log.warning("rescore failed for %s: %s", lead.get("job_id", "?"), exc)

    await asyncio.gather(*(_one(lead) for lead in leads))
    return {"candidates": len(leads), "scored": scored, "failed": failed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--resume", required=True, help="resume file: .pdf, .docx, .md, or .txt")
    parser.add_argument("--out", default=str(DEFAULT_PROFILE_PATH), help="profile JSON to write (default candidate_profile.json)")
    parser.add_argument("--db", default=None, help="database file (defaults to the installed app's)")
    parser.add_argument("--no-rescore", action="store_true", help="skip re-ranking the existing dataset after ingest")
    args = parser.parse_args()

    resume_path = Path(args.resume)
    if not resume_path.exists():
        print(f"  ! resume file not found: {resume_path}")
        return 2

    txt = _document(str(resume_path))
    if not txt.strip():
        print(f"  ! no extractable text in {resume_path} (scanned/image-only PDF?)")
        return 2

    t0 = time.monotonic()
    print(f"\n  extracting profile from {resume_path.name} ({len(txt):,} chars)...")
    parsed = parse_resume(txt)
    print(f"  extracted: {len(parsed.skills)} skills, {len(parsed.exp)} roles, "
          f"{len(parsed.projects)} projects, {len(parsed.certifications)} certifications "
          f"({time.monotonic() - t0:.1f}s)")

    out_path = Path(args.out)
    existing = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    profile = profile_dict_from_model(parsed, existing)
    out_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {out_path}")

    if args.no_rescore:
        return 0

    db_path = run_scrape.resolve_db(args.db)
    cfg = _load_cfg(db_path)
    print(f"\n  re-ranking existing dataset in {db_path} against the updated profile...")
    stats = asyncio.run(rescore_all_leads(profile, cfg, db_path))
    print(f"  re-ranked {stats['scored']}/{stats['candidates']} leads ({stats['failed']} failed)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
