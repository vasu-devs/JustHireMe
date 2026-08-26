from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceKind(StrEnum):
    DIRECT_EMPLOYER = "direct_employer"
    ATS = "ats"
    AGGREGATOR = "aggregator"
    COMMUNITY = "community"


class ActiveHint(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class LiveStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class SourceRecord(StrictModel):
    """One immutable public observation, before cross-source deduplication."""

    source_record_id: str = Field(min_length=1, max_length=240)
    source_target_id: str = Field(default="", max_length=240)
    provider: str = Field(min_length=1, max_length=80)
    provider_tenant: str = Field(default="", max_length=240)
    source_kind: SourceKind = SourceKind.ATS
    source_url: str = Field(min_length=1, max_length=4000)
    canonical_source_url: str = Field(min_length=1, max_length=4000)
    apply_url: str = Field(default="", max_length=4000)
    provider_requisition_id: str = Field(default="", max_length=240)
    employer_name: str = Field(min_length=1, max_length=300)
    employer_domain: str = Field(default="", max_length=300)
    title: str = Field(min_length=1, max_length=500)
    location_text: str = Field(default="", max_length=1000)
    workplace_text: str = Field(default="", max_length=1000)
    description_full: str = Field(default="", max_length=500_000)
    description_sha256: str = Field(default="", min_length=0, max_length=64)
    raw_payload_sha256: str = Field(default="", min_length=0, max_length=64)
    provider_published_text: str = Field(default="", max_length=500)
    provider_updated_text: str = Field(default="", max_length=500)
    provider_deadline_text: str = Field(default="", max_length=500)
    published_at: datetime | None = None
    updated_at: datetime | None = None
    deadline_at: datetime | None = None
    observed_at: datetime
    active_hint: ActiveHint = ActiveHint.UNKNOWN
    attribution: str = Field(default="", max_length=1000)
    public_metadata: dict[str, Any] = Field(default_factory=dict)
    parser_version: str = Field(default="1", max_length=80)

    @field_validator("provider", "provider_tenant", "employer_domain", mode="after")
    @classmethod
    def normalize_lowercase_fields(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def fill_content_hash(self) -> SourceRecord:
        expected = hashlib.sha256(self.description_full.encode("utf-8")).hexdigest()
        if self.description_sha256 and self.description_sha256 != expected:
            raise ValueError("description_sha256 does not match description_full")
        if not self.description_sha256:
            object.__setattr__(self, "description_sha256", expected)
        return self


class LifecycleFacts(StrictModel):
    status: LiveStatus
    first_seen_at: datetime
    last_seen_at: datetime
    last_verified_active_at: datetime | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    deadline_at: datetime | None = None
    evidence: list[str] = Field(default_factory=list)


class CanonicalOpportunity(StrictModel):
    """One employer requisition with every source observation retained."""

    opportunity_id: str = Field(min_length=1, max_length=80)
    identity_keys: list[str] = Field(min_length=1)
    employer_name: str = Field(min_length=1, max_length=300)
    employer_domain: str = Field(default="", max_length=300)
    title: str = Field(min_length=1, max_length=500)
    location_text: str = Field(default="", max_length=1000)
    canonical_apply_url: str = Field(min_length=1, max_length=4000)
    lifecycle: LifecycleFacts
    observations: list[SourceRecord] = Field(min_length=1)
    dedupe_confidence: float = Field(ge=0.0, le=1.0)
    dedupe_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def retain_unique_observations(self) -> CanonicalOpportunity:
        ids = [record.source_record_id for record in self.observations]
        if len(ids) != len(set(ids)):
            raise ValueError("observations must have unique source_record_id values")
        return self
