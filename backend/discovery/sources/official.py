"""First-party career-site adapters with stable public interfaces.

These are deliberately narrow: only public job facts are projected. Application
questions, demographic surveys, and candidate-form schemas are never retained.
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import httpx

from discovery.normalizer import clean_text, strip_html_text
from discovery.sources.common import json_get, json_post, text_get, text_lead


DELIVEROO_ROLES_API = "https://careers.deliveroo.co.uk/wp-json/wp/v2/roles"
DELIVEROO_INDIA_CAREERS = "https://careers.deliveroo.co.uk/locations/india/"
ZEQO_CAREERS = "https://zeqo.in/careers"
AICTE_INTERNSHIPS = "https://internship.aicte-india.org/internships.php"
AICTE_CSE_SEARCH = f"{AICTE_INTERNSHIPS}?future=intern"
AICTE_DETAILS_BASE = "https://internship.aicte-india.org/"
_ZEQO_CARD = re.compile(
    r'<div class="bg-white border border-border-theme rounded-3xl[^>]*>(.*?)'
    r'(?=<div class="bg-white border border-border-theme rounded-3xl|</main>)',
    re.I | re.S,
)
_ZEQO_TITLE = re.compile(r'<h2[^>]*>(.*?)</h2>', re.I | re.S)
_ZEQO_FACT = re.compile(r'<span[^>]*>(.*?)</span>', re.I | re.S)
_ZEQO_APPLY = re.compile(r'<a\s+href="mailto:[^"]+"[^>]*>\s*Apply Now', re.I | re.S)
_ZEQO_MONTHLY_PAY = re.compile(
    r"₹\s*([\d,]+)(?:\s*[-–]\s*₹?\s*([\d,]+))?\s*/\s*mo",
    re.I,
)
_AICTE_CARD = re.compile(
    r'<div\s+class=["\']internships-list["\']>(.*?)'
    r'(?=<div\s+class=["\']internships-list["\']|<div\s+class=["\']pagination|</main>)',
    re.I | re.S,
)
_AICTE_DETAIL_LINK = re.compile(
    r'href=["\'](?P<href>internship-details[.]php[?]uid=[^"\']+)["\']',
    re.I,
)
_AICTE_SECTION = re.compile(
    r'<section[^>]*>\s*<h4[^>]*>(?P<title>.*?)</h4>(?P<body>.*?)</section>',
    re.I | re.S,
)
_AICTE_TECH_TITLE = re.compile(
    r"\b(software|developer|programmer|programming|data(?:\s+(?:analyst|engineer|science|scientist))?|"
    r"machine learning|artificial intelligence|ai\s*(?:[/ -]\s*)?ml|\bai\b|\bml\b|"
    r"cloud|devops|security|cyber|"
    r"quality assurance|test(?:ing)?|embedded|firmware|backend|frontend|full[ -]?stack|"
    r"android|ios|web(?:site)?|computer|robotics?|automation|internet of things|iot|"
    r"blockchain|database|network(?:ing)?|systems? engineer)\b",
    re.I,
)
_AICTE_MONTHLY_PAY = re.compile(
    r"(?P<min>\d[\d,]*)\s*(?:(?:to|[-–])\s*(?P<max>\d[\d,]*))?\s*/?\s*month",
    re.I,
)
IBM_SEARCH_API = "https://www-api.ibm.com/search/api/v2"
IBM_INDIA_EARLY_CAREER_SEARCH = (
    "https://www.ibm.com/careers/search?field_keyword_18%5B0%5D=Internship"
)
IBM_EARLY_CAREER_LEVELS = ("Internship", "Entry Level")
_IBM_SOURCE_FIELDS = (
    "title",
    "url",
    "description",
    "body",
    "country",
    "language",
    "dcdate",
    "effectivedate",
    "expiredate",
    "processedtime",
    "keywords",
    "field_keyword_08",  # career area
    "field_keyword_18",  # experience level
    "field_keyword_19",  # display location
)
_IBM_WORKPLACE_BEFORE_LEVEL = re.compile(r"\b(Hybrid|Remote)\s+(?:Internship|Entry Level)\b", re.I)

AMAZON_SEARCH_API = "https://www.amazon.jobs/en/search.json"
AMAZON_INDIA_CAREERS = "https://www.amazon.jobs/en/search?country=IND"
AMAZON_CSE_SEARCHES = (
    "intern",
    "software development engineer",
    "machine learning engineer",
    "data engineer",
    "quality assurance engineer",
    "system development engineer",
    "cloud support engineer",
    "security engineer",
)
MICROSOFT_SEARCH_API = "https://apply.careers.microsoft.com/api/pcsx/search"
MICROSOFT_CAREERS_BASE = "https://apply.careers.microsoft.com"
MICROSOFT_INDIA_CAREERS = "https://apply.careers.microsoft.com/careers?location=India"
MICROSOFT_CSE_SEARCHES = (
    "intern",
    "software engineer",
    "machine learning engineer",
    "data engineer",
    "cloud engineer",
    "security engineer",
    "quality assurance",
    "research engineer",
)
QUALCOMM_SEARCH_API = "https://careers.qualcomm.com/api/pcsx/search"
QUALCOMM_CAREERS_BASE = "https://careers.qualcomm.com"
QUALCOMM_INDIA_CAREERS = "https://careers.qualcomm.com/careers?location=India"
QUALCOMM_EARLY_SEARCHES = (
    "intern",
    "campus hire",
    "graduate",
    "associate engineer",
)
GOOGLE_CAREERS_SEARCH = "https://www.google.com/about/careers/applications/jobs/results"
GOOGLE_INDIA_EARLY_CAREERS = (
    f"{GOOGLE_CAREERS_SEARCH}?location=India&target_level=EARLY&"
    "target_level=INTERN_AND_APPRENTICE"
)
ATLASSIAN_LISTINGS_API = "https://www.atlassian.com/endpoint/careers/listings"
ATLASSIAN_INDIA_CAREERS = (
    "https://www.atlassian.com/company/careers/all-jobs?location=India"
)
ORACLE_RECRUITING_API = (
    "https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest"
)
ORACLE_SITE_NUMBER = "CX_45001"
ORACLE_INDIA_EARLY_CAREERS = (
    "https://careers.oracle.com/en/sites/jobsearch/jobs?location=India"
)
ORACLE_EARLY_FACETS = (
    ("AttributeChar6|0 to 2+ years", "Experience band: 0 to 2+ years"),
    ("AttributeChar13|Student / Intern", "Experience level: Student / Intern"),
)
SWIGGY_CAREERS_API = "https://swiggy.mynexthire.com/employer/careers/reqlist/get"
SWIGGY_CAREERS = "https://careers.swiggy.com/careers"
DELL_RECRUITING_API = (
    "https://enterpriseplatform.dell.com/hcmRestApi/resources/latest"
)
DELL_SITE_NUMBER = "CX_1001"
DELL_INDIA_CAREERS = "https://jobs.dell.com/en/sites/careers/jobs?location=India"
YCOMBINATOR_CAREERS_BASE = "https://www.ycombinator.com"
YCOMBINATOR_STARTUP_LISTINGS = {
    "india": f"{YCOMBINATOR_CAREERS_BASE}/jobs/role/software-engineer/india",
    "remote": f"{YCOMBINATOR_CAREERS_BASE}/jobs/role/software-engineer/remote",
}
_YCOMBINATOR_JOB_PATH = re.compile(
    r'href=["\'](/companies/[^/"\']+/jobs/[^"\']+)["\']',
    re.I,
)
_SCHEMA_COUNTRY_NAMES = {
    "IN": "India",
    "IND": "India",
    "US": "United States",
    "USA": "United States",
    "GB": "United Kingdom",
    "UK": "United Kingdom",
    "AU": "Australia",
    "PL": "Poland",
    "IL": "Israel",
    "NL": "Netherlands",
}
_DELL_TEXT_DEADLINE = re.compile(
    r"\bapplication closing date\s*:\s*(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(january|february|march|april|may|june|july|august|september|october|"
    r"november|december)\s+(20\d{2})\b",
    re.I,
)
_OFFICIAL_EARLY_TITLE = re.compile(
    r"\b(intern(?:ship)?|new\s*grad(?:uate)?|graduate|campus|fresher|entry[ -]?level|"
    r"junior|associate|engineer\s+(?:i|1))\b",
    re.I,
)
_OFFICIAL_SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|manager|director|architect|head|vice president|vp)\b",
    re.I,
)
_OFFICIAL_TECH_TITLE = re.compile(
    r"\b(software|systems?|developer|programmer|data engineer|data science|data scientist|machine learning|"
    r"artificial intelligence|\bai\b|\bml\b|applied scientist|research sciences?|cloud|"
    r"devops|site reliability|sre|security|cyber|quality assurance|test engineer|embedded|"
    r"firmware|compiler|platform engineer|backend|frontend|full[ -]?stack|android|ios|mobile|"
    r"technology consulting|silicon|design verification|solutions engineer|hardware engineer|"
    r"network engineer|cad engineer|integration architect|integration engineer|support engineer|"
    r"technical support)\b",
    re.I,
)
_MICROSOFT_JSON_LD = re.compile(
    r"<script[^>]*application/ld[+]json[^>]*>\s*(.*?)\s*</script>",
    re.I | re.S,
)
_GOOGLE_JOBS_DATA = re.compile(
    r"AF_initDataCallback\(\{key: .ds:1., hash: .[^.]+., data:(.*?), "
    r"sideChannel: \{\}\}\);",
    re.S,
)


async def scrape_deliveroo_india() -> list[dict]:
    """Read Deliveroo's public India roles feed without application-form data."""
    payload = await json_get(DELIVEROO_ROLES_API, {
        "_adjust_ids": "1",
        "locations_slug": "india",
        "per_page": "100",
        "page": "1",
        "orderby": "date",
        "order": "desc",
    })
    results: list[dict] = []
    for job in payload if isinstance(payload, list) else []:
        if not isinstance(job, dict) or str(job.get("status") or "") != "publish":
            continue
        title_data = job.get("title") if isinstance(job.get("title"), dict) else {}
        content_data = job.get("content") if isinstance(job.get("content"), dict) else {}
        excerpt_data = job.get("excerpt") if isinstance(job.get("excerpt"), dict) else {}
        meta = job.get("meta") if isinstance(job.get("meta"), dict) else {}
        title = clean_text(str(title_data.get("rendered") or ""))
        link = str(job.get("link") or "").strip()
        if not title or not link:
            continue
        description = strip_html_text(
            str(content_data.get("rendered") or excerpt_data.get("rendered") or "")
        )
        location = clean_text(str(
            meta.get("ats_location")
            or meta.get("ashby_location")
            or meta.get("greenhouse_location")
            or ""
        ))
        requisition_id = clean_text(str(meta.get("ashby_req_id") or job.get("id") or ""))
        is_remote = bool(
            meta.get("ats_remote")
            or meta.get("ashby_remote")
            or meta.get("greenhouse_remote")
        )
        if location:
            description = f"{description}\nLocation: {location}".strip()
        results.append(text_lead({
            "title": title,
            "company": "Deliveroo",
            "url": link,
            "apply_url": f"{link.rstrip('/')}/apply/",
            "platform": "deliveroo",
            "description": description,
            "posted_date": str(job.get("date_gmt") or job.get("date") or ""),
            "updated_at": str(job.get("modified_gmt") or job.get("modified") or ""),
            "location": location,
            "workplace": "remote" if is_remote else "",
            "active_hint": "active",
            "attribution": DELIVEROO_INDIA_CAREERS,
            "source_meta": {
                "source": "official_careers",
                "slug": "deliveroo",
                "id": requisition_id,
                "employer_domain": "deliveroo.co.uk",
            },
        }))
    return results


