from __future__ import annotations

from importlib import import_module


def annotate_job_lead(lead: dict) -> dict:
    """Attach the resolved seniority level (and beginner flag) to a job lead.

    Lives here rather than in a router so the leads and generation APIs can both
    use it without importing each other.
    """
    meta = dict(lead.get("source_meta") or {})
    level = str(meta.get("seniority_level") or lead.get("seniority_level") or "").strip().lower()
    if level not in {"fresher", "junior", "mid", "senior", "unknown"}:
        level = classify_job_seniority(lead)
    meta["seniority_level"] = level
    meta["is_beginner"] = level in {"fresher", "junior"}
    return {**lead, "source_meta": meta, "seniority_level": level}


def classify_job_seniority(lead: dict) -> str:
    return import_module("discovery.normalizer").classify_job_seniority(lead)


def manual_lead_from_text(text: str, url: str, kind: str = "job") -> dict:
    return import_module("discovery.lead_intel").manual_lead_from_text(text, url, kind)
