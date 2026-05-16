"""Welcome to the Jungle source adapter — French tech job platform with alternance listings.

Searches https://www.welcometothejungle.com/ for Apprentissage / Alternance
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

_WTTJ_GRAPHQL = "https://www.welcometothejungle.com/api/v1/search"
_WTTJ_JOBS_BASE = "https://www.welcometothejungle.com/fr/jobs"


def _normalize_wttj_job(raw: dict) -> dict | None:
    """Convert a Welcome to the Jungle record to JustHireMe lead format."""
    title = raw.get("title") or raw.get("name") or ""
    company = (
        raw.get("organization", {}).get("name")
        or raw.get("company", {}).get("name")
        or ""
    )
    location_parts = raw.get("location") or raw.get("place") or {}
    if isinstance(location_parts, dict):
        location = location_parts.get("fullAddress") or location_parts.get("city") or ""
    else:
        location = str(location_parts)

    description = raw.get("description") or raw.get("job", {}).get("description") or ""
    url = raw.get("url") or raw.get("jobUrl") or ""
    if not url and raw.get("slug"):
        url = f"{_WTTJ_JOBS_BASE}/{raw['slug']}"

    contract = raw.get("contractType") or raw.get("contract_type") or ""
    if isinstance(contract, dict):
        contract = contract.get("name", "")

    if not title:
        return None

    job_id = str(raw.get("id") or raw.get("_id") or "")
    if not job_id:
        job_id = hashlib.sha256(f"{title}-{company}-{url}".encode()).hexdigest()[:16]

    return {
        "job_id": f"wttj-{job_id}",
        "title": title,
        "company": company,
        "url": url,
        "platform": "welcome_to_the_jungle",
        "status": "discovered",
        "description": description,
        "location": location,
        "kind": "job",
        "source_meta": {
            "alternance": "alternance" in contract.lower() or "apprentissage" in contract.lower(),
            "signal_tags": ["alternance", "apprentissage", "france"],
            "contract_type": contract,
        },
    }


def search_alternance(
    query: str = "",
    location: str = "",
    limit: int = 20,
) -> list[dict]:
    """Search Welcome to the Jungle for alternance listings.

    Args:
        query: Job keyword (e.g., "développeur", "informatique").
        location: City name.
        limit: Max results.

    Returns:
        List of normalized lead dicts.
    """
    # WTTJ GraphQL search payload
    payload: dict[str, Any] = {
        "query": query or "",
        "page": 1,
        "per_page": limit,
        "refinementList": {
            "contract_type.name.fr": ["Apprentissage / Alternance"],
        },
        "aroundLatLng": "",
        "aroundRadius": "all",
    }
    if location:
        payload["aroundQuery"] = location

    try:
        if httpx is None:
            import requests as _requests

            resp = _requests.post(
                _WTTJ_GRAPHQL,
                json=payload,
                timeout=30,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        else:
            with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
                resp = client.post(
                    _WTTJ_GRAPHQL,
                    json=payload,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
    except Exception as exc:
        _LOG.warning("Welcome to the Jungle API error: %s", exc)
        return []

    # WTTJ returns hits under "hits" or "results"
    raw_jobs = data.get("hits") or data.get("results") or data.get("jobs") or []
    if not isinstance(raw_jobs, list):
        _LOG.debug("Unexpected WTTJ response shape: %s", type(raw_jobs))
        return []

    leads: list[dict] = []
    for raw in raw_jobs:
        normalized = _normalize_wttj_job(raw)
        if normalized:
            leads.append(normalized)

    return leads


class WelcomeToTheJungleSource:
    """JustHireMe discovery source adapter for Welcome to the Jungle."""

    name = "welcome_to_the_jungle"
    kind = "job"

    def scan(self, cfg: dict | None = None, profile: dict | None = None) -> list[dict]:
        """Run a scan against Welcome to the Jungle.

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

        return search_alternance(query=query, location=location, limit=cfg.get("wttj_limit", 20))
