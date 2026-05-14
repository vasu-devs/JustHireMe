from __future__ import annotations

from importlib import import_module


def classify_job_seniority(lead: dict) -> str:
    return import_module("discovery.normalizer").classify_job_seniority(lead)


def manual_lead_from_text(text: str, url: str, kind: str = "job") -> dict:
    return import_module("discovery.lead_intel").manual_lead_from_text(text, url, kind)
