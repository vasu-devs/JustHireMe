from __future__ import annotations

import json
from dataclasses import dataclass

from evals.opportunity_contracts import PILOT_CANDIDATE, OpportunityCase, load_opportunity_cases
from opportunities.eligibility import CandidateConstraints, evaluate_applicability


AUDITED_FIELDS = (
    "decision",
    "live_status",
    "opportunity_type",
    "technical_track",
    "workplace_scope",
    "india_eligible",
    "paid_status",
    "hard_blockers",
    "safety_blockers",
)


@dataclass(frozen=True)
class ApplicabilityHarnessResult:
    cases: int
    exact_cases: int
    field_checks: int
    matching_fields: int
    mismatches: list[dict]

    @property
    def field_accuracy(self) -> float:
        return self.matching_fields / self.field_checks if self.field_checks else 0.0


def evaluate_cases(cases: list[OpportunityCase]) -> ApplicabilityHarnessResult:
    mismatches: list[dict] = []
    matching_fields = 0
    exact_cases = 0
    for case in cases:
        candidate = CandidateConstraints(**{
            key: value for key, value in {**PILOT_CANDIDATE, **case.candidate}.items()
            if key in CandidateConstraints.model_fields
        })
        decision = evaluate_applicability(
            title=str(case.posting["title"]),
            description=str(case.posting["description"]),
            location=str(case.posting["location"]),
            candidate=candidate,
            source_observed_active=True,
        ).model_dump(mode="json")
        case_mismatches: dict[str, dict] = {}
        for field in AUDITED_FIELDS:
            actual = decision[field]
            expected = case.expected[field]
            if field in {"hard_blockers", "safety_blockers"}:
                actual = sorted(actual)
                expected = sorted(expected)
            if actual == expected:
                matching_fields += 1
            else:
                case_mismatches[field] = {"expected": expected, "actual": actual}
        if case_mismatches:
            mismatches.append({"case_id": case.id, "fields": case_mismatches})
        else:
            exact_cases += 1
    return ApplicabilityHarnessResult(
        cases=len(cases),
        exact_cases=exact_cases,
        field_checks=len(cases) * len(AUDITED_FIELDS),
        matching_fields=matching_fields,
        mismatches=mismatches,
    )


def main() -> int:
    result = evaluate_cases(load_opportunity_cases())
    print(f"Exact cases: {result.exact_cases}/{result.cases}")
    print(f"Field accuracy: {result.matching_fields}/{result.field_checks} ({result.field_accuracy:.1%})")
    if result.mismatches:
        print(json.dumps(result.mismatches, indent=2, ensure_ascii=False))
    return 0 if not result.mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