def _zeqo_role_slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _zeqo_compensation(text: str) -> dict:
    match = _ZEQO_MONTHLY_PAY.search(text)
    if not match:
        return {}
    minimum = int(match.group(1).replace(",", ""))
    maximum = int(match.group(2).replace(",", "")) if match.group(2) else None
    return {
        "currency": "INR",
        "interval": "month",
        "min": minimum,
        "max": maximum,
    }


async def scrape_zeqo_early_career() -> list[dict]:
    """Read Zeqo's first-party paid India early-career role cards.

    The careers page is server-rendered and contains one self-contained card per
    opening. Only cards with the employer's visible ``Apply Now`` mail handoff
    are considered live. The mail address is not placed in metadata; candidates
    are handed to the official page, where the current instructions remain the
    source of truth.
    """
    raw_html = await text_get(ZEQO_CAREERS)
    # Next.js repeats the rendered text in hydration scripts. Restrict parsing
    # to the visible main document so each live card is observed exactly once.
    visible_html = f'{raw_html.split("</main>", 1)[0]}</main>'
    results: list[dict] = []
    for card_match in _ZEQO_CARD.finditer(visible_html):
        card = card_match.group(1)
        title_match = _ZEQO_TITLE.search(card)
        if not title_match or not _ZEQO_APPLY.search(card):
            continue
        title = strip_html_text(html.unescape(title_match.group(1)))
        slug = _zeqo_role_slug(title)
        if not title or not slug:
            continue
        facts = [
            strip_html_text(html.unescape(match.group(1)))
            for match in _ZEQO_FACT.finditer(card[: title_match.end() + 2_000])
        ]
        facts = [fact for fact in facts if fact]
        location_fact = next(
            (fact for fact in facts if "remote" in fact.lower() or "/" in fact),
            "",
        )
        compensation_text = next((fact for fact in facts if "₹" in fact), "")
        location = clean_text(re.sub(r"\s*/\s*", "; ", location_fact))
        if ";" in location and "india" not in location.lower():
            location = f"{location}, India"
        description = strip_html_text(html.unescape(card))
        source_url = f"{ZEQO_CAREERS}?{urlencode({'role': slug})}"
        results.append(text_lead({
            "title": title,
            "company": "Zeqo",
            "url": source_url,
            "apply_url": source_url,
            "platform": "zeqo",
            "description": description,
            "location": location,
            "workplace": "remote" if "remote" in location.lower() else "",
            "active_hint": "active",
            "attribution": ZEQO_CAREERS,
            "source_meta": {
                "source": "official_careers",
                "slug": "zeqo",
                "id": slug,
                "employer_domain": "zeqo.in",
                "application_method": "Email via the official careers page",
                "compensation_text": compensation_text,
                "base_salary": _zeqo_compensation(compensation_text),
            },
        }))
    return results


def _aicte_class_text(fragment: str, class_name: str) -> str:
    pattern = re.compile(
        rf'<(?P<tag>[a-z0-9]+)[^>]*class=["\'][^"\']*\b{re.escape(class_name)}\b'
        rf'[^"\']*["\'][^>]*>(?P<body>.*?)</(?P=tag)>',
        re.I | re.S,
    )
    match = pattern.search(fragment)
    return strip_html_text(html.unescape(match.group("body"))) if match else ""


def _aicte_fact(fragment: str, label: str) -> str:
    pattern = re.compile(
        rf'<h6[^>]*>\s*{re.escape(label)}\s*</h6>\s*<span[^>]*>(.*?)</span>',
        re.I | re.S,
    )
    match = pattern.search(fragment)
    return strip_html_text(html.unescape(match.group(1))) if match else ""


def _aicte_requisition_id(detail_url: str) -> str:
    values = parse_qs(urlsplit(detail_url).query).get("uid") or []
    encoded = values[0].strip() if values else ""
    if not encoded:
        return ""
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8").strip()
    except (ValueError, UnicodeDecodeError):
        return encoded
    return decoded or encoded


