from __future__ import annotations

from core.types import CandidateEvidence, CriterionScore
from ranking.criteria.base import CriterionSpec
from ranking.scoring_engine import PostingSignals, _direct_and_adjacent, _fmt_terms, clamp

SPEC = CriterionSpec(
    key="stack_coverage",
    name="Stack overlap",
    max_weight=22,
    description="Required technology and framework coverage.",
)


def evaluate_stack_coverage(posting: PostingSignals, candidate: CandidateEvidence, weight: int) -> CriterionScore:
    required = posting.terms
    if not required:
        score = 55 if posting.role_tags else 25
        return CriterionScore("Stack overlap", score, weight, "no explicit stack to compare")

    direct, adjacent, missing = _direct_and_adjacent(posting, candidate)
    direct_value = len(direct)
    adjacent_value = 0.30 * len(adjacent)
    coverage = (direct_value + adjacent_value) / max(1, len(required))
    # Specificity-scaled ceiling: full coverage of a generic 2-term JD is weaker
    # evidence than full coverage of a specific 6-term one, so the ceiling grows
    # with how much the posting actually asked for.
    ceiling = 70 + min(26, 4 * len(required))
    score = clamp((coverage * ceiling) + min(8, 2 * len(direct)))
    if direct and not missing:
        score = max(score, 72)
    elif direct:
        score = max(score, 50)
    elif adjacent:
        score = max(min(38, 22 + len(adjacent) * 4), 22)
    reason = (
        f"matched {_fmt_terms(direct)}"
        + (f"; adjacent {_fmt_terms(adjacent)}" if adjacent else "")
        + (f"; missing {_fmt_terms(missing)}" if missing else "")
    )
    return CriterionScore("Stack overlap", score, weight, reason)
