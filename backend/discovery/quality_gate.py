"""Deterministic lead quality gate for discovery sources."""

from __future__ import annotations
import logging

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from discovery.lead_intel import clean_text, signal_quality


MIN_DEFAULT_QUALITY = 60
HOT_LEAD_THRESHOLD = 80

_RED_FLAGS = (
    "unpaid",
    "for exposure",
    "equity only",
    "commission only",
    "no budget",
    "lowest bidder",
    "college assignment",
    "homework",
    "free trial",
    "training course",
)

_SENIOR_FLAGS = (
    "senior",
    "staff",
    "principal",
    "lead engineer",
    "engineering manager",
    "director",
    "architect",
    "5+ years",
    "7+ years",
    "10+ years",
)

_BEGINNER_FLAGS = (
    "junior",
    "entry level",
    "entry-level",
    "new grad",
    "graduate",
    "fresher",
    "intern",
    "0-2 years",
    "0 to 2 years",
    "1-2 years",
)


def _lead_text(lead: dict) -> str:
    meta = lead.get("source_meta") or {}
    meta_text = ""
    if isinstance(meta, dict):
        meta_text = " ".join(str(v) for v in meta.values() if isinstance(v, (str, int, float)))
    return clean_text(
        "\n".join(
            str(lead.get(key, "") or "")
            for key in ("title", "company", "platform", "description", "location", "posted_date")
        )
        + "\n"
        + meta_text
    )


def _parse_date(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    now = datetime.now(timezone.utc)
    if lower in {"today", "just now", "moments ago"}:
        return now
    if lower == "yesterday":
        return now - timedelta(days=1)
    match = re.search(r"(\d+)\s*(hour|day|week|month|year)s?\s*ago", lower)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        days = {"hour": 0, "day": amount, "week": amount * 7, "month": amount * 30, "year": amount * 365}[unit]
        if unit == "hour":
            return now - timedelta(hours=amount)
        return now - timedelta(days=days)
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/discovery/quality_gate.py:_parse_date: %s', log_exc)
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%b %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _freshness(lead: dict, max_age_days: int = 7) -> tuple[bool, str]:
    values = [
        lead.get("posted_date"),
        (lead.get("source_meta") or {}).get("posted_date") if isinstance(lead.get("source_meta"), dict) else "",
        (lead.get("source_meta") or {}).get("created_at") if isinstance(lead.get("source_meta"), dict) else "",
    ]
    dates = [_parse_date(str(v or "")) for v in values if str(v or "").strip()]
    dates = [d for d in dates if d is not None]
    if not dates:
        return True, "freshness unknown"
    newest = max(dates)
    age_days = (datetime.now(timezone.utc) - newest).days
    if age_days > max_age_days:
        return False, f"stale posting: {age_days} days old"
    return True, f"fresh posting: {age_days} days old"


def _seniority(text: str, source_level: str = "") -> str:
    level = str(source_level or "").lower().strip()
    if level:
        return level
    lower = text.lower()
    if any(flag in lower for flag in _SENIOR_FLAGS):
        return "senior"
    if any(flag in lower for flag in _BEGINNER_FLAGS):
        return "junior"
    return "unknown"


def evaluate_lead_quality(
    lead: dict,
    *,
    min_quality: int = MIN_DEFAULT_QUALITY,
    target_level: str = "beginner",
    max_age_days: int = 7,
) -> dict:
    text = _lead_text(lead)
    reasons: list[str] = []
    penalties = 0

    if not str(lead.get("url") or "").strip():
        return {"accepted": False, "score": 0, "reason": "missing source/apply URL", "tags": ["missing_url"]}

    if len(text) < 140:
        penalties += 18
        reasons.append("thin scraped posting")
    if not str(lead.get("company") or "").strip():
        penalties += 8
        reasons.append("missing company")

    fresh, fresh_reason = _freshness(lead, max_age_days=max_age_days)
    reasons.append(fresh_reason)
    if not fresh:
        penalties += 35

    lower = text.lower()
    red_flags = [flag for flag in _RED_FLAGS if flag in lower]
    if red_flags:
        penalties += min(45, 16 * len(red_flags))
        reasons.append("red flags: " + ", ".join(red_flags[:3]))

    meta = lead.get("source_meta") or {}
    seniority = _seniority(text, meta.get("seniority_level", "") if isinstance(meta, dict) else "")
    if target_level in {"beginner", "fresher", "junior"} and seniority == "senior":
        penalties += 38
        reasons.append("senior-only role for beginner-focused feed")
    elif seniority in {"junior", "fresher"}:
        reasons.append("beginner-friendly seniority signal")

    signal = int(lead.get("signal_score") or 0)
    if signal <= 0:
        signal = int(signal_quality(text).get("score") or 0)
    score = max(0, min(100, signal - penalties))
    accepted = score >= max(0, min(int(min_quality or MIN_DEFAULT_QUALITY), 100))

    if not reasons:
        reasons.append("passes source quality checks")
    return {
        "accepted": accepted,
        "score": score,
        "reason": "; ".join(reasons),
        "tags": ["quality_gate", f"seniority:{seniority}"],
    }


def attach_quality_metadata(lead: dict, quality: dict) -> dict:
    meta = lead.get("source_meta") if isinstance(lead.get("source_meta"), dict) else {}
    merged = {
        **meta,
        "lead_quality_score": quality.get("score", 0),
        "lead_quality_reason": quality.get("reason", ""),
        "lead_quality_accepted": bool(quality.get("accepted")),
    }
    return {**lead, "source_meta": merged}
