"""La Bonne Alternance source adapter — French government alternance job API.

Searches https://labonnealternance.apprentissage.beta.gouv.fr/ for alternance
listings and returns them in JustHireMe normalized lead format.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None  # type: ignore

_LOG = logging.getLogger(__name__)

_LBA_BASE = "https://labonnealternance.apprentissage.beta.gouv.fr/api/v1/jobs"


def _normalize_lba_job(raw: dict) -> dict | None:
    """Convert a La Bonne Alternance record to JustHireMe lead format."""
    title = raw.get("title") or raw.get("intitule") or raw.get("romeLabel") or ""
    company = raw.get("company", {}).get("name") or raw.get("entreprise", {}).get("nom") or ""
    location = raw.get("place", {}).get("fullAddress") or raw.get("lieu", {}).get("adresse") or ""
    description = raw.get("job", {}).get("description") or raw.get("description") or ""
    url = raw.get("url") or raw.get("ideaUrl") or raw.get("origineOffre", {}).get("urlOrigine", "")
    if not url:
        job_id = raw.get("id") or raw.get("_id") or ""
        if job_id:
            url = f"https://labonnealternance.apprentissage.beta.gouv.fr/recherche-apprentissage?display=list&job_selected={job_id}"

    if not title:
        return None

    job_id = str(raw.get("id") or raw.get("_id") or "")
    if not job_id:
        job_id = hashlib.sha256(f"{title}-{company}-{url}".encode()).hexdigest()[:16]

    return {
        "job_id": f"lba-{job_id}",
        "title": title,
        "company": company,
        "url": url,
        "platform": "la_bonne_alternance",
        "status": "discovered",
        "description": description,
        "location": location,
        "kind": "job",
        "source_meta": {
            "alternance": True,
            "signal_tags": ["alternance", "apprentissage", "france"],
        },
    }


def search_alternance(
    query: str = "",
    location: str = "",
    radius: int = 30,
    limit: int = 20,
) -> list[dict]:
    """Search La Bonne Alternance API for alternance listings.

    Args:
        query: Job keyword (e.g., "développeur", "informatique").
        location: City or postal code.
        radius: Search radius in km.
        limit: Max results.

    Returns:
        List of normalized lead dicts.
    """
    params: dict[str, Any] = {
        "romes": "",
        "caller": "justhireme-alternance",
        "page": 1,
        "limit": limit,
    }
    if query:
        params["q"] = query
    if location:
        params["location"] = location
        params["radius"] = radius

    try:
        if httpx is None:
            import requests as _requests

            resp = _requests.get(_LBA_BASE, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        else:
            with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
                resp = client.get(_LBA_BASE, params=params)
                resp.raise_for_status()
                data = resp.json()
    except Exception as exc:
        _LOG.warning("La Bonne Alternance API error: %s", exc)
        return []

    raw_jobs = data.get("jobs") or data.get("resultats") or data.get("results") or []
    leads: list[dict] = []
    for raw in raw_jobs:
        normalized = _normalize_lba_job(raw)
        if normalized:
            leads.append(normalized)

    return leads


class LaBonneAlternanceSource:
    """JustHireMe discovery source adapter for La Bonne Alternance."""

    name = "la_bonne_alternance"
    kind = "job"

    def scan(self, cfg: dict | None = None, profile: dict | None = None) -> list[dict]:
        """Run a scan against La Bonne Alternance.

        Derives query from profile target role / skills.
        """
        cfg = cfg or {}
        profile = profile or {}
        query = ""
        target_role = str(profile.get("target_role") or profile.get("role") or "").strip()
        if target_role:
            query = target_role
        else:
            skills = profile.get("skills", [])
            if skills:
                query = str(skills[0].get("n") or skills[0].get("name", ""))

        location = cfg.get("alternance_location", "")
        if not location and profile.get("location"):
            location = str(profile.get("location"))

        return search_alternance(query=query, location=location, limit=cfg.get("lba_limit", 20))
