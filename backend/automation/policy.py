"""Candidate-scoped policy gates for unattended job submission.

The browser actuator is deliberately policy-blind: it can fill a page, but it
must never decide whether a candidate should apply.  This module makes that
decision deterministic and auditable before Chromium or an LLM is invoked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class AutoApplyDecision:
    allowed: bool
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


def _submitted_today(events: list[dict], now: datetime) -> int:
    today = now.astimezone(timezone.utc).date()
    opportunities: set[str] = set()
    for event in events:
        if str(event.get("event_type") or "") != "application_submitted":
            continue
        try:
            occurred = datetime.fromisoformat(
                str(event.get("occurred_at") or "").replace("Z", "+00:00")
            )
        except ValueError:
            continue
        if occurred.astimezone(timezone.utc).date() == today:
            opportunities.add(str(event.get("opportunity_id") or event.get("event_id") or ""))
    return len(opportunities)


def assess_auto_apply(
    candidate: dict,
    opportunity: dict,
    applicability: dict,
    events: list[dict],
    *,
    application_profile_ready: bool,
    already_applied: bool = False,
    now: datetime | None = None,
) -> AutoApplyDecision:
    """Return a default-deny submission decision with human-readable blockers."""

    blockers: list[str] = []
    warnings: list[str] = []
    now = now or datetime.now(timezone.utc)

    if not candidate.get("consent_confirmed_at"):
        blockers.append("candidate processing consent is missing")
    if not candidate.get("auto_apply_enabled"):
        blockers.append("auto-apply is not enabled for this candidate")
    if not candidate.get("auto_apply_confirmed_at"):
        blockers.append("candidate auto-apply confirmation is missing")
    if not application_profile_ready:
        blockers.append("candidate-specific application profile is incomplete")

    lifecycle = opportunity.get("lifecycle") if isinstance(opportunity.get("lifecycle"), dict) else {}
    if str(lifecycle.get("status") or "unknown") != "active":
        blockers.append("opportunity is not verified active")
    if not str(opportunity.get("canonical_apply_url") or "").strip():
        blockers.append("opportunity has no direct application URL")

    decision = str(applicability.get("decision") or "")
    permitted = {"apply_now"}
    if candidate.get("auto_apply_allow_strong_stretch"):
        permitted.add("strong_stretch")
    if decision not in permitted:
        blockers.append(f"decision {decision or 'unknown'} is not eligible for auto-apply")

    if str(applicability.get("eligibility") or "") not in {"eligible", "likely_eligible"}:
        blockers.append("candidate eligibility is unresolved")
    paid_status = str(applicability.get("paid_status") or "")
    if paid_status != "paid":
        blockers.append("compensation is not verified paid")

    for key, label in (
        ("hard_blockers", "eligibility blocker"),
        ("safety_blockers", "safety blocker"),
        ("unknowns", "unresolved job fact"),
    ):
        values = [str(value).strip() for value in applicability.get(key, []) if str(value).strip()]
        if values:
            blockers.append(f"{label}: {values[0]}")

    fit = int(applicability.get("candidate_fit_score") or 0)
    minimum_fit = int(candidate.get("auto_apply_minimum_fit_score") or 80)
    if fit < minimum_fit:
        blockers.append(f"candidate fit {fit} is below auto-apply floor {minimum_fit}")

    if applicability.get("candidate_evidence_missing"):
        blockers.append("candidate evidence is insufficient for truthful tailoring")
    opportunity_id = str(opportunity.get("opportunity_id") or "")
    if already_applied or any(
        str(event.get("event_type") or "") == "application_submitted"
        and str(event.get("opportunity_id") or "") == opportunity_id
        for event in events
    ):
        blockers.append("an application has already been submitted for this opportunity")

    daily_limit = int(candidate.get("auto_apply_daily_limit") or 5)
    submitted_today = _submitted_today(events, now)
    if submitted_today >= daily_limit:
        blockers.append(f"daily auto-apply limit reached ({daily_limit})")

    warnings.extend(
        str(value).strip()
        for value in applicability.get("safety_warnings", [])
        if str(value).strip()
    )
    return AutoApplyDecision(not blockers, tuple(dict.fromkeys(blockers)), tuple(dict.fromkeys(warnings)))
