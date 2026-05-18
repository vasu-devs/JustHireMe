"""
query_gen.py — Generates profile-tailored job search queries.

Called at the start of every scan.  For each job-board domain the user has
configured, it produces ONE focused Google site: query that targets the
candidate's actual role, skills, and project evidence rather than generic keywords.
"""

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from pydantic import BaseModel
from core.logging import get_logger

_log = get_logger(__name__)


class _Plan(BaseModel):
    queries: list[str]


def _extract_domains(urls: list[str]) -> tuple[list[str], list[str]]:
    """
    Split the configured URL list into:
      - site_domains : bare domain strings extracted from 'site:...' entries
      - passthrough  : all other URLs (RSS, API, direct) that stay unchanged
    """
    site_domains: list[str] = []
    passthrough:  list[str] = []

    for url in urls:
        if url.strip().lower().startswith("site:"):
            # site:boards.greenhouse.io "AI" OR ...  →  boards.greenhouse.io
            raw = url.strip()[5:]          # strip 'site:'
            domain = raw.split()[0].strip().strip('"')
            if domain:
                site_domains.append(domain)
        else:
            passthrough.append(url)

    return site_domains, passthrough


def _detect_experience_level(profile: dict) -> str:
    """
    Infer the candidate's seniority level from their profile.
    Returns one of: "fresher", "junior", "mid", "senior"
    """
    exp_entries = profile.get("exp", []) or []
    real_roles = []
    for entry in exp_entries:
        role = str(entry.get("role", "")).lower() if isinstance(entry, dict) else ""
        if not role:
            continue
        if any(kw in role for kw in ("intern", "trainee", "student", "assistant only")):
            continue
        real_roles.append(entry)

    total_months = sum(_period_months(str(entry.get("period", ""))) for entry in real_roles if isinstance(entry, dict))
    senior_titles = sum(
        1 for entry in real_roles
        if any(kw in str(entry.get("role", "")).lower() for kw in ("senior", "lead", "principal", "staff", "head of", "manager"))
    )
    project_count = len(profile.get("projects", []) or [])

    if senior_titles >= 1 and total_months >= 36:
        return "senior"
    if total_months >= 60:
        return "senior"
    if total_months >= 24 or len(real_roles) >= 2:
        return "mid"
    if real_roles or project_count >= 2:
        return "junior"
    return "fresher"


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _period_months(period: str) -> int:
    if not period:
        return 0
    text = str(period).lower()
    text = re.sub(r"\bpresent\b|\bcurrent\b|\bnow\b|\btoday\b", "2099-12", text)
    pairs = re.findall(
        r"([a-z]{3,4})?\s*(\d{4})\s*(?:to|-|–|—|->|→)\s*([a-z]{3,4})?\s*(\d{4})",
        text,
    )
    months = 0
    for sm, sy, em, ey in pairs:
        try:
            sy_i, ey_i = int(sy), int(ey)
        except ValueError:
            continue
        s_m = _MONTHS.get((sm or "jan")[:4], 1)
        e_m = _MONTHS.get((em or "dec")[:4], 12)
        delta = (ey_i - sy_i) * 12 + (e_m - s_m) + 1
        if delta > 0:
            months += min(delta, 600)
    if not pairs:
        years = re.search(r"(\d{1,2})\s*\+?\s*(?:years|yrs|yoe)", text)
        if years:
            months = int(years.group(1)) * 12
    return months


def _seniority_hint(level: str) -> str:
    hints = {
        "fresher": '"intern" OR "new grad" OR "entry level" OR "junior"',
        "junior": '"junior" OR "entry level" OR "associate" OR "coordinator"',
        "mid": '"specialist" OR "associate" OR "manager" OR "consultant"',
        "senior": '"senior" OR "lead" OR "principal" OR "manager"',
    }
    return hints.get(level, '"job" OR "role" OR "hiring"')