def _aicte_compensation(stipend: str) -> dict:
    match = _AICTE_MONTHLY_PAY.search(stipend.replace("₹", ""))
    if not match:
        return {}
    minimum = int(match.group("min").replace(",", ""))
    maximum = (
        int(match.group("max").replace(",", ""))
        if match.group("max")
        else None
    )
    return {
        "currency": "INR",
        "interval": "month",
        "min": minimum,
        "max": maximum,
    }


def _aicte_paid_technical_cards(raw_html: str) -> list[dict[str, str]]:
    """Project the paid CSE/AI cards before making bounded detail requests.

    AICTE's broad public search currently contains hundreds of unpaid training
    listings. They are deliberately excluded at the collection boundary: the
    product must not spend one detail request per unsafe role, nor present
    unpaid work as a viable opportunity. Detail pages remain the source of truth
    for employer, description, eligibility, terms, openings and apply state.
    """
    cards: dict[str, dict[str, str]] = {}
    for match in _AICTE_CARD.finditer(raw_html):
        card = match.group(1)
        title = _aicte_class_text(card, "job-title")
        stipend = _aicte_fact(card, "Stipend")
        link = _AICTE_DETAIL_LINK.search(card)
        if (
            not title
            or not link
            or not _AICTE_TECH_TITLE.search(title)
            or re.search(r"\bunpaid\b|\bno\s+stipend\b", stipend, re.I)
        ):
            continue
        detail_url = urljoin(AICTE_DETAILS_BASE, html.unescape(link.group("href")))
        requisition_id = _aicte_requisition_id(detail_url)
        if not requisition_id:
            continue
        cards.setdefault(requisition_id, {
            "detail_url": detail_url,
            "listing_title": title,
            "listing_stipend": stipend,
        })
    return list(cards.values())


def _aicte_detail_lead(detail_url: str, raw_html: str) -> dict | None:
    title = _aicte_class_text(raw_html, "job-title")
    employer = _aicte_class_text(raw_html, "company-name")
    location = _aicte_class_text(raw_html, "location").rstrip(" ,")
    arrangement = _aicte_class_text(raw_html, "wfh")
    published = _aicte_class_text(raw_html, "posted-on")
    start_date = _aicte_fact(raw_html, "Start date")
    duration = _aicte_fact(raw_html, "Duration")
    stipend = _aicte_fact(raw_html, "Stipend")
    credits = _aicte_fact(raw_html, "No of Credits")
    deadline = _aicte_fact(raw_html, "Apply by")
    requisition_id = _aicte_requisition_id(detail_url)
    has_apply_control = bool(re.search(
        r'<button[^>]*(?:id=["\']applyBtn["\']|name=["\']apply_login_private["\'])[^>]*>'
        r'\s*Apply Now\s*</button>',
        raw_html,
        re.I | re.S,
    ))
    if (
        not title
        or not employer
        or not requisition_id
        or not has_apply_control
        or re.search(r"\bunpaid\b|\bno\s+stipend\b", stipend, re.I)
    ):
        return None

    sections: list[str] = []
    openings = ""
    for section in _AICTE_SECTION.finditer(raw_html):
        heading = strip_html_text(html.unescape(section.group("title")))
        body = strip_html_text(html.unescape(section.group("body")))
        if heading.lower() == "number of openings":
            openings = body
        if heading and body:
            sections.append(f"{heading}:\n{body}")
    workplace = "remote" if re.search(r"virtual|remote", arrangement, re.I) else "onsite"
    facts = [
        f"Internship format: {arrangement}" if arrangement else "",
        f"Location: {location}" if location else "",
        f"Start date: {start_date}" if start_date else "",
        f"Duration: {duration}" if duration else "",
        f"Stipend: {stipend}" if stipend else "",
        f"Academic credits: {credits}" if credits else "",
        f"Number of openings: {openings}" if openings else "",
        f"Apply by: {deadline}" if deadline else "",
    ]
    description = "\n\n".join([*sections, *filter(None, facts)]).strip()
    return text_lead({
        "title": title,
        "company": employer,
        "url": detail_url,
        "apply_url": detail_url,
        "platform": "aicte",
        "description": description,
        "posted_date": published,
        "deadline": deadline,
        "location": location,
        "workplace": workplace,
        "active_hint": "active",
        "attribution": AICTE_CSE_SEARCH,
        "source_meta": {
            "source": "official_marketplace",
            "slug": "national-internship-portal",
            "id": requisition_id,
            "internship_format": arrangement,
            "start_date_text": start_date,
            "duration_text": duration,
            "stipend_text": stipend,
            "base_salary": _aicte_compensation(stipend),
            "academic_credits": credits,
            "number_of_openings": openings,
            "application_method": "AICTE student login via the official detail page",
        },
    })


async def scrape_aicte_cse_internships() -> list[dict]:
    """Read paid technical internships from AICTE's national public portal.

    One broad listing request discovers the current market. Only paid technical
    cards receive a bounded detail request, with four-way concurrency. Parsing
    stops at public role sections; CSRF tokens, CAPTCHA material, login fields,
    custom application questions and all candidate data are never projected.
    """
    listing_html = await text_get(AICTE_CSE_SEARCH)
    cards = _aicte_paid_technical_cards(listing_html)
    semaphore = asyncio.Semaphore(4)

    async def fetch(card: dict[str, str]) -> dict | None:
        async with semaphore:
            detail_html = await text_get(card["detail_url"])
        lead = _aicte_detail_lead(card["detail_url"], detail_html)
        if lead and clean_text(str(lead.get("title") or "")) != card["listing_title"]:
            logging.getLogger(__name__).warning(
                "AICTE listing/detail title drift for %s", card["detail_url"]
            )
        return lead

    projected = await asyncio.gather(*(fetch(card) for card in cards))
    return [lead for lead in projected if lead is not None]


def _ibm_request(*, level: str, offset: int, size: int = 100) -> dict:
    return {
        "appId": "careers",
        "scopes": ["careers2"],
        "query": {"bool": {"must": []}},
        "post_filter": {
            "bool": {
                "must": [
                    {"term": {"field_keyword_18": level}},
                    {"term": {"country": "in"}},
                ]
            }
        },
        "from": offset,
        "size": size,
        "sort": [{"_score": "desc"}],
        "_source": list(_IBM_SOURCE_FIELDS),
    }


