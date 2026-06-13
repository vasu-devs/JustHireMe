from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from discovery.lead_intel import budget_from_text as budget_from_text
from discovery.lead_intel import fit_bullets as fit_bullets
from discovery.lead_intel import followup_sequence as followup_sequence
from discovery.lead_intel import lead_id as lead_id
from discovery.lead_intel import location_from_text as location_from_text
from discovery.lead_intel import outreach_drafts as outreach_drafts
from discovery.lead_intel import proof_snippet as proof_snippet
from discovery.lead_intel import signal_quality as signal_quality
from discovery.lead_intel import tech_stack_from_text as tech_stack_from_text
from discovery.lead_intel import urgency_from_text as urgency_from_text


MAX_AGE_DAYS = 7

FRESHER_TERMS = (
    "fresher", "new grad", "new graduate", "graduate", "intern",
    "internship", "trainee", "apprentice", "campus", "no experience required",
)

JUNIOR_TERMS = (
    "junior", "jr.", "jr ", "entry level", "entry-level", "fresher",
    "new grad", "new graduate", "graduate", "associate", "intern",
    "internship", "trainee", "apprentice", "early career", "campus",
    "software engineer i", "software engineer 1", "developer i",
    "developer 1", "engineer i", "engineer 1", "sde i", "sde 1",
    "level 1", "level i", "l1", "0-1 year", "0-2 years", "0 to 2 years",
    "1-2 years", "1 to 2 years", "1+ year", "no experience required",
)

MID_TERMS = (
    "mid-level", "mid level", "mid senior", "intermediate",
    "software engineer ii", "software engineer 2", "developer ii",
    "developer 2", "engineer ii", "engineer 2", "sde ii", "sde 2",
    "level 2", "level ii", "l2", "3+ years", "3 years", "4+ years",
    "4 years",
)

SENIOR_TERMS = (
    "senior", "sr.", "sr ", "lead", "staff", "principal", "manager",
    "director", "head of", "architect", "expert", "5+ years", "5 years",
    "7+ years", "7 years", "10+ years", "10 years", "software engineer iii",
    "software engineer 3", "developer iii", "developer 3", "engineer iii",
    "engineer 3", "sde iii", "sde 3", "level 3", "level iii", "l3",
)


def cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)


