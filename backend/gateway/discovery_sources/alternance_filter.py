"""Post-scrape alternance filter — boosts signal scores for alternance matches.

Runs after any discovery source produces leads. Keeps leads where title
or description contains alternance-related keywords, and boosts their
signal_score while adding 'alternance' to signal_tags.
"""
from __future__ import annotations

import re

_ALTERNANCE_KEYWORDS = [
    "alternance",
    "apprentissage",
    "apprenti",
    "pro alternance",
    "contrat pro",
    "contrat de professionnalisation",
    "apprenticeship",
    "bac+",
    "bachelor",
    "master en alternance",
]

_ALTERNANCE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(kw) for kw in _ALTERNANCE_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

_BOOST = 10


def _looks_like_alternance(lead: dict) -> bool:
    """Check if a lead title or description contains alternance keywords."""
    text = f"{lead.get('title', '')} {lead.get('description', '')}"
    return bool(_ALTERNANCE_RE.search(text))


def filter_leads(leads: list[dict]) -> list[dict]:
    """Filter leads for alternance content and boost matching ones.

    Args:
        leads: Raw lead dicts from any discovery source.

    Returns:
        Filtered list. Non-matching leads are dropped. Matching leads have
        signal_score boosted by +10 and 'alternance' added to signal_tags.
    """
    filtered: list[dict] = []
    for lead in leads:
        if _looks_like_alternance(lead):
            lead = dict(lead)
            lead["signal_score"] = int(lead.get("signal_score", 0)) + _BOOST
            tags = list(lead.get("signal_tags", []) or [])
            if "alternance" not in tags:
                tags.append("alternance")
            lead["signal_tags"] = tags
            filtered.append(lead)
    return filtered
