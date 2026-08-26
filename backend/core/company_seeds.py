"""Auto-derived, keyless ATS company targets — the zero-config structured backbone.

The reliable keyless job source is the ATS JSON API (greenhouse/lever/ashby/...),
but it needs a company slug. Historically that slug came ONLY from a manually-typed
company watchlist, so the "zero-config ATS backbone" never actually fired for a fresh
user. This module closes that gap: it classifies the candidate's FIELD and REGION
from their profile and emits ``ats:<provider>:<slug>`` targets for well-known
companies in that field, with no manual config.

Lives in ``core`` (like occupations.py) so ``core.config`` can use it without
importing a project package — the import-boundary keeps ``core`` dependency-free.

Slug notes: these are stable, well-known ATS boards. A company that has since
migrated ATS just 404s, which the scrapers already treat as an empty board (never a
crash), so a stale slug wastes one scan slot at worst. Breadth for every field/region
comes from the keyless aggregator (Arbeitnow + The Muse); these seeds add
company-direct structured postings on top, strongest for tech.
"""

from __future__ import annotations

import json
import re

from pathlib import Path

# --- Field classification -----------------------------------------------------

# field -> signal keywords (matched against the profile's role/skills/summary text).
_FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "tech": (
        "software", "engineer", "developer", "programmer", "backend", "frontend",
        "full stack", "fullstack", "devops", "sre", "sde", "python", "java", "react",
        "node", "golang", "kubernetes", "cloud", "web developer", "mobile developer",
        "ios", "android", "qa", "security engineer", "platform",
    ),
    "data": (
        "data scientist", "data analyst", "data engineer", "machine learning",
        "ml engineer", "ai engineer", "analytics", "statistician", "nlp",
    ),
    "design": ("designer", "ux", "ui ", "product design", "graphic design", "motion"),
    "product": ("product manager", "product owner", "program manager"),
    "healthcare": (
        "nurse", "nursing", "physician", "doctor", "medical", "clinical", "therapist",
        "pharmacist", "dental", "caregiver", "paramedic", "surgeon", "healthcare",
    ),
    "finance": (
        "accountant", "accounting", "bookkeeper", "auditor", "financial analyst",
        "finance", "investment", "banker", "actuary", "controller",
    ),
    "legal": ("lawyer", "attorney", "paralegal", "legal", "counsel", "compliance"),
    "marketing": ("marketing", "seo", "growth", "brand", "content", "social media", "pr "),
    "sales": ("sales", "account executive", "business development", "account manager"),
    "education": ("teacher", "tutor", "instructor", "professor", "lecturer", "educator", "curriculum"),
    "trades": (
        "electrician", "plumber", "carpenter", "welder", "mechanic", "machinist",
        "hvac", "technician", "fabricator", "installer", "operator",
    ),
    "hospitality": ("chef", "cook", "baker", "barista", "server", "bartender", "hospitality", "hotel"),
}

# Ordered so a more specific field wins ties (data/design/product before generic tech).
_FIELD_ORDER = (
    "data", "design", "product", "healthcare", "finance", "legal", "marketing",
    "sales", "education", "trades", "hospitality", "tech",
)


def _profile_text(profile: dict) -> str:
    profile = profile or {}
    parts = [
        str(profile.get("desired_position") or ""),
        str(profile.get("s") or ""),
    ]
    for exp in profile.get("exp", []) or []:
        if isinstance(exp, dict):
            parts.append(str(exp.get("role") or ""))
    for skill in profile.get("skills", []) or []:
        if isinstance(skill, dict):
            parts.append(str(skill.get("n") or ""))
    return re.sub(r"\s+", " ", " ".join(parts)).lower()


def detect_field(profile: dict) -> str:
    """Best-guess field bucket for the candidate, or 'general' when unclear."""
    text = _profile_text(profile)
    if not text.strip():
        return "general"
    best_field = "general"
    best_hits = 0
    for field in _FIELD_ORDER:
        hits = sum(1 for kw in _FIELD_KEYWORDS[field] if kw.strip() in text)
        if hits > best_hits:
            best_hits = hits
            best_field = field
    return best_field


