"""City name normalizer for French university locations."""
from __future__ import annotations

import re

# Common aliases — map input city → list of search terms
_CITY_ALIASES: dict[str, list[str]] = {
    "paris": ["PARIS"],
    "lyon": ["LYON", "VILLEURBANNE"],
    "lille": ["LILLE"],
    "rennes": ["RENNES"],
    "nantes": ["NANTES"],
    "bordeaux": ["BORDEAUX"],
    "toulouse": ["TOULOUSE"],
    "strasbourg": ["STRASBOURG"],
    "montpellier": ["MONTPELLIER"],
    "nice": ["NICE"],
    "grenoble": ["GRENOBLE", "SAINT-MARTIN-D'HERES"],
    "aix-en-provence": ["AIX-EN-PROVENCE"],
    "marseille": ["MARSEILLE"],
    "toulon": ["TOULON"],
    "clermont-ferrand": ["CLERMONT-FERRAND"],
    "dijon": ["DIJON"],
    "rouen": ["ROUEN"],
    "reims": ["REIMS"],
    "tours": ["TOURS"],
    "orleans": ["ORLEANS"],
    "nancy": ["NANCY", "VANDOEUVRE-LES-NANCY"],
    "metz": ["METZ"],
    "amiens": ["AMIENS"],
    "besancon": ["BESANCON"],
    "caen": ["CAEN"],
    "limoges": ["LIMOGES"],
    "poitiers": ["POITIERS"],
    "saint-etienne": ["SAINT-ETIENNE"],
    "brest": ["BREST"],
    "le mans": ["LE MANS"],
    "angers": ["ANGERS"],
    "perpignan": ["PERPIGNAN"],
    "cergy": ["CERGY", "CERGY-PONTOISE"],
    "pontoise": ["CERGY-PONTOISE", "PONTOISE"],
    "evry": ["EVRY", "EVRY-COURCOURONNES"],
    "courcouronnes": ["EVRY-COURCOURONNES"],
    "versailles": ["VERSAILLES"],
    "creteil": ["CRETEIL", "VITRY-SUR-SEINE"],
    "vitry-sur-seine": ["VITRY-SUR-SEINE"],
}

# Postal code → city mapping (common ones)
_POSTAL_PREFIXES: dict[str, str] = {
    "75": "PARIS", "77": "PARIS", "78": "PARIS", "91": "PARIS", "92": "PARIS",
    "93": "PARIS", "94": "PARIS", "95": "PARIS",
    "59": "LILLE", "62": "LILLE",
    "69": "LYON", "01": "LYON",
    "35": "RENNES",
    "44": "NANTES",
    "33": "BORDEAUX",
    "31": "TOULOUSE",
    "67": "STRASBOURG",
    "34": "MONTPELLIER",
    "06": "NICE",
    "38": "GRENOBLE",
    "13": "MARSEILLE",
    "83": "TOULON",
    "63": "CLERMONT-FERRAND",
    "21": "DIJON",
    "76": "ROUEN",
    "51": "REIMS",
    "37": "TOURS",
    "45": "ORLEANS",
    "54": "NANCY",
    "57": "METZ",
    "80": "AMIENS",
    "25": "BESANCON",
    "14": "CAEN",
    "87": "LIMOGES",
    "86": "POITIERS",
    "42": "SAINT-ETIENNE",
    "29": "BREST",
    "72": "LE MANS",
    "49": "ANGERS",
    "66": "PERPIGNAN",
    "95": "CERGY",
    "91": "EVRY",
    "78": "VERSAILLES",
    "94": "CRETEIL",
}


_CEDEX_RE = re.compile(r"\bCEDEX\b.*", re.IGNORECASE)
_CED_RE = re.compile(r"\bCED\b.*", re.IGNORECASE)
_POSTAL_RE = re.compile(r"\b\d{5}\b")
_POSTAL_PREFIX_RE = re.compile(r"\b(\d{2})\d{3}\b")


def _strip_postal_and_cedex(text: str) -> str:
    """Remove postal codes and CEDEX suffixes."""
    text = _CEDEX_RE.sub("", text)
    text = _CED_RE.sub("", text)
    text = _POSTAL_RE.sub("", text)
    return text


def extract_city(location: str, description: str = "") -> str:
    """Extract and normalize a French city name from job location/description.

    Returns uppercase, normalized city suitable for Mon Master API queries.
    """
    combined = f"{location} {description}"
    # Try postal code prefix
    prefix_match = _POSTAL_PREFIX_RE.search(combined)
    if prefix_match:
        prefix = prefix_match.group(1)
        city_from_postal = _POSTAL_PREFIXES.get(prefix)
        if city_from_postal:
            return city_from_postal

    # Clean the location string
    cleaned = _strip_postal_and_cedex(location)
    # Remove common noise
    cleaned = re.sub(r"\b(Remote|Hybride|Hybrid|Full?\s*Remote|Télétravail|À distance|France|National)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\(\)\|·,;\/]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Try to find a known city (case-insensitive)
    lower_cleaned = cleaned.lower()
    for alias_key, search_terms in _CITY_ALIASES.items():
        if alias_key in lower_cleaned:
            return search_terms[0]  # Return primary form

    # Fallback: take the last word/phrase as city name, uppercase it
    # (location strings are often "City · Remote" or "75001 Paris")
    parts = cleaned.split()
    if not parts:
        return ""

    # Heuristic: if there are 2-3 words and the last looks like a city, use it
    candidate = parts[-1] if len(parts[-1]) > 2 else ""
    if len(parts) >= 2 and len(parts[-2]) > 2:
        bigram = f"{parts[-2]} {parts[-1]}"
        if bigram.lower() in _CITY_ALIASES:
            return _CITY_ALIASES[bigram.lower()][0]
        # Check if last word alone is a city
        if parts[-1].lower() in _CITY_ALIASES:
            return _CITY_ALIASES[parts[-1].lower()][0]
        candidate = bigram

    return candidate.upper().strip(" -") if candidate else ""


def get_city_search_terms(city: str) -> list[str]:
    """Get all search variants for a city."""
    normalized = city.lower().strip()
    aliases = _CITY_ALIASES.get(normalized)
    if aliases:
        return aliases
    return [city.upper()]
