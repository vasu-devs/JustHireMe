from __future__ import annotations

from data.repository import Repository
from opportunities.eligibility import CandidateConstraints
from opportunities.models import CanonicalOpportunity
from opportunities.pipeline import evaluate_canonical_opportunities


def rescore_existing(
    repo: Repository,
    candidate: CandidateConstraints,
    *,
    db_path: str | None = None,
) -> dict[str, int]:
    """Recompute one candidate against current canonical truth without network I/O."""
    storage_kwargs = {"db_path": db_path} if db_path else {}
    # The canonical index can exceed the repository's display-oriented 20k
    # default. A rescore is a consistency operation, so request the storage
    # ceiling explicitly instead of silently leaving the oldest rows stale.
    payloads = repo.opportunities.list_canonical_opportunities(limit=100_000, **storage_kwargs)
    if not payloads:
        return {}
    canonical: list[CanonicalOpportunity] = []
    invalid = 0
    for payload in payloads:
        try:
            canonical.append(CanonicalOpportunity.model_validate(payload))
        except Exception:
            invalid += 1
    result = evaluate_canonical_opportunities(canonical, candidate=candidate)
    repo.opportunities.save_candidate_decisions(
        result,
        candidate_id=candidate.candidate_id,
        **storage_kwargs,
    )
    return {**result.decision_counts, "opportunities": len(result.opportunities), "invalid_canonical": invalid}
