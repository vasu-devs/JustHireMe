"""Load, run, and report labeled ranking-evaluation cases.

A *case* is one ``(profile, job description) -> expectation`` example. Expectations
are expressed as a score band (or explicit ``min``/``max``) plus an optional
``capped`` assertion (whether a hard cap — wrong-field / seniority / thin-stack —
should have fired). Cases flagged ``invariant`` are product guarantees: a failure
there is a hard CI failure, not just a metric dip.

The harness is deliberately dependency-light: it calls the public
:func:`ranking.scoring_engine.score_job_lead` exactly as production does, so what
it measures is what ships. The semantic criterion self-disables when the vector
store is absent (as in CI), keeping results deterministic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ranking.scoring_engine import score_job_lead

CASES_DIR = Path(__file__).parent / "cases"

# Readable shorthand for a score range. A case may override either bound with an
# explicit ``min``/``max``. Bands overlap on purpose — "solid" and "strong" both
# mean "a real, tailor-worthy match", they just differ in how strong.
_BANDS: dict[str, tuple[int, int]] = {
    "strong": (68, 100),  # unambiguous, tailor-immediately match
    "solid": (52, 100),   # genuine on-field match with some gaps
    "weak": (30, 74),     # plausible but thin; kept, not auto-tailored
    "reject": (0, 40),    # cross-field / seniority-blown / junk
}


@dataclass(frozen=True)
class Case:
    """One labeled ranking example."""

    id: str
    field: str
    profile: dict[str, Any]
    jd: str
    min_score: int
    max_score: int
    capped: bool | None  # None => don't assert cap state
    invariant: bool
    note: str

    @staticmethod
    def from_raw(raw: dict[str, Any], *, source: str) -> Case:
        if "id" not in raw or "profile" not in raw or "jd" not in raw:
            raise ValueError(f"{source}: case is missing one of id/profile/jd: {raw!r}")
        expect = raw.get("expect") or {}
        band = expect.get("band")
        if band is not None and band not in _BANDS:
            raise ValueError(f"{source}: unknown band {band!r} (known: {sorted(_BANDS)})")
        lo, hi = _BANDS[band] if band else (0, 100)
        return Case(
            id=str(raw["id"]),
            field=str(raw.get("field", "unknown")),
            profile=dict(raw["profile"]),
            jd=str(raw["jd"]),
            min_score=int(expect.get("min", lo)),
            max_score=int(expect.get("max", hi)),
            capped=expect.get("capped"),
            invariant=bool(raw.get("invariant", False)),
            note=str(raw.get("note", "")),
        )


@dataclass(frozen=True)
class CaseResult:
    case: Case
    score: int
    applied_cap: int | None
    failures: list[str]

    @property
    def passed(self) -> bool:
        return not self.failures


def evaluate_case(case: Case) -> CaseResult:
    """Score one case and check it against its expectation."""
    result = score_job_lead(case.jd, case.profile)
    failures: list[str] = []
    if not (case.min_score <= result.score <= case.max_score):
        failures.append(f"score {result.score} outside [{case.min_score}, {case.max_score}]")
    if case.capped is not None:
        was_capped = result.applied_cap is not None
        if was_capped != case.capped:
            failures.append(
                f"capped={was_capped} (cap={result.applied_cap}), expected capped={case.capped}"
            )
    return CaseResult(
        case=case,
        score=result.score,
        applied_cap=result.applied_cap,
        failures=failures,
    )


def load_cases(cases_dir: Path = CASES_DIR) -> list[Case]:
    """Load every case from ``cases_dir/*.jsonl`` (blank lines and ``#`` comments skipped)."""
    cases: list[Case] = []
    seen_ids: set[str] = set()
    for path in sorted(cases_dir.glob("*.jsonl")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            source = f"{path.name}:{line_no}"
            try:
                raw = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{source}: invalid JSON: {exc}") from exc
            case = Case.from_raw(raw, source=source)
            if case.id in seen_ids:
                raise ValueError(f"{source}: duplicate case id {case.id!r}")
            seen_ids.add(case.id)
            cases.append(case)
    return cases


@dataclass(frozen=True)
class Report:
    results: list[CaseResult]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 1.0

    @property
    def failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.passed]

    @property
    def invariant_failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.passed and r.case.invariant]

    def by_field(self) -> dict[str, tuple[int, int]]:
        """Return ``{field: (passed, total)}``."""
        out: dict[str, tuple[int, int]] = {}
        for r in self.results:
            passed, total = out.get(r.case.field, (0, 0))
            out[r.case.field] = (passed + (1 if r.passed else 0), total + 1)
        return out


def run_evals(cases_dir: Path = CASES_DIR) -> Report:
    return Report([evaluate_case(c) for c in load_cases(cases_dir)])


def format_report(report: Report) -> str:
    """Render a human-readable report (used by the CLI)."""
    lines: list[str] = []
    lines.append(
        f"Ranking evals: {report.passed}/{report.total} passed "
        f"({report.accuracy * 100:.1f}%)"
    )
    lines.append("")
    lines.append("By field:")
    for field, (passed, total) in sorted(report.by_field().items()):
        flag = "" if passed == total else "  <-- regressions"
        lines.append(f"  {field:<14} {passed}/{total}{flag}")
    if report.failures:
        lines.append("")
        lines.append("Failures:")
        for r in report.failures:
            tag = "INVARIANT " if r.case.invariant else ""
            lines.append(f"  [{tag}{r.case.field}] {r.case.id} (score={r.score}, cap={r.applied_cap})")
            for reason in r.failures:
                lines.append(f"      - {reason}")
            if r.case.note:
                lines.append(f"      note: {r.case.note}")
    else:
        lines.append("")
        lines.append("All cases passed.")
    return "\n".join(lines)


def main() -> int:
    report = run_evals()
    print(format_report(report))
    return 1 if report.invariant_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
