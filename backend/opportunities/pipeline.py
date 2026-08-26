from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opportunities.canonicalize import source_record_from_lead
from opportunities.deduplicate import canonicalize_observations
from opportunities.eligibility import ApplicabilityDecision, CandidateConstraints, Decision, evaluate_applicability
from opportunities.models import CanonicalOpportunity, SourceKind, SourceRecord


class CandidateOpportunity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity: CanonicalOpportunity
    applicability: ApplicabilityDecision


class OpportunityPipelineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_records: list[SourceRecord] = Field(default_factory=list)
    opportunities: list[CandidateOpportunity] = Field(default_factory=list)
    conversion_errors: list[str] = Field(default_factory=list)
    decision_counts: dict[str, int] = Field(default_factory=dict)


def _primary_observation(opportunity: CanonicalOpportunity) -> SourceRecord:
    # Repeated scans of the same requisition are immutable observations. Prefer
    # the newest observation when it remains substantially complete, but do not
    # let a transient card-only/detail-fetch fallback erase richer known facts.
    # After collapsing each source identity this way, retain the existing
    # direct-source and richness preference across genuinely different sources.
    by_source: dict[tuple[str, str, str, str], list[SourceRecord]] = {}
    for record in opportunity.observations:
        key = (
            record.provider,
            record.provider_tenant,
            record.provider_requisition_id,
            record.canonical_source_url,
        )
        by_source.setdefault(key, []).append(record)
    current_by_source: list[SourceRecord] = []
    for observations in by_source.values():
        longest = max(len(record.description_full) for record in observations)
        completeness_floor = int(longest * 0.8)
        complete = [
            record for record in observations
            if len(record.description_full) >= completeness_floor
        ]
        current_by_source.append(max(complete, key=lambda record: record.observed_at))
    return max(
        current_by_source,
        key=lambda record: (
            record.source_kind in {SourceKind.DIRECT_EMPLOYER, SourceKind.ATS},
            len(record.description_full),
            record.observed_at,
        ),
    )


def process_leads(
    leads: list[dict[str, Any]],
    *,
    candidate: CandidateConstraints,
    observed_at: datetime | None = None,
    parser_version: str = "1",
) -> OpportunityPipelineResult:
    """Bridge existing adapters into truth -> applicability without persistence."""
    observed = observed_at or datetime.now(timezone.utc)
    records_by_id: dict[str, SourceRecord] = {}
    errors: list[str] = []
    for index, lead in enumerate(leads):
        try:
            record = source_record_from_lead(
                lead,
                observed_at=observed,
                raw_payload=lead,
                parser_version=parser_version,
            )
        except Exception as exc:
            errors.append(f"lead[{index}]: {type(exc).__name__}: {exc}")
            continue
        records_by_id[record.source_record_id] = record

    records = list(records_by_id.values())
    canonical = canonicalize_observations(records)
    evaluated = evaluate_canonical_opportunities(canonical, candidate=candidate)
    return evaluated.model_copy(update={"source_records": records, "conversion_errors": errors})


def evaluate_canonical_opportunities(
    canonical: list[CanonicalOpportunity],
    *,
    candidate: CandidateConstraints,
) -> OpportunityPipelineResult:
    """Recompute private candidate decisions without refetching public sources."""
    candidate_opportunities: list[CandidateOpportunity] = []
    for opportunity in canonical:
        primary = _primary_observation(opportunity)
        applicability = evaluate_applicability(
            title=opportunity.title,
            description=primary.description_full,
            location=opportunity.location_text,
            candidate=candidate,
            workplace=primary.workplace_text,
            live_status=opportunity.lifecycle.status,
        )
        candidate_opportunities.append(
            CandidateOpportunity(opportunity=opportunity, applicability=applicability)
        )

    decision_order = {
        Decision.APPLY_NOW: 0,
        Decision.STRONG_STRETCH: 1,
        Decision.NEEDS_REVIEW: 2,
        Decision.SKIP: 3,
    }
    candidate_opportunities.sort(
        key=lambda item: (
            decision_order[item.applicability.decision],
            item.opportunity.employer_name.lower(),
            item.opportunity.title.lower(),
        )
    )
    counts = Counter(item.applicability.decision.value for item in candidate_opportunities)
    return OpportunityPipelineResult(
        source_records=[],
        opportunities=candidate_opportunities,
        conversion_errors=[],
        decision_counts=dict(counts),
    )