async def scrape_ibm_india_early_career() -> list[dict]:
    """Read IBM's live India internship and entry-level search index.

    IBM's public careers UI uses the same v2 interface. The adapter requests only
    public job fields and applies IBM's exact experience-level and country filters.
    Search-index expiry is retained as provenance, not treated as an application
    deadline (IBM currently uses multi-year index expiry values).
    """
    results: list[dict] = []
    seen: set[str] = set()
    page_size = 100
    for requested_level in IBM_EARLY_CAREER_LEVELS:
        offset = 0
        while offset < 5_000:
            payload = await json_post(
                IBM_SEARCH_API,
                _ibm_request(level=requested_level, offset=offset, size=page_size),
            )
            hits_data = payload.get("hits") if isinstance(payload, dict) else {}
            hits = hits_data.get("hits") if isinstance(hits_data, dict) else []
            rows = hits if isinstance(hits, list) else []
            total_data = hits_data.get("total") if isinstance(hits_data, dict) else 0
            total = (
                int(total_data.get("value") or 0)
                if isinstance(total_data, dict)
                else int(total_data or 0)
            )
            for hit in rows:
                if not isinstance(hit, dict):
                    continue
                source = hit.get("_source") if isinstance(hit.get("_source"), dict) else {}
                title = clean_text(str(source.get("title") or ""))
                url = str(source.get("url") or "").strip()
                if not title or not url:
                    continue
                query = parse_qs(urlsplit(url).query)
                requisition_id = clean_text(str((query.get("jobId") or [""])[0]))
                stable_key = requisition_id or str(hit.get("_id") or url)
                if stable_key in seen:
                    continue
                seen.add(stable_key)
                level = clean_text(str(source.get("field_keyword_18") or requested_level))
                career_area = clean_text(str(source.get("field_keyword_08") or ""))
                location = clean_text(str(source.get("field_keyword_19") or "India"))
                if not re.search(r"\bindia\b|,\s*in$", location, re.I):
                    location = f"{location}, India"
                description = clean_text(str(source.get("body") or source.get("description") or ""))
                tail = description[-600:]
                workplace_match = _IBM_WORKPLACE_BEFORE_LEVEL.search(tail)
                workplace = workplace_match.group(1).lower() if workplace_match else ""
                facts = [
                    f"Career area: {career_area}" if career_area else "",
                    f"Experience level: {level}" if level else "",
                    f"Location: {location}",
                    f"Workplace: {workplace}" if workplace else "",
                ]
                description = "\n".join([description, *(fact for fact in facts if fact)]).strip()
                countries = source.get("country") if isinstance(source.get("country"), list) else []
                results.append(text_lead({
                    "title": title,
                    "company": "IBM",
                    "url": url,
                    "apply_url": url,
                    "platform": "ibm",
                    "description": description,
                    "posted_date": str(source.get("dcdate") or ""),
                    "updated_at": str(source.get("processedtime") or ""),
                    "location": location,
                    "workplace": workplace,
                    "active_hint": "active",
                    "attribution": IBM_INDIA_EARLY_CAREER_SEARCH,
                    "source_meta": {
                        "source": "official_careers",
                        "slug": "careers",
                        "id": requisition_id or str(hit.get("_id") or ""),
                        "employer_domain": "ibm.com",
                        "career_area": career_area,
                        "experience_level": level,
                        "country_codes": [clean_text(str(value)) for value in countries],
                        "effective_date": str(source.get("effectivedate") or ""),
                        "index_expire_date": str(source.get("expiredate") or ""),
                    },
                }))
            offset += len(rows)
            if not rows or offset >= total or len(rows) < page_size:
                break
    return results


def _amazon_india_location(value: object) -> tuple[str, str]:
    raw = clean_text(str(value or ""))
    if not re.match(r"^IN(?:,|$)", raw, re.I):
        return "", ""
    parts = [clean_text(part) for part in raw.split(",") if clean_text(part)]
    if any(part.casefold() in {"virtual", "remote"} for part in parts[1:]):
        return "Remote - India", "remote"
    locality = list(reversed(parts[1:]))
    return ", ".join([*locality, "India"]), "onsite"


async def scrape_amazon_india_cse() -> list[dict]:
    """Read Amazon's public India JSON index for technical early/stretch roles."""
    jobs: dict[str, dict] = {}
    page_size = 100
    for query in AMAZON_CSE_SEARCHES:
        offset = 0
        while offset < 500:
            raw = await text_get(
                AMAZON_SEARCH_API,
                {
                    "offset": offset,
                    "result_limit": page_size,
                    "sort": "relevant",
                    "country": "IND",
                    "base_query": query,
                },
                request_headers={
                    "Accept": "application/json",
                    # Amazon occasionally double-advertises a compressed stream;
                    # identity avoids a decoder failure without changing content.
                    "Accept-Encoding": "identity",
                },
            )
            payload = json.loads(raw)
            rows = payload.get("jobs") if isinstance(payload, dict) else []
            rows = rows if isinstance(rows, list) else []
            total = int(payload.get("hits") or 0) if isinstance(payload, dict) else 0
            for job in rows:
                if not isinstance(job, dict):
                    continue
                title = clean_text(str(job.get("title") or ""))
                path = str(job.get("job_path") or "").strip()
                location, _workplace = _amazon_india_location(job.get("location"))
                if (
                    title
                    and path
                    and location
                    and _OFFICIAL_TECH_TITLE.search(title)
                    and not _OFFICIAL_SENIOR_TITLE.search(title)
                ):
                    jobs.setdefault(path, job)
            offset += len(rows)
            if not rows or len(rows) < page_size or offset >= total:
                break

    results: list[dict] = []
    for path, job in jobs.items():
        title = clean_text(str(job.get("title") or ""))
        location, workplace = _amazon_india_location(job.get("location"))
        url = f"https://www.amazon.jobs{path}"
        requisition_match = re.search(r"/jobs/(\d+)", path)
        requisition_id = (
            requisition_match.group(1)
            if requisition_match
            else clean_text(str(job.get("id") or ""))
        )
        description = strip_html_text(str(job.get("description") or ""))
        basic = strip_html_text(str(job.get("basic_qualifications") or ""))
        preferred = strip_html_text(str(job.get("preferred_qualifications") or ""))
        facts = [
            f"Basic qualifications: {basic}" if basic else "",
            f"Preferred qualifications: {preferred}" if preferred else "",
            f"Job category: {clean_text(str(job.get('job_category') or ''))}",
            f"Location: {location}",
            f"Workplace: {workplace}",
        ]
        results.append(text_lead({
            "title": title,
            "company": "Amazon",
            "url": url,
            "apply_url": url,
            "platform": "amazon",
            "description": "\n".join([description, *(fact for fact in facts if fact)]).strip(),
            "posted_date": str(job.get("posted_date") or ""),
            "location": location,
            "workplace": workplace,
            "active_hint": "active",
            "attribution": AMAZON_INDIA_CAREERS,
            "source_meta": {
                "source": "official_careers",
                "slug": "amazon-jobs-india",
                "id": requisition_id,
                "employer_domain": "amazon.jobs",
                "job_category": clean_text(str(job.get("job_category") or "")),
                "business_category": clean_text(str(job.get("business_category") or "")),
            },
        }))
    return results


def _eightfold_india_location(card: dict) -> str:
    locations = card.get("locations") if isinstance(card.get("locations"), list) else []
    values = [clean_text(str(value)) for value in locations if clean_text(str(value))]
    if not any(re.search(r"\bindia\b", value, re.I) for value in values):
        standardized = (
            card.get("standardizedLocations")
            if isinstance(card.get("standardizedLocations"), list)
            else []
        )
        if not any(re.search(r"(?:^|,\s*)IN$", str(value), re.I) for value in standardized):
            return ""
    return "; ".join(dict.fromkeys(values)) or "India"


def _job_posting_schema(raw_html: str) -> dict:
    match = _MICROSOFT_JSON_LD.search(raw_html)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(1))
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) and payload.get("@type") == "JobPosting" else {}


def _schema_names(value: object) -> list[str]:
    nodes = value if isinstance(value, list) else [value]
    names: list[str] = []
    for node in nodes:
        if isinstance(node, dict):
            raw = node.get("name") or node.get("addressCountry")
            if isinstance(raw, dict):
                raw = raw.get("name")
            name = clean_text(str(raw or ""))
        else:
            name = clean_text(str(node or ""))
        if name:
            names.append(_SCHEMA_COUNTRY_NAMES.get(name.upper(), name))
    return list(dict.fromkeys(names))


def _schema_job_locations(value: object) -> list[str]:
    nodes = value if isinstance(value, list) else [value]
    locations: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        address = node.get("address") if isinstance(node.get("address"), dict) else node
        country = address.get("addressCountry")
        if isinstance(country, dict):
            country = country.get("name")
        country_text = clean_text(str(country or ""))
        country_text = _SCHEMA_COUNTRY_NAMES.get(country_text.upper(), country_text)
        parts = [
            clean_text(str(address.get("addressLocality") or "")),
            clean_text(str(address.get("addressRegion") or "")),
            country_text,
        ]
        rendered = ", ".join(dict.fromkeys(part for part in parts if part))
        if rendered:
            locations.append(rendered)
    return list(dict.fromkeys(locations))


