"""Shared predicate for rejecting junk vector/graph labels.

Lives in ``core`` (Common) because both the data layer (when writing embedding
rows) and the graph business layer (when rendering them) must agree on what
counts as a junk label — a scraped error page must never become a Skill node.
"""

from __future__ import annotations


BAD_VECTOR_LABEL_PATTERNS = (
    "404:",
    "not_found",
    "not found",
    "error code",
    "failed to fetch",
    "server returned",
    "traceback",
)


def is_bad_vector_label(value: object) -> bool:
    text = str(value or "").strip()
    lower = text.lower()
    return not text or any(pattern in lower for pattern in BAD_VECTOR_LABEL_PATTERNS)
