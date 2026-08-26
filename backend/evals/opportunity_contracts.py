"""Contracts and validation for the Phase-0 opportunity evaluation corpus.

This module measures whether the evidence set is ready; it does not implement
production opportunity decisions.  Keeping those concerns separate prevents a
classifier from grading fixtures that were shaped around its own behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CASES_DIR = Path(__file__).parent / "opportunity_cases"

VALID_CATEGORIES = {
    "india_internship",
    "india_early_career",
    "remote_india_eligible",
    "remote_india_ineligible",
    "seniority_trap",
    "non_technical",
    "closed_or_ambiguous",
    "unsafe",
    "duplicate",
}
VALID_DECISIONS = {"apply_now", "strong_stretch", "needs_review", "skip"}
VALID_LIVE_STATUSES = {"active", "closed", "expired", "unknown"}
VALID_OPPORTUNITY_TYPES = {
    "internship",
    "new_grad",
    "entry_level_full_time",
    "stretch_full_time",
    "other",
}
VALID_WORKPLACE_SCOPES = {
    "india_onsite",
    "india_hybrid",
    "india_remote",
    "worldwide_remote",
    "region_remote",
    "restricted_remote",
    "outside_india_onsite",
    "unknown",
}
VALID_PAID_STATUSES = {"paid", "unpaid", "unknown", "suspicious"}
VALID_REVIEW_STATUSES = {"unreviewed", "single_review", "double_review"}
VALID_FIXTURE_KINDS = {"synthetic", "public_snapshot"}

PILOT_CANDIDATE: dict[str, Any] = {
    "home_country": "IN",
    "timezone": "Asia/Kolkata",
    "graduation_year": 2027,
    "currently_enrolled": True,
    "accepted_india_cities": ["Bengaluru", "Hyderabad", "Pune", "Gurugram", "Noida", "Chennai", "Mumbai"],
    "allowed_workplaces": ["india_onsite", "india_hybrid", "india_remote", "worldwide_remote"],
    "desired_opportunity_types": ["internship", "new_grad", "entry_level_full_time", "stretch_full_time"],
    "desired_tracks": ["software", "backend", "frontend", "fullstack", "ai_ml", "data", "cloud_devops", "security"],
    "allow_unpaid": False,
    "allow_bond": False,
}


def _required_mapping(raw: dict[str, Any], key: str, *, source: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{source}: {key} must be an object")
    return value


def _required_text(raw: dict[str, Any], key: str, *, source: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise ValueError(f"{source}: {key} is required")
    return value


def _enum(raw: dict[str, Any], key: str, allowed: set[str], *, source: str) -> str:
    value = _required_text(raw, key, source=source)
    if value not in allowed:
        raise ValueError(f"{source}: {key}={value!r}; expected one of {sorted(allowed)}")
    return value


def _string_list(raw: dict[str, Any], key: str, *, source: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{source}: {key} must be a string array")
    return tuple(item.strip() for item in value if item.strip())


@dataclass(frozen=True)
class OpportunityCase:
    id: str
    category: str
    candidate: dict[str, Any]
    posting: dict[str, Any]
    expected: dict[str, Any]
    provenance: dict[str, Any]
    invariant: bool
    note: str

    @staticmethod
    def from_raw(raw: dict[str, Any], *, source: str) -> OpportunityCase:
        case_id = _required_text(raw, "id", source=source)
        category = _enum(raw, "category", VALID_CATEGORIES, source=source)

        candidate_overrides = raw.get("candidate") or {}
        if not isinstance(candidate_overrides, dict):
            raise ValueError(f"{source}: candidate must be an object")
        candidate = {**PILOT_CANDIDATE, **candidate_overrides}
        if str(candidate.get("home_country") or "").upper() != "IN":
            raise ValueError(f"{source}: Phase-0 pilot candidate home_country must be IN")
        if not isinstance(candidate.get("graduation_year"), int):
            raise ValueError(f"{source}: candidate.graduation_year must be an integer")

        posting = _required_mapping(raw, "posting", source=source)
        for key in ("title", "company", "url", "source", "description", "location", "observed_at"):
            _required_text(posting, key, source=f"{source}:posting")

        expected = _required_mapping(raw, "expected", source=source)
        expected_normalized = {
            **expected,
            "decision": _enum(expected, "decision", VALID_DECISIONS, source=f"{source}:expected"),
            "live_status": _enum(expected, "live_status", VALID_LIVE_STATUSES, source=f"{source}:expected"),
            "opportunity_type": _enum(
                expected, "opportunity_type", VALID_OPPORTUNITY_TYPES, source=f"{source}:expected"
            ),
            "workplace_scope": _enum(
                expected, "workplace_scope", VALID_WORKPLACE_SCOPES, source=f"{source}:expected"
            ),
            "paid_status": _enum(expected, "paid_status", VALID_PAID_STATUSES, source=f"{source}:expected"),
            "hard_blockers": _string_list(expected, "hard_blockers", source=f"{source}:expected"),
            "safety_blockers": _string_list(expected, "safety_blockers", source=f"{source}:expected"),
        }
        if not isinstance(expected.get("india_eligible"), bool):
            raise ValueError(f"{source}:expected: india_eligible must be boolean")
        expected_normalized["india_eligible"] = expected["india_eligible"]
        _required_text(expected, "technical_track", source=f"{source}:expected")

        provenance = _required_mapping(raw, "provenance", source=source)
        fixture_kind = _enum(provenance, "fixture_kind", VALID_FIXTURE_KINDS, source=f"{source}:provenance")
        review_status = _enum(
            provenance, "review_status", VALID_REVIEW_STATUSES, source=f"{source}:provenance"
        )
        _required_text(provenance, "captured_at", source=f"{source}:provenance")
        if fixture_kind == "public_snapshot":
            _required_text(provenance, "source_url", source=f"{source}:provenance")
        if review_status == "double_review":
            reviewers = _string_list(provenance, "reviewers", source=f"{source}:provenance")
            if len(set(reviewers)) < 2:
                raise ValueError(f"{source}:provenance: double_review requires two distinct reviewers")

        return OpportunityCase(
            id=case_id,
            category=category,
            candidate=candidate,
            posting=dict(posting),
            expected=expected_normalized,
            provenance=dict(provenance),
            invariant=bool(raw.get("invariant", False)),
            note=str(raw.get("note") or ""),
        )


def load_opportunity_cases(cases_dir: Path = CASES_DIR) -> list[OpportunityCase]:
    cases: list[OpportunityCase] = []
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
            if not isinstance(raw, dict):
                raise ValueError(f"{source}: case must be a JSON object")
            case = OpportunityCase.from_raw(raw, source=source)
            if case.id in seen_ids:
                raise ValueError(f"{source}: duplicate case id {case.id!r}")
            seen_ids.add(case.id)
            cases.append(case)
    return cases


@dataclass(frozen=True)
class CorpusReadiness:
    total: int
    public_snapshots: int
    double_reviewed: int
    invariants: int
    by_category: dict[str, int]
    gaps: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.gaps


TARGET_CATEGORY_COUNTS = {
    "india_internship": 60,
    "india_early_career": 50,
    "remote_india_eligible": 40,
    "remote_india_ineligible": 35,
    "seniority_trap": 30,
    "non_technical": 25,
    "closed_or_ambiguous": 25,
    "unsafe": 20,
    "duplicate": 15,
}


def corpus_readiness(cases: list[OpportunityCase]) -> CorpusReadiness:
    by_category = {category: 0 for category in VALID_CATEGORIES}
    for case in cases:
        by_category[case.category] += 1
    public_snapshots = sum(1 for case in cases if case.provenance.get("fixture_kind") == "public_snapshot")
    double_reviewed = sum(1 for case in cases if case.provenance.get("review_status") == "double_review")
    invariants = sum(1 for case in cases if case.invariant)
    gaps: list[str] = []
    for category, target in TARGET_CATEGORY_COUNTS.items():
        current = by_category.get(category, 0)
        if current < target:
            gaps.append(f"{category}: {current}/{target}")
    if public_snapshots < 200:
        gaps.append(f"public snapshots: {public_snapshots}/200")
    if double_reviewed < 300:
        gaps.append(f"double reviewed: {double_reviewed}/300")
    if invariants < 10:
        gaps.append(f"invariants: {invariants}/10")
    return CorpusReadiness(
        total=len(cases),
        public_snapshots=public_snapshots,
        double_reviewed=double_reviewed,
        invariants=invariants,
        by_category=by_category,
        gaps=tuple(gaps),
    )