def _ycombinator_location(schema: dict) -> tuple[str, str, list[str]]:
    applicant_regions = _schema_names(schema.get("applicantLocationRequirements"))
    job_locations = _schema_job_locations(schema.get("jobLocation"))
    is_remote = str(schema.get("jobLocationType") or "").upper() == "TELECOMMUTE"
    if is_remote:
        # Explicit applicant restrictions outrank a card/title location. This is
        # intentionally conservative: a current YC "India" card can still carry
        # a US-only structured applicantLocationRequirements value.
        scope = applicant_regions or job_locations
        return (
            f"Remote - {'; '.join(scope)}" if scope else "Remote",
            "remote",
            applicant_regions,
        )
    return "; ".join(job_locations), "onsite" if job_locations else "", applicant_regions


def _ycombinator_salary(schema: dict) -> tuple[str, dict]:
    salary = schema.get("baseSalary") if isinstance(schema.get("baseSalary"), dict) else {}
    value = salary.get("value") if isinstance(salary.get("value"), dict) else {}
    currency = clean_text(str(salary.get("currency") or ""))
    unit = clean_text(str(value.get("unitText") or ""))
    minimum = value.get("minValue")
    maximum = value.get("maxValue")
    exact = value.get("value")
    bounds = [str(item) for item in (minimum, maximum) if item is not None]
    if not bounds and exact is not None:
        bounds = [str(exact)]
    rendered = " - ".join(bounds)
    text = " ".join(part for part in (currency, rendered, f"per {unit}" if unit else "") if part)
    return text, {
        "currency": currency,
        "unit": unit,
        "min": minimum,
        "max": maximum,
        "value": exact,
    }


async def scrape_ycombinator_startups(scope: str) -> list[dict]:
    """Read current public YC India or remote software-startup listings.

    Listing membership plus a live first-party JobPosting document is active
    evidence at observation time. Authentication/application-form data is never
    requested or retained; the public detail page remains the apply handoff.
    """
    normalized_scope = clean_text(scope).lower()
    listing_url = YCOMBINATOR_STARTUP_LISTINGS.get(normalized_scope)
    if not listing_url:
        raise ValueError(f"unsupported Y Combinator startup scope: {scope}")
    listing_html = await text_get(listing_url)
    paths = list(dict.fromkeys(_YCOMBINATOR_JOB_PATH.findall(listing_html)))
    semaphore = asyncio.Semaphore(4)

    async def detail_lead(path: str) -> dict | None:
        detail_url = f"{YCOMBINATOR_CAREERS_BASE}{html.unescape(path)}"
        try:
            async with semaphore:
                raw_html = await text_get(detail_url)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {404, 410}:
                return None
            raise
        schema = _job_posting_schema(raw_html)
        if not schema:
            return None
        title = clean_text(str(schema.get("title") or ""))
        organization = (
            schema.get("hiringOrganization")
            if isinstance(schema.get("hiringOrganization"), dict)
            else {}
        )
        company = clean_text(str(organization.get("name") or ""))
        if not title or not company:
            return None
        location, workplace, applicant_regions = _ycombinator_location(schema)
        salary_text, salary_meta = _ycombinator_salary(schema)
        employment = schema.get("employmentType")
        employment_values = employment if isinstance(employment, list) else [employment]
        employment_text = ", ".join(
            clean_text(str(value)).replace("_", " ").title()
            for value in employment_values
            if clean_text(str(value or ""))
        )
        description = strip_html_text(str(schema.get("description") or ""))
        facts = [
            f"Employment type: {employment_text}" if employment_text else "",
            f"Location: {location}" if location else "",
            f"Workplace: {workplace}" if workplace else "",
            f"Applicant location requirements: {'; '.join(applicant_regions)}"
            if applicant_regions
            else "",
            f"Compensation: {salary_text}" if salary_text else "",
        ]
        job_key = path.split("/jobs/", 1)[-1].split("-", 1)[0]
        company_slug = path.split("/companies/", 1)[-1].split("/", 1)[0]
        employer_url = str(organization.get("sameAs") or "").strip()
        employer_domain = (urlsplit(employer_url).hostname or "").lower()
        return text_lead({
            "title": title,
            "company": company,
            "url": detail_url,
            "apply_url": detail_url,
            "platform": "ycombinator",
            "description": "\n".join(
                value for value in [description, *(fact for fact in facts if fact)] if value
            ).strip(),
            "posted_date": str(schema.get("datePosted") or ""),
            "deadline": str(schema.get("validThrough") or ""),
            "location": location,
            "workplace": workplace,
            "active_hint": "active",
            "attribution": listing_url,
            "source_meta": {
                "source": "official_startup_marketplace",
                "slug": company_slug,
                "id": job_key,
                "employer_domain": employer_domain,
                "employer_url": employer_url,
                "listing_scope": normalized_scope,
                "applicant_location_requirements": applicant_regions,
                "employment_type": employment_values,
                "base_salary": salary_meta,
                "company_logo": str(organization.get("logo") or ""),
            },
        })

    rows = await asyncio.gather(*(detail_lead(path) for path in paths))
    return [row for row in rows if row is not None]


async def _scrape_eightfold_india(
    *,
    search_api: str,
    careers_base: str,
    careers_attribution: str,
    domain: str,
    company: str,
    provider: str,
    searches: tuple[str, ...],
    max_stretch: int,
) -> list[dict]:
    """Project public Eightfold search cards and JobPosting facts only."""
    early_cards: dict[str, dict] = {}
    stretch_cards: dict[str, dict] = {}
    for query in searches:
        start = 0
        while start < 200:
            payload = await json_get(search_api, {
                "domain": domain,
                "query": query,
                "location": "India",
                "start": start,
            })
            data = payload.get("data") if isinstance(payload, dict) else {}
            rows = data.get("positions") if isinstance(data, dict) else []
            rows = rows if isinstance(rows, list) else []
            total = int(data.get("count") or 0) if isinstance(data, dict) else 0
            for card in rows:
                if not isinstance(card, dict):
                    continue
                title = clean_text(str(card.get("name") or ""))
                title_signal = title.replace("_", " ")
                position_id = clean_text(str(card.get("id") or ""))
                if (
                    not title
                    or not position_id
                    or not _eightfold_india_location(card)
                    or _OFFICIAL_SENIOR_TITLE.search(title_signal)
                ):
                    continue
                if _OFFICIAL_EARLY_TITLE.search(title_signal):
                    early_cards.setdefault(position_id, card)
                elif _OFFICIAL_TECH_TITLE.search(title_signal):
                    stretch_cards.setdefault(position_id, card)
            start += len(rows)
            if not rows or len(rows) < 10 or start >= total:
                break

    selected = [
        *list(early_cards.values())[:60],
        *list(stretch_cards.values())[:max_stretch],
    ]
    semaphore = asyncio.Semaphore(4)

    async def project(card: dict) -> dict | None:
        position_path = str(card.get("positionUrl") or f"/careers/job/{card.get('id')}")
        url = f"{careers_base}{position_path}"
        async with semaphore:
            raw_html = await text_get(
                url,
                request_headers={"Accept-Encoding": "identity"},
            )
        schema = _job_posting_schema(raw_html)
        if not schema:
            return None
        title = clean_text(str(schema.get("title") or card.get("name") or ""))
        location = _eightfold_india_location(card)
        if not title or not location:
            return None
        workplace = clean_text(str(card.get("workLocationOption") or "")).lower()
        description = strip_html_text(str(schema.get("description") or ""))
        facts = [
            f"Department: {clean_text(str(card.get('department') or ''))}",
            f"Employment type: {clean_text(str(schema.get('employmentType') or ''))}",
            f"Location: {location}",
            f"Workplace: {workplace}" if workplace else "",
        ]
        return text_lead({
            "title": title,
            "company": company,
            "url": url,
            "apply_url": url,
            "platform": provider,
            "description": "\n".join([description, *(fact for fact in facts if fact)]).strip(),
            "posted_date": str(schema.get("datePosted") or ""),
            "deadline": str(schema.get("validThrough") or ""),
            "location": location,
            "workplace": workplace,
            "active_hint": "active",
            "attribution": careers_attribution,
            "source_meta": {
                "source": "official_careers",
                "slug": f"{provider}-careers",
                "id": clean_text(str(card.get("displayJobId") or card.get("atsJobId") or "")),
                "employer_domain": domain,
                "position_id": clean_text(str(card.get("id") or "")),
                "department": clean_text(str(card.get("department") or "")),
                "standardized_locations": card.get("standardizedLocations") or [],
                "employment_type": clean_text(str(schema.get("employmentType") or "")),
            },
        })

    projected = await asyncio.gather(*(project(card) for card in selected), return_exceptions=True)
    return [row for row in projected if isinstance(row, dict)]


