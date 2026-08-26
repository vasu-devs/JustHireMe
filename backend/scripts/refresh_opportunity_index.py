"""Refresh selected public providers in an existing canonical opportunity index."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog.market_registry import production_market_targets, scrape_market_target
from catalog.source_registry import run_direct_scan
from data.sqlite.connection import close_all
from data.sqlite.opportunities import get_candidate_profile, save_pipeline_result
from data.sqlite.opportunity_index import backup_database, public_index_status
from opportunities.eligibility import CandidateConstraints


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", help="SQLite canonical index to refresh")
    parser.add_argument("--candidate-id", default="phase0-representative-cse")
    parser.add_argument(
        "--provider",
        action="append",
        required=True,
        help="Provider family to refresh; repeat for multiple providers",
    )
    parser.add_argument(
        "--target-id",
        action="append",
        help="Optional exact production target ID; repeat to refresh only selected targets",
    )
    parser.add_argument("--backup", required=True, help="Required non-existing backup path")
    parser.add_argument("--report", help="Optional JSON evidence report")
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=480)
    return parser


async def _scan(args, candidate: CandidateConstraints):
    requested = {str(value).strip().lower() for value in args.provider if str(value).strip()}
    targets = [
        target
        for target in production_market_targets(company_limit=500)
        if target.provider.lower() in requested
    ]
    found = {target.provider.lower() for target in targets}
    missing = sorted(requested - found)
    if missing:
        raise ValueError(f"providers have no production targets: {', '.join(missing)}")
    if args.target_id:
        requested_targets = {
            str(value).strip().lower() for value in args.target_id if str(value).strip()
        }
        available = {target.target_id.lower() for target in targets}
        missing_targets = sorted(requested_targets - available)
        if missing_targets:
            raise ValueError(
                f"target IDs are not registered for the requested providers: "
                f"{', '.join(missing_targets)}"
            )
        targets = [target for target in targets if target.target_id.lower() in requested_targets]
    if not targets:
        raise ValueError("no production targets selected")
    scan = await run_direct_scan(
        targets,
        candidate=candidate,
        scraper=scrape_market_target,
        max_concurrency=max(1, min(args.max_concurrency, 12)),
        target_timeout_seconds=max(1, min(args.timeout_seconds, 1800)),
    )
    return targets, scan


def main() -> int:
    args = _parser().parse_args()
    db_path = str(Path(args.db_path).expanduser().resolve())
    profile = get_candidate_profile(args.candidate_id, db_path=db_path)
    if not profile:
        raise SystemExit(f"candidate profile not found: {args.candidate_id}")
    candidate_payload = dict(profile)
    candidate_payload.pop("profile_updated_at", None)
    candidate = CandidateConstraints.model_validate(candidate_payload)
    before = public_index_status(db_path=db_path)
    targets, scan = asyncio.run(_scan(args, candidate))
    failures = [
        row.model_dump(mode="json")
        for row in scan.source_health
        if row.status.value not in {"success", "zero_result"}
    ]
    if failures:
        rendered = "; ".join(
            f"{row['target_id']}: {row.get('error_type') or row['status']}"
            for row in failures
        )
        raise SystemExit(f"refusing partial provider refresh; source failures: {rendered}")

    close_all()
    backup = backup_database(db_path, backup_path=args.backup)
    persisted = save_pipeline_result(
        scan.pipeline,
        candidate_id=candidate.candidate_id,
        db_path=db_path,
    )
    close_all()
    after = public_index_status(db_path=db_path)
    report = {
        "candidate_id": candidate.candidate_id,
        "providers": sorted({target.provider for target in targets}),
        "targets": [
            {
                "target_id": target.target_id,
                "provider": target.provider,
                "scan_target": target.scan_target,
            }
            for target in targets
        ],
        "source_health": [row.model_dump(mode="json") for row in scan.source_health],
        "raw_rows": sum(row.raw_rows for row in scan.source_health),
        "accepted_source_records": len(scan.pipeline.source_records),
        "conversion_errors": scan.pipeline.conversion_errors,
        "delta_decision_counts": scan.pipeline.decision_counts,
        "persisted": persisted,
        "before": before,
        "after": after,
        "backup": backup,
        "private_candidate_id": candidate.candidate_id,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.report:
        output = Path(args.report).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
