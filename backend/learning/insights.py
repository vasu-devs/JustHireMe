"""Learning insights: what this candidate should learn next, mined from the
job market they are actually in.

Every scan leaves behind a corpus of real, fresh postings in the local lead
store. This module reads that corpus against the candidate's own profile and
answers three questions deterministically (no LLM cost, fully local):

- **Gaps** — skills in real demand across the candidate's market that their
  profile does not evidence, ranked by leverage. A skill demanded by a
  *near-miss* role (a lead scored 55-84, i.e. a job they'd plausibly land with
  one more skill) counts extra: closing that gap converts real postings.
- **Strengths** — skills the candidate already has that the market keeps
  asking for, so they know what to lead with.
- **Themes** — deliverable-level currents in their market (agentic AI, RAG,
  dashboards, ...), share-of-postings weighted by recency.

Field-agnosticism: canonical tech terms come from the shared taxonomy, and the
candidate's own domain phrases (nurse, welder, teacher vocabularies) are
matched against postings the same way the scoring engine does it — a non-tech
candidate sees which of their skills the market demands rather than nothing.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ranking.scoring_engine import (
    _contains_phrase,
    _find_tags,
    _find_terms,
    analyze_candidate,
    candidate_domain_phrases,
)
from ranking.taxonomy import DELIVERABLE_KEYWORDS, TECH_CATEGORY

# Terms that show up in scraped descriptions as infrastructure boilerplate,
# not hiring demand. "cloudflare" appeared in 49% of a real corpus — every
# block-page ("Attention Required! | Cloudflare", "Cloudflare Ray ID") that a
# scrape stored as description text counts as a mention. Skills are only worth
# surfacing when a posting asks for them, so these never enter the mining.
NOISE_TERMS = frozenset({"cloudflare"})

# A lead in this score band is a near-miss: real interest, one gap away.
NEAR_MISS_LOW = 55
NEAR_MISS_HIGH = 84
# Near-miss demand is worth extra leverage when ranking gaps.
NEAR_MISS_BONUS = 1.5

MAX_GAPS = 8
MAX_STRENGTHS = 6
MAX_THEMES = 5
MAX_EXAMPLE_ROLES = 3


def _recency_weight(created_at: str, now: datetime) -> float:
    """Fresh demand counts more than stale demand."""
    if not created_at:
        return 0.3
    try:
        stamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.3
    age_days = max(0.0, (now - stamp).total_seconds() / 86400)
    if age_days <= 7:
        return 1.0
    if age_days <= 14:
        return 0.6
    if age_days <= 30:
        return 0.3
    return 0.1


def _lead_text(lead: dict) -> str:
    return f"{lead.get('title', '')}\n{lead.get('description', '')}"


def _display_role(lead: dict) -> dict:
    return {
        "title": str(lead.get("title", ""))[:120],
        "company": str(lead.get("company", ""))[:80],
        "score": int(lead.get("score") or 0),
    }


def _first_step(term: str, category: str, adjacent: bool) -> str:
    """One honest, deterministic next action per gap. No invented courses."""
    if adjacent:
        return (
            f"You already work in {category or 'this area'} — ship one small, "
            f"real project that uses {term} and add it to your evidence."
        )
    if category:
        return (
            f"New territory ({category}): learn {term} fundamentals, then build "
            "one portfolio piece that pairs it with work you've already shipped."
        )
    return f"Learn {term} fundamentals and back it with one concrete project before listing it."


def compute_learning_insights(
    leads: list[dict],
    profile: dict,
    *,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    candidate = analyze_candidate(profile)
    own_phrases = candidate_domain_phrases(profile)
    candidate_categories = {TECH_CATEGORY[t] for t in candidate.all_terms if t in TECH_CATEGORY}

    considered = [lead for lead in leads if (lead.get("status") or "") not in ("discarded", "rejected")]

    # term -> aggregated demand
    demand: dict[str, dict] = {}
    theme_weight: dict[str, float] = {}
    postings_with_theme: dict[str, int] = {}
    total = 0

    for lead in considered:
        text = _lead_text(lead)
        if not text.strip():
            continue
        total += 1
        weight = _recency_weight(str(lead.get("created_at") or ""), now)
        score = int(lead.get("score") or 0)
        near_miss = NEAR_MISS_LOW <= score <= NEAR_MISS_HIGH

        terms = {t for t in _find_terms(text) if t.lower() not in NOISE_TERMS}
        # The candidate's own domain vocabulary counts as market signal too —
        # this is what keeps a non-tech profile from seeing an empty page.
        terms |= {phrase for phrase in own_phrases if phrase.lower() not in NOISE_TERMS and _contains_phrase(text, phrase)}

        for term in terms:
            row = demand.setdefault(
                term,
                {"weight": 0.0, "postings": 0, "near_miss": 0, "examples": []},
            )
            row["weight"] += weight * (NEAR_MISS_BONUS if near_miss else 1.0)
            row["postings"] += 1
            if near_miss:
                row["near_miss"] += 1
            row["examples"].append((score, _display_role(lead)))

        for theme in _find_tags(text, DELIVERABLE_KEYWORDS):
            theme_weight[theme] = theme_weight.get(theme, 0.0) + weight
            postings_with_theme[theme] = postings_with_theme.get(theme, 0) + 1

    def _finalize(term: str, row: dict) -> dict:
        category = TECH_CATEGORY.get(term, "")
        adjacent = bool(category) and category in candidate_categories
        examples = [role for _, role in sorted(row["examples"], key=lambda item: -item[0])[:MAX_EXAMPLE_ROLES]]
        share = round(100 * row["postings"] / max(1, total))
        return {
            "skill": term,
            "category": category,
            "demand": round(row["weight"], 1),
            "postings": row["postings"],
            "share_pct": share,
            "near_miss_postings": row["near_miss"],
            "adjacent": adjacent,
            "example_roles": examples,
            "first_step": _first_step(term, category, adjacent),
        }

    have = {t.lower() for t in candidate.all_terms} | {p.lower() for p in own_phrases}
    gap_rows = sorted(
        (
            _finalize(term, row)
            for term, row in demand.items()
            if term.lower() not in have and row["postings"] >= 2
        ),
        key=lambda item: (-item["demand"], -item["near_miss_postings"], item["skill"]),
    )[:MAX_GAPS]

    strength_rows = sorted(
        (
            {**_finalize(term, row), "first_step": ""}
            for term, row in demand.items()
            if term.lower() in have and row["postings"] >= 2
        ),
        key=lambda item: (-item["demand"], item["skill"]),
    )[:MAX_STRENGTHS]

    themes = sorted(
        (
            {
                "theme": theme,
                "demand": round(w, 1),
                "share_pct": round(100 * postings_with_theme[theme] / max(1, total)),
            }
            for theme, w in theme_weight.items()
        ),
        key=lambda item: -item["demand"],
    )[:MAX_THEMES]

    note = ""
    if total < 10:
        note = "Run a scan first — learning insights sharpen as the lead journal fills with real postings."
    elif not gap_rows:
        note = "No high-demand skills are missing from your evidence right now; keep your strengths sharp."

    return {
        "generated_at": now.isoformat(),
        "sample_size": total,
        "gaps": gap_rows,
        "strengths": strength_rows,
        "themes": themes,
        "note": note,
    }


def insights_summary_line(insights: dict) -> str:
    """One-line digest for logs/UI captions."""
    gaps = insights.get("gaps") or []
    if not gaps:
        return "No high-leverage skill gaps detected in the current market sample."
    top = ", ".join(g["skill"] for g in gaps[:3])
    return f"Top learning leverage right now: {top} (from {insights.get('sample_size', 0)} live postings)."
