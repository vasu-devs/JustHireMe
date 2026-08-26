"""Audit unregistered public job boards against a stored candidate profile.

This is the admission gate between broad, harmless ATS slug probing and the
production registry. It fetches each explicit public target through the real
adapter, converts every row through the canonical opportunity pipeline, and
writes candidate-relevant yield plus conversion failures to an evidence file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog.market_registry import scrape_market_target
from data.sqlite.opportunities import get_candidate_profile
from opportunities.eligibility import OPPORTUNITY_RULE_VERSION, CandidateConstraints, Decision
from opportunities.pipeline import process_leads


def _iso(value: object) -> str | None:
    isoformat = getattr(value, "isoformat", None)
    return str(isoformat()) if callable(isoformat) else None


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def _opportunity_evidence(opportunity: object) -> dict:
    """Return bounded provenance and freshness evidence for admission review."""
    lifecycle = getattr(opportunity, "lifecycle", None)
    published_at = getattr(lifecycle, "published_at", None)
    updated_at = getattr(lifecycle, "updated_at", None)
    last_seen_at = getattr(lifecycle, "last_seen_at", None)
    content_signal = max(
        (value for value in (published_at, updated_at) if value is not None),
        default=None,
    )
    posting_age_days = None
    if content_signal is not None and last_seen_at is not None:
        posting_age_days = max(0, int((last_seen_at - content_signal).total_seconds() // 86400))
    if posting_age_days is None:
        freshness_band = "undated"
    elif posting_age_days <= 30:
        freshness_band = "recent_30d"
    elif posting_age_days <= 90:
        freshness_band = "recent_90d"
    elif posting_age_days <= 180:
        freshness_band = "recent_180d"
    else:
        # A current first-party apply control is still meaningful evidence, but
        # an old publication/update signal must remain visible to reviewers.
        freshness_band = "aged_180d_plus"

    observations = list(getattr(opportunity, "observations", []) or [])
    primary = max(observations, key=lambda row: str(getattr(row, "observed_at", "") or "")) if observations else None
    return {
        "live_status": _enum_value(getattr(lifecycle, "status", "")),
        "first_seen_at": _iso(getattr(lifecycle, "first_seen_at", None)),
        "last_seen_at": _iso(last_seen_at),
        "last_verified_active_at": _iso(getattr(lifecycle, "last_verified_active_at", None)),
        "published_at": _iso(published_at),
        "updated_at": _iso(updated_at),
        "deadline_at": _iso(getattr(lifecycle, "deadline_at", None)),
        "lifecycle_evidence": list(getattr(lifecycle, "evidence", []) or []),
        "posting_age_days": posting_age_days,
        "freshness_band": freshness_band,
        "source_provider": str(getattr(primary, "provider", "") or ""),
        "source_tenant": str(getattr(primary, "provider_tenant", "") or ""),
        "source_kind": _enum_value(getattr(primary, "source_kind", "")),
        "source_target_id": str(getattr(primary, "source_target_id", "") or ""),
        "provider_requisition_id": str(getattr(primary, "provider_requisition_id", "") or ""),
        "provider_published_text": str(getattr(primary, "provider_published_text", "") or ""),
        "provider_updated_text": str(getattr(primary, "provider_updated_text", "") or ""),
        "provider_deadline_text": str(getattr(primary, "provider_deadline_text", "") or ""),
        "active_hint": _enum_value(getattr(primary, "active_hint", "")),
        "attribution": str(getattr(primary, "attribution", "") or ""),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--candidate-id", default="phase0-representative-cse")
    parser.add_argument("--target", action="append", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--max-concurrency", type=int, default=4)
    return parser


async def _audit_target(
    target: str,
    *,
    candidate: CandidateConstraints,
    semaphore: asyncio.Semaphore,
) -> dict:
    async with semaphore:
        try:
            rows = await scrape_market_target(target)
        except Exception as exc:
            return {
                "target": target,
                "status": "fetch_error",
                "error": f"{type(exc).__name__}: {exc}",
                "rows": 0,
                "accepted": 0,
                "conversion_errors": [],
                "decision_counts": {},
                "skip_reason_counts": {},
                "freshness_counts": {},
                "aged_relevant_count": 0,
                "skip_samples": [],
                "relevant": [],
            }
    pipeline = process_leads(rows, candidate=candidate)
    relevant = []
    skip_reason_counts: Counter[str] = Counter()
    freshness_counts: Counter[str] = Counter()
    aged_relevant_count = 0
    skip_samples = []
    for item in pipeline.opportunities:
        opportunity = item.opportunity
        evidence = _opportunity_evidence(opportunity)
        freshness_counts.update([evidence["freshness_band"]])
        applicability = item.applicability
        if applicability.decision == Decision.SKIP:
            reasons = [*applicability.hard_blockers, *applicability.safety_blockers]
            if not reasons:
                reasons = ["skip_without_explicit_blocker"]
            skip_reason_counts.update(reasons)
            if len(skip_samples) < 12:
                skip_samples.append(
                    {
                        "employer": opportunity.employer_name,
                        "title": opportunity.title,
                        "location": opportunity.location_text,
                        "hard_blockers": applicability.hard_blockers,
                        "safety_blockers": applicability.safety_blockers,
                        **evidence,
                    }
                )
            continue
        if evidence["freshness_band"] == "aged_180d_plus":
            aged_relevant_count += 1
        relevant.append(
            {
                "opportunity_id": opportunity.opportunity_id,
                "employer": opportunity.employer_name,
                "title": opportunity.title,
                "location": opportunity.location_text,
                "apply_url": opportunity.canonical_apply_url,
                "decision": applicability.decision.value,
                "eligibility": applicability.eligibility.value,
                "minimum_experience_years": applicability.minimum_experience_years,
                "technical_track": applicability.technical_track.value,
                "workplace_scope": applicability.workplace_scope.value,
                "paid_status": applicability.paid_status.value,
                "priority_score": applicability.priority_score,
                "hard_blockers": applicability.hard_blockers,
                "safety_blockers": applicability.safety_blockers,
                "safety_warnings": applicability.safety_warnings,
                **evidence,
            }
        )
    return {
        "target": target,
        "status": "success" if rows else "zero_result",
        "rows": len(rows),
        "accepted": len(pipeline.source_records),
        "conversion_errors": pipeline.conversion_errors,
        "decision_counts": pipeline.decision_counts,
        "skip_reason_counts": dict(skip_reason_counts.most_common()),
        "freshness_counts": dict(freshness_counts.most_common()),
        "aged_relevant_count": aged_relevant_count,
        "skip_samples": skip_samples,
        "relevant": relevant,
    }


async def _run(args: argparse.Namespace, candidate: CandidateConstraints) -> list[dict]:
    semaphore = asyncio.Semaphore(max(1, min(int(args.max_concurrency), 12)))
    return list(
        await asyncio.gather(
            *(
                _audit_target(target, candidate=candidate, semaphore=semaphore)
                for target in args.target
            )
        )
    )


def main() -> int:
    args = _parser().parse_args()
    db_path = str(Path(args.db_path).expanduser().resolve())
    profile = get_candidate_profile(args.candidate_id, db_path=db_path)
    if not profile:
        raise SystemExit(f"candidate profile not found: {args.candidate_id}")
    profile.pop("profile_updated_at", None)
    candidate = CandidateConstraints.model_validate(profile)
    boards = asyncio.run(_run(args, candidate))
    report = {
        "candidate_id": candidate.candidate_id,
        "rule_version": OPPORTUNITY_RULE_VERSION,
        "target_count": len(boards),
        "raw_rows": sum(board["rows"] for board in boards),
        "accepted": sum(board["accepted"] for board in boards),
        "conversion_error_count": sum(len(board["conversion_errors"]) for board in boards),
        "relevant_count": sum(len(board["relevant"]) for board in boards),
        "boards": boards,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    output = Path(args.report).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if all(board["status"] in {"success", "zero_result"} for board in boards) else 1


if __name__ == "__main__":
    raise SystemExit(main())
