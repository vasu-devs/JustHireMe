"""Global-remote-aware shortlist — corrected criterion.

Moved out of ``scripts/shortlist_global.py`` so both the CLI script and
``reporting.service`` (the dashboard's "Shortlisted" funnel stage) call the
same tested classifier instead of two copies drifting apart.

The candidate is based in India but does NOT need the company to be in India
or APAC. They need to work from home, from any country, under any employment
mechanism (direct employee, EOR, contractor/B2B), optimising for pay.
Location requirements on the *company* are irrelevant; what matters is
whether an India-resident could actually be hired into the role.

Every lead is classified into a hireability band from its title/location/
description text:

    A  hire-from-anywhere / worldwide / any-timezone remote
    B  company has an India entity or India office
    C  hires via an EOR (Deel, Remote.com, Oyster, ...) or contractor/B2B
    D  region-locked (US-only, must reside in ..., onsite, hybrid, ...)
    U  no signal either way

Only A/B/C are kept; D and U are excluded (D explicitly, U because we have
no evidence the company would hire an India-resident — absence of a
positive signal is not treated as a green light). Deterministic regex only,
no LLM calls.
"""
from __future__ import annotations

import re
from collections import Counter

# Same broad AI/LLM relevance signal as shortlist.py — deliberately wide,
# better a few borderline hits than silently dropping a genuine AI role.
_AI_RE = re.compile(
    r"\b("
    r"ai|artificial intelligence|machine learning|ml engineer|ml ops|mlops|"
    r"llm|large language model|genai|generative ai|gpt|claude|anthropic|openai|"
    r"langchain|langgraph|rag|retrieval augmented|nlp|natural language|"
    r"chatbot|conversational ai|voice agent|deep learning|neural network|"
    r"data scientist|prompt engineer|agentic|mcp|computer vision"
    r")\b",
    re.IGNORECASE,
)

# ---- Band A: hire-from-anywhere / worldwide / any-timezone ----------------
_GLOBAL_RE = re.compile(
    r"\b("
    r"work from anywhere|hire[sd]? (?:from )?anywhere|anywhere in the world|"
    r"remote,? ?worldwide|worldwide remote|remote across the globe|"
    r"remote from any ?(?:country|location)|remote,? any (?:country|location)|"
    r"globally distributed|distributed globally|distributed team.{0,20}(?:world|global)|"
    r"global(?:ly)? remote|remote[- ]first.{0,20}global|"
    r"any ?time ?zone|all time ?zones|"
    r"open to (?:any|all) (?:location|countries|timezones)|"
    r"regardless of (?:location|timezone|country)|"
    r"no location restrictions?|international remote"
    r")\b",
    re.IGNORECASE,
)

# ---- Band B: company has an India entity or India office ------------------
_INDIA_RE = re.compile(
    r"\b("
    r"india|indian entity|bengaluru|bangalore|hyderabad|pune|gurgaon|gurugram|"
    r"noida|chennai|mumbai|delhi|kolkata|ahmedabad"
    r")\b",
    re.IGNORECASE,
)

# ---- Band C: EOR or contractor/B2B -----------------------------------------
_EOR_RE = re.compile(
    r"\b("
    r"deel|remote\.com|oyster ?hr?|velocity global|papaya global|multiplier|"
    r"globalization partners|g-p\.com|justworks|rippling global|omnipresent|"
    r"employer of record|\beor\b|\bcontractor\b|\bb2b\b|1099 contractor|"
    r"freelance contract|hire[sd]? as an? contractor|"
    r"no (?:visa )?sponsorship required|does not require (?:visa )?sponsorship"
    r")\b",
    re.IGNORECASE,
)

