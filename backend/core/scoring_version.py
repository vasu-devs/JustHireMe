"""Persisted candidate-fit score compatibility.

Increment ``MATCH_SCORING_VERSION`` whenever a scoring change can materially
change recommendations. Stored scores from an older algorithm are hidden until
the user runs Re-score; discovery/source signals remain untouched.
"""

from __future__ import annotations

MATCH_SCORING_VERSION = 1


def is_match_score_stale(score: int, source_meta: dict) -> bool:
    if int(score or 0) <= 0:
        return False
    try:
        stored = int((source_meta or {}).get("match_scoring_version") or 0)
    except (TypeError, ValueError):
        stored = 0
    return stored < MATCH_SCORING_VERSION
