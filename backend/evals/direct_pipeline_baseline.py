from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from catalog.source_registry import SourceTarget, run_direct_scan
from catalog.query_matrix import expand_early_career_targets
from catalog.market_registry import production_market_targets, scrape_market_target
from data.sqlite.opportunities import (
    create_scan_run,
    finish_scan_run,
    save_candidate_profile,
    save_pipeline_result,
)
from discovery.sources.ats import scrape_target as scrape_ats_target
from evals.company_benchmark import DEFAULT_OUTPUT as COMPANY_BENCHMARK_PATH
from evals.company_benchmark import load_company_benchmark
from opportunities.eligibility import CandidateConstraints, DegreeLevel
from opportunities.taxonomy import TechnicalTrack


DEFAULT_REPORT_PATH = Path(__file__).parent / "output" / "direct_pipeline_baseline.json"


def representative_cse_candidate() -> CandidateConstraints:
    """Synthetic, non-private profile used for repeatable coverage decisions."""
    return CandidateConstraints(
        candidate_id="phase0-representative-cse",
        home_country="IN",
        graduation_year=2027,
        currently_enrolled=True,
        current_degree_level=DegreeLevel.BACHELORS,
        accepted_india_cities=[
            "Bengaluru", "Hyderabad", "Pune", "Gurugram", "Noida", "Chennai", "Mumbai",
        ],
        technical_skills=[
            "Python", "Java", "JavaScript", "TypeScript", "React", "Node.js",
            "SQL", "Git", "Docker", "AWS", "machine learning", "data structures",
        ],
        spoken_languages=["English"],
        project_keywords=["REST API", "full-stack", "LLM", "computer vision", "cloud deployment"],
        preferred_technical_tracks=[
            TechnicalTrack.SOFTWARE,
            TechnicalTrack.BACKEND,
            TechnicalTrack.FRONTEND,
            TechnicalTrack.FULLSTACK,
            TechnicalTrack.AI_ML,
            TechnicalTrack.DATA,
            TechnicalTrack.CLOUD_DEVOPS,
        ],
        allow_unpaid=False,
        allow_bond=False,
    )


def _targets(benchmark_path: Path, max_boards: int, provider: str = "") -> list[SourceTarget]:
    records = load_company_benchmark(benchmark_path)
    if provider:
        records = [record for record in records if str(record.get("provider") or "").lower() == provider.lower()]
    targets = [
        SourceTarget(
            target_id=str(record["company_id"]),
            company_id=str(record["company_id"]),
            provider=str(record["provider"]),
            scan_target=str(record["scan_target"]),
            parser_version="opportunity-v1",
        )
        for record in records[: max(1, max_boards)]
    ]
    return expand_early_career_targets(targets)


