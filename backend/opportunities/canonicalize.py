from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from discovery.normalizer import clean_text
from opportunities.models import ActiveHint, SourceKind, SourceRecord


_TRACKING_KEYS = {
    "gh_src",
    "lever-source",
    "oga",
    "ref",
    "referrer",
    "referral",
    "source",
    "sourceid",
    "trk",
    "trackingid",
}
_GREENHOUSE_PATH_ID = re.compile(r"/(?:jobs|roles)/(\d+)(?:/|$)", re.I)
_ASHBY_OR_LEVER_ID = re.compile(
    r"/(?:[a-z0-9_.-]+)/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:/|$)",
    re.I,
)
# Workday requisitions appear either as their own path segment (`/R123`) or
# after the human-readable slug (`/Software-Engineer_R123`).
_WORKDAY_ID = re.compile(r"(?:/|_)(R-?\d+|JR-?\d+|REQ-?\d+)(?:/|$)", re.I)
_SMARTRECRUITERS_PATH = re.compile(r"^(/[^/]+/)(\d+)(?:-[^/]*)?$", re.I)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_RELATIVE_DAYS = re.compile(r"^(?:posted\s+)?(\d+)\s+days?\s+ago$", re.I)
_PRIVATE_METADATA_KEY = re.compile(
    r"(?:^|_)(?:candidate|email|phone|resume|cv|token|secret|password|cookie|"
    r"demographic)(?:_|$)|application_(?:form|questions?)",
    re.I,
)