def detect_region(profile: dict) -> str:
    """Coarse region bucket from the CV-derived discovery location."""
    loc = str((profile or {}).get("_discovery_location") or "").lower()
    if not loc:
        return "global"
    if any(k in loc for k in ("india", "bengaluru", "bangalore", "mumbai", "delhi", "hyderabad", "pune", "chennai")):
        return "india"
    if any(k in loc for k in ("united states", "usa", "u.s", "america", "new york", "san francisco", "seattle", "austin", "boston", "chicago")):
        return "us"
    if any(k in loc for k in ("london", "united kingdom", "uk", "berlin", "germany", "france", "paris", "amsterdam", "netherlands", "europe", "ireland", "dublin", "spain", "madrid")):
        return "europe"
    return "global"


# --- Seed data (provider, slug) -----------------------------------------------
# Well-known, stable ATS boards. Tech has the deepest, most reliable coverage
# (greenhouse/lever/ashby dominate tech hiring); other fields lean on the keyless
# aggregator for breadth and add a few cross-industry names here.

_TECH_SEEDS: tuple[tuple[str, str], ...] = (
    # Greenhouse — the widest keyless board. Slugs verified against
    # boards-api.greenhouse.io/v1/boards/<slug>/jobs.
    ("greenhouse", "stripe"), ("greenhouse", "airbnb"), ("greenhouse", "dropbox"),
    ("greenhouse", "coinbase"), ("greenhouse", "databricks"), ("greenhouse", "gitlab"),
    ("greenhouse", "cloudflare"), ("greenhouse", "robinhood"), ("greenhouse", "doordash"),
    ("greenhouse", "instacart"), ("greenhouse", "pinterest"), ("greenhouse", "reddit"),
    ("greenhouse", "discord"), ("greenhouse", "twitch"), ("greenhouse", "roblox"),
    ("greenhouse", "samsara"), ("greenhouse", "affirm"), ("greenhouse", "asana"),
    ("greenhouse", "figma"), ("greenhouse", "elastic"), ("greenhouse", "hashicorp"),
    ("greenhouse", "datadog"), ("greenhouse", "mongodb"), ("greenhouse", "twilio"),
    ("greenhouse", "brex"), ("greenhouse", "flexport"), ("greenhouse", "benchling"),
    ("greenhouse", "airtable"), ("greenhouse", "sentry"), ("greenhouse", "postman"),
    ("greenhouse", "grafanalabs"), ("greenhouse", "sourcegraph"), ("greenhouse", "chime"),
    ("greenhouse", "duolingo"), ("greenhouse", "lyft"), ("greenhouse", "wise"),
    ("greenhouse", "monzo"), ("greenhouse", "deliveroo"), ("greenhouse", "starlingbank"),
    # Ashby — heavily used by newer/AI companies.
    ("ashby", "ramp"), ("ashby", "vercel"), ("ashby", "linear"), ("ashby", "openai"),
    ("ashby", "notion"), ("ashby", "mercury"), ("ashby", "replicate"),
    ("ashby", "anthropic"), ("ashby", "perplexityai"), ("ashby", "huggingface"),
    ("ashby", "cursor"), ("ashby", "modal"), ("ashby", "supabase"), ("ashby", "railway"),
    ("ashby", "deel"), ("ashby", "loom"), ("ashby", "clerk"),
    # Probed live before adding — a guessed slug just 404s and wastes a scan slot.
    ("ashby", "elevenlabs"), ("ashby", "decagon"), ("ashby", "abridge"),
    # Lever
    ("lever", "plaid"), ("lever", "attentive"), ("lever", "gopuff"),
    ("lever", "shieldai"), ("lever", "voleon"), ("lever", "wealthfront"),
    # Workable / SmartRecruiters / Recruitee / Personio broaden geography.
    ("workable", "wearedevelopers"), ("smartrecruiters", "Visa"),
    ("smartrecruiters", "Bosch"), ("personio", "personio"),
)

# Cross-industry / non-tech names on keyless ATSs (kept small; aggregator carries breadth).
_GENERAL_SEEDS: tuple[tuple[str, str], ...] = (
    ("greenhouse", "wayfair"), ("greenhouse", "warbyparker"), ("greenhouse", "peloton"),
    ("greenhouse", "sofi"), ("greenhouse", "betterment"), ("greenhouse", "wework"),
    ("greenhouse", "cargurus"), ("greenhouse", "zillow"), ("greenhouse", "eventbrite"),
    ("smartrecruiters", "Visa"), ("smartrecruiters", "Bosch"),
    ("smartrecruiters", "McDonalds"), ("smartrecruiters", "Ubisoft"),
)