def _role_terms(profile: dict) -> list[str]:
    chunks = [
        str(profile.get("s") or ""),
        *(str(e.get("role", "")) for e in profile.get("exp", []) if isinstance(e, dict)),
        *(str(p.get("title", "")) for p in profile.get("projects", []) if isinstance(p, dict)),
    ]
    text = " ".join(chunks).lower()
    catalog = [
        ("marketing", ("marketing", "growth", "seo", "content")),
        ("sales", ("sales", "business development", "account executive", "bd")),
        ("product", ("product manager", "product", "pm")),
        ("design", ("designer", "design", "ui/ux", "ux")),
        ("data", ("data analyst", "data scientist", "analytics", "bi")),
        ("finance", ("finance", "accounting", "investment")),
        ("operations", ("operations", "ops", "supply chain")),
        ("customer success", ("customer success", "support", "solutions")),
        ("human resources", ("hr", "human resources", "recruiter", "talent")),
        ("software", ("software", "engineer", "developer", "backend", "frontend", "full stack", "ai", "ml")),
    ]
    roles = [label for label, aliases in catalog if any(alias in text for alias in aliases)]
    return roles[:3] or ["job", "role", "hiring"]


def _profile_search_terms(profile: dict) -> list[str]:
    target_role = str(profile.get("s") or "").strip()
    recent_roles = [str(e.get("role", "")).strip() for e in profile.get("exp", []) if isinstance(e, dict) and e.get("role")]
    skills = [str(s.get("n", "")).strip() for s in profile.get("skills", []) if isinstance(s, dict) and s.get("n")]
    terms = [target_role, *recent_roles[:2], *skills[:4], *_role_terms(profile)]
    clean: list[str] = []
    seen: set[str] = set()
    for term in terms:
        term = re.sub(r"\s+", " ", term).strip(" ,.;:-")
        if not term:
            continue
        # Keep API search terms compact; long summaries make bad query params.
        words = term.split()
        if len(words) > 5:
            term = " ".join(words[:5])
        key = term.lower()
        if key not in seen:
            seen.add(key)
            clean.append(term)
    return clean[:8] or ["job"]


