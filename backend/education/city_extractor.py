"""City name normalizer for French university locations."""
from __future__ import annotations

import re

# Common aliases — map input city → list of search terms
_CITY_ALIASES: dict[str, list[str]] = {
    "paris": ["PARIS", "PARIS CEDEX", "PARIS CEDEX 01", "PARIS CEDEX 02", "PARIS CEDEX 03",
              "PARIS CEDEX 04", "PARIS CEDEX 05", "PARIS CEDEX 06", "PARIS CEDEX 07",
              "PARIS CEDEX 08", "PARIS CEDEX 09", "PARIS CEDEX 10", "PARIS CEDEX 11",
              "PARIS CEDEX 12", "PARIS CEDEX 13", "PARIS CEDEX 14", "PARIS CEDEX 15",
              "PARIS CEDEX 16", "PARIS CEDEX 17", "PARIS CEDEX 18", "PARIS CEDEX 19",
              "PARIS CEDEX 20"],
    "lyon": ["LYON", "LYON CEDEX 02", "LYON CEDEX 07", "VILLEURBANNE", "VILLEURBANNE CEDEX"],
    "lille": ["LILLE", "LILLE CEDEX", "VILLENEUVE D ASCQ", "VILLENEUVE D ASCQ CEDEX"],
    "rennes": ["RENNES", "RENNES CEDEX", "RENNES CEDEX 7"],
    "nantes": ["NANTES", "NANTES CEDEX 2", "NANTES CEDEX 3"],
    "bordeaux": ["BORDEAUX"],
    "toulouse": ["TOULOUSE", "TOULOUSE CEDEX 3", "TOULOUSE CEDEX 4", "TOULOUSE CEDEX 9"],
    "strasbourg": ["STRASBOURG", "STRASBOURG CEDEX"],
    "montpellier": ["MONTPELLIER", "MONTPELLIER CEDEX 2", "MONTPELLIER cedex 5"],
    "nice": ["NICE", "NICE CEDEX 2"],
    "grenoble": ["GRENOBLE", "GRENOBLE CEDEX 1", "GRENOBLE CEDEX 2", "GRENOBLE CEDEX 9",
                  "ST MARTIN D HERES"],
    "aix-en-provence": ["AIX-EN-PROVENCE", "AIX EN PROVENCE"],
    "marseille": ["MARSEILLE", "MARSEILLE CEDEX 07", "MARSEILLE CEDEX 13"],
    "toulon": ["TOULON", "TOULON CEDEX"],
    "clermont-ferrand": ["CLERMONT-FERRAND", "CLERMONT FERRAND", "CLERMONT-FERRAND CEDEX"],
    "dijon": ["DIJON", "DIJON CEDEX"],
    "rouen": ["ROUEN", "ROUEN CEDEX"],
    "reims": ["REIMS", "REIMS CEDEX"],
    "tours": ["TOURS", "TOURS CEDEX"],
    "orleans": ["ORLEANS", "ORLEANS CEDEX", "ORLEANS CEDEX 2"],
    "nancy": ["NANCY", "VANDOEUVRE-LES-NANCY", "VANDOEUVRE LES NANCY", "NANCY CEDEX"],
    "metz": ["METZ", "METZ CEDEX"],
    "amiens": ["AMIENS", "AMIENS CEDEX 1", "AMIENS CEDEX"],
    "besancon": ["BESANCON", "BESANCON CEDEX"],
    "caen": ["CAEN", "CAEN CEDEX"],
    "limoges": ["LIMOGES", "LIMOGES CEDEX"],
    "poitiers": ["POITIERS", "POITIERS CEDEX"],
    "saint-etienne": ["SAINT-ETIENNE", "SAINT ETIENNE", "SAINT-ETIENNE CEDEX"],
    "brest": ["BREST", "BREST CEDEX"],
    "le-mans": ["LE MANS", "LE MANS CEDEX"],
    "angers": ["ANGERS", "ANGERS CEDEX"],
    "perpignan": ["PERPIGNAN", "PERPIGNAN CEDEX"],
    "cergy": ["CERGY", "CERGY PONTOISE", "CERGY PONTOISE CEDEX", "CERGY-PONTOISE"],
    "pontoise": ["CERGY PONTOISE", "CERGY PONTOISE CEDEX", "PONTOISE", "PONTOISE CEDEX", "CERGY-PONTOISE"],
    "evry": ["EVRY", "EVRY CEDEX", "EVRY COURCOURONNES", "EVRY-COURCOURONNES"],
    "courcouronnes": ["EVRY COURCOURONNES", "COURCOURONNES", "EVRY-COURCOURONNES"],
    "versailles": ["VERSAILLES", "VERSAILLES CEDEX"],
    "creteil": ["CRETEIL", "VITRY SUR SEINE", "CRETEIL CEDEX", "VITRY-SUR-SEINE"],
    "vitry-sur-seine": ["VITRY-SUR-SEINE", "VITRY SUR SEINE"],
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


def normalize_city(city: str) -> str:
    """Normalize a raw city string to its canonical name.

    Steps:
    1. Uppercase input.
    2. Strip CEDEX, CED, and postal codes (5-digit numbers).
    3. Look up in known aliases.
    4. Return lowercase canonical name (e.g. 'paris').

    Args:
        city: Raw city string from job location or description.

    Returns:
        Canonical lowercase city name, or original cleaned string if unknown.
    """
    text = city.upper()
    text = _CEDEX_RE.sub("", text)
    text = _CED_RE.sub("", text)
    text = _POSTAL_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("-", " ")

    # Reverse lookup: which alias list contains this cleaned text?
    for canonical, aliases in _CITY_ALIASES.items():
        if text in aliases:
            return canonical
        # Also check loose containment
        if any(text in alias for alias in aliases):
            return canonical
        if any(alias in text for alias in aliases if len(alias) > 3):
            return canonical

    return text.lower().replace(" ", "-")


def expand_city(city: str) -> list[str]:
    """Return all known search synonyms for a canonical city.

    Args:
        city: Canonical lowercase city name (e.g. 'paris').

    Returns:
        List of uppercase search terms suitable for API queries.
    """
    normalized = city.lower().strip().replace(" ", "-")
    aliases = _CITY_ALIASES.get(normalized)
    if aliases:
        return aliases
    return [city.upper()]



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
    """Get all search variants for a city, using synonym expansion."""
    canonical = normalize_city(city)
    return expand_city(canonical)
