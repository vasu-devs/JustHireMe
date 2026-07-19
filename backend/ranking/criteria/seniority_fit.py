from __future__ import annotations

from core.types import CandidateEvidence, CriterionScore
from ranking.criteria.base import CriterionSpec
from ranking.scoring_engine import PostingSignals

SPEC = CriterionSpec(
    key="seniority_fit",
    name="Seniority fit",
    max_weight=25,
    description="Years, scope, title, and responsibility fit.",
)


def posting_states_seniority_requirement(posting: PostingSignals) -> bool:
    """Whether the posting states ANY seniority requirement (years or title flags).

    When it doesn't, the seniority criterion returns the same near-neutral score
    for every candidate, so the scoring engine shifts its weight onto criteria
    that actually discriminate (proof of work, semantic fit).
    """
    return bool(posting.max_years or posting.seniority_flags)


def evaluate_seniority_fit(posting: PostingSignals, candidate: CandidateEvidence) -> CriterionScore:
    level_years = {"fresher": 0, "junior": 1.5, "mid": 3.5, "senior": 7}.get(candidate.level, 1)
    flags = posting.seniority_flags
    required_years = posting.max_years

    if posting.entry_level and candidate.level in {"fresher", "junior"}:
        return CriterionScore("Seniority fit", 92, 20, f"{candidate.level} profile matches entry-level signal")
    if not required_years and not flags:
        return CriterionScore("Seniority fit", 84, 20, f"no hard seniority requirement; profile reads {candidate.level}")

    effective_required = required_years
    if "senior" in flags:
        effective_required = max(effective_required, 5)
    if "manager" in flags:
        effective_required = max(effective_required, 6)

    gap = effective_required - level_years
    if gap <= 0.5:
        score = 86
    elif gap <= 1.5:
        score = 62
    elif gap <= 3:
        score = 34
    elif gap <= 5:
        score = 18
    else:
        score = 10
    reason = f"requires about {effective_required:g}+ years; profile reads {candidate.level}"
    if flags:
        reason += " with " + ", ".join(sorted(flags)) + " title signal"
    return CriterionScore("Seniority fit", score, 20, reason)
