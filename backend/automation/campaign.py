"""End-to-end candidate opportunity auto-apply orchestration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from automation.policy import assess_auto_apply
from automation.service import AutomationService
from data.repository import Repository
from generation.service import GenerationService


_INFLIGHT: set[str] = set()
_INFLIGHT_LOCK = asyncio.Lock()


class AutoApplyCampaignService:
    def __init__(
        self,
        repo: Repository,
        opportunities,
        generation: GenerationService,
        automation: AutomationService,
    ) -> None:
        self.repo = repo
        self.opportunities = opportunities
        self.generation = generation
        self.automation = automation

    async def _policy(self, candidate_id: str, opportunity_id: str) -> tuple[dict, dict, dict]:
        candidate = await asyncio.to_thread(
            self.repo.opportunities.get_candidate_profile, candidate_id
        )
        row = await self.opportunities.get_detail(
            candidate_id=candidate_id, opportunity_id=opportunity_id
        )
        status = await self.opportunities.application_profile_status(candidate_id=candidate_id)
        events = await asyncio.to_thread(
            self.repo.opportunities.list_candidate_events,
            candidate_id,
            limit=2000,
        )
        opportunity = row.get("opportunity") or {}
        applicability = row.get("applicability") or {}
        policy = assess_auto_apply(
            candidate or {},
            opportunity,
            applicability,
            events,
            application_profile_ready=bool(status.get("ready")),
        ).as_dict()
        return policy, opportunity, applicability

    async def _record_audit(
        self,
        candidate_id: str,
        opportunity_id: str,
        event_type: str,
        *,
        lead_id: str = "",
        note: str,
        metadata: dict,
    ) -> dict:
        return await asyncio.to_thread(
            self.repo.opportunities.record_candidate_event,
            candidate_id,
            opportunity_id,
            event_type,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            lead_id=lead_id,
            note=note,
            metadata=metadata,
        )

    async def apply(self, *, candidate_id: str, opportunity_id: str) -> dict:
        key = candidate_id
        async with _INFLIGHT_LOCK:
            if key in _INFLIGHT:
                return {
                    "status": "already_running",
                    "candidate_id": candidate_id,
                    "opportunity_id": opportunity_id,
                    "blockers": ["another auto-apply attempt is already running for this candidate"],
                }
            _INFLIGHT.add(key)

        try:
            policy, _opportunity, _applicability = await self._policy(candidate_id, opportunity_id)
            if not policy["allowed"]:
                await self._record_audit(
                    candidate_id,
                    opportunity_id,
                    "auto_apply_blocked",
                    note="Auto-apply policy blocked submission",
                    metadata={"blockers": policy["blockers"], "warnings": policy["warnings"]},
                )
                return {
                    "status": "blocked",
                    "candidate_id": candidate_id,
                    "opportunity_id": opportunity_id,
                    **policy,
                }

            lead = await self.opportunities.track_application(
                candidate_id=candidate_id, opportunity_id=opportunity_id
            )
            if lead.get("status") == "applied":
                await self._record_audit(
                    candidate_id,
                    opportunity_id,
                    "auto_apply_blocked",
                    lead_id=lead.get("job_id", ""),
                    note="Auto-apply found an application already marked submitted",
                    metadata={"blockers": ["application is already marked submitted"]},
                )
                return {
                    "status": "blocked",
                    "candidate_id": candidate_id,
                    "opportunity_id": opportunity_id,
                    "blockers": ["application is already marked submitted"],
                    "warnings": policy["warnings"],
                }

            asset = lead.get("resume_asset") or lead.get("asset") or ""
            cover = lead.get("cover_letter_asset") or ""
            if not asset or not cover:
                package = await self.generation.generate_package(lead)
                await asyncio.to_thread(
                    self.repo.leads.save_asset_package,
                    lead["job_id"],
                    package["resume"],
                    package["cover_letter"],
                    package.get("selected_projects", []),
                    package.get("keyword_coverage", {}),
                )

            lead, asset = await self.automation.get_lead_for_fire(lead["job_id"])
            preview = await self.automation.preview_application(lead, asset)
            if not preview.get("ready_to_submit"):
                preflight = {
                    key: preview.get(key, [])
                    for key in (
                        "fields_filled", "required_unfilled", "sensitive_questions",
                        "page_blockers", "resume_uploaded", "submit_found",
                    )
                }
                await self._record_audit(
                    candidate_id,
                    opportunity_id,
                    "auto_apply_needs_review",
                    lead_id=lead["job_id"],
                    note="Auto-apply form preflight requires manual review",
                    metadata=preflight,
                )
                return {
                    "status": "needs_review",
                    "candidate_id": candidate_id,
                    "opportunity_id": opportunity_id,
                    "lead_id": lead["job_id"],
                    "warnings": policy["warnings"],
                    "preflight": preflight,
                }

            # Generation and browser preflight can take minutes. Re-read every
            # mutable policy input at the irreversible boundary so a revoked
            # authorization, new duplicate, closed role, or reached daily cap
            # cannot race the final click.
            final_policy, _opportunity, _applicability = await self._policy(
                candidate_id, opportunity_id
            )
            if not final_policy["allowed"]:
                await self._record_audit(
                    candidate_id,
                    opportunity_id,
                    "auto_apply_blocked",
                    lead_id=lead["job_id"],
                    note="Auto-apply policy changed before submission",
                    metadata={
                        "blockers": final_policy["blockers"],
                        "warnings": final_policy["warnings"],
                    },
                )
                return {
                    "status": "blocked",
                    "candidate_id": candidate_id,
                    "opportunity_id": opportunity_id,
                    "lead_id": lead["job_id"],
                    **final_policy,
                }

            await asyncio.to_thread(
                self.repo.opportunities.record_candidate_event,
                candidate_id,
                opportunity_id,
                "application_started",
                occurred_at=datetime.now(timezone.utc).isoformat(),
                lead_id=lead["job_id"],
                note="Auto-apply preflight passed",
                metadata={
                    "mode": "auto_apply",
                    "fields_filled": preview.get("fields_filled", []),
                    "warnings": final_policy["warnings"],
                },
            )
            result = await self.automation.submit_application_result(lead, asset)
            if result.get("status") != "submitted":
                submission = {
                    key: result.get(key)
                    for key in (
                        "ready_to_submit", "required_unfilled", "sensitive_questions",
                        "page_blockers", "confirmation_evidence", "reason",
                    )
                }
                await self._record_audit(
                    candidate_id,
                    opportunity_id,
                    "auto_apply_unconfirmed",
                    lead_id=lead["job_id"],
                    note="Auto-apply did not receive positive employer confirmation",
                    metadata={"status": result.get("status"), **submission},
                )
                return {
                    "status": result.get("status") or "failed",
                    "candidate_id": candidate_id,
                    "opportunity_id": opportunity_id,
                    "lead_id": lead["job_id"],
                    "warnings": final_policy["warnings"],
                    "submission": submission,
                }

            await self.automation.mark_applied(lead["job_id"])
            event = await asyncio.to_thread(
                self.repo.opportunities.record_candidate_event,
                candidate_id,
                opportunity_id,
                "application_submitted",
                occurred_at=datetime.now(timezone.utc).isoformat(),
                lead_id=lead["job_id"],
                note="Submitted by candidate-approved auto-apply",
                metadata={
                    "mode": "auto_apply",
                    "confirmation_evidence": result.get("confirmation_evidence", ""),
                },
                idempotency_key="auto-apply-submitted",
            )
            return {
                "status": "submitted",
                "candidate_id": candidate_id,
                "opportunity_id": opportunity_id,
                "lead_id": lead["job_id"],
                "event_id": event["event_id"],
                "confirmation_evidence": result.get("confirmation_evidence", ""),
                "warnings": final_policy["warnings"],
            }
        finally:
            async with _INFLIGHT_LOCK:
                _INFLIGHT.discard(key)
