from __future__ import annotations

from core.types import CandidateEvidence, CriterionScore
from ranking.criteria.base import CriterionSpec
from ranking.scoring_engine import PostingSignals

SPEC = CriterionSpec(
    key="role_alignment",
    name="Role alignment",
    max_weight=15,
    description="Role title, function, and domain lane alignment.",
)


def evaluate_role_alignment(posting: PostingSignals, candidate: CandidateEvidence) -> CriterionScore:
    if posting.wrong_field:
        detail = ", ".join(posting.wrong_field_terms[:3])
        if posting.wrong_field_title:
            detail = f"job title is a different occupation ({detail or posting.title})"
        return CriterionScore(
            "Role alignment",
            0,
            18,
            "non-target field: " + detail,
        )

    if not posting.role_tags and not posting.terms:
        return CriterionScore("Role alignment", 30, 18, "posting has no clear technical role signal")

    overlap = posting.role_tags & candidate.role_tags
    direct_terms = posting.terms & candidate.all_terms
    if overlap:
        if direct_terms:
            score = 88
            reason = "same role lane (" + ", ".join(sorted(overlap)) + ") with direct stack overlap"
        elif posting.terms:
            # Same lane label but no shared concrete tools - likely a different sub-niche.
            score = 64
            reason = "role lane label matches (" + ", ".join(sorted(overlap)) + ") but stacks differ"
        else:
            score = 78
            reason = "same role lane: " + ", ".join(sorted(overlap))
    elif posting.role_tags and (posting.role_tags & {"backend", "frontend", "fullstack", "ai", "data"}) and candidate.all_terms:
        score = 55
        reason = "technical role is adjacent to candidate profile"
    elif posting.terms and direct_terms:
        score = 60
        reason = "technical stack overlap exists but role lane is weakly specified"
    elif posting.terms and candidate.all_terms:
        score = 38
        reason = "stack mentioned but no shared tools and no role label"
    else:
        score = 22
        reason = "role does not map to candidate target"
    return CriterionScore("Role alignment", score, 18, reason)
