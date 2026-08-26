"""Shared public-market refresh for every local pilot candidate.

The network is scanned once per cycle. Candidate-specific decisions are then
recomputed locally, avoiding five identical ATS requests for a five-person pilot.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from data.repository import Repository
from opportunities.eligibility import CandidateConstraints, Decision
from opportunities.orchestrator import OPPORTUNITY_SCANS
from opportunities.rescore import rescore_existing


def create_scheduled_opportunity_tick(repo: Repository, logger):
    async def tick() -> None:
        profiles = await asyncio.to_thread(repo.opportunities.list_candidate_profiles)
        candidates: list[CandidateConstraints] = []
        for payload in profiles:
            candidate_payload = dict(payload)
            candidate_payload.pop("profile_updated_at", None)
            try:
                candidate = CandidateConstraints.model_validate(candidate_payload)
                if candidate.consent_confirmed_at is None:
                    logger.info(
                        "scheduled opportunity profile skipped until consent is confirmed: %s",
                        candidate.candidate_id,
                    )
                    continue
                candidates.append(candidate)
            except Exception as exc:
                logger.warning("scheduled opportunity profile skipped: %s", exc)
        if not candidates:
            return

        primary = candidates[0]
        started = await OPPORTUNITY_SCANS.start(
            repo=repo,
            candidate=primary,
            target_limit=500,
            max_concurrency=6,
        )
        if not started.get("started"):
            logger.info("scheduled opportunity refresh joined an active scan")
        shared_state = await OPPORTUNITY_SCANS.wait()
        if shared_state.get("status") != "completed":
            logger.warning("scheduled opportunity refresh did not complete: %s", shared_state.get("error", "unknown"))
            return

        source_candidate = str(shared_state.get("candidate_id") or "")
        decision_names = {decision.value for decision in Decision}
        for candidate in candidates:
            if candidate.candidate_id == source_candidate:
                continue
            try:
                counts = await asyncio.to_thread(rescore_existing, repo, candidate)
                run_id = await asyncio.to_thread(
                    repo.opportunities.create_scan_run,
                    candidate.candidate_id,
                    target_count=int(shared_state.get("target_count") or 0),
                )
                state = {
                    "run_id": run_id,
                    "candidate_id": candidate.candidate_id,
                    "status": "completed",
                    "target_count": int(shared_state.get("target_count") or 0),
                    "targets_completed": int(shared_state.get("targets_completed") or 0),
                    "source_failures": int(shared_state.get("source_failures") or 0),
                    "opportunities": int(counts.get("opportunities") or 0),
                    "decision_counts": {key: int(value) for key, value in counts.items() if key in decision_names},
                    "conversion_errors": int(counts.get("invalid_canonical") or 0),
                    "shared_public_scan": True,
                    "source_candidate_id": source_candidate,
                    "started_at": str(shared_state.get("started_at") or datetime.now(timezone.utc).isoformat()),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
                await asyncio.to_thread(
                    repo.opportunities.finish_scan_run,
                    run_id,
                    candidate.candidate_id,
                    status="completed",
                    payload=state,
                )
            except Exception as exc:
                logger.warning("scheduled opportunity rescore failed for %s: %s", candidate.candidate_id, exc)

    return tick
