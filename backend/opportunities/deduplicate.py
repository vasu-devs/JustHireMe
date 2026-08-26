from __future__ import annotations

import hashlib
from collections import defaultdict

from core.syndication import (
    is_high_confidence_syndication_payload,
    syndication_identity_key_payload,
)
from opportunities.canonicalize import identity_keys, normalized_identity_text
from opportunities.lifecycle import resolve_lifecycle
from opportunities.models import CanonicalOpportunity, SourceKind, SourceRecord


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def _record_preference(record: SourceRecord) -> tuple[int, int, float]:
    directness = 2 if record.source_kind in {SourceKind.DIRECT_EMPLOYER, SourceKind.ATS} else 1
    return directness, len(record.description_full), record.observed_at.timestamp()


def is_high_confidence_syndication(left: SourceRecord, right: SourceRecord) -> bool:
    return is_high_confidence_syndication_payload(
        left.model_dump(mode="json"), right.model_dump(mode="json")
    )


def syndication_identity_key(left: SourceRecord, right: SourceRecord) -> str:
    """Build the stable evidence key shared by batch and historical reconciliation."""
    return syndication_identity_key_payload(
        left.model_dump(mode="json"), right.model_dump(mode="json")
    )


def _provider_identity_conflict(
    union: _UnionFind,
    left: int,
    right: int,
    records: list[SourceRecord],
) -> bool:
    """Reject content-only merges of distinct IDs in the same provider tenant.

    Some employers reuse an exact title, location, and description template for
    several simultaneously live requisitions. The provider requisition ID is
    authoritative in that case. Inspect the complete current clusters so a
    provider-less syndicated record cannot create a transitive bridge between
    two distinct official requisitions.
    """
    left_root = union.find(left)
    right_root = union.find(right)
    if left_root == right_root:
        return False
    identities: dict[tuple[str, str], dict[int, set[str]]] = defaultdict(
        lambda: {left_root: set(), right_root: set()}
    )
    for index, record in enumerate(records):
        root = union.find(index)
        if root not in {left_root, right_root} or not record.provider_requisition_id:
            continue
        key = (record.provider, record.provider_tenant)
        identities[key][root].add(record.provider_requisition_id.strip().lower())
    return any(
        values[left_root]
        and values[right_root]
        and values[left_root] != values[right_root]
        for values in identities.values()
    )


def canonicalize_observations(records: list[SourceRecord]) -> list[CanonicalOpportunity]:
    """Merge only exact, high-confidence identities and retain all provenance."""
    if not records:
        return []
    union = _UnionFind(len(records))
    key_owner: dict[str, int] = {}
    record_keys = [identity_keys(record) for record in records]
    for index, keys in enumerate(record_keys):
        for key in keys:
            owner = key_owner.setdefault(key, index)
            if key.startswith("content:") and _provider_identity_conflict(
                union, owner, index, records
            ):
                continue
            union.union(owner, index)

    # Exact provider/URL/content keys cannot connect an official job to a
    # syndicated copy when the aggregator reformats location and appends its
    # attribution. Restrict fuzzy reconciliation to same-employer/same-title
    # cross-source pairs whose substantive descriptions are near-verbatim.
    candidates: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        employer = normalized_identity_text(record.employer_domain or record.employer_name)
        title = normalized_identity_text(record.title)
        if employer and title:
            candidates[(employer, title)].append(index)
    for indexes in candidates.values():
        for offset, left_index in enumerate(indexes):
            for right_index in indexes[offset + 1:]:
                if not is_high_confidence_syndication(records[left_index], records[right_index]):
                    continue
                if _provider_identity_conflict(union, left_index, right_index, records):
                    continue
                reason = syndication_identity_key(
                    records[left_index], records[right_index]
                )
                record_keys[left_index].append(reason)
                record_keys[right_index].append(reason)
                union.union(left_index, right_index)

    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        groups[union.find(index)].append(index)

    opportunities: list[CanonicalOpportunity] = []
    for indexes in groups.values():
        observations = sorted((records[index] for index in indexes), key=lambda record: record.observed_at)
        primary = max(observations, key=_record_preference)
        keys = sorted({key for index in indexes for key in record_keys[index]})
        strongest = next((key for key in keys if key.startswith("provider:")), keys[0])
        opportunity_id = "opp_" + hashlib.sha256(strongest.encode("utf-8")).hexdigest()[:24]
        reasons = []
        if len(observations) > 1:
            shared = set(record_keys[indexes[0]])
            for index in indexes[1:]:
                shared &= set(record_keys[index])
            reasons = sorted(shared)
        confidence = 1.0 if any(reason.startswith("provider:") for reason in reasons) else 0.99
        opportunities.append(
            CanonicalOpportunity(
                opportunity_id=opportunity_id,
                identity_keys=keys,
                employer_name=primary.employer_name,
                employer_domain=primary.employer_domain,
                title=primary.title,
                location_text=primary.location_text,
                canonical_apply_url=primary.apply_url or primary.canonical_source_url,
                lifecycle=resolve_lifecycle(observations),
                observations=observations,
                dedupe_confidence=confidence,
                dedupe_reasons=reasons,
            )
        )
    return sorted(opportunities, key=lambda opportunity: opportunity.opportunity_id)
