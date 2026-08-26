from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from discovery.sources.ats import scrape_target
from discovery.sources.common import opportunity_scan_mode
from opportunities.eligibility import CandidateConstraints
from opportunities.pipeline import OpportunityPipelineResult, process_leads


class ScanStatus(StrEnum):
    SUCCESS = "success"
    ZERO_RESULT = "zero_result"
    FAILURE = "failure"
    CONFIG_ERROR = "config_error"
    BUDGET_EXHAUSTED = "budget_exhausted"


class SourceTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: str = Field(min_length=1, max_length=240)
    company_id: str = Field(default="", max_length=240)
    provider: str = Field(min_length=1, max_length=80)
    scan_target: str = Field(min_length=1, max_length=2000)
    parser_version: str = Field(default="1", max_length=80)


class SourceHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: str
    company_id: str = ""
    provider: str
    scan_target: str
    status: ScanStatus
    attempted_at: datetime
    duration_ms: int = Field(ge=0)
    raw_rows: int = Field(ge=0)
    accepted_source_records: int = Field(ge=0)
    conversion_errors: int = Field(ge=0)
    error_type: str = ""
    error_message: str = ""
    parser_version: str = "1"


class DirectScanRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    completed_at: datetime
    source_health: list[SourceHealth]
    pipeline: OpportunityPipelineResult


_OPPORTUNITY_FIELDS = (
    "title",
    "company",
    "url",
    "apply_url",
    "platform",
    "source",
    "description",
    "location",
    "workplace",
    "posted_date",
    "updated_at",
    "deadline",
    "active_hint",
    "attribution",
)


def _opportunity_projection(row: dict, *, target_id: str) -> dict:
    """Discard discovery-only drafts before canonical truth processing.

    Legacy adapters attach outreach copy, follow-up sequences, and scoring hints
    to every lead. None are public posting facts, and retaining them across a
    large market scan roughly doubles memory and payload-hash work.
    """
    source_meta = row.get("source_meta") if isinstance(row.get("source_meta"), dict) else {}
    projected = {key: row[key] for key in _OPPORTUNITY_FIELDS if key in row}
    projected["source_meta"] = {**source_meta, "source_target_id": target_id}
    return projected


async def run_direct_scan(
    targets: list[SourceTarget],
    *,
    candidate: CandidateConstraints,
    scraper: Callable[[str], Awaitable[list[dict]]] = scrape_target,
    max_concurrency: int = 6,
    target_timeout_seconds: float = 480,
    on_target_complete: Callable[[SourceHealth], object] | None = None,
) -> DirectScanRun:
    started_at = datetime.now(timezone.utc)
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def scan_one(target: SourceTarget) -> tuple[SourceTarget, list[dict], SourceHealth]:
        attempted_at = datetime.now(timezone.utc)
        started = time.monotonic()
        try:
            async with semaphore:
                # Queue wait is capacity telemetry, not provider latency. Start
                # source health timing only when this target owns a slot.
                attempted_at = datetime.now(timezone.utc)
                started = time.monotonic()
                mode_token = opportunity_scan_mode.set(True)
                try:
                    rows = await asyncio.wait_for(
                        scraper(target.scan_target),
                        timeout=max(0.01, min(float(target_timeout_seconds or 480), 1800)),
                    )
                finally:
                    opportunity_scan_mode.reset(mode_token)
            valid_rows = [
                _opportunity_projection(row, target_id=target.target_id)
                for row in rows
                if isinstance(row, dict)
            ]
            status = ScanStatus.SUCCESS if valid_rows else ScanStatus.ZERO_RESULT
            health = SourceHealth(
                target_id=target.target_id,
                company_id=target.company_id,
                provider=target.provider,
                scan_target=target.scan_target,
                status=status,
                attempted_at=attempted_at,
                duration_ms=max(0, round((time.monotonic() - started) * 1000)),
                raw_rows=len(rows),
                accepted_source_records=0,
                conversion_errors=max(0, len(rows) - len(valid_rows)),
                parser_version=target.parser_version,
            )
            if on_target_complete:
                callback_result = on_target_complete(health)
                if inspect.isawaitable(callback_result):
                    await callback_result
            return target, valid_rows, health
        except Exception as exc:
            status = (
                ScanStatus.BUDGET_EXHAUSTED
                if type(exc).__name__ == "PaidProviderBudgetExceeded"
                else ScanStatus.FAILURE
            )
            health = SourceHealth(
                target_id=target.target_id,
                company_id=target.company_id,
                provider=target.provider,
                scan_target=target.scan_target,
                status=status,
                attempted_at=attempted_at,
                duration_ms=max(0, round((time.monotonic() - started) * 1000)),
                raw_rows=0,
                accepted_source_records=0,
                conversion_errors=0,
                error_type=type(exc).__name__,
                error_message=str(exc)[:2000],
                parser_version=target.parser_version,
            )
            if on_target_complete:
                callback_result = on_target_complete(health)
                if inspect.isawaitable(callback_result):
                    await callback_result
            return target, [], health

    results = await asyncio.gather(*(scan_one(target) for target in targets))
    combined_leads: list[dict] = []
    for _target, rows, _health in results:
        combined_leads.extend(rows)

    pipeline = process_leads(combined_leads, candidate=candidate, observed_at=started_at)
    accepted_by_target: dict[str, int] = {}
    for record in pipeline.source_records:
        accepted_by_target[record.source_target_id] = accepted_by_target.get(record.source_target_id, 0) + 1

    health_rows: list[SourceHealth] = []
    for target, _rows, health in results:
        health_rows.append(
            health.model_copy(update={
                "accepted_source_records": accepted_by_target.get(target.target_id, 0),
            })
        )

    return DirectScanRun(
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        source_health=health_rows,
        pipeline=pipeline,
    )
