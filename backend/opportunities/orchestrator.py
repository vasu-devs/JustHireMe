from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone

from catalog.market_registry import production_market_targets, scrape_market_target
from catalog.source_registry import run_direct_scan
from data.repository import Repository
from opportunities.eligibility import CandidateConstraints, Decision
from opportunities.rescore import rescore_existing
from opportunities.paid_sources import PAID_PROVIDERS, paid_provider_targets, scrape_paid_target


class OpportunityScanRegistry:
    """Own one resource-bounded opportunity scan and its inspectable state."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._state: dict = {"status": "idle"}

    async def start(
        self,
        *,
        repo: Repository,
        candidate: CandidateConstraints,
        target_limit: int = 500,
        max_concurrency: int = 6,
        notify=None,
    ) -> dict:
        async with self._lock:
            if self._task and not self._task.done():
                return {**deepcopy(self._state), "started": False}
            cfg: dict = {}
            usage_by_provider: dict[str, dict] = {}
            if hasattr(repo, "settings"):
                cfg = await asyncio.to_thread(repo.settings.get_settings)
            if hasattr(repo, "paid_sources"):
                usage_pairs = await asyncio.gather(*(
                    asyncio.to_thread(repo.paid_sources.provider_usage, provider)
                    for provider in PAID_PROVIDERS
                ))
                usage_by_provider = dict(zip(PAID_PROVIDERS, usage_pairs, strict=True))
            targets = [
                *production_market_targets(company_limit=target_limit),
                *paid_provider_targets(cfg, candidate, usage_by_provider),
            ]
            run_id = await asyncio.to_thread(
                repo.opportunities.create_scan_run,
                candidate.candidate_id,
                target_count=len(targets),
            )
            self._state = {
                "run_id": run_id,
                "candidate_id": candidate.candidate_id,
                "status": "running",
                "target_count": len(targets),
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            self._task = asyncio.create_task(self._run(
                repo=repo,
                candidate=candidate,
                targets=targets,
                cfg=cfg,
                max_concurrency=max_concurrency,
                notify=notify,
            ))
            return {**deepcopy(self._state), "started": True}

    async def _run(self, *, repo, candidate, targets, cfg, max_concurrency, notify) -> None:
        run_id = str(self._state["run_id"])
        async def safe_notify(message: dict) -> None:
            if not notify:
                return
            try:
                await notify(message)
            except Exception:
                # Websocket delivery is observability, never scan correctness.
                return

        await safe_notify({
                "type": "agent", "event": "opportunity_scan_started",
                "msg": f"Checking {len(targets)} company career searches for {candidate.candidate_id}.",
            })
        try:
            progress_lock = asyncio.Lock()

            async def on_target_complete(health) -> None:
                async with progress_lock:
                    completed = int(self._state.get("targets_completed", 0)) + 1
                    failures = int(self._state.get("source_failures", 0))
                    if health.status.value in {"failure", "config_error"}:
                        failures += 1
                    self._state = {
                        **self._state,
                        "targets_completed": completed,
                        "source_failures": failures,
                        "raw_rows_seen": int(self._state.get("raw_rows_seen", 0)) + health.raw_rows,
                    }
                    if hasattr(repo.opportunities, "save_candidate_source_health"):
                        await asyncio.to_thread(
                            repo.opportunities.save_candidate_source_health,
                            candidate.candidate_id,
                            health.model_dump(mode="json"),
                        )
                if completed == len(targets) or completed % 10 == 0:
                    await safe_notify({
                        "type": "agent", "event": "opportunity_scan_progress",
                        "msg": f"Opportunity scan: {completed}/{len(targets)} company searches checked.",
                    })

            async def scrape_target(scan_target: str) -> list[dict]:
                if scan_target.lower().startswith("paid:"):
                    return await scrape_paid_target(
                        scan_target,
                        cfg=cfg,
                        run_id=run_id,
                        paid_store=repo.paid_sources,
                    )
                return await scrape_market_target(scan_target)

            scan = await run_direct_scan(
                targets,
                candidate=candidate,
                scraper=scrape_target,
                max_concurrency=max(1, min(int(max_concurrency or 6), 12)),
                on_target_complete=on_target_complete,
            )
            persisted = await asyncio.to_thread(
                repo.opportunities.save_pipeline_result,
                scan.pipeline,
                candidate_id=candidate.candidate_id,
            )
            provider_yield = persisted.get("provider_yield") if isinstance(persisted, dict) else {}
            paid_yield = {
                provider: values
                for provider, values in (provider_yield or {}).items()
                if provider in PAID_PROVIDERS
            }
            if paid_yield and hasattr(repo, "paid_sources"):
                await asyncio.to_thread(
                    repo.paid_sources.save_scan_yield,
                    run_id,
                    candidate.candidate_id,
                    paid_yield,
                )
            health = [row.model_dump(mode="json") for row in scan.source_health]
            failures = sum(row.status.value in {"failure", "config_error"} for row in scan.source_health)
            successful_targets = [
                row.target_id
                for row in scan.source_health
                if row.status.value in {"success", "zero_result"}
            ]
            closed_ids = await asyncio.to_thread(
                repo.opportunities.reconcile_missing_direct_opportunities,
                successful_target_ids=successful_targets,
                seen_source_record_ids=[record.source_record_id for record in scan.pipeline.source_records],
                observed_at=scan.completed_at.isoformat(),
            )
            rescored = await asyncio.to_thread(rescore_existing, repo, candidate)
            decision_names = {decision.value for decision in Decision}
            decision_counts = {
                key: int(value) for key, value in rescored.items() if key in decision_names
            }
            state = {
                "run_id": run_id,
                "candidate_id": candidate.candidate_id,
                "status": "completed",
                "target_count": len(targets),
                "source_failures": failures,
                "targets_completed": len(targets),
                "decision_counts": decision_counts,
                "conversion_errors": len(scan.pipeline.conversion_errors),
                "closed_reconciled": len(closed_ids),
                **persisted,
                "opportunities": int(rescored.get("opportunities") or persisted.get("opportunities") or 0),
                "started_at": scan.started_at.isoformat(),
                "completed_at": scan.completed_at.isoformat(),
            }
            await asyncio.to_thread(
                repo.opportunities.finish_scan_run,
                run_id,
                candidate.candidate_id,
                status="completed",
                payload=state,
                source_health=health,
            )
            async with self._lock:
                self._state = state
            apply_count = int(decision_counts.get("apply_now", 0))
            await safe_notify({
                    "type": "agent", "event": "opportunity_scan_done",
                    "msg": f"Opportunity scan finished: {apply_count} apply-now matches for {candidate.candidate_id}.",
                })
        except Exception as exc:
            state = {
                **deepcopy(self._state),
                "status": "failed",
                "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                await asyncio.to_thread(
                    repo.opportunities.finish_scan_run,
                    run_id,
                    candidate.candidate_id,
                    status="failed",
                    payload=state,
                )
            finally:
                async with self._lock:
                    self._state = state
            await safe_notify({
                    "type": "agent", "event": "opportunity_scan_failed",
                    "msg": "Opportunity scan failed; inspect the candidate scan status for details.",
                })

    async def status(self, *, candidate_id: str, repo: Repository) -> dict:
        async with self._lock:
            if self._state.get("candidate_id") == candidate_id:
                return deepcopy(self._state)
        persisted = await asyncio.to_thread(repo.opportunities.get_latest_scan_run, candidate_id)
        if persisted.get("status") == "running":
            persisted = {
                **persisted,
                "status": "failed",
                "error": "Scan was interrupted by an app restart. Start a fresh scan.",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            run_id = str(persisted.get("run_id") or "")
            if run_id:
                await asyncio.to_thread(
                    repo.opportunities.finish_scan_run,
                    run_id,
                    candidate_id,
                    status="failed",
                    payload=persisted,
                )
        return persisted

    async def wait(self) -> dict:
        """Wait for the active shared-source scan, if any, without polling."""
        async with self._lock:
            task = self._task
        if task and not task.done():
            await task
        async with self._lock:
            return deepcopy(self._state)

    async def shutdown(self) -> None:
        async with self._lock:
            task = self._task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


OPPORTUNITY_SCANS = OpportunityScanRegistry()