def _public_source_metadata(value: Any, *, depth: int = 0) -> Any:
    """Retain bounded public job facts while dropping candidate/form secrets."""
    if depth > 6:
        return None
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, item in list(value.items())[:256]:
            key = str(raw_key)[:240]
            if not key or _PRIVATE_METADATA_KEY.search(key):
                continue
            result[key] = _public_source_metadata(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        return [_public_source_metadata(item, depth=depth + 1) for item in list(value)[:500]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:8_000]


def canonicalize_url(url: str) -> str:
    raw = url.strip()
    if not raw:
        return ""
    parts = urlsplit(raw if "://" in raw else f"https://{raw}")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        return raw
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if host == "jobs.smartrecruiters.com":
        match = _SMARTRECRUITERS_PATH.match(path.rstrip("/"))
        if match:
            path = f"{match.group(1)}{match.group(2)}"
    if path != "/":
        path = path.rstrip("/")
    kept = []
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        lower = key.lower()
        if lower.startswith("utm_") or lower in _TRACKING_KEYS:
            continue
        kept.append((key, value))
    return urlunsplit(("https", netloc, path, urlencode(sorted(kept)), ""))


def provider_requisition_id(url: str, provider: str, explicit_id: str = "") -> str:
    if explicit_id.strip():
        return explicit_id.strip()
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    provider = provider.strip().lower()
    if provider == "greenhouse":
        if query.get("gh_jid"):
            return query["gh_jid"]
        match = _GREENHOUSE_PATH_ID.search(parts.path)
        return match.group(1) if match else ""
    if provider in {"ashby", "lever"}:
        match = _ASHBY_OR_LEVER_ID.search(parts.path)
        return match.group(1).lower() if match else ""
    if provider == "workday":
        match = _WORKDAY_ID.search(parts.path)
        return match.group(1).upper() if match else ""
    if provider == "smartrecruiters":
        match = _SMARTRECRUITERS_PATH.match(parts.path.rstrip("/"))
        return match.group(2) if match else ""
    return ""


def normalized_identity_text(value: str) -> str:
    return _NON_ALNUM.sub(" ", clean_text(value).lower()).strip()


def description_fingerprint(description: str) -> str:
    normalized = normalized_identity_text(description)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def parse_provider_datetime(value: Any, *, observed_at: datetime) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = clean_text(str(value or ""))
    if not text:
        return None
    lower = text.lower()
    if lower in {"posted today", "today"}:
        return observed_at
    if lower in {"posted yesterday", "yesterday"}:
        return observed_at - timedelta(days=1)
    if match := _RELATIVE_DAYS.match(text):
        return observed_at - timedelta(days=int(match.group(1)))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
        for date_format in ("%d-%b-%Y", "%d-%B-%Y", "%d %b %Y", "%d %B %Y"):
            try:
                parsed = datetime.strptime(text, date_format)
                break
            except ValueError:
                continue
        if parsed is None:
            return None
    assert parsed is not None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def identity_keys(record: SourceRecord) -> list[str]:
    keys: list[str] = []
    if record.provider_requisition_id:
        tenant = f":{record.provider_tenant}" if record.provider_tenant else ""
        keys.append(f"provider:{record.provider}{tenant}:{record.provider_requisition_id.lower()}")
    keys.append(f"url:{record.canonical_source_url}")
    employer = normalized_identity_text(record.employer_domain or record.employer_name)
    title = normalized_identity_text(record.title)
    location = normalized_identity_text(record.location_text)
    fingerprint = description_fingerprint(record.description_full)
    if employer and title and location and fingerprint:
        keys.append(f"content:{employer}|{title}|{location}|{fingerprint}")
    return list(dict.fromkeys(keys))


def source_record_from_lead(
    lead: dict[str, Any],
    *,
    observed_at: datetime | None = None,
    raw_payload: Any | None = None,
    parser_version: str = "1",
) -> SourceRecord:
    observed = observed_at or datetime.now(timezone.utc)
    provider = clean_text(str(lead.get("platform") or lead.get("source") or "unknown")).lower()
    source_url = str(lead.get("url") or "").strip()
    source_meta = lead.get("source_meta") if isinstance(lead.get("source_meta"), dict) else {}
    provider_tenant = clean_text(str(source_meta.get("slug") or source_meta.get("tenant") or "")).lower()
    req_id = provider_requisition_id(
        source_url,
        provider,
        str(source_meta.get("id") or source_meta.get("job_id") or ""),
    )
    payload_hash = ""
    if raw_payload is not None:
        encoded = json.dumps(raw_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        payload_hash = hashlib.sha256(encoded).hexdigest()
    if provider in {
        "amazon", "atlassian", "dell", "deliveroo", "google", "ibm", "microsoft", "oracle",
        "qualcomm", "swiggy", "zeqo",
    }:
        source_kind = SourceKind.DIRECT_EMPLOYER
    elif provider in {
        "ashby", "bamboohr", "breezy", "greenhouse", "lever", "personio", "pinpoint", "recruitee",
        "rippling", "smartrecruiters", "teamtailor", "workable", "workday", "oraclehcm",
        "eightfold", "icims", "avature", "jobvite", "successfactors", "jibe",
        "zohorecruit", "freshteam", "keka",
    }:
        source_kind = SourceKind.ATS
    elif provider in {"hn", "hn_hiring"}:
        source_kind = SourceKind.COMMUNITY
    else:
        source_kind = SourceKind.AGGREGATOR
    active_hint_raw = lead.get("active_hint")
    active_hint = (
        ActiveHint(str(active_hint_raw))
        if active_hint_raw is not None
        else (ActiveHint.ACTIVE if source_kind == SourceKind.ATS else ActiveHint.UNKNOWN)
    )
    stable_id = req_id or hashlib.sha256(canonicalize_url(source_url).encode("utf-8")).hexdigest()[:24]
    observation_basis = "|".join(
        (
            provider,
            provider_tenant,
            stable_id,
            observed.isoformat(),
            payload_hash,
            clean_text(str(lead.get("description") or "")),
        )
    )
    observation_id = hashlib.sha256(observation_basis.encode("utf-8")).hexdigest()[:20]
    published_text = clean_text(str(lead.get("posted_date") or ""))
    updated_text = clean_text(str(lead.get("updated_at") or ""))
    deadline_text = clean_text(str(lead.get("deadline") or ""))
    return SourceRecord(
        source_record_id=f"{provider}:{stable_id}:{observation_id}",
        source_target_id=str(source_meta.get("source_target_id") or ""),
        provider=provider,
        provider_tenant=provider_tenant,
        source_kind=source_kind,
        source_url=source_url,
        canonical_source_url=canonicalize_url(source_url),
        apply_url=str(lead.get("apply_url") or source_url),
        provider_requisition_id=req_id,
        employer_name=clean_text(str(lead.get("company") or "Unknown employer")),
        employer_domain=clean_text(str(source_meta.get("employer_domain") or "")),
        title=clean_text(str(lead.get("title") or "Untitled opportunity")),
        location_text=clean_text(str(lead.get("location") or "")),
        workplace_text=clean_text(str(lead.get("workplace") or "")),
        description_full=clean_text(str(lead.get("description") or "")),
        raw_payload_sha256=payload_hash,
        provider_published_text=published_text,
        provider_updated_text=updated_text,
        provider_deadline_text=deadline_text,
        published_at=parse_provider_datetime(published_text, observed_at=observed),
        updated_at=parse_provider_datetime(updated_text, observed_at=observed),
        deadline_at=parse_provider_datetime(deadline_text, observed_at=observed),
        observed_at=observed,
        active_hint=active_hint,
        attribution=str(lead.get("attribution") or source_url),
        public_metadata=_public_source_metadata(source_meta),
        parser_version=parser_version,
    )
