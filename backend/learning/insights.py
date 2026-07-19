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
On top of that, market-phrase mining surfaces *unknown* non-tech gaps: 2-3-word
phrases that recur across independent employers near the candidate's field but
appear nowhere in their profile ("wound care" for a nurse who never wrote it).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ranking.scoring_engine import (
    _contains_phrase,
    _field_vector,
    _find_tags,
    _find_terms,
    _profile_text,
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

# Market-phrase mining (non-tech gap discovery). A 2-3-word posting phrase only
# becomes a gap candidate when it recurs across independent employers (kills
# per-company boilerplate) AND sits semantically near the candidate's own
# profile (kills market-wide boilerplate like "equal opportunity employer").
MIN_PHRASE_POSTINGS = 3
MIN_PHRASE_COMPANIES = 3
MIN_PHRASE_COSINE = 0.30
# Above this share of ALL postings a phrase is posting grammar ("help build",
# "join our team"), not a differentiating skill — measured on a real corpus
# where "help build" hit 50% share and sailed through the semantic filter.
# Share is only meaningful with a real sample: below the floor every phrase in
# a tiny corpus would read as "ubiquitous" and mining would return nothing.
MAX_PHRASE_SHARE = 0.30
MIN_CORPUS_FOR_SHARE_CEILING = 20
MAX_MINED_GAPS = 4  # taxonomy gaps keep priority in the merged ranking
MAX_MINING_CHARS = 8000  # per-posting cap so pathological descriptions can't blow up the phrase table
MINED_FIRST_STEP = (
    "This keeps appearing in postings near your profile — find what it involves and add one piece of evidence."
)

# Edge stopwords for mined phrases: a phrase may contain one inside ("care for
# patients"), but a phrase starting or ending with one is grammar or posting
# boilerplate, not a skill.
_MINING_STOPWORDS = frozenset({
    "the", "and", "with", "for", "our", "you", "will", "are", "this", "that", "have", "work", "team", "join",
    "role", "job", "apply", "experience", "years", "skills", "looking", "hiring", "remote", "salary", "benefits",
    "full", "time", "part", "more", "about", "what", "who", "when", "where", "other", "all", "new", "etc",
    "an", "as", "at", "be", "by", "do", "in", "is", "it", "its", "of", "on", "or", "to", "we", "us", "your",
    "their", "they", "them", "has", "had", "was", "were", "been", "being", "from", "into", "not", "no", "can",
    "may", "if", "so", "such", "than", "then", "also", "both", "each", "any", "some", "most", "per", "out", "up",
    "own", "well", "must", "should", "would", "could", "plus", "within", "across", "including", "include",
    "includes", "required", "requirements", "preferred", "ability", "able", "using", "use", "used",
    # Recruiting fluff that survives every other filter ("next generation
    # platform", "world class team", "fast paced environment").
    "next", "generation", "world", "class", "cutting", "edge", "fast", "paced",
    "mission", "driven", "growing", "exciting", "dynamic", "passionate", "help",
    "build", "builds", "building",
})

# Phrases never cross punctuation or digits — those are sentence/list breaks.
_MINING_SEGMENT_SPLIT = re.compile(r"[^a-z\s]+")


def _is_role_phrase(phrase: str) -> bool:
    """A role NAME ("software engineer", "senior developer") is what the
    candidate applies AS, not a skill they could learn — never a gap row."""
    from discovery.normalizer import _pure_role_segment

    return _pure_role_segment(phrase)


def _mined_phrase_candidates(text: str) -> set[str]:
    """Candidate 2-3-word phrases: lowercase alpha tokens only, no stopword at
    either edge, no single-letter tokens, never crossing punctuation/digits."""
    phrases: set[str] = set()
    lower = (text or "").lower()[:MAX_MINING_CHARS]
    for segment in _MINING_SEGMENT_SPLIT.split(lower):
        tokens = segment.split()
        for size in (2, 3):
            for i in range(len(tokens) - size + 1):
                gram = tokens[i : i + size]
                if any(len(tok) < 2 for tok in gram):
                    continue
                if gram[0] in _MINING_STOPWORDS or gram[-1] in _MINING_STOPWORDS:
                    continue
                if any(tok in NOISE_TERMS for tok in gram):
                    continue
                phrase = " ".join(gram)
                if len(phrase) <= 48:
                    phrases.add(phrase)
    return phrases


def mine_market_phrases(
    considered_leads: list[dict],
    candidate_profile_text: str,
    *,
    now: datetime | None = None,
) -> dict[str, dict] | None:
    """Deterministic market-phrase mining for gaps the tech taxonomy can't see
    (wound care, lesson planning, TIG welding).

    Returns phrase -> {weight, postings, near_miss, companies, examples} for
    phrases that (a) recur in >= MIN_PHRASE_POSTINGS postings from
    >= MIN_PHRASE_COMPANIES distinct companies, (b) aren't already covered by
    the tech taxonomy or the candidate's own vocabulary, and (c) sit
    semantically near the candidate's profile (cosine >= MIN_PHRASE_COSINE).

    Returns None when only hash embeddings are available: hash cosine cannot
    validate field relevance, so mining is skipped entirely rather than
    shipping noise as gaps.
    """
    profile_vec = _field_vector((candidate_profile_text or "")[:2000])
    if profile_vec is None:
        return None
    now = now or datetime.now(timezone.utc)

    stats: dict[str, dict] = {}
    lead_phrases: list[tuple[dict, set[str]]] = []
    for lead in considered_leads:
        text = _lead_text(lead)
        if not text.strip():
            continue
        phrases = _mined_phrase_candidates(text)
        if not phrases:
            continue
        lead_phrases.append((lead, phrases))
        weight = _recency_weight(str(lead.get("created_at") or ""), now)
        near_miss = NEAR_MISS_LOW <= int(lead.get("score") or 0) <= NEAR_MISS_HIGH
        company = str(lead.get("company") or "").strip().lower()
        for phrase in phrases:
            row = stats.setdefault(
                phrase,
                {"weight": 0.0, "postings": 0, "near_miss": 0, "companies": set(), "examples": []},
            )
            row["weight"] += weight * (NEAR_MISS_BONUS if near_miss else 1.0)
            row["postings"] += 1
            if near_miss:
                row["near_miss"] += 1
            if company:
                row["companies"].add(company)

    total_postings = max(1, len(lead_phrases))
    survivors: dict[str, dict] = {}
    for phrase, row in stats.items():
        if row["postings"] < MIN_PHRASE_POSTINGS or len(row["companies"]) < MIN_PHRASE_COMPANIES:
            continue
        if total_postings >= MIN_CORPUS_FOR_SHARE_CEILING and row["postings"] / total_postings > MAX_PHRASE_SHARE:
            # Ubiquity means grammar, not skill: a phrase in a third of ALL
            # postings ("help build", "join our team") is how postings are
            # written, however semantically near the candidate's field it sits.
            continue
        if _is_role_phrase(phrase):
            continue  # a role name ("software engineer") is not a learnable gap
        if _find_terms(phrase):
            continue  # the taxonomy already surfaces this as a term gap
        if _contains_phrase(candidate_profile_text, phrase):
            continue  # candidate's own vocabulary, not an unknown
        # Embedding only runs on the few phrases left after the cheap filters.
        vec = _field_vector(phrase)
        if vec is None:
            continue
        cosine = sum(a * b for a, b in zip(profile_vec, vec, strict=False))
        if cosine < MIN_PHRASE_COSINE:
            continue  # market-wide boilerplate, not field demand
        survivors[phrase] = row

    if survivors:
        # Second pass over the SAME leads collects example roles for survivors
        # only, instead of holding a role dict per occurrence of every
        # candidate phrase in memory. Still O(leads * phrases_per_lead).
        survivor_keys = set(survivors)
        for lead, phrases in lead_phrases:
            score = int(lead.get("score") or 0)
            for phrase in phrases & survivor_keys:
                survivors[phrase]["examples"].append((score, _display_role(lead)))
    return survivors


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

    def _gap_sort_key(item: dict) -> tuple:
        return (-item["demand"], -item["near_miss_postings"], item["skill"])

    have = {t.lower() for t in candidate.all_terms} | {p.lower() for p in own_phrases}
    taxonomy_gap_rows = sorted(
        (
            _finalize(term, row)
            for term, row in demand.items()
            if term.lower() not in have and row["postings"] >= 2
        ),
        key=_gap_sort_key,
    )

    # Unknown-skill discovery beyond the tech taxonomy: without this a nurse or
    # welder sees strengths but never a gap they haven't already written down.
    mined = mine_market_phrases(considered, _profile_text(profile), now=now)
    mined_rows: list[dict] = []
    if mined:
        for phrase, row in mined.items():
            if phrase in have:
                continue
            examples = [role for _, role in sorted(row["examples"], key=lambda item: -item[0])[:MAX_EXAMPLE_ROLES]]
            mined_rows.append(
                {
                    "skill": phrase,
                    "category": "",
                    "demand": round(row["weight"], 1),
                    "postings": row["postings"],
                    "share_pct": round(100 * row["postings"] / max(1, total)),
                    "near_miss_postings": row["near_miss"],
                    "adjacent": False,
                    "example_roles": examples,
                    "first_step": MINED_FIRST_STEP,
                }
            )
        mined_rows = sorted(mined_rows, key=_gap_sort_key)[:MAX_MINED_GAPS]

    gap_rows = sorted(taxonomy_gap_rows + mined_rows, key=_gap_sort_key)[:MAX_GAPS]

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
        # True when only hash embeddings were available: phrase mining cannot
        # validate field relevance without real semantics, so no mined gaps ship.
        "phrase_mining_skipped": mined is None,
    }


def insights_summary_line(insights: dict) -> str:
    """One-line digest for logs/UI captions."""
    gaps = insights.get("gaps") or []
    if not gaps:
        return "No high-leverage skill gaps detected in the current market sample."
    top = ", ".join(g["skill"] for g in gaps[:3])
    return f"Top learning leverage right now: {top} (from {insights.get('sample_size', 0)} live postings)."
