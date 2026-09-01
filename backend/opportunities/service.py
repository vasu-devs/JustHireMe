from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
from collections import Counter
from datetime import datetime, timezone

from core.errors import ConflictError, NotFoundError, UnprocessableError, ValidationError
from data.repository import Repository
from opportunities.eligibility import Decision
from opportunities.eligibility import CandidateConstraints
from opportunities.orchestrator import OPPORTUNITY_SCANS
from opportunities.rescore import rescore_existing
from opportunities.paid_sources import PAID_PROVIDERS, redacted_provider_status
from catalog.market_registry import production_market_targets


_SAFE_ID = re.compile(r"^[a-zA-Z0-9_.:\-]{1,240}$")
_VALID_DECISIONS = {decision.value for decision in Decision}
_VALID_OUTCOME_EVENTS = {
    "application_started", "application_submitted", "outreach_sent", "recruiter_reply",
    "screening", "technical_assessment", "interview", "rejected", "offer",
    "withdrawn", "skipped",
}
_OUTCOME_LEAD_STATUS = {
    "application_started": "tailoring",
    "application_submitted": "applied",
    "screening": "interviewing",
    "technical_assessment": "interviewing",
    "interview": "interviewing",
    "rejected": "rejected",
    "offer": "offer",
    "withdrawn": "discarded",
    "skipped": "discarded",
}