# ---- Band D, strong: decisive region/citizenship lock -- always excludes,
# wins even over an incidental "remote"/global mention elsewhere in the post.
_REGION_LOCK_STRONG_RE = re.compile(
    r"\b("
    r"us(?:a)? only|u\.s\.? only|united states only|uk only|eu only|"
    r"only (?:candidates|applicants|residents) (?:based |located )?in (?:the )?"
    r"(?:us|usa|united states|uk|canada|europe|eu)|"
    r"must (?:be |)(?:currently )?(?:reside|be located|be based|live) in (?:the )?"
    r"(?:us|usa|united states|u\.s\.?|uk|united kingdom|canada|europe|eu member state|australia)|"
    r"authorized to work in (?:the )?(?:us|usa|united states|uk|canada)|"
    r"work authorization (?:in|for) (?:the )?(?:us|usa|united states|uk|canada)|"
    r"must have (?:a )?valid (?:us |uk |)?work (?:visa|permit)|"
    r"(?:us|uk|eu) citizens? only|green card holders? (?:only|required)|"
    r"must relocate to (?!india)"
    r")\b",
    re.IGNORECASE,
)

# ---- Band D, weak: generic onsite/hybrid/no-remote -- only excludes when
# nothing else earns the lead a positive band (a "remote-first, optional
# hybrid office" post should not be sunk by the word "hybrid" alone).
_REGION_LOCK_WEAK_RE = re.compile(
    r"\b(onsite|on-site|in-office|hybrid|no remote|not remote|without remote)\b",
    re.IGNORECASE,
)


def _lead_text(lead: dict) -> str:
    return " ".join([
        str(lead.get("title", "")),
        str(lead.get("location", "")),
        str(lead.get("description", "")),
    ])


def is_ai_relevant(lead: dict) -> bool:
    return bool(_AI_RE.search(_lead_text(lead)))


def classify_geo(lead: dict) -> tuple[str, str]:
    """Band (A/B/C/D/U) + the matched phrase, per the CORRECTED criterion:
    hireability of an India-resident, not company location."""
    text = _lead_text(lead)

    m = _REGION_LOCK_STRONG_RE.search(text)
    if m:
        return "D", m.group(0)

    m = _GLOBAL_RE.search(text)
    if m:
        return "A", m.group(0)

    m = _EOR_RE.search(text)
    if m:
        return "C", m.group(0)

    m = _INDIA_RE.search(text)
    if m:
        return "B", m.group(0)

    m = _REGION_LOCK_WEAK_RE.search(text)
    if m:
        return "D", m.group(0)

    return "U", ""


_KEEP_BANDS = {"A": 0, "C": 1, "B": 2}  # sort preference among kept bands


def filtered_ranked_leads(leads: list[dict], *, limit: int | None = None) -> list[dict]:
    """AI/LLM-relevant AND hireable-from-India (band A/B/C), ranked by CGFE
    fit score first, signal_score (posting quality/freshness, the CGFE
    engine's separate untouched axis) as tiebreak, band preference last.
    Excludes discarded/rejected leads -- they were already ruled out."""
    kept = []
    for lead in leads:
        if str(lead.get("status") or "") in {"discarded", "rejected"}:
            continue
        if not is_ai_relevant(lead):
            continue
        band, evidence = classify_geo(lead)
        if band not in _KEEP_BANDS:
            continue
        enriched = dict(lead)
        enriched["geo_band"] = band
        enriched["geo_evidence"] = evidence
        kept.append(enriched)

    kept.sort(
        key=lambda lead: (
            int(lead.get("score") or 0),
            int(lead.get("signal_score") or 0),
            -_KEEP_BANDS[lead["geo_band"]],
        ),
        reverse=True,
    )
    return kept[:limit] if limit else kept


def band_report(leads: list[dict]) -> dict:
    """Raw band distribution + AI-relevance count over all non-discarded
    leads (independent of each other), for the human-readable summary."""
    live = [lead for lead in leads if str(lead.get("status") or "") not in {"discarded", "rejected"}]
    counts = Counter(classify_geo(lead)[0] for lead in live)
    for band in ("A", "B", "C", "D", "U"):
        counts.setdefault(band, 0)
    ai_relevant = sum(1 for lead in live if is_ai_relevant(lead))
    return {"total": len(leads), "live": len(live), "ai_relevant": ai_relevant, "bands": dict(counts)}