def _report(run) -> dict:
    health_counts = Counter(health.status.value for health in run.source_health)
    raw_by_provider: Counter[str] = Counter()
    accepted_by_provider: Counter[str] = Counter()
    durations_by_provider: dict[str, list[int]] = {}
    for health in run.source_health:
        raw_by_provider[health.provider] += health.raw_rows
        accepted_by_provider[health.provider] += health.accepted_source_records
        durations_by_provider.setdefault(health.provider, []).append(health.duration_ms)

    types: Counter[str] = Counter()
    tracks: Counter[str] = Counter()
    workplaces: Counter[str] = Counter()
    hard_blockers: Counter[str] = Counter()
    safety_blockers: Counter[str] = Counter()
    unknowns: Counter[str] = Counter()
    direct_urls = 0
    for item in run.pipeline.opportunities:
        applicability = item.applicability
        types[applicability.opportunity_type.value] += 1
        tracks[applicability.technical_track.value] += 1
        workplaces[applicability.workplace_scope.value] += 1
        hard_blockers.update(applicability.hard_blockers)
        safety_blockers.update(applicability.safety_blockers)
        unknowns.update(applicability.unknowns)
        if any(record.source_kind.value in {"direct_employer", "ats"} for record in item.opportunity.observations):
            direct_urls += 1

    source_records = run.pipeline.source_records
    completeness_fields = {
        "source_target_id": lambda record: record.source_target_id,
        "provider_tenant": lambda record: record.provider_tenant,
        "canonical_source_url": lambda record: record.canonical_source_url,
        "apply_url": lambda record: record.apply_url,
        "provider_requisition_id": lambda record: record.provider_requisition_id,
        "employer_domain": lambda record: record.employer_domain,
        "location_text": lambda record: record.location_text,
        "workplace_text": lambda record: record.workplace_text,
        "description_full": lambda record: record.description_full,
        "description_sha256": lambda record: record.description_sha256,
        "raw_payload_sha256": lambda record: record.raw_payload_sha256,
        "provider_published_text": lambda record: record.provider_published_text,
        "provider_updated_text": lambda record: record.provider_updated_text,
        "provider_deadline_text": lambda record: record.provider_deadline_text,
        "published_at": lambda record: record.published_at,
        "updated_at": lambda record: record.updated_at,
        "deadline_at": lambda record: record.deadline_at,
        "attribution": lambda record: record.attribution,
    }
    field_completeness = {
        field: {
            "populated": sum(bool(getter(record)) for record in source_records),
            "total": len(source_records),
            "percent": round(
                100 * sum(bool(getter(record)) for record in source_records) / len(source_records),
                2,
            ) if source_records else 0.0,
        }
        for field, getter in completeness_fields.items()
    }
    observation_counts = [len(item.opportunity.observations) for item in run.pipeline.opportunities]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat(),
        "candidate_profile": {
            "home_country": "IN",
            "graduation_year": 2027,
            "currently_enrolled": True,
            "current_degree_level": "bachelors",
            "allow_unpaid": False,
            "allow_bond": False,
            "technical_skills": [
                "Python", "Java", "JavaScript", "TypeScript", "React", "Node.js",
                "SQL", "Git", "Docker", "AWS", "machine learning", "data structures",
            ],
            "project_keywords": [
                "REST API", "full-stack", "LLM", "computer vision", "cloud deployment",
            ],
            "preferred_technical_tracks": [
                "software", "backend", "frontend", "fullstack", "ai_ml", "data", "cloud_devops",
            ],
            "contains_private_candidate_data": False,
        },
        "targets": len(run.source_health),
        "source_health_counts": dict(health_counts),
        "raw_rows": sum(health.raw_rows for health in run.source_health),
        "accepted_source_records": len(run.pipeline.source_records),
        "conversion_error_count": len(run.pipeline.conversion_errors),
        "conversion_error_samples": run.pipeline.conversion_errors[:20],
        "canonical_opportunities": len(run.pipeline.opportunities),
        "decision_counts": run.pipeline.decision_counts,
        "opportunity_type_counts": dict(types),
        "technical_track_counts": dict(tracks),
        "workplace_scope_counts": dict(workplaces),
        "hard_blocker_counts": dict(hard_blockers),
        "safety_blocker_counts": dict(safety_blockers),
        "unknown_counts": dict(unknowns),
        "direct_source_opportunities": direct_urls,
        "field_completeness": field_completeness,
        "deduplication": {
            "source_records": len(source_records),
            "canonical_opportunities": len(run.pipeline.opportunities),
            "collapsed_observations": max(0, len(source_records) - len(run.pipeline.opportunities)),
            "opportunities_with_multiple_observations": sum(count > 1 for count in observation_counts),
            "maximum_observations_per_opportunity": max(observation_counts, default=0),
        },
        "raw_rows_by_provider": dict(raw_by_provider),
        "accepted_records_by_provider": dict(accepted_by_provider),
        "provider_max_duration_ms": {
            provider: max(durations) for provider, durations in durations_by_provider.items()
        },
        "source_health": [health.model_dump(mode="json") for health in run.source_health],
        "labels_are_automated_not_human_gold": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, default=COMPANY_BENCHMARK_PATH)
    parser.add_argument("--max-boards", type=int, default=500)
    parser.add_argument("--max-concurrency", type=int, default=6)
    parser.add_argument("--provider", default="", help="Optional provider-only diagnostic run")
    parser.add_argument(
        "--target-id",
        action="append",
        default=[],
        help="optional exact runtime target id; repeat to run a reproducible delta scan",
    )
    parser.add_argument(
        "--runtime-market",
        action="store_true",
        help="scan the complete production company + keyless market inventory instead of the benchmark",
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="optionally persist this scan into an isolated canonical SQLite opportunity index",
    )
    args = parser.parse_args()

    candidate = representative_cse_candidate()
    targets = (
        production_market_targets(company_limit=args.max_boards)
        if args.runtime_market
        else _targets(args.benchmark, args.max_boards, args.provider)
    )
    if args.runtime_market and args.provider:
        targets = [target for target in targets if target.provider.lower() == args.provider.lower()]
    if args.target_id:
        selected = {value.strip().lower() for value in args.target_id if value.strip()}
        targets = [target for target in targets if target.target_id.lower() in selected]
        missing = sorted(selected - {target.target_id.lower() for target in targets})
        if missing:
            parser.error(f"unknown or filtered target ids: {', '.join(missing)}")
    if not targets:
        parser.error("no scan targets matched the requested filters")
    run_id = ""
    if args.db_path is not None:
        args.db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path = str(args.db_path.resolve())
        save_candidate_profile(
            candidate.candidate_id,
            candidate.model_dump(mode="json"),
            db_path=db_path,
        )
        run_id = create_scan_run(
            candidate.candidate_id,
            target_count=len(targets),
            db_path=db_path,
        )
    run = asyncio.run(
        run_direct_scan(
            targets,
            candidate=candidate,
            scraper=scrape_market_target if args.runtime_market else scrape_ats_target,
            max_concurrency=args.max_concurrency,
            on_target_complete=lambda health: print(
                f"[{health.status.value}] {health.target_id}: "
                f"{health.raw_rows} raw in {health.duration_ms} ms"
            ),
        )
    )
    persisted = None
    if args.db_path is not None:
        db_path = str(args.db_path.resolve())
        persisted = save_pipeline_result(
            run.pipeline,
            candidate_id=candidate.candidate_id,
            db_path=db_path,
        )
        finish_scan_run(
            run_id,
            candidate.candidate_id,
            status="completed",
            payload={
                "run_id": run_id,
                "candidate_id": candidate.candidate_id,
                "status": "completed",
                "target_count": len(targets),
                "decision_counts": run.pipeline.decision_counts,
                "persisted": persisted,
            },
            source_health=[health.model_dump(mode="json") for health in run.source_health],
            db_path=db_path,
        )
    report = _report(run)
    if persisted is not None:
        report["persisted_index"] = {
            "db_path": str(args.db_path.resolve()),
            "run_id": run_id,
            **persisted,
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Targets: {len(targets)}")
    print(f"Source health: {report['source_health_counts']}")
    print(f"Raw rows: {report['raw_rows']}")
    print(f"Canonical opportunities: {report['canonical_opportunities']}")
    print(f"Decisions: {report['decision_counts']}")
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
