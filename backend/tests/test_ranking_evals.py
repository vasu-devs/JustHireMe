"""CI gates over the ranking evaluation harness (``backend/evals/``).

Two gates:

1. **Invariants** — cases flagged ``invariant`` are product guarantees (a nurse
   applying to a nursing job is not floored; a cross-field or seniority mismatch
   stays capped). Any invariant failure fails the build, with a readable diff.
2. **Aggregate floor** — overall accuracy must stay at/above a threshold, so a
   change that quietly regresses several non-invariant cases is caught even if no
   single guarantee breaks.

Run the harness directly for a human report:  ``uv run python -m evals.harness``
"""

from __future__ import annotations

import pytest

from evals.harness import format_report, load_cases, run_evals

# Floor for aggregate pass rate. Cases are calibrated to current engine output,
# so this starts at 1.0; lower it deliberately (with a comment) only if you add
# aspirational cases the engine does not yet satisfy.
ACCURACY_FLOOR = 1.0


def test_eval_dataset_loads() -> None:
    cases = load_cases()
    assert cases, "no eval cases found under evals/cases/*.jsonl"
    # Guard against an accidentally-empty or single-field dataset.
    fields = {c.field for c in cases}
    assert len(fields) >= 4, f"expected several professions in the eval set, got {sorted(fields)}"
    assert any(c.invariant for c in cases), "eval set has no invariant (guarantee) cases"


def test_ranking_eval_invariants_hold() -> None:
    report = run_evals()
    if report.invariant_failures:
        pytest.fail(
            "ranking eval INVARIANT(s) regressed:\n\n" + format_report(report),
            pytrace=False,
        )


def test_ranking_eval_accuracy_floor() -> None:
    report = run_evals()
    assert report.accuracy >= ACCURACY_FLOOR, (
        f"ranking eval accuracy {report.accuracy:.1%} below floor "
        f"{ACCURACY_FLOOR:.0%}\n\n" + format_report(report)
    )
