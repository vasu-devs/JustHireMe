from __future__ import annotations

from datetime import datetime, timezone

from opportunities.models import ActiveHint, LifecycleFacts, LiveStatus, SourceRecord


def resolve_lifecycle(records: list[SourceRecord], *, now: datetime | None = None) -> LifecycleFacts:
    if not records:
        raise ValueError("at least one source record is required")
    current = now or datetime.now(timezone.utc)
    ordered = sorted(records, key=lambda record: record.observed_at)
    deadlines = [record.deadline_at for record in records if record.deadline_at]
    deadline = min(deadlines) if deadlines else None
    active_records = [record for record in records if record.active_hint == ActiveHint.ACTIVE]
    closed_records = [record for record in records if record.active_hint == ActiveHint.CLOSED]
    evidence: list[str] = []

    if deadline and deadline < current:
        status = LiveStatus.EXPIRED
        evidence.append(f"deadline_passed:{deadline.isoformat()}")
    elif active_records:
        status = LiveStatus.ACTIVE
        evidence.append(f"active_source_observation:{max(record.observed_at for record in active_records).isoformat()}")
    elif closed_records and len(closed_records) == len(records):
        status = LiveStatus.CLOSED
        evidence.append("all_source_observations_closed")
    else:
        status = LiveStatus.UNKNOWN
        evidence.append("no_authoritative_active_or_closed_signal")

    published = [record.published_at for record in records if record.published_at]
    updated = [record.updated_at for record in records if record.updated_at]
    return LifecycleFacts(
        status=status,
        first_seen_at=ordered[0].observed_at,
        last_seen_at=ordered[-1].observed_at,
        last_verified_active_at=max((record.observed_at for record in active_records), default=None),
        published_at=min(published) if published else None,
        updated_at=max(updated) if updated else None,
        deadline_at=deadline,
        evidence=evidence,
    )