# field -> the seed pools to draw from (in priority order).
_FIELD_SEEDS: dict[str, tuple[tuple[tuple[str, str], ...], ...]] = {
    "tech": (_TECH_SEEDS,),
    "data": (_TECH_SEEDS,),
    "design": (_TECH_SEEDS,),
    "product": (_TECH_SEEDS,),
    "finance": (_GENERAL_SEEDS, _TECH_SEEDS),
    "marketing": (_GENERAL_SEEDS, _TECH_SEEDS),
    "sales": (_GENERAL_SEEDS, _TECH_SEEDS),
    # Previously these returned [] and the ATS backbone never fired for them.
    # Large employers on keyless ATSs hire across every function, so a general
    # pool beats no pool; the aggregator still carries field-specific breadth.
    "general": (_GENERAL_SEEDS,),
}


def _load_workday_boards() -> list[dict]:
    """Live Workday boards discovered by ``scripts/probe_workday.py``.

    Kept as data rather than a literal because tenant/host/site slugs are not
    guessable and do drift — re-running the probe refreshes this file without a
    code change.
    """
    path = Path(__file__).resolve().parent / "workday_seeds.json"
    try:
        boards = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [b for b in boards if isinstance(b, dict) and b.get("tenant") and b.get("site")]


def workday_seed_targets(profile: dict, limit: int = 12) -> list[str]:
    """``ats:workday:...`` targets, one per live enterprise board.

    Workday hosts the employers the Greenhouse/Ashby startup pool structurally
    misses — insurers, banks, IT consultancies, healthcare and retail IT — which
    is where .NET, SQL Server and enterprise-cloud roles are actually posted.

    Unlike every other seed source these are *search* targets: Workday's list
    endpoint takes a keyword, so the candidate's own headline drives the query
    instead of pulling whole boards and discarding most of them. The keyword
    match is fuzzy, so scoring still does the real filtering.
    """
    # The bundled Workday inventory is a technology/enterprise-employer set,
    # not a field-neutral hospital or education inventory. Sending a nurse or
    # teacher profile through it creates a large irrelevant ATS flood.
    if detect_field(profile) not in _FIELD_SEEDS:
        return []
    query = _search_query(profile)
    targets = []
    for board in _load_workday_boards()[:max(1, limit)]:
        targets.append(
            f"ats:workday:{board['tenant']}:{board.get('host', 'wd5')}:{board['site']}:{query}"
        )
    return targets


def _search_query(profile: dict) -> str:
    """A short keyword string for search-first boards.

    Prefers the candidate's stated title, falls back to their top skills, and
    finally to the field bucket — always non-empty, since an empty Workday
    search returns the whole board.
    """
    # "desired_position" is the key ingest_resume.py / candidate_profile.json
    # actually populate; the others are legacy/alternate spellings kept for
    # profiles that use them. Checked BEFORE skills so a profile with a title
    # never falls through to the (dict-shaped) skills list below.
    for key in ("desired_position", "target_title", "title", "headline", "current_title"):
        value = str(profile.get(key) or "").strip()
        if value:
            return value[:60]

    skills = profile.get("skills") or profile.get("top_skills") or []
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(",")]
    # Each skill is normally {"n": "...", "cat": "..."} (see candidate_profile.json)
    # -- str()-ing the dict itself produced a literal "{'n': '...', 'cat': '...'}"
    # search string, which is what actually got POSTed as Workday's searchText.
    names = [
        str(s.get("n") or s.get("name") or "").strip() if isinstance(s, dict) else str(s).strip()
        for s in skills
    ]
    picked = [name for name in names if name][:3]
    if picked:
        return " ".join(picked)[:60]

    field = detect_field(profile)
    return "engineer" if field in ("tech", "data") else field


def ats_seed_targets(profile: dict, limit: int = 40) -> list[str]:
    """``ats:<provider>:<slug>`` targets for the candidate's detected field/region.

    Returns [] for fields where curated ATS slugs would be unreliable (healthcare,
    trades, education, hospitality, legal, general) — the keyless aggregator + HN/RSS
    sources cover those, and a wrong guess would only waste scan slots.
    """
    field = detect_field(profile)
    pools = _FIELD_SEEDS.get(field)
    if not pools:
        return []
    seen: set[str] = set()
    targets: list[str] = []
    for pool in pools:
        for provider, slug in pool:
            key = f"{provider}:{slug}"
            if key in seen:
                continue
            seen.add(key)
            targets.append(f"ats:{provider}:{slug}")
            if len(targets) >= max(1, limit):
                return targets
    return targets
