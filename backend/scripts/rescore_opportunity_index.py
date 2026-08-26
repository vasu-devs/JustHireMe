"""Recompute a persisted canonical opportunity index with current rules."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.repository import create_repository
from data.sqlite.opportunity_index import backup_database
from data.sqlite.opportunities import get_candidate_profile
from opportunities.eligibility import OPPORTUNITY_RULE_VERSION, CandidateConstraints
from opportunities.rescore import rescore_existing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--candidate-id", default="phase0-representative-cse")
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    db_path = str(args.db_path.resolve())
    profile = get_candidate_profile(args.candidate_id, db_path=db_path)
    if not profile:
        parser.error(f"candidate profile not found: {args.candidate_id}")
    candidate = CandidateConstraints.model_validate(profile)
    backup = backup_database(db_path, backup_path=args.backup)
    result = rescore_existing(
        create_repository(),
        candidate,
        db_path=db_path,
    )
    report = {
        "candidate_id": candidate.candidate_id,
        "rule_version": OPPORTUNITY_RULE_VERSION,
        "backup": backup,
        **result,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.report:
        report_path = args.report.expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