def _set_query_param(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params[key] = value
    return urlunparse(parsed._replace(query=urlencode(params)))


def _enrich_passthrough_targets(urls: list[str], profile: dict) -> list[str]:
    if not urls:
        return urls
    terms = _profile_search_terms(profile)
    primary = terms[0]
    broad_role = next((t for t in terms if t.lower() not in {"job", "role", "hiring"}), primary)
    out: list[str] = []
    for url in urls:
        lower = url.lower()
        if "remotive.com/api/remote-jobs" in lower and "search=" not in lower:
            out.append(_set_query_param(url, "search", primary))
        elif "jobicy.com/api" in lower and "tag=" not in lower:
            out.append(_set_query_param(url, "tag", broad_role))
        else:
            out.append(url)
    return out


def _market_focus(value) -> str:
    focus = str(value or "global").strip().lower()
    return "india" if focus in {"india", "in", "indian", "indian_startups"} else "global"


def _india_clause(query: str) -> str:
    lower = query.lower()
    if any(term in lower for term in ("india", "indian", "bangalore", "bengaluru", "mumbai", "delhi", "pune", "hyderabad")):
        return query
    return f'{query} (India OR Indian OR Bengaluru OR Bangalore OR Mumbai OR Pune OR Hyderabad OR Delhi OR "Indian startup")'


def generate(profile: dict, urls: list[str], market_focus: str = "global") -> list[str]:
    """
    Main entry point.  Returns a new URL list where every 'site:' entry has
    been replaced with a profile-tailored query, while RSS/API/direct URLs
    are kept as-is.
    """
    from llm import call_llm

    focus = _market_focus(market_focus)
    site_domains, passthrough = _extract_domains(urls)
    passthrough = _enrich_passthrough_targets(passthrough, profile)

    if not site_domains:
        return passthrough  # API/RSS/direct targets may still have been enriched.

    # ── Build a compact profile summary for the prompt ──────────────────────
    target_role      = (profile.get("s") or "General job seeker").strip()
    skills           = [s["n"] for s in profile.get("skills", []) if s.get("n")]
    experience_level = _detect_experience_level(profile)
    role_terms       = _role_terms(profile)

    seniority_hint = _seniority_hint(experience_level)

    # Collect unique stack tokens from projects
    stack_tokens: list[str] = []
    for proj in profile.get("projects", []):
        raw = proj.get("stack", [])
        items = raw if isinstance(raw, list) else [x.strip() for x in str(raw).split(",") if x.strip()]
        stack_tokens.extend(items[:4])
    stack_tokens = list(dict.fromkeys(stack_tokens))[:20]  # dedupe, cap at 20

    # Most recent role titles
    recent_roles = [e.get("role", "") for e in profile.get("exp", []) if e.get("role")][:3]

    # ── Prompt ──────────────────────────────────────────────────────────────
    system = """You are JustHireMe's production query-planning agent: a senior global recruiter and Boolean search expert.
Your job is to write highly targeted Google site: search queries that will surface
the most relevant job postings for a specific candidate.

Rules:
- Output exactly ONE query per domain — no more.
- Each query must start with   site:<domain>
- Use 2-4 specific role, industry, tool, or skill terms the candidate actually knows.
- Do not assume the user is a software/tech candidate; support any field.
- Prefer role-specific terms over generic ones ("Growth Marketer" beats "Marketing", "SEO Specialist" beats "Content").
- Use the detected candidate seniority as a preference, not a hard global filter.
- Do not exclude other levels unless the profile is clearly unsuitable for that level.
- Use OR between alternatives: site:jobs.lever.co "FastAPI" ("junior" OR "entry level")
- Never add quotation marks around the whole query, only around individual terms.
- Never invent skills, locations, seniority, visa status, degrees, employers, or clearance.
- Avoid query spam: do not include more than 6 OR alternatives in one query.
- Return only the list of queries — no extra commentary."""

    if focus == "india":
        system += """
- This scan is INDIA ONLY. Add India/Indian startup location intent to every query.
- Prefer India-friendly terms such as India, Indian, Bengaluru, Bangalore, Mumbai, Pune, Hyderabad, Delhi, and "Indian startup".
- Do not produce broad global remote queries for this mode."""

    user = f"""CANDIDATE PROFILE
Target role / summary : {target_role}
Detected seniority    : {experience_level.upper()} - preferred seniority query terms: {seniority_hint}
Market focus          : {"INDIA ONLY - Indian startups and India-based roles" if focus == "india" else "Global"}
Top skills            : {', '.join(skills[:15])}
Detected role themes  : {', '.join(role_terms)}
Project/tool stack    : {', '.join(stack_tokens)}
Recent role titles    : {', '.join(recent_roles) if recent_roles else 'none (fresher/student)'}

JOB BOARD DOMAINS (one query each):
{chr(10).join(f'- {d}' for d in site_domains)}

Generate the queries now."""

    try:
        result = call_llm(system, user, _Plan, step="query_gen")
        smart = [q.strip() for q in result.queries if q.strip()]
    except Exception as exc:
        _log.warning("LLM failed (%s), falling back to default queries", exc)
        # Fallback: build simple queries from top skills or inferred role themes.
        top_terms = _profile_search_terms(profile)[:3] or skills[:3] or role_terms[:3] or [target_role]
        top = " OR ".join(f'"{s}"' for s in top_terms)
        smart = [f"site:{d} ({top}) ({seniority_hint})" for d in site_domains]

    if focus == "india":
        smart = [_india_clause(q) for q in smart]

    _log.info("Generated %s queries for %s domains", len(smart), len(site_domains))
    for q in smart:
        _log.debug("  → %s", q)

    return passthrough + smart
