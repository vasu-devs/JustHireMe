from __future__ import annotations

from catalog.source_registry import SourceTarget


# Workday search is fuzzy and its list endpoint omits descriptions.  Three
# independent keyword targets used to fetch the first global page (and every
# detail on it), which was both expensive and frequently irrelevant to India.
# The connector now owns one bounded, country-faceted CSE query plan.
WORKDAY_EARLY_CAREER_QUERIES = ("india-cse",)


def expand_early_career_targets(targets: list[SourceTarget]) -> list[SourceTarget]:
    """Expand search-based ATS targets; full-board APIs remain one call."""
    expanded: list[SourceTarget] = []
    for target in targets:
        if target.provider.lower() != "workday":
            expanded.append(target)
            continue
        prefix, separator, _old_query = target.scan_target.rpartition(":")
        if not separator:
            expanded.append(target)
            continue
        for query in WORKDAY_EARLY_CAREER_QUERIES:
            query_id = query.replace(" ", "-")
            expanded.append(target.model_copy(update={
                "target_id": f"{target.target_id}:{query_id}",
                "scan_target": f"{prefix}:{query}",
            }))
    return expanded
