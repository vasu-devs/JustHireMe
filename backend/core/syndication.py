from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Mapping
from difflib import SequenceMatcher
from typing import Any


_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_SYNDICATION_TAIL = re.compile(r"\bOriginally posted on Himalayas\b", re.I)
_AUTHORITATIVE_SOURCE_KINDS = {"ats", "direct_employer"}
_COUNTRY_MARKERS = {
    "in": ("india",),
    "us": ("united states", "usa", "u s"),
    "ca": ("canada",),
    "gb": ("united kingdom", "uk", "great britain"),
    "au": ("australia",),
    "de": ("germany",),
    "fr": ("france",),
    "es": ("spain",),
    "it": ("italy",),
    "nl": ("netherlands",),
    "pt": ("portugal",),
    "pl": ("poland",),
    "ie": ("ireland",),
    "sg": ("singapore",),
    "jp": ("japan",),
    "br": ("brazil",),
    "mx": ("mexico",),
}


def _normalized_identity_text(value: Any) -> str:
    return _NON_ALNUM.sub(" ", str(value or "").casefold()).strip()


def _syndicated_body(description: Any) -> str:
    raw = str(description or "")
    match = _SYNDICATION_TAIL.search(raw)
    body = raw[: match.start()] if match else raw
    return _normalized_identity_text(body)


def _token_multiset_dice(left: str, right: str) -> float:
    left_tokens = Counter(re.findall(r"[a-z0-9]+", left))
    right_tokens = Counter(re.findall(r"[a-z0-9]+", right))
    total = sum(left_tokens.values()) + sum(right_tokens.values())
    if not total:
        return 0.0
    shared = sum((left_tokens & right_tokens).values())
    return (2.0 * shared) / total


def _location_country_markers(payload: Mapping[str, Any]) -> set[str]:
    metadata = payload.get("public_metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    fragments = [
        payload.get("location_text"),
        metadata.get("country"),
        metadata.get("country_code"),
        metadata.get("location"),
    ]
    for value in metadata.get("all_locations") or []:
        fragments.append(value)
    normalized = f" {_normalized_identity_text(' '.join(str(value or '') for value in fragments))} "
    if any(marker in normalized for marker in (" worldwide ", " global ", " anywhere ")):
        return {"*"}
    markers: set[str] = set()
    words = set(normalized.split())
    for code, names in _COUNTRY_MARKERS.items():
        if code in words or any(f" {name} " in normalized for name in names):
            markers.add(code)
    return markers


def _syndication_locations_compatible(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> bool:
    left_markers = _location_country_markers(left)
    right_markers = _location_country_markers(right)
    if not left_markers or not right_markers or "*" in left_markers | right_markers:
        return True
    return bool(left_markers & right_markers)


def is_high_confidence_syndication_payload(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> bool:
    """Return true only for a near-verbatim aggregator/authoritative pair."""
    left_kind = str(left.get("source_kind") or "")
    right_kind = str(right.get("source_kind") or "")
    kinds = {left_kind, right_kind}
    if "aggregator" not in kinds or not (kinds & _AUTHORITATIVE_SOURCE_KINDS):
        return False
    if str(left.get("provider") or "") == str(right.get("provider") or ""):
        return False
    left_employer = _normalized_identity_text(
        left.get("employer_domain") or left.get("employer_name")
    )
    right_employer = _normalized_identity_text(
        right.get("employer_domain") or right.get("employer_name")
    )
    if not left_employer or left_employer != right_employer:
        return False
    left_title = _normalized_identity_text(left.get("title"))
    right_title = _normalized_identity_text(right.get("title"))
    if not left_title or left_title != right_title:
        return False
    if not _syndication_locations_compatible(left, right):
        return False
    left_body = _syndicated_body(left.get("description_full"))
    right_body = _syndicated_body(right.get("description_full"))
    if min(len(left_body), len(right_body)) < 800:
        return left_body == right_body and bool(left_body)
    return (
        SequenceMatcher(None, left_body, right_body).ratio() >= 0.97
        or _token_multiset_dice(left_body, right_body) >= 0.97
    )


def syndication_identity_key_payload(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> str:
    employer = _normalized_identity_text(
        left.get("employer_domain") or left.get("employer_name")
    )
    title = _normalized_identity_text(left.get("title"))
    pair_basis = "|".join(sorted((
        str(left.get("canonical_source_url") or ""),
        str(right.get("canonical_source_url") or ""),
    )))
    return "syndicated:" + hashlib.sha256(
        f"{employer}|{title}|{pair_basis}".encode()
    ).hexdigest()[:24]
