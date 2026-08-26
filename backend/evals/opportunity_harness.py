"""Human-readable Phase-0 opportunity-corpus readiness report."""

from __future__ import annotations

from evals.opportunity_contracts import corpus_readiness, load_opportunity_cases


def format_readiness() -> str:
    cases = load_opportunity_cases()
    report = corpus_readiness(cases)
    lines = [
        f"Opportunity corpus: {report.total}/300 cases",
        f"Public snapshots: {report.public_snapshots}/200",
        f"Double reviewed: {report.double_reviewed}/300",
        f"Product invariants: {report.invariants}/10",
        "",
        "By category:",
    ]
    for category, count in sorted(report.by_category.items()):
        lines.append(f"  {category:<27} {count}")
    lines.extend(["", "Status: " + ("READY" if report.ready else "NOT READY")])
    if report.gaps:
        lines.append("Outstanding evidence:")
        lines.extend(f"  - {gap}" for gap in report.gaps)
    return "\n".join(lines)


def main() -> int:
    print(format_readiness())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
