"""Mon Master API client — thin wrapper with in-memory caching."""
from __future__ import annotations

import time
from typing import Any

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None  # type: ignore

_MON_MASTER_BASE = (
    "https://data.enseignementsup-recherche.gouv.fr/api/explore/v2.1/catalog/datasets/"
    "fr-esr-tmm-donnees-du-portail-dinformation-trouver-mon-master-mentions-de-master/records"
)

_CACHE: dict[str, tuple[list[dict], float]] = {}
_CACHE_TTL_SECONDS = 3600


def _cache_key(city: str, domain: str | None, modalities: list[str] | None) -> str:
    dom = domain or "*"
    mod = ",".join(sorted(modalities or [])) or "*"
    return f"{city}|{dom}|{mod}"


def _get_cached(city: str, domain: str | None, modalities: list[str] | None) -> list[dict] | None:
    key = _cache_key(city, domain, modalities)
    entry = _CACHE.get(key)
    if entry is None:
        return None
    results, ts = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        del _CACHE[key]
        return None
    return results


def _set_cached(city: str, domain: str | None, modalities: list[str] | None, results: list[dict]) -> None:
    _CACHE[_cache_key(city, domain, modalities)] = (results, time.time())


def query_mon_master(
    city: str,
    domain: str | None = None,
    modalities: list[str] | None = None,
    limit: int = 20,
) -> list[dict]:
    """Query the Mon Master open-data API.

    Args:
        city: Normalized city name (uppercase).
        domain: Academic domain filter (e.g., "INFORMATIQUE").
        modalities: List of modalities to require (e.g., ["Alternance"]).
        limit: Maximum records to fetch.

    Returns:
        List of program dicts from the API ``results`` array.
    """
    cached = _get_cached(city, domain, modalities)
    if cached is not None:
        return cached

    where_clauses: list[str] = []
    if city:
        where_clauses.append(f'etab_ville LIKE "%{city}%"')
    if modalities:
        for mod in modalities:
            where_clauses.append(f'for_modalite LIKE "%{mod}%"')

    params: dict[str, Any] = {"limit": limit}
    if where_clauses:
        params["where"] = " AND ".join(where_clauses)

    try:
        if httpx is None:
            import requests as _requests

            resp = _requests.get(_MON_MASTER_BASE, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        else:
            with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
                resp = client.get(_MON_MASTER_BASE, params=params)
                resp.raise_for_status()
                data = resp.json()
    except Exception as exc:
        # Graceful degradation — log and return empty on any error
        import logging

        logging.getLogger(__name__).warning("Mon Master API error: %s", exc)
        return []

    results = data.get("results") or []
    _set_cached(city, domain, modalities, results)
    return results