def parse_date(value: str) -> datetime | None:
    if not value or not value.strip():
        return None
    text = value.strip().lower()
    now = datetime.now(timezone.utc)

    if text in ("just now", "moments ago", "seconds ago", "today"):
        return now
    if text == "yesterday":
        return now - timedelta(days=1)

    match = re.search(r"(\d+)\s*(second|minute|hour|day|week|month|year)s?\s*ago", text)
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        delta = {
            "second": timedelta(seconds=amount),
            "minute": timedelta(minutes=amount),
            "hour": timedelta(hours=amount),
            "day": timedelta(days=amount),
            "week": timedelta(weeks=amount),
            "month": timedelta(days=amount * 30),
            "year": timedelta(days=amount * 365),
        }.get(unit)
        return now - delta if delta else None

    raw = value.strip()

    # RFC-2822 feed dates ("Thu, 11 Jun 2026 10:00:00 GMT"): strptime's %z can't
    # match timezone names like GMT, so use the stdlib email parser first.
    if re.match(r"^[a-z]{3},\s*\d{1,2}\s+[a-z]{3}\s+\d{4}", text):
        try:
            parsed = parsedate_to_datetime(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (ValueError, TypeError):
            pass

    # ISO 8601, including fractional seconds (Lever emits millisecond precision).
    iso_candidate = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(iso_candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        pass

    original = text.strip()
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%d %B %Y",
    ):
        try:
            parsed = datetime.strptime(original, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue
    return None


def is_recent(date_str: str) -> bool:
    # Fail closed: an empty/unparseable date can't be confirmed recent, so for an
    # auto-apply pipeline treat it as NOT recent. Callers that have a fresh-source
    # hint (e.g. a past-week query) override this at the call site.
    if not date_str:
        return False
    parsed = parse_date(date_str)
    if parsed is None:
        return False
    return parsed >= cutoff()


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", strip_html_text(text)).strip()


def company_from_url(url: str) -> str:
    try:
        host = urlparse(url if "://" in url else "https://" + url).netloc.lower()
    except ValueError:
        host = ""
    host = host.replace("www.", "")
    if not host:
        return "Manual Lead"
    first = host.split(".")[0]
    return first[:1].upper() + first[1:]


def strip_html_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<p(?:\s+[^>]*)?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _lead_text(lead: dict) -> str:
    meta = lead.get("source_meta") or {}
    if isinstance(meta, dict):
        meta_text = " ".join(str(v) for v in meta.values() if isinstance(v, (str, int, float)))
    else:
        meta_text = ""
    return "\n".join(
        str(lead.get(key, ""))
        for key in ("title", "company", "platform", "description", "posted_date")
    ) + "\n" + meta_text


def _experience_years(text: str) -> list[int]:
    years: list[int] = []
    for match in re.finditer(r"(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*(?:years|yrs|yoe)", text, flags=re.I):
        years.append(max(int(match.group(1)), int(match.group(2))))
    for match in re.finditer(r"(\d{1,2})\s*\+?\s*(?:years|yrs|yoe)", text, flags=re.I):
        years.append(int(match.group(1)))
    return years


def _has_seniority_term(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        pattern = re.escape(term.strip()).replace(r"\ ", r"\s+")
        if re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text, flags=re.I):
            return True
    return False


def classify_job_seniority(lead: dict) -> str:
    text = _lead_text(lead).lower()
    years = _experience_years(text)
    max_years = max(years) if years else 0

    if _has_seniority_term(text, SENIOR_TERMS) or max_years >= 5:
        return "senior"
    if _has_seniority_term(text, MID_TERMS) or max_years >= 3:
        return "mid"
    if _has_seniority_term(text, FRESHER_TERMS):
        return "fresher"
    if _has_seniority_term(text, JUNIOR_TERMS):
        return "junior"
    if years:
        if max_years <= 1:
            return "fresher"
        if max_years <= 2:
            return "junior"
    return "unknown"


def looks_role_like(text: str) -> bool:
    lower = text.lower()
    # Field-agnostic: recognize a role/occupation in ANY field (healthcare,
    # trades, business, education, creative, ...), not just software. Reuses the
    # broad occupation vocabulary so a "Registered Nurse" or "Electrician"
    # posting is no longer dropped at HN/RSS ingestion as "not role-like".
    from core.occupations import EMPLOYMENT_TERMS, OCCUPATION_TERMS

    extra = (
        "software", "frontend", "front-end", "backend", "full stack",
        "full-stack", "data", "ai", "ml", "devops", "sre", "qa", "mobile",
        "product", "solution architect", "solutions architect",
    )
    return any(term in lower for term in OCCUPATION_TERMS) \
        or any(term in lower for term in EMPLOYMENT_TERMS) \
        or any(term in lower for term in extra)


def looks_like_hn_job_post(text: str) -> bool:
    clean = strip_html_text(text)
    if len(clean) < 80:
        return False

    first_line = clean.splitlines()[0]
    lower = clean.lower()
    role_terms = (
        "engineer", "developer", "software", "backend", "front-end", "frontend",
        "full-stack", "full stack", "devops", "sre", "site reliability", "data",
        "analyst", "designer", "product", "security", "machine learning", "ml",
        "ai", "research", "infrastructure", "platform", "mobile", "ios",
        "android", "qa", "support", "solution architect", "solutions architect",
        "solutions", "architect", "sales", "marketing", "operations", "founding",
    )
    hiring_terms = (
        "remote", "onsite", "on-site", "hybrid", "visa", "salary", "apply",
        "full-time", "part-time", "contract", "intern", "hiring", "equity",
        "location", "relocation",
    )

    has_role = any(term in lower for term in role_terms)
    has_hiring_signal = any(term in lower for term in hiring_terms)
    if first_line.count("|") >= 2 and has_role:
        return True
    if has_role and has_hiring_signal and any(
        phrase in lower
        for phrase in ("we are hiring", "we're hiring", "is hiring", "are hiring", "hiring for")
    ):
        return True
    return first_line.count("|") >= 1 and has_role and has_hiring_signal


def hn_company_role(text: str, author: str = "") -> tuple[str, str]:
    clean = strip_html_text(text)
    first_line = clean.splitlines()[0].strip() if clean else ""
    pipe_parts = [part.strip(" -|:") for part in first_line.split("|") if part.strip()]
    company = (pipe_parts[0] if pipe_parts else author or "HN Hiring")[:100]

    role_noise = {
        "remote", "onsite", "on-site", "hybrid", "visa", "relocation",
        "full-time", "part-time", "contract", "internship",
    }

    def clean_role(raw: str) -> str:
        role = re.sub(r"^\s*(?:\d+\s*[\).:-]?\s*)+", "", raw or "").strip(" -|:;,.")
        role = re.sub(r"\s+", " ", role)
        return role[:140]

    for segment in pipe_parts[1:]:
        lower = segment.lower()
        if any(noise == lower or noise in lower for noise in role_noise):
            continue
        if looks_role_like(segment):
            return company, clean_role(segment)

    role_block = re.search(
        r"(?:hiring\s+for\s+(?:multiple\s+)?(?:core\s+)?roles?|roles?|positions?)\s*:\s*([^\n.]+)",
        clean,
        flags=re.I,
    )
    if role_block:
        raw = role_block.group(1)
        for part in re.split(r",|;|\band\b", raw):
            role = clean_role(part)
            if role and looks_role_like(role):
                return company, role

    for line in clean.splitlines()[1:8]:
        role = clean_role(line)
        if role and looks_role_like(role) and len(role.split()) <= 8:
            return company, role

    return company, f"Hiring at {company}" if company else "HN hiring lead"


# Legacy private aliases used while source adapters migrate.
_is_recent = is_recent
_strip_html_text = strip_html_text
_looks_like_hn_job_post = looks_like_hn_job_post
_hn_company_role = hn_company_role