async def scrape_microsoft_india_cse() -> list[dict]:
    """Read Microsoft's public Eightfold index and JSON-LD job facts."""
    return await _scrape_eightfold_india(
        search_api=MICROSOFT_SEARCH_API,
        careers_base=MICROSOFT_CAREERS_BASE,
        careers_attribution=MICROSOFT_INDIA_CAREERS,
        domain="microsoft.com",
        company="Microsoft",
        provider="microsoft",
        searches=MICROSOFT_CSE_SEARCHES,
        max_stretch=30,
    )


async def scrape_qualcomm_india_early_career() -> list[dict]:
    """Read Qualcomm's official India internship and campus-hire inventory."""
    return await _scrape_eightfold_india(
        search_api=QUALCOMM_SEARCH_API,
        careers_base=QUALCOMM_CAREERS_BASE,
        careers_attribution=QUALCOMM_INDIA_CAREERS,
        domain="qualcomm.com",
        company="Qualcomm",
        provider="qualcomm",
        searches=QUALCOMM_EARLY_SEARCHES,
        max_stretch=20,
    )


def _google_jobs_payload(raw_html: str) -> tuple[list[list], int, int]:
    """Parse Google's server-rendered public job list, excluding UI state."""
    match = _GOOGLE_JOBS_DATA.search(raw_html)
    if not match:
        return [], 0, 20
    try:
        payload = json.loads(match.group(1))
    except (TypeError, ValueError):
        return [], 0, 20
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        return [], 0, 20
    rows = [row for row in payload[0] if isinstance(row, list)]
    total = int(payload[2] or len(rows)) if len(payload) > 2 else len(rows)
    page_size = int(payload[3] or 20) if len(payload) > 3 else 20
    return rows, total, max(1, page_size)


def _google_nested_text(row: list, index: int) -> str:
    value = row[index] if len(row) > index else None
    if isinstance(value, list) and len(value) > 1:
        return strip_html_text(str(value[1] or ""))
    return ""


def _google_timestamp(row: list, index: int) -> str:
    value = row[index] if len(row) > index else None
    if not isinstance(value, list) or not value:
        return ""
    try:
        return datetime.fromtimestamp(int(value[0]), timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError):
        return ""


async def scrape_google_india_early_career() -> list[dict]:
    """Read Google's first-party India early/intern search with full job facts."""
    results: list[dict] = []
    seen: set[str] = set()
    page = 1
    while page <= 10:
        raw_html = await text_get(GOOGLE_CAREERS_SEARCH, {
            "location": "India",
            "target_level": ["EARLY", "INTERN_AND_APPRENTICE"],
            "page": page,
        })
        rows, total, page_size = _google_jobs_payload(raw_html)
        for row in rows:
            requisition_id = clean_text(str(row[0] if len(row) > 0 else ""))
            title = clean_text(str(row[1] if len(row) > 1 else ""))
            apply_url = str(row[2] if len(row) > 2 else "").strip()
            locations = row[9] if len(row) > 9 and isinstance(row[9], list) else []
            india_locations = [
                clean_text(str(location[0]))
                for location in locations
                if isinstance(location, list)
                and location
                and (
                    (len(location) > 5 and str(location[5]).upper() == "IN")
                    or re.search(r"\bindia\b", str(location[0]), re.I)
                )
            ]
            if (
                not requisition_id
                or requisition_id in seen
                or not title
                or not apply_url
                or not india_locations
                or not _OFFICIAL_TECH_TITLE.search(title)
                or _OFFICIAL_SENIOR_TITLE.search(title)
            ):
                continue
            seen.add(requisition_id)
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            url = f"{GOOGLE_CAREERS_SEARCH}/{requisition_id}-{slug}"
            company = clean_text(str(row[7] if len(row) > 7 else "Google")) or "Google"
            location_text = "; ".join(dict.fromkeys(india_locations))
            description = _google_nested_text(row, 10)
            qualifications = _google_nested_text(row, 4)
            responsibilities = _google_nested_text(row, 3)
            facts = [
                f"Qualifications: {qualifications}" if qualifications else "",
                f"Responsibilities: {responsibilities}" if responsibilities else "",
                f"Location: {location_text}",
                "Workplace: onsite",
            ]
            levels = row[11] if len(row) > 11 and isinstance(row[11], list) else []
            results.append(text_lead({
                "title": title,
                "company": company,
                "url": url,
                "apply_url": apply_url,
                "platform": "google",
                "description": "\n".join([
                    description,
                    *(fact for fact in facts if fact),
                ]).strip(),
                "posted_date": _google_timestamp(row, 12),
                "location": location_text,
                "workplace": "onsite",
                "active_hint": "active",
                "attribution": GOOGLE_INDIA_EARLY_CAREERS,
                "source_meta": {
                    "source": "official_careers",
                    "slug": "google-careers-india-early",
                    "id": requisition_id,
                    "employer_domain": "google.com",
                    "target_levels": levels,
                },
            }))
        if not rows or page * page_size >= total:
            break
        page += 1
    return results


async def scrape_atlassian_india_cse() -> list[dict]:
    """Read Atlassian's first-party public listings and retain India tech roles.

    The feed currently repeats some requisitions, so the provider id is used as
    the stable deduplication key. Senior roles remain visible to downstream
    applicability rules rather than being silently hidden at collection time;
    this also keeps the official board under continuous health observation.
    """
    payload = await json_get(ATLASSIAN_LISTINGS_API)
    rows = payload if isinstance(payload, list) else []
    jobs: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = clean_text(str(row.get("title") or ""))
        locations = row.get("locations") if isinstance(row.get("locations"), list) else []
        location_values = [
            clean_text(str(value))
            for value in locations
            if clean_text(str(value))
        ]
        if (
            not title
            or not _OFFICIAL_TECH_TITLE.search(title.replace("_", " "))
            or not any(re.search(r"\bindia\b", value, re.I) for value in location_values)
        ):
            continue
        portal = row.get("portalJobPost") if isinstance(row.get("portalJobPost"), dict) else {}
        requisition_id = clean_text(str(row.get("id") or portal.get("id") or ""))
        if not requisition_id:
            continue
        jobs.setdefault(requisition_id, row)

    results: list[dict] = []
    for requisition_id, job in jobs.items():
        title = clean_text(str(job.get("title") or ""))
        locations = job.get("locations") if isinstance(job.get("locations"), list) else []
        location_values = list(dict.fromkeys(
            clean_text(str(value))
            for value in locations
            if clean_text(str(value))
        ))
        location = "; ".join(location_values)
        workplace = (
            "remote"
            if any(
                re.search(r"(?:remote\s*-\s*india|india\s*-\s*remote)", value, re.I)
                for value in location_values
            )
            else ""
        )
        portal = (
            job.get("portalJobPost")
            if isinstance(job.get("portalJobPost"), dict)
            else {}
        )
        detail_url = (
            f"https://www.atlassian.com/company/careers/details/{requisition_id}"
        )
        apply_url = str(job.get("applyUrl") or portal.get("portalUrl") or detail_url).strip()
        category = clean_text(str(job.get("category") or ""))
        role_type = clean_text(str(job.get("type") or ""))
        description_parts = [
            strip_html_text(str(job.get(field) or ""))
            for field in ("overview", "responsibilities", "qualifications", "compensation")
        ]
        facts = [
            f"Category: {category}" if category else "",
            f"Role type: {role_type}" if role_type else "",
            f"Location: {location}",
            f"Workplace: {workplace}" if workplace else "",
        ]
        description = "\n".join(
            value for value in [*description_parts, *facts] if value
        ).strip()
        results.append(text_lead({
            "title": title,
            "company": "Atlassian",
            "url": detail_url,
            "apply_url": apply_url,
            "platform": "atlassian",
            "description": description,
            "updated_at": str(portal.get("updatedDate") or ""),
            "location": location,
            "workplace": workplace,
            "active_hint": "active",
            "attribution": ATLASSIAN_INDIA_CAREERS,
            "source_meta": {
                "source": "official_careers",
                "slug": "atlassian-india",
                "id": requisition_id,
                "employer_domain": "atlassian.com",
                "portal_id": clean_text(str(
                    portal.get("portalId") or job.get("portalId") or ""
                )),
                "category": category,
                "role_type": role_type,
            },
        }))
    return results