def _safe_id(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not _SAFE_ID.fullmatch(normalized):
        raise ValidationError(f"Invalid {label}")
    return normalized


def _tracking_job_id(candidate_id: str, opportunity_id: str) -> str:
    digest = hashlib.sha256(f"{candidate_id}|{opportunity_id}".encode()).hexdigest()[:24]
    return f"opptrack_{digest}"


def _occurred_at(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError("Invalid outcome timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _card(row: dict) -> dict:
    opportunity = row["opportunity"]
    applicability = row["applicability"]
    observations = opportunity.get("observations") or []
    providers = sorted({str(record.get("provider") or "unknown") for record in observations})
    return {
        "opportunity_id": opportunity.get("opportunity_id"),
        "employer_name": opportunity.get("employer_name"),
        "title": opportunity.get("title"),
        "location_text": opportunity.get("location_text"),
        "canonical_apply_url": opportunity.get("canonical_apply_url"),
        "lifecycle": opportunity.get("lifecycle"),
        "source_count": len(observations),
        "providers": providers,
        "applicability": applicability,
        "updated_at": row.get("updated_at"),
    }


class OpportunityService:
    def __init__(self, repo: Repository, profile_parser=None) -> None:
        self._repo = repo
        self._profile_parser = profile_parser

    async def list_queue(
        self,
        *,
        candidate_id: str,
        decision: str = "",
        limit: int = 100,
    ) -> list[dict]:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        decision = str(decision or "").strip().lower()
        if decision and decision not in _VALID_DECISIONS:
            raise ValidationError("Invalid opportunity decision")
        rows = await asyncio.to_thread(
            self._repo.opportunities.list_candidate_opportunities,
            candidate_id,
            decision=decision,
            limit=max(1, min(int(limit or 100), 500)),
        )
        cards = [_card(row) for row in rows]
        return sorted(
            cards,
            key=lambda card: (
                -int(card.get("applicability", {}).get("priority_score", 0) or 0),
                str(card.get("employer_name") or "").lower(),
                str(card.get("title") or "").lower(),
            ),
        )

    async def get_detail(self, *, candidate_id: str, opportunity_id: str) -> dict:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        opportunity_id = _safe_id(opportunity_id, "opportunity ID")
        row = await asyncio.to_thread(
            self._repo.opportunities.get_candidate_opportunity,
            candidate_id,
            opportunity_id,
        )
        if not row:
            raise NotFoundError("Opportunity not found")
        return row

    async def get_candidate(self, *, candidate_id: str) -> dict:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        payload = await asyncio.to_thread(self._repo.opportunities.get_candidate_profile, candidate_id)
        if not payload:
            payload = CandidateConstraints(candidate_id=candidate_id).model_dump(mode="json")
        return CandidateConstraints.model_validate({**payload, "candidate_id": candidate_id}).model_dump(mode="json")

    async def save_candidate(self, *, candidate_id: str, payload: dict) -> dict:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        candidate = CandidateConstraints.model_validate({**payload, "candidate_id": candidate_id})
        data = candidate.model_dump(mode="json")
        saved = await asyncio.to_thread(self._repo.opportunities.save_candidate_profile, candidate_id, data)
        decision_counts = await asyncio.to_thread(rescore_existing, self._repo, candidate)
        return {**saved, "decision_counts": decision_counts}

    async def _require_candidate_consent(self, candidate_id: str) -> CandidateConstraints:
        profile = await self.get_candidate(candidate_id=candidate_id)
        candidate = CandidateConstraints.model_validate(profile)
        if candidate.consent_confirmed_at is None:
            raise UnprocessableError(
                "Record this candidate's consent to local processing before scanning or applying"
            )
        return candidate

    async def list_candidates(self) -> list[dict]:
        profiles = await asyncio.to_thread(self._repo.opportunities.list_candidate_profiles)
        candidates: list[dict] = []
        for payload in profiles:
            updated_at = str(payload.get("profile_updated_at") or "")
            candidate_payload = dict(payload)
            candidate_payload.pop("profile_updated_at", None)
            try:
                candidate = CandidateConstraints.model_validate(candidate_payload)
            except Exception:
                continue
            application_status = await asyncio.to_thread(
                self._repo.opportunities.candidate_application_profile_status,
                candidate.candidate_id,
            )
            consented = candidate.consent_confirmed_at is not None
            application_ready = bool(application_status.get("ready"))
            candidates.append({
                "candidate_id": candidate.candidate_id,
                "graduation_year": candidate.graduation_year,
                "preferred_technical_tracks": [track.value for track in candidate.preferred_technical_tracks],
                "accepted_opportunity_types": [kind.value for kind in candidate.accepted_opportunity_types],
                "consent_confirmed_at": (
                    candidate.consent_confirmed_at.isoformat() if candidate.consent_confirmed_at else None
                ),
                "application_profile_ready": application_ready,
                "pilot_ready": consented and application_ready,
                "auto_apply_enabled": candidate.auto_apply_enabled,
                "auto_apply_confirmed_at": (
                    candidate.auto_apply_confirmed_at.isoformat()
                    if candidate.auto_apply_confirmed_at else None
                ),
                "auto_apply_minimum_fit_score": candidate.auto_apply_minimum_fit_score,
                "auto_apply_daily_limit": candidate.auto_apply_daily_limit,
                "profile_updated_at": updated_at,
            })
        return candidates

    async def application_profile_status(self, *, candidate_id: str) -> dict:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        return await asyncio.to_thread(
            self._repo.opportunities.candidate_application_profile_status,
            candidate_id,
        )

    @staticmethod
    def _profile_preview(candidate_id: str, profile: dict) -> dict:
        name = str(profile.get("n") or "").strip()
        summary = str(profile.get("s") or "").strip()
        counts = {
            "skill_count": len(profile.get("skills") or []),
            "project_count": len(profile.get("projects") or []),
            "experience_count": len(profile.get("exp") or []),
            "education_count": len(profile.get("education") or []),
        }
        evidence_count = sum(
            len(profile.get(key) or [])
            for key in ("skills", "projects", "exp", "education", "certifications", "achievements")
        )
        if not name or not summary or evidence_count == 0:
            raise UnprocessableError(
                "Complete the current Profile workspace before linking it to this candidate"
            )
        payload_json = json.dumps(profile, ensure_ascii=False, sort_keys=True, default=str)
        if len(payload_json.encode()) > 2 * 1024 * 1024:
            raise UnprocessableError("Candidate application profile is too large")
        return {
            "candidate_id": candidate_id,
            "ready": True,
            "profile_name": name,
            "summary_preview": summary[:160],
            "evidence_count": evidence_count,
            "payload_sha256": hashlib.sha256(payload_json.encode()).hexdigest(),
            **counts,
        }

    @staticmethod
    def _candidate_identity(profile: dict, identity: dict) -> dict:
        normalized = {
            key: str(identity.get(key) or "").strip()
            for key in (
                "email", "phone", "linkedin_url", "github_url", "website_url", "city"
            )
        }
        missing = [key for key in ("email", "phone") if not normalized[key]]
        if missing:
            raise UnprocessableError(
                "Candidate contact identity requires: " + ", ".join(missing)
            )
        if not re.fullmatch(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", normalized["email"]):
            raise UnprocessableError("Candidate contact email is invalid")
        if len(re.sub(r"\D", "", normalized["phone"])) < 7:
            raise UnprocessableError("Candidate contact phone is invalid")
        return normalized

    async def preview_candidate_resume(self, *, candidate_id: str, document_path: str) -> dict:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        await self._require_candidate_consent(candidate_id)
        if self._profile_parser is None or not hasattr(self._profile_parser, "parse_resume"):
            raise UnprocessableError("Candidate resume parsing is unavailable")
        profile = await self._profile_parser.parse_resume("", document_path)
        if not isinstance(profile, dict):
            raise UnprocessableError("Candidate resume did not produce a usable profile")
        return {**self._profile_preview(candidate_id, profile), "profile": profile}

    async def confirm_candidate_resume(
        self,
        *,
        candidate_id: str,
        profile: dict,
        identity: dict,
        expected_payload_sha256: str,
    ) -> dict:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        await self._require_candidate_consent(candidate_id)
        preview = self._profile_preview(candidate_id, profile)
        expected = str(expected_payload_sha256 or "").strip().lower()
        if not hmac.compare_digest(expected, preview["payload_sha256"]):
            raise ConflictError("The parsed resume changed after review; upload and review it again")
        candidate_profile = {
            **profile,
            "identity": self._candidate_identity(profile, identity),
        }
        return await asyncio.to_thread(
            self._repo.opportunities.save_candidate_application_profile,
            candidate_id,
            candidate_profile,
            source=f"confirmed_candidate_resume:{expected[:12]}",
        )

    async def preview_application_profile(self, *, candidate_id: str) -> dict:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        await self._require_candidate_consent(candidate_id)
        profile = await asyncio.to_thread(self._repo.profile.get_profile)
        if not isinstance(profile, dict):
            raise UnprocessableError("The current Profile workspace is unavailable")
        return self._profile_preview(candidate_id, profile)

    async def snapshot_application_profile(
        self,
        *,
        candidate_id: str,
        identity: dict,
        expected_payload_sha256: str,
    ) -> dict:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        await self._require_candidate_consent(candidate_id)
        profile = await asyncio.to_thread(self._repo.profile.get_profile)
        if not isinstance(profile, dict):
            raise UnprocessableError("The current Profile workspace is unavailable")
        preview = self._profile_preview(candidate_id, profile)
        expected = str(expected_payload_sha256 or "").strip().lower()
        if not hmac.compare_digest(expected, preview["payload_sha256"]):
            raise ConflictError(
                "The current Profile changed after review; review it again before linking"
            )
        candidate_profile = {
            **profile,
            "identity": self._candidate_identity(profile, identity),
        }
        return await asyncio.to_thread(
            self._repo.opportunities.save_candidate_application_profile,
            candidate_id,
            candidate_profile,
            source=f"confirmed_profile_snapshot:{expected[:12]}",
        )

    async def start_scan(
        self,
        *,
        candidate_id: str,
        target_limit: int,
        max_concurrency: int,
        notify=None,
    ) -> dict:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        candidate = await self._require_candidate_consent(candidate_id)
        result = await OPPORTUNITY_SCANS.start(
            repo=self._repo,
            candidate=candidate,
            target_limit=target_limit,
            max_concurrency=max_concurrency,
            notify=notify,
        )
        if not result.get("started"):
            active_candidate = str(result.get("candidate_id") or "another candidate")
            raise ConflictError(f"An opportunity scan is already running for {active_candidate}")
        return result

    async def scan_status(self, *, candidate_id: str) -> dict:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        return await OPPORTUNITY_SCANS.status(candidate_id=candidate_id, repo=self._repo)

    async def provider_status(self) -> dict:
        """Paid-source readiness and yield telemetry, with no credential values."""
        cfg = await asyncio.to_thread(self._repo.settings.get_settings)
        usage_rows = await asyncio.gather(*(
            asyncio.to_thread(self._repo.paid_sources.provider_usage, provider)
            for provider in PAID_PROVIDERS
        ))
        providers = [
            redacted_provider_status(provider, cfg, usage)
            for provider, usage in zip(PAID_PROVIDERS, usage_rows, strict=True)
        ]
        return {
            "master_enabled": str(cfg.get("paid_sources_enabled") or "false").lower() == "true",
            "providers": providers,
            "secrets_redacted": True,
            "retention_rule": "Retain after >=10 successful requests only when net-new eligible yield is >=10%.",
        }

    async def coverage_status(self, *, candidate_id: str) -> dict:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        targets = production_market_targets(company_limit=500)
        inventory_by_provider = Counter(target.provider for target in targets)
        health_rows = await asyncio.to_thread(
            self._repo.opportunities.list_candidate_source_health,
            candidate_id,
        )
        index_status = await asyncio.to_thread(
            self._repo.opportunities.get_public_index_status,
        )
        status_counts = Counter(str(row.get("status") or "unknown") for row in health_rows)
        attempted_ids = {str(row.get("target_id") or "") for row in health_rows}
        latest_attempted_at = max(
            (str(row.get("attempted_at") or "") for row in health_rows),
            default="",
        )
        provider_health: dict[str, dict[str, int]] = {}
        for row in health_rows:
            provider = str(row.get("provider") or "unknown")
            bucket = provider_health.setdefault(provider, {
                "targets": 0,
                "success": 0,
                "zero_result": 0,
                "failure": 0,
                "raw_rows": 0,
                "accepted_source_records": 0,
            })
            bucket["targets"] += 1
            status = str(row.get("status") or "")
            if status in {"success", "zero_result", "failure"}:
                bucket[status] += 1
            elif status in {"config_error", "budget_exhausted"}:
                bucket["failure"] += 1
            bucket["raw_rows"] += int(row.get("raw_rows") or 0)
            bucket["accepted_source_records"] += int(row.get("accepted_source_records") or 0)
        return {
            "candidate_id": candidate_id,
            "inventory_target_count": len(targets),
            "inventory_provider_count": len(inventory_by_provider),
            "inventory_by_provider": dict(sorted(inventory_by_provider.items())),
            "attempted_target_count": len(attempted_ids),
            "unattempted_target_count": max(0, len(targets) - len(attempted_ids)),
            "health_counts": dict(sorted(status_counts.items())),
            "provider_health": provider_health,
            "raw_rows": sum(int(row.get("raw_rows") or 0) for row in health_rows),
            "accepted_source_records": sum(
                int(row.get("accepted_source_records") or 0) for row in health_rows
            ),
            "latest_attempted_at": latest_attempted_at or None,
            "paid_provider_count": len(PAID_PROVIDERS),
            "index": index_status,
        }

    async def track_application(self, *, candidate_id: str, opportunity_id: str) -> dict:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        opportunity_id = _safe_id(opportunity_id, "opportunity ID")
        await self._require_candidate_consent(candidate_id)
        application_status = await self.application_profile_status(candidate_id=candidate_id)
        if not application_status.get("ready"):
            raise UnprocessableError(
                "Link a complete application profile before adding opportunities to the pipeline"
            )
        row = await self.get_detail(candidate_id=candidate_id, opportunity_id=opportunity_id)
        applicability = row.get("applicability") or {}
        if applicability.get("decision") == Decision.SKIP.value:
            raise UnprocessableError("Skipped opportunities cannot enter the application pipeline")
        opportunity = row.get("opportunity") or {}
        observations = opportunity.get("observations") or []
        primary = max(
            observations,
            key=lambda record: (
                str(record.get("source_kind") or "") in {"ats", "direct_employer"},
                len(str(record.get("description_full") or "")),
            ),
            default={},
        )
        job_id = _tracking_job_id(candidate_id, opportunity_id)
        lead = {
            "job_id": job_id,
            "title": opportunity.get("title") or "Opportunity",
            "company": opportunity.get("employer_name") or "Unknown employer",
            "url": opportunity.get("canonical_apply_url") or primary.get("apply_url") or primary.get("source_url") or "",
            "platform": primary.get("provider") or "opportunity",
            "description": primary.get("description_full") or "",
            "location": opportunity.get("location_text") or "",
            "kind": "job",
            "signal_score": int(applicability.get("priority_score") or 0),
            "signal_reason": "Candidate-verified opportunity queue",
            "source_meta": {
                "candidate_id": candidate_id,
                "opportunity_id": opportunity_id,
                "applicability": applicability,
            },
        }
        await asyncio.to_thread(self._repo.leads.save_lead, lead)
        await asyncio.to_thread(self._repo.opportunities.link_lead_to_opportunity, job_id, opportunity_id)
        await asyncio.to_thread(
            self._repo.opportunities.record_candidate_event,
            candidate_id,
            opportunity_id,
            "tracked",
            occurred_at=datetime.now(timezone.utc).isoformat(),
            lead_id=job_id,
            idempotency_key="pipeline-track",
        )
        saved = await asyncio.to_thread(self._repo.leads.get_lead_by_id, job_id)
        return saved or {**lead, "opportunity_id": opportunity_id, "status": "discovered"}

    async def record_outcome(
        self,
        *,
        candidate_id: str,
        opportunity_id: str,
        event_type: str,
        occurred_at: str = "",
        note: str = "",
        idempotency_key: str = "",
    ) -> dict:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        opportunity_id = _safe_id(opportunity_id, "opportunity ID")
        await self._require_candidate_consent(candidate_id)
        event_type = str(event_type or "").strip().lower()
        if event_type not in _VALID_OUTCOME_EVENTS:
            raise ValidationError("Invalid opportunity outcome")
        row = await self.get_detail(candidate_id=candidate_id, opportunity_id=opportunity_id)
        decision = str((row.get("applicability") or {}).get("decision") or "")
        if decision == Decision.SKIP.value and event_type != "skipped":
            raise UnprocessableError("Skipped opportunities cannot record application outcomes")

        job_id = _tracking_job_id(candidate_id, opportunity_id)
        lead = await asyncio.to_thread(self._repo.leads.get_lead_by_id, job_id)
        if not lead and event_type != "skipped":
            lead = await self.track_application(candidate_id=candidate_id, opportunity_id=opportunity_id)
        event = await asyncio.to_thread(
            self._repo.opportunities.record_candidate_event,
            candidate_id,
            opportunity_id,
            event_type,
            occurred_at=_occurred_at(occurred_at),
            lead_id=job_id if lead else "",
            note=str(note or "").strip()[:1000],
            idempotency_key=str(idempotency_key or "").strip(),
        )
        target_status = _OUTCOME_LEAD_STATUS.get(event_type)
        if lead and target_status:
            await asyncio.to_thread(self._repo.leads.update_lead_status, job_id, target_status)
        return event

    async def list_events(
        self,
        *,
        candidate_id: str,
        opportunity_id: str = "",
        limit: int = 500,
    ) -> list[dict]:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        if opportunity_id:
            opportunity_id = _safe_id(opportunity_id, "opportunity ID")
        return await asyncio.to_thread(
            self._repo.opportunities.list_candidate_events,
            candidate_id,
            opportunity_id=opportunity_id,
            limit=max(1, min(int(limit or 500), 2000)),
        )

    async def funnel_metrics(self, *, candidate_id: str) -> dict:
        candidate_id = _safe_id(candidate_id, "candidate ID")
        return await asyncio.to_thread(self._repo.opportunities.candidate_funnel_metrics, candidate_id)

    async def cohort_metrics(self) -> dict:
        saved_candidates = await self.list_candidates()
        candidates = [candidate for candidate in saved_candidates if candidate.get("pilot_ready")]
        candidate_metrics = [
            await asyncio.to_thread(self._repo.opportunities.candidate_funnel_metrics, row["candidate_id"])
            for row in candidates
        ]
        funnel_keys = (
            "tracked", "application_started", "application_submitted", "outreach_sent",
            "meaningful_contacts", "screening_processes", "interviews", "offers",
            "rejections", "withdrawn",
        )
        funnel = {
            key: sum(int(item.get("funnel", {}).get(key) or 0) for item in candidate_metrics)
            for key in funnel_keys
        }
        submitted = funnel["application_submitted"]
        traction_candidates = sum(
            int(item.get("funnel", {}).get("meaningful_contacts") or 0) > 0
            for item in candidate_metrics
        )
        rates = {
            "meaningful_contacts_per_20_applications": round(20 * funnel["meaningful_contacts"] / submitted, 2) if submitted else 0.0,
            "interviews_per_20_applications": round(20 * funnel["interviews"] / submitted, 2) if submitted else 0.0,
            "offers_per_20_applications": round(20 * funnel["offers"] / submitted, 2) if submitted else 0.0,
        }
        targets = {
            "candidate_count": 5,
            "application_submitted": 100,
            "meaningful_contacts": 10,
            "interviews": 5,
            "candidates_with_traction": 3,
            "stretch_offers": 1,
        }
        return {
            "candidate_count": len(candidates),
            "saved_candidate_count": len(saved_candidates),
            "pending_candidate_count": len(saved_candidates) - len(candidates),
            "candidates": candidate_metrics,
            "funnel": funnel,
            "rates": rates,
            "candidates_with_traction": traction_candidates,
            "targets": targets,
            "progress_percent": {
                "candidate_count": min(100.0, round(100 * len(candidates) / targets["candidate_count"], 1)),
                "application_submitted": min(100.0, round(100 * submitted / targets["application_submitted"], 1)),
                "meaningful_contacts": min(100.0, round(100 * funnel["meaningful_contacts"] / targets["meaningful_contacts"], 1)),
                "interviews": min(100.0, round(100 * funnel["interviews"] / targets["interviews"], 1)),
                "candidates_with_traction": min(100.0, round(100 * traction_candidates / targets["candidates_with_traction"], 1)),
            },
        }


def create_opportunity_service(repo: Repository, profile_parser=None) -> OpportunityService:
    return OpportunityService(repo, profile_parser)
