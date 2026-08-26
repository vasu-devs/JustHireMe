#!/usr/bin/env python
"""Ingest a user-supplied application queue and prepare safe application packets.

This is the handoff point between a spreadsheet/list of roles and the existing
JustHireMe workflow:

    input file -> durable leads -> live verification -> draft_ready -> autofill queue

Accepted input formats are a text file with one URL per line, CSV with a
required ``url`` column, or JSON (a list of objects or ``{"targets": [...]}``).
CSV/JSON may additionally provide ``title``, ``company``, ``location``,
``description``, and ``score``. Inputs are idempotent: the normalized URL is
hashed into a stable intake job ID, so rerunning the same file does not create
duplicates.

The script never opens a browser, uploads a resume, sends email, or submits an
application. It only creates a verified, auditable queue. The separate
``autofill_application.py`` runner can fill resulting ``draft_ready`` roles
in a signed-in browser, where CAPTCHA, unanswered questions, and final submit
remain human checkpoints.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

import generate_drafts  # noqa: E402
import run_scrape  # noqa: E402
import verify_shortlist  # noqa: E402
from data.sqlite.connection import run_migrations  # noqa: E402
from data.sqlite.leads import get_lead_by_id, save_lead, update_lead_status  # noqa: E402


def normalize_url(value: str) -> str:
    """Return a stable HTTP(S) URL, dropping fragments only."""
    raw = str(value or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"expected an http(s) URL, got {raw!r}")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))


def intake_job_id(url: str) -> str:
    return "intake_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def infer_platform(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    if "greenhouse" in host:
        return "greenhouse"
    if "ashbyhq" in host:
        return "ashby"
    if "lever.co" in host:
        return "lever"
    if "workday" in host:
        return "workday"
    return "intake"


def _as_target(item: object, *, source: Path) -> dict:
    if isinstance(item, str):
        item = {"url": item}
    if not isinstance(item, dict):
        raise ValueError(f"{source}: every target must be a URL string or an object")
    url = normalize_url(str(item.get("url") or ""))
    try:
        score = max(0, min(int(item.get("score") or 0), 100))
    except (TypeError, ValueError):
        score = 0
    return {
        "url": url,
        "title": str(item.get("title") or "").strip(),
        "company": str(item.get("company") or "").strip(),
        "location": str(item.get("location") or "").strip(),
        "description": str(item.get("description") or "").strip(),
        "score": score,
        "source": str(item.get("source") or source.name).strip() or source.name,
    }


def load_targets(path: Path) -> list[dict]:
    """Load and URL-dedupe a text/CSV/JSON intake file in its given order."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            targets = [_as_target(row, source=path) for row in csv.DictReader(handle)]
    elif suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw.get("targets") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            raise ValueError(f"{path}: JSON must be a list or contain a 'targets' list")
        targets = [_as_target(item, source=path) for item in items]
    else:
        lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
        targets = [_as_target(line, source=path) for line in lines if line and not line.startswith("#")]

    unique: dict[str, dict] = {}
    for target in targets:
        unique.setdefault(target["url"], target)
    return list(unique.values())


def _lead_from_target(target: dict) -> dict:
    url = target["url"]
    company = target["company"] or urlsplit(url).netloc.removeprefix("www.")
    return {
        "job_id": intake_job_id(url),
        "title": target["title"] or "Application target",
        "company": company,
        "url": url,
        "platform": infer_platform(url),
        "description": target["description"],
        "location": target["location"],
        "kind": "job",
        "source_meta": {"intake": True, "intake_source": target["source"], "intake_score": target["score"]},
    }


def ingest_targets(targets: list[dict], db_path: str) -> tuple[list[dict], int]:
    """Persist targets and return canonical lead rows plus inserted count."""
    leads: list[dict] = []
    inserted = 0
    for target in targets:
        lead = _lead_from_target(target)
        if not get_lead_by_id(lead["job_id"], db_path):
            save_lead(lead, db_path)
            inserted += 1
        canonical = get_lead_by_id(lead["job_id"], db_path)
        if not canonical:
            raise RuntimeError(f"failed to persist intake target {lead['url']}")
        leads.append(canonical)
    return leads, inserted


def apply_verdict_statuses(leads: list[dict], results: dict, db_path: str) -> dict[str, int]:
    """Persist conservative queue state after the live verifier finishes."""
    counts: dict[str, int] = {"discarded": 0, "matched": 0, "unresolved": 0}
    for lead in leads:
        verdict = str(results.get(lead["job_id"], {}).get("verdict") or "UNCLEAR")
        if verdict in {"REJECTED", "DEAD"}:
            update_lead_status(lead["job_id"], "discarded", db_path)
            counts["discarded"] += 1
        elif verdict == "CONFIRMED":
            update_lead_status(lead["job_id"], "matched", db_path)
            counts["matched"] += 1
        else:
            counts["unresolved"] += 1
    return counts


def draft_confirmed(leads: list[dict], results: dict, *, profile: dict, out_dir: Path, cap: int, db_path: str) -> int:
    drafted = 0
    for lead in leads:
        if drafted >= cap or results.get(lead["job_id"], {}).get("verdict") != "CONFIRMED":
            continue
        canonical = get_lead_by_id(lead["job_id"], db_path)
        generate_drafts.generate_draft(profile, canonical, out_dir, db_path)
        update_lead_status(lead["job_id"], "draft_ready", db_path)
        drafted += 1
    return drafted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help=".txt, .csv, or .json target list")
    parser.add_argument("--db", default=None, help="database file (defaults to the installed app's)")
    parser.add_argument("--fresh", action="store_true", help="live-verify even if a target is cached")
    parser.add_argument("--no-verify", action="store_true", help="ingest only; do not make network requests")
    parser.add_argument("--concurrency", type=int, default=4, help="maximum simultaneous verification requests (default 4)")
    parser.add_argument("--draft", action="store_true", help="write tailored drafts for confirmed roles; never sends them")
    parser.add_argument("--draft-cap", type=int, default=10, help="maximum drafts with --draft (default 10)")
    parser.add_argument("--profile", default=str(Path(__file__).with_name("candidate_profile.json")))
    parser.add_argument("--out", default=str(Path(__file__).with_name("drafts")), help="draft output directory")
    args = parser.parse_args()

    source = Path(args.input)
    if not source.is_file():
        parser.error(f"input file not found: {source}")
    if args.draft_cap < 1:
        parser.error("--draft-cap must be at least 1")
    targets = load_targets(source)
    if not targets:
        parser.error("input contained no application targets")

    db_path = run_scrape.resolve_db(args.db)
    run_migrations(db_path)
    leads, inserted = ingest_targets(targets, db_path)
    report: dict = {"input": str(source), "targets": len(targets), "inserted": inserted,
                    "job_ids": [lead["job_id"] for lead in leads], "verified": False, "drafted": 0}
    if not args.no_verify:
        results = asyncio.run(verify_shortlist.run(leads, db_path, fresh=args.fresh, concurrency=args.concurrency))
        report["verified"] = True
        report["verdicts"] = {lead["job_id"]: results.get(lead["job_id"], {}).get("verdict", "UNCLEAR") for lead in leads}
        report["queue"] = apply_verdict_statuses(leads, results, db_path)
        if args.draft:
            profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
            report["drafted"] = draft_confirmed(leads, results, profile=profile, out_dir=Path(args.out), cap=args.draft_cap, db_path=db_path)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("\nNext: run autofill_application.py only in a signed-in browser; CAPTCHA, unknown questions, and final submission stay human-controlled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