async def scrape_oracle_india_early_cse() -> list[dict]:
    """Read Oracle Recruiting Cloud's exact India early-career facets.

    Oracle's keyword search also matches words such as ``internal``. Exact
    provider facets prevent that false-positive flood while retaining both
    0-2-year professional roles and Student / Intern roles. Detail requests are
    restricted to technically relevant search rows and never request apply-form
    schemas.
    """
    search_url = f"{ORACLE_RECRUITING_API}/recruitingCEJobRequisitions"
    jobs: dict[str, tuple[dict, set[str]]] = {}
    page_size = 25
    for facet, facet_fact in ORACLE_EARLY_FACETS:
        offset = 0
        while offset < 500:
            finder = ",".join((
                f"findReqs;siteNumber={ORACLE_SITE_NUMBER}",
                f"limit={page_size}",
                f"offset={offset}",
                "location=India",
                f"selectedFlexFieldsFacets={facet}",
            ))
            payload = await json_get(search_url, {
                "onlyData": "true",
                "expand": "requisitionList.secondaryLocations",
                "finder": finder,
            })
            items = payload.get("items") if isinstance(payload, dict) else []
            context = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {}
            rows = context.get("requisitionList") if isinstance(context, dict) else []
            rows = rows if isinstance(rows, list) else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                requisition_id = clean_text(str(row.get("Id") or ""))
                title = clean_text(str(row.get("Title") or ""))
                short_description = strip_html_text(str(row.get("ShortDescriptionStr") or ""))
                country_code = clean_text(str(row.get("PrimaryLocationCountry") or ""))
                location = clean_text(str(row.get("PrimaryLocation") or ""))
                technical_text = f"{title} {short_description}".replace("_", " ")
                if (
                    not requisition_id
                    or not title
                    or country_code.upper() != "IN"
                    or not re.search(r"\bindia\b", location, re.I)
                    or not _OFFICIAL_TECH_TITLE.search(technical_text)
                ):
                    continue
                existing = jobs.get(requisition_id)
                if existing:
                    existing[1].add(facet_fact)
                else:
                    jobs[requisition_id] = (row, {facet_fact})
            total = int(context.get("TotalJobsCount") or 0) if isinstance(context, dict) else 0
            offset += len(rows)
            if not rows or len(rows) < page_size or (total and offset >= total):
                break

    detail_url = f"{ORACLE_RECRUITING_API}/recruitingCEJobRequisitionDetails"
    semaphore = asyncio.Semaphore(4)

    async def project(requisition_id: str, row: dict, facet_facts: set[str]) -> dict:
        detail: dict = {}
        try:
            async with semaphore:
                payload = await json_get(detail_url, {
                    "onlyData": "true",
                    "expand": "all",
                    "finder": (
                        f'ById;Id="{requisition_id}",siteNumber={ORACLE_SITE_NUMBER}'
                    ),
                })
            items = payload.get("items") if isinstance(payload, dict) else []
            if isinstance(items, list) and items and isinstance(items[0], dict):
                detail = items[0]
        except Exception as log_exc:
            logging.getLogger(__name__).warning(
                "Oracle detail fallback for %s: %s", requisition_id, log_exc
            )
        merged = {**row, **detail}
        title = clean_text(str(merged.get("Title") or row.get("Title") or ""))
        primary_location = clean_text(str(
            merged.get("PrimaryLocation") or row.get("PrimaryLocation") or "India"
        ))
        secondary = (
            merged.get("secondaryLocations")
            if isinstance(merged.get("secondaryLocations"), list)
            else []
        )
        locations = [primary_location]
        for location_row in secondary:
            if not isinstance(location_row, dict):
                continue
            value = clean_text(str(location_row.get("Name") or ""))
            if value and re.search(r"\bindia\b", value, re.I):
                locations.append(value)
        location = "; ".join(dict.fromkeys(value for value in locations if value))
        workplace_raw = clean_text(str(merged.get("WorkplaceType") or ""))
        workplace = (
            "remote" if re.search(r"remote", workplace_raw, re.I)
            else "hybrid" if re.search(r"hybrid", workplace_raw, re.I)
            else "onsite"
        )
        sections = [
            strip_html_text(str(merged.get(field) or ""))
            for field in (
                "ExternalDescriptionStr",
                "ExternalResponsibilitiesStr",
                "ExternalQualificationsStr",
            )
        ]
        fact_fields = (
            ("Job function", "JobFunction"),
            ("Job family", "JobFamily"),
            ("Worker type", "WorkerType"),
            ("Job schedule", "JobSchedule"),
            ("Study level", "StudyLevel"),
        )
        facts = [
            *(sorted(facet_facts)),
            *(
                f"{label}: {clean_text(str(merged.get(field) or ''))}"
                for label, field in fact_fields
                if clean_text(str(merged.get(field) or ""))
            ),
            f"Location: {location}",
            f"Workplace: {workplace}",
        ]
        url = f"https://careers.oracle.com/en/sites/jobsearch/job/{requisition_id}"
        return text_lead({
            "title": title,
            "company": "Oracle",
            "url": url,
            "apply_url": url,
            "platform": "oracle",
            "description": "\n".join(value for value in [*sections, *facts] if value).strip(),
            "posted_date": str(row.get("PostedDate") or merged.get("PostedDate") or ""),
            "deadline": str(row.get("PostingEndDate") or merged.get("PostingEndDate") or ""),
            "location": location,
            "workplace": workplace,
            "active_hint": "active",
            "attribution": ORACLE_INDIA_EARLY_CAREERS,
            "source_meta": {
                "source": "official_careers",
                "slug": "oracle-india-early",
                "id": requisition_id,
                "employer_domain": "oracle.com",
                "site_number": ORACLE_SITE_NUMBER,
                "requisition_id": clean_text(str(merged.get("RequisitionId") or "")),
                "discovery_facets": sorted(facet_facts),
            },
        })

    return await asyncio.gather(*(
        project(requisition_id, row, facet_facts)
        for requisition_id, (row, facet_facts) in jobs.items()
    ))


def _swiggy_job_url(requisition_id: str) -> str:
    context = {
        "pageType": "jd",
        "cvSource": "careers",
        "reqId": int(requisition_id),
        "requester": {"id": "", "code": "", "name": ""},
        "page": "careers",
        "bufilter": -1,
    }
    encoded = base64.b64encode(
        json.dumps(context, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return f"https://careers.swiggy.com/careers/apply?{urlencode({'src': 'careers', 'p': encoded})}"


async def scrape_swiggy_india_cse() -> list[dict]:
    """Read Swiggy's first-party NextHire feed and retain technical roles."""
    payload = await json_post(SWIGGY_CAREERS_API, {
        "source": "careers",
        "code": "",
        "filterByBuId": -1,
    })
    rows = payload.get("reqDetailsBOList") if isinstance(payload, dict) else []
    jobs: dict[str, dict] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        requisition_id = clean_text(str(row.get("reqId") or ""))
        title = clean_text(str(row.get("reqTitle") or row.get("designation") or ""))
        if (
            requisition_id
            and title
            and _OFFICIAL_TECH_TITLE.search(title.replace("_", " "))
        ):
            jobs.setdefault(requisition_id, row)

    results: list[dict] = []
    for requisition_id, job in jobs.items():
        title = clean_text(str(job.get("reqTitle") or job.get("designation") or ""))
        raw_location = clean_text(str(job.get("locationAddress") or job.get("location") or ""))
        location = raw_location
        if location and not re.search(r"\bindia\b", location, re.I):
            location = f"{location}, India"
        description = clean_text(str(job.get("jdDisplay") or ""))
        workplace = (
            "remote" if re.search(r"\bremote\b", raw_location, re.I)
            else "hybrid" if re.search(r"\bhybrid\b", description[:600], re.I)
            else "onsite"
        )
        exp_min = job.get("expMin")
        exp_max = job.get("expMax")
        experience = ""
        if exp_min is not None or exp_max is not None:
            experience = f"{exp_min if exp_min is not None else '?'} to {exp_max if exp_max is not None else '?'} years"
        facts = [
            f"Experience range: {experience}" if experience else "",
            f"Employment type: {clean_text(str(job.get('employmentType') or ''))}",
            f"Career stream: {clean_text(str(job.get('careerStream') or ''))}",
            f"Business unit: {clean_text(str(job.get('buName') or ''))}",
            f"Total positions: {job.get('totalPositions')}" if job.get("totalPositions") is not None else "",
            f"Location: {location}" if location else "",
            f"Workplace: {workplace}",
        ]
        url = _swiggy_job_url(requisition_id)
        results.append(text_lead({
            "title": title,
            "company": "Swiggy",
            "url": url,
            "apply_url": url,
            "platform": "swiggy",
            "description": "\n".join(value for value in [description, *facts] if value).strip(),
            "posted_date": str(job.get("approvedOn") or ""),
            "location": location,
            "workplace": workplace,
            "active_hint": "active",
            "attribution": SWIGGY_CAREERS,
            "source_meta": {
                "source": "official_careers",
                "slug": "swiggy-india",
                "id": requisition_id,
                "employer_domain": "swiggy.com",
                "business_unit": clean_text(str(job.get("buName") or "")),
                "career_stream": clean_text(str(job.get("careerStream") or "")),
                "employment_type": clean_text(str(job.get("employmentType") or "")),
                "experience_min": exp_min,
                "experience_max": exp_max,
                "fresher": bool(job.get("fresher")),
                "total_positions": job.get("totalPositions"),
            },
        }))
    return results


def _dell_deadline(description: str) -> str:
    match = _DELL_TEXT_DEADLINE.search(description)
    if not match:
        return ""
    try:
        parsed = datetime.strptime(
            f"{match.group(1)} {match.group(2)} {match.group(3)}",
            "%d %B %Y",
        )
    except ValueError:
        return ""
    return parsed.date().isoformat()


async def scrape_dell_india_cse() -> list[dict]:
    """Read Dell's current Oracle Recruiting Cloud India board.

    Dell's old Workday tenant is no longer authoritative. Search cards are
    enriched from the public detail endpoint, including application closing
    dates embedded in the description so a still-visible expired card cannot
    be recommended as live.
    """
    search_url = f"{DELL_RECRUITING_API}/recruitingCEJobRequisitions"
    page_size = 25
    offset = 0
    jobs: dict[str, dict] = {}
    while offset < 500:
        finder = ",".join((
            f"findReqs;siteNumber={DELL_SITE_NUMBER}",
            f"limit={page_size}",
            f"offset={offset}",
            "location=India",
        ))
        payload = await json_get(search_url, {
            "onlyData": "true",
            "expand": "requisitionList.secondaryLocations",
            "finder": finder,
        })
        items = payload.get("items") if isinstance(payload, dict) else []
        context = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {}
        rows = context.get("requisitionList") if isinstance(context, dict) else []
        rows = rows if isinstance(rows, list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            requisition_id = clean_text(str(row.get("Id") or ""))
            title = clean_text(str(row.get("Title") or ""))
            country_code = clean_text(str(row.get("PrimaryLocationCountry") or ""))
            location = clean_text(str(row.get("PrimaryLocation") or ""))
            if (
                requisition_id
                and title
                and country_code.upper() == "IN"
                and re.search(r"\bindia\b", location, re.I)
                and _OFFICIAL_TECH_TITLE.search(title.replace("_", " "))
            ):
                jobs.setdefault(requisition_id, row)
        total = int(context.get("TotalJobsCount") or 0) if isinstance(context, dict) else 0
        offset += len(rows)
        if not rows or len(rows) < page_size or (total and offset >= total):
            break

    detail_url = f"{DELL_RECRUITING_API}/recruitingCEJobRequisitionDetails"
    semaphore = asyncio.Semaphore(4)

    async def project(requisition_id: str, row: dict) -> dict:
        detail: dict = {}
        try:
            async with semaphore:
                payload = await json_get(detail_url, {
                    "onlyData": "true",
                    "expand": "all",
                    "finder": (
                        f'ById;Id="{requisition_id}",siteNumber={DELL_SITE_NUMBER}'
                    ),
                })
            items = payload.get("items") if isinstance(payload, dict) else []
            if isinstance(items, list) and items and isinstance(items[0], dict):
                detail = items[0]
        except Exception as log_exc:
            logging.getLogger(__name__).warning(
                "Dell detail fallback for %s: %s", requisition_id, log_exc
            )
        merged = {**row, **detail}
        title = clean_text(str(merged.get("Title") or row.get("Title") or ""))
        location = clean_text(str(
            merged.get("PrimaryLocation") or row.get("PrimaryLocation") or "India"
        ))
        workplace_raw = clean_text(str(merged.get("WorkplaceType") or ""))
        workplace = (
            "remote" if re.search(r"remote", workplace_raw, re.I)
            else "hybrid" if re.search(r"hybrid", workplace_raw, re.I)
            else "onsite"
        )
        sections = [
            strip_html_text(str(merged.get(field) or ""))
            for field in (
                "ExternalDescriptionStr",
                "ExternalResponsibilitiesStr",
                "ExternalQualificationsStr",
            )
        ]
        description = "\n".join(value for value in sections if value).strip()
        deadline = str(row.get("PostingEndDate") or merged.get("PostingEndDate") or "")
        deadline = deadline or _dell_deadline(description)
        deadline_date = None
        try:
            deadline_date = datetime.fromisoformat(deadline.replace("Z", "+00:00")).date()
        except ValueError:
            pass
        expired = bool(deadline_date and deadline_date < datetime.now(timezone.utc).date())
        facts = [
            f"Job function: {clean_text(str(merged.get('JobFunction') or ''))}",
            f"Job schedule: {clean_text(str(merged.get('JobSchedule') or ''))}",
            f"Location: {location}",
            f"Workplace: {workplace}",
        ]
        description = "\n".join(value for value in [description, *facts] if value).strip()
        url = f"https://jobs.dell.com/en/sites/careers/job/{requisition_id}"
        return text_lead({
            "title": title,
            "company": "Dell Technologies",
            "url": url,
            "apply_url": url,
            "platform": "dell",
            "description": description,
            "posted_date": str(row.get("PostedDate") or merged.get("PostedDate") or ""),
            "deadline": deadline,
            "location": location,
            "workplace": workplace,
            "active_hint": "closed" if expired else "active",
            "attribution": DELL_INDIA_CAREERS,
            "source_meta": {
                "source": "official_careers",
                "slug": "dell-india",
                "id": requisition_id,
                "employer_domain": "dell.com",
                "site_number": DELL_SITE_NUMBER,
                "job_function": clean_text(str(merged.get("JobFunction") or "")),
                "job_schedule": clean_text(str(merged.get("JobSchedule") or "")),
                "workplace_type": workplace_raw,
                "text_deadline_expired": expired,
            },
        })

    return await asyncio.gather(*(
        project(requisition_id, row) for requisition_id, row in jobs.items()
    ))
