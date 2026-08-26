#!/usr/bin/env python
"""Live-verify every role in the CGFE global shortlist against its real posting.

``shortlist_global.py`` produces a ~373-lead shortlist from a deterministic
regex pre-filter over *scraped, possibly stale* text. That pre-filter is
cheap but wrong often enough that a manual spot-check of the top 25 found
only 6 genuinely confirmed (17 rejected, 1 dead, 1 blocked) -- see
``shortlist_verified.md``. This script does the same live-fetch verification
for the *entire* shortlist, not just the top 25, preferring each ATS's own
structured data over regex-over-HTML wherever one exists:

    - Greenhouse   -> boards-api.greenhouse.io/v1/boards/{slug}/jobs/{id}
    - Ashby        -> api.ashbyhq.com/posting-api/job-board/{org} (cached per org)
    - Workday      -> {tenant}.{host}.myworkdayjobs.com/wday/cxs/... (Accept: json)
    - Lever        -> api.lever.co/v0/postings/{company}/{id}
    - everything else -> schema.org JobPosting JSON-LD, else plain-text regex

No LLM calls -- this is deterministic parsing, so it costs nothing to re-run.
Results are cached to JSON incrementally (crash-safe / resumable) and the
verdict is persisted back onto the `leads` row (verify_status/verify_evidence/
verify_checked_at, migration 006) so the desktop app can use it too.

    python scripts/verify_shortlist.py                  # full run, resumable
    python scripts/verify_shortlist.py --limit 20        # smoke test
    python scripts/verify_shortlist.py --fresh           # ignore cache, re-check everything
    python scripts/verify_shortlist.py --db path\\to\\crm.db
"""
from __future__ import annotations

import argparse
import asyncio
import html as html_mod
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

import httpx  # noqa: E402

import run_scrape  # noqa: E402  sibling script, for resolve_db()
import shortlist_global as sg  # noqa: E402  reuse filtered_ranked_leads, don't reimplement it
from data.sqlite.connection import get_connection, run_migrations  # noqa: E402
from data.sqlite.leads import get_all_leads  # noqa: E402
# Band regexes moved to the business layer (leads.shortlist) along with the
# rest of the classifier; reuse them directly instead of reaching through the
# sibling script's namespace.
import leads.shortlist as _shortlist  # noqa: E402

CACHE_PATH = Path(__file__).resolve().parent / "verify_shortlist_cache.json"
CONCURRENCY = 9
TIMEOUT = 15.0
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------------------------
# Regex: reuse the shortlist's own band patterns (private but same module, a
# sibling script) instead of re-deriving "what counts as a region lock" --
# that logic already exists and is already tuned.
# ---------------------------------------------------------------------------
_GLOBAL_RE = _shortlist._GLOBAL_RE
_REGION_LOCK_STRONG_RE = _shortlist._REGION_LOCK_STRONG_RE
_REGION_LOCK_WEAK_RE = _shortlist._REGION_LOCK_WEAK_RE
_EOR_RE = _shortlist._EOR_RE
_INDIA_RE = _shortlist._INDIA_RE

_JUNIOR_RE = re.compile(
    r"\b(intern(?:ship)?s?|junior|jr\.?\b|entry[- ]level|new grad(?:uate)?|"
    r"graduate program|apprentice(?:ship)?)\b",
    re.IGNORECASE,
)

_NON_ENG_TITLE_RE = re.compile(
    r"\b(sales|account executive|account manager|account director|business development|"
    r"partner(?:ship)?s? (?:manager|director|lead)|client partner|regional client partner|"
    r"marketing|customer success|customer support|technical support|technical services engineer|"
    r"recruiter|talent acquisition|human resources|\bhr\b|legal counsel|paralegal|"
    r"content review(?:er)?|community manager|product marketing|chief of staff|builder relations|"
    r"solutions? consultant|solutions? engineer|implementation consultant|billing|payroll|"
    r"accounting|accountant|fp&a|indirect tax|\brevenue\b|\banalyst\b|workplace operations|"
    r"social media|adoption strategist|deployment strategist|field cto|ops administrator|"
    r"product support|\bproduct manager\b|systems? ops|field engineer(?:ing)?|\bbfsi\b|"
    r"hardware engineer|physical design|chip design|\basic\b|thermal[- ]?(?:mechanical)?|"
    r"mechanical engineer|electrical engineer)\b",
    re.IGNORECASE,
)

_AI_TITLE_RE = re.compile(
    r"\b(ai|ml|machine learning|llm|genai|generative ai|nlp|deep learning|agentic|"
    r"prompt engineer|mlops|computer vision|data scientist|conversational ai|"
    r"voice agent|language model|foundation model)\b",
    re.IGNORECASE,
)

_BACKEND_TITLE_RE = re.compile(
    r"\b(software engineer(?:ing)?|backend|back-end|full[- ]stack|\.net|c#|asp\.net|"
    r"platform engineer(?:ing)?|infrastructure engineer(?:ing)?|cloud engineer(?:ing)?|devops|"
    r"site reliability|\bsre\b|systems? engineer(?:ing)?|principal engineer|staff engineer|"
    r"senior engineer|solutions? architect|engineering manager|data engineer(?:ing)?)\b",
    re.IGNORECASE,
)

# A weak "AI mentioned only in the description" signal is only trusted when
# the title itself at least reads as a technical/engineering role -- gates
# out Sales/Finance/Ops/Partnerships/Analyst titles that inherit a company's
# "we use AI" boilerplate without being an engineering role at all (the exact
# false-positive class the manual top-25 review flagged).
_TECH_TITLE_NOUN_RE = re.compile(
    r"\b(engineer(?:ing)?|develop(?:er|ment)|architect|scientist|technologist|programmer)\b",
    re.IGNORECASE,
)

_WORK_AUTH_RE = re.compile(
    r"([^.]*\b(?:visa sponsorship|sponsor(?:ship)?|work authorization|"
    r"authorized to work|security clearance|us citizen|u\.s\. citizen|"
    r"citizenship|green card)\b[^.]*\.)",
    re.IGNORECASE,
)

_NEGATIVE_AUTH_RE = re.compile(
    r"\b(us citizens? (?:only|required)|must be (?:a )?(?:us|u\.s\.?|uk) citizen|"
    r"security clearance required|active(?:ly held)? security clearance|"
    r"does not (?:provide|offer) (?:visa )?sponsorship|no visa sponsorship|"
    r"not able to sponsor|cannot sponsor|unable to sponsor|will not sponsor|"
    r"sponsorship is not (?:available|provided))\b",
    re.IGNORECASE,
)

_SALARY_RE = re.compile(
    r"(\$\s?\d{2,3}(?:,\d{3})?\s?[kK]?\s?[-–—]\s?\$?\s?\d{2,3}(?:,\d{3})?\s?[kK]?"
    r"|\$\s?\d{2,3}(?:,\d{3})?\s?[kK]?\s*/\s*(?:yr|year|hour|hr)"
    r"|£\s?\d[\d,]*|€\s?\d[\d,]*)",
    re.IGNORECASE,
)

_TAG_RE = re.compile(r"<[^>]+>")
_JSONLD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
_BOT_BLOCK_RE = re.compile(
    r"just a moment|attention required|cloudflare|access denied|are you a human|"
    r"enable javascript and cookies|captcha",
    re.IGNORECASE,
)


def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = html_mod.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _find_jobposting(node):
    """Recursively hunt a schema.org JobPosting inside a JSON-LD blob -- some
    sites (arbeitnow) wrap it in ``@graph``, most don't."""
    if isinstance(node, dict):
        t = node.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(str(x).lower() == "jobposting" for x in types if x):
            return node
        for v in node.values():
            found = _find_jobposting(v)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_jobposting(item)
            if found is not None:
                return found
    return None


def _extract_schema_org(page_html: str) -> dict | None:
    for block in _JSONLD_RE.findall(page_html):
        try:
            data = json.loads(block.strip())
        except (ValueError, TypeError):
            continue
        jp = _find_jobposting(data)
        if jp:
            return jp
    return None


class DeadPosting(Exception):
    """Fetch-level failure: 404/410, unreachable, or bot-blocked. Never guess
    a verdict from stale DB text when this happens -- record DEAD instead."""

    def __init__(self, evidence: str):
        super().__init__(evidence)
        self.evidence = evidence


class UnparseableURL(Exception):
    """The URL doesn't match this ATS's expected shape (e.g. a Greenhouse-
    powered lead on a custom domain with no gh_jid). Not evidence the posting
    is dead -- fetch_posting falls back to the generic schema.org/HTML path."""


# ---------------------------------------------------------------------------
# Per-platform structured fetchers. Each returns a normalized dict:
#   title, location_text, workplace_type ("remote"/"hybrid"/"onsite"/None),
#   is_remote (True/False/None), description_text (plain), salary_text,
#   source (which parser produced this)
# or raises DeadPosting.
# ---------------------------------------------------------------------------

async def _get(client: httpx.AsyncClient, url: str, **kw) -> httpx.Response:
    """One GET with one retry on a transient failure (network error / 429 / 5xx)."""
    last_exc = None
    for attempt in range(2):
        try:
            r = await client.get(url, timeout=TIMEOUT, **kw)
            if r.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                await asyncio.sleep(1.5)
                continue
            return r
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt == 0:
                await asyncio.sleep(1.0)
                continue
    raise DeadPosting(f"unreachable: {type(last_exc).__name__ if last_exc else 'unknown error'}")


def _extract_gh_jid(lead: dict) -> str | None:
    parsed = urlparse(lead.get("url") or "")
    qs = parse_qs(parsed.query)
    gh_jid = next(iter(qs.get("gh_jid", [])), None)
    if not gh_jid:
        m = re.search(r"/jobs/(\d+)", parsed.path)
        gh_jid = m.group(1) if m else None
    return gh_jid


def _gh_slug_candidates(lead: dict) -> list[str]:
    """Greenhouse board token, in order of confidence. Companies embed the
    Greenhouse board on their own (often Cloudflare-protected) domain, but
    boards-api.greenhouse.io is Greenhouse's own infra and isn't behind that
    same wall -- reaching it at all just requires the right token. When
    source_meta didn't capture one (custom-domain postings, e.g. make.com),
    the company name is usually the token verbatim."""
    candidates = []
    slug = (lead.get("source_meta") or {}).get("slug")
    if slug:
        candidates.append(slug)
    parsed = urlparse(lead.get("url") or "")
    parts = [p for p in parsed.path.split("/") if p]
    if parsed.netloc in ("job-boards.greenhouse.io", "boards.greenhouse.io") and parts:
        candidates.append(parts[0])
    company = re.sub(r"[^a-z0-9]", "", (lead.get("company") or "").lower())
    if company and company not in candidates:
        candidates.append(company)
    return candidates


async def fetch_greenhouse(client: httpx.AsyncClient, lead: dict) -> dict:
    gh_jid = _extract_gh_jid(lead)
    candidates = _gh_slug_candidates(lead)
    if not gh_jid or not candidates:
        raise UnparseableURL("could not determine Greenhouse board token/job id from URL")

    responses: list[httpx.Response] = []
    for slug in candidates:
        api = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{gh_jid}?content=true"
        resp = await _get(client, api, headers=HEADERS)
        if resp.status_code == 200:
            responses = [resp]
            break
        responses.append(resp)
    r = responses[-1]
    if r.status_code == 404:
        raise DeadPosting(f"Greenhouse boards-api 404 for {gh_jid} (tried {candidates}) -- requisition no longer exists")
    if r.status_code != 200:
        raise DeadPosting(f"Greenhouse boards-api HTTP {r.status_code}")
    data = r.json()
    location = ((data.get("location") or {}).get("name") or "").strip()
    metadata = {m.get("name"): m.get("value") for m in (data.get("metadata") or [])}
    working_model = metadata.get("Working Model Eligibility")
    salary_meta = None
    for key in ("Baseline Budgeted Salary", "Other Large Market Budgeted Salary"):
        v = metadata.get(key)
        if isinstance(v, dict) and (v.get("min_cents") or v.get("max_cents")):
            salary_meta = v
            break
    return {
        "source": "greenhouse",
        "title": data.get("title") or lead.get("title"),
        "location_text": location,
        "workplace_type": None,  # Greenhouse has no clean boolean; infer from location/content text
        "is_remote": None,
        "description_text": _strip_html(data.get("content") or ""),
        "salary_text": json.dumps(salary_meta) if salary_meta else "",
        "extra_evidence": f"working model: {working_model}" if working_model else "",
        "final_url": data.get("absolute_url") or lead.get("url"),
    }


_ashby_cache: dict[str, dict | None] = {}
_ashby_locks: dict[str, asyncio.Lock] = {}


async def _fetch_ashby_org(client: httpx.AsyncClient, org: str) -> dict | None:
    if org in _ashby_cache:
        return _ashby_cache[org]
    lock = _ashby_locks.setdefault(org, asyncio.Lock())
    async with lock:
        if org in _ashby_cache:  # another task filled it while we waited
            return _ashby_cache[org]
        api = f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true"
        try:
            r = await _get(client, api, headers=HEADERS)
        except DeadPosting:
            _ashby_cache[org] = None
            return None
        if r.status_code != 200:
            _ashby_cache[org] = None
            return None
        try:
            data = r.json()
        except ValueError:
            _ashby_cache[org] = None
            return None
        by_id = {j.get("id"): j for j in data.get("jobs", [])}
        _ashby_cache[org] = by_id
        return by_id


async def fetch_ashby(client: httpx.AsyncClient, lead: dict) -> dict:
    parsed = urlparse(lead.get("url") or "")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise UnparseableURL("could not parse Ashby org/job-id from URL")
    org, job_id = parts[0], parts[1]
    by_id = await _fetch_ashby_org(client, org)
    if by_id is None:
        raise DeadPosting(f"Ashby job-board API unreachable/empty for org {org!r}")
    job = by_id.get(job_id)
    if job is None:
        raise DeadPosting(f"job {job_id} no longer listed on Ashby board for {org!r} -- likely closed/removed")
    locs = [job.get("location") or ""]
    for sec in job.get("secondaryLocations") or []:
        loc = sec.get("location") if isinstance(sec, dict) else None
        if loc:
            locs.append(loc)
    workplace_type = (job.get("workplaceType") or "").strip() or None
    comp = job.get("compensation") or {}
    salary_text = ""
    summary = comp.get("compensationTierSummary") if isinstance(comp, dict) else None
    if summary:
        salary_text = str(summary)
    return {
        "source": "ashby",
        "title": job.get("title") or lead.get("title"),
        "location_text": " | ".join(location for location in locs if location),
        "workplace_type": workplace_type.lower() if workplace_type else None,
        "is_remote": job.get("isRemote"),
        "description_text": job.get("descriptionPlain") or _strip_html(job.get("descriptionHtml") or ""),
        "salary_text": salary_text,
        "extra_evidence": "",
        "final_url": job.get("jobUrl") or lead.get("url"),
    }


async def fetch_workday(client: httpx.AsyncClient, lead: dict) -> dict:
    parsed = urlparse(lead.get("url") or "")
    host_parts = parsed.netloc.split(".")
    if len(host_parts) < 2:
        raise UnparseableURL("could not parse Workday tenant/host from URL")
    tenant = host_parts[0]
    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) < 2:
        raise UnparseableURL("Workday URL path too short to derive job id")
    site = path_parts[0]
    rest = "/".join(path_parts[1:])
    api = f"https://{parsed.netloc}/wday/cxs/{tenant}/{site}/{rest}"
    r = await _get(client, api, headers={**HEADERS, "Accept": "application/json"})
    ctype = r.headers.get("content-type", "")
    if "application/json" not in ctype:
        # Workday redirects dead/retired requisitions to a generic HTML page
        # (often community.workday.com/maintenance-page) instead of a clean 404.
        final = str(r.url)
        raise DeadPosting(f"Workday requisition not resolvable (redirected to {final})")
    try:
        data = r.json()
    except ValueError as exc:
        raise DeadPosting("Workday cxs endpoint returned unparseable JSON") from exc
    info = data.get("jobPostingInfo")
    if not info:
        raise DeadPosting("Workday cxs response had no jobPostingInfo -- requisition closed")
    country = ((info.get("country") or {}).get("descriptor")) or ""
    req_loc = ((info.get("jobRequisitionLocation") or {}).get("descriptor")) or ""
    location_text = ", ".join(x for x in (info.get("location"), req_loc, country) if x)
    return {
        "source": "workday",
        "title": info.get("title") or lead.get("title"),
        "location_text": location_text,
        "workplace_type": None,  # Workday requisitions are location-anchored; infer via text below
        "is_remote": None,
        "description_text": _strip_html(info.get("jobDescription") or ""),
        "salary_text": "",
        "extra_evidence": "",
        "final_url": info.get("externalUrl") or lead.get("url"),
    }


async def fetch_lever(client: httpx.AsyncClient, lead: dict) -> dict:
    parsed = urlparse(lead.get("url") or "")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise UnparseableURL("could not parse Lever company/job-id from URL")
    company, job_id = parts[0], parts[1]
    api = f"https://api.lever.co/v0/postings/{company}/{job_id}?mode=json"
    r = await _get(client, api, headers=HEADERS)
    if r.status_code == 404:
        raise DeadPosting("Lever posting 404 -- no longer listed")
    if r.status_code != 200:
        raise DeadPosting(f"Lever API HTTP {r.status_code}")
    try:
        data = r.json()
    except ValueError as exc:
        raise DeadPosting("Lever API returned unparseable JSON") from exc
    categories = data.get("categories") or {}
    return {
        "source": "lever",
        "title": data.get("text") or lead.get("title"),
        "location_text": categories.get("location") or "",
        "workplace_type": (data.get("workplaceType") or "").strip().lower() or None,
        "is_remote": (data.get("workplaceType") == "remote") if data.get("workplaceType") else None,
        "description_text": _strip_html(data.get("descriptionBody") or "") + " " + _strip_html(data.get("additional") or ""),
        "salary_text": "",
        "extra_evidence": f"country: {data.get('country')}" if data.get("country") else "",
        "final_url": lead.get("url"),
    }


async def fetch_generic(client: httpx.AsyncClient, lead: dict) -> dict:
    """Fallback for anything without a dedicated ATS API: schema.org JobPosting
    JSON-LD if present, else plain regex over the page text."""
    url = lead.get("url") or ""
    r = await _get(client, url, headers=HEADERS)
    if r.status_code in (404, 410):
        raise DeadPosting(f"HTTP {r.status_code} -- posting no longer exists")
    body = r.text
    if r.status_code == 403 or (r.status_code >= 400 and _BOT_BLOCK_RE.search(body[:4000])):
        raise DeadPosting(f"blocked (HTTP {r.status_code}, anti-bot page)")
    if r.status_code != 200:
        raise DeadPosting(f"HTTP {r.status_code}")
    if _BOT_BLOCK_RE.search(body[:4000]) and len(body) < 20000:
        raise DeadPosting("blocked (anti-bot challenge page, not the real posting)")

    jp = _extract_schema_org(body)
    if jp:
        loc_req = jp.get("applicantLocationRequirements")
        countries = []
        if isinstance(loc_req, list):
            for item in loc_req:
                name = item.get("name") if isinstance(item, dict) else item
                if name:
                    countries.append(str(name))
        elif isinstance(loc_req, dict):
            name = loc_req.get("name")
            if name:
                countries.append(str(name))
        job_location_type = str(jp.get("jobLocationType") or "")
        job_loc = jp.get("jobLocation")
        loc_text_parts = list(countries)
        if isinstance(job_loc, dict):
            addr = job_loc.get("address") or {}
            for k in ("addressLocality", "addressRegion", "addressCountry"):
                v = addr.get(k)
                if v:
                    loc_text_parts.append(str(v))
        base_salary = jp.get("baseSalary")
        salary_text = ""
        if isinstance(base_salary, dict):
            val = base_salary.get("value") or {}
            currency = base_salary.get("currency") or ""
            lo, hi = val.get("minValue"), val.get("maxValue")
            if lo or hi:
                salary_text = f"{currency} {lo}-{hi}"
        workplace_type = "remote" if job_location_type.upper() == "TELECOMMUTE" else None
        return {
            "source": "schema_org",
            "title": jp.get("title") or lead.get("title"),
            "location_text": " | ".join(loc_text_parts),
            "workplace_type": workplace_type,
            "is_remote": True if workplace_type == "remote" else None,
            "description_text": _strip_html(jp.get("description") or ""),
            "salary_text": salary_text,
            "extra_evidence": "",
            "final_url": str(r.url),
        }

    # No structured data at all: last resort is the raw page text.
    return {
        "source": "html_text",
        "title": lead.get("title"),
        "location_text": "",
        "workplace_type": None,
        "is_remote": None,
        "description_text": _strip_html(body)[:6000],
        "salary_text": "",
        "extra_evidence": "",
        "final_url": str(r.url),
    }


_PLATFORM_FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "ashby": fetch_ashby,
    "workday": fetch_workday,
    "lever": fetch_lever,
}


async def fetch_posting(client: httpx.AsyncClient, lead: dict) -> dict:
    platform = (lead.get("platform") or "").strip().lower()
    fetcher = _PLATFORM_FETCHERS.get(platform, fetch_generic)
    if fetcher is fetch_generic:
        return await fetch_generic(client, lead)
    try:
        return await fetcher(client, lead)
    except UnparseableURL:
        # e.g. a Greenhouse-platform lead on a custom domain (make.com) with
        # no gh_jid we can extract -- the posting may still be perfectly
        # alive, just not shaped the way we expected. Fall back rather than
        # calling it DEAD on a URL-parsing miss.
        return await fetch_generic(client, lead)


# ---------------------------------------------------------------------------
# Analysis: turn the fetched structured/plain data into the four verdict axes.
# ---------------------------------------------------------------------------

def classify_role(title: str, description_text: str) -> tuple[bool, str]:
    t = title or ""
    non_eng = _NON_ENG_TITLE_RE.search(t)
    if non_eng:
        return False, f"non-engineering title match: {non_eng.group(0)!r}"
    ai_m = _AI_TITLE_RE.search(t)
    if ai_m:
        return True, f"AI/ML title match: {ai_m.group(0)!r}"
    be_m = _BACKEND_TITLE_RE.search(t)
    if be_m:
        return True, f"senior backend/infra title match (secondary fit): {be_m.group(0)!r}"
    if _TECH_TITLE_NOUN_RE.search(t):
        desc_ai = _AI_TITLE_RE.search(description_text or "")
        if desc_ai:
            return True, f"AI mentioned in description only, title is technical (weak signal): {desc_ai.group(0)!r}"
    return False, "no AI/ML or senior-backend engineering signal in title (or title reads as non-technical)"


def classify_seniority(title: str, description_text: str) -> tuple[bool, str]:
    m = _JUNIOR_RE.search(title or "")
    if m:
        return False, f"junior/intern title match: {m.group(0)!r}"
    # Description-level junior signal only counts if it's clearly about *this*
    # role's level, not a stray mention -- keep it title-only to avoid false
    # rejects from "mentors junior engineers" style copy.
    return True, "no junior/intern/new-grad signal in title"


_LOC_ANYWHERE_RE = re.compile(r"\b(anywhere|worldwide|global|any\s*location)\b", re.IGNORECASE)


def classify_geo(struct: dict) -> tuple[str, str]:
    """remote_policy + evidence, from structured fields first, live-text
    regex only when the platform gave us no explicit remote flag.

    Deliberately scores the STRUCTURED location field (short: "Canada",
    "Bengaluru, IND", "Anywhere") ahead of the full job-description body.
    The manual top-25 pass found company-wide boilerplate ("globally
    distributed, remote-first team") in the description text of postings
    whose actual location field was a single specific country -- scanning
    the full text for that phrase produces exactly that false positive.
    Full text is only consulted when the platform gave us no location field
    at all (schema_org/html_text fallback)."""
    loc = (struct.get("location_text") or "").strip()
    text = struct.get("description_text") or ""
    wt = (struct.get("workplace_type") or "").lower()
    is_remote = struct.get("is_remote")

    signal_text = loc if loc else text
    strong = _REGION_LOCK_STRONG_RE.search(signal_text)
    weak = _REGION_LOCK_WEAK_RE.search(signal_text)
    global_m = _GLOBAL_RE.search(signal_text) or _LOC_ANYWHERE_RE.search(signal_text)
    india_m = _INDIA_RE.search(signal_text)

    if wt == "onsite" or is_remote is False:
        return "onsite", (loc or (weak.group(0) if weak else "workplaceType: onsite"))
    if wt == "hybrid":
        return "hybrid", loc or "workplaceType: hybrid"
    if wt == "remote" or is_remote is True:
        if strong:
            return "remote-region-locked", strong.group(0)
        if global_m or india_m:
            return "remote-anywhere", global_m.group(0) if global_m else f"location includes India: {loc}"
        if loc:
            return "remote-region-locked", loc  # remote, but anchored to a specific place with no "anywhere" language
        return "remote-anywhere", "workplaceType: remote, no location restriction stated"

    # No structured remote flag at all (Greenhouse/Workday always land here; Ashby/Lever sometimes too).
    if strong:
        return "remote-region-locked", strong.group(0)
    if global_m:
        return "remote-anywhere", global_m.group(0)
    if india_m:
        return ("hybrid" if weak else "onsite"), f"India location: {loc or india_m.group(0)}"
    if weak:
        return "onsite", weak.group(0)
    if loc:
        # A specific location string with no remote/global/region-lock wording
        # anywhere means that location IS the job's requirement (this is how
        # Greenhouse/Workday always present a location, and how Ashby/Lever
        # present one when their own remote flag is null).
        return "onsite", loc
    return "unclear", "no explicit remote/location signal in live posting"


def extract_work_auth(text: str) -> str:
    m = _WORK_AUTH_RE.search(text or "")
    return m.group(0).strip()[:220] if m else ""


def extract_comp(struct: dict) -> str:
    if struct.get("salary_text"):
        return str(struct["salary_text"])[:200]
    m = _SALARY_RE.search(struct.get("description_text") or "")
    return m.group(0) if m else ""


# Same idea as shortlist_global's own _EOR_RE, but scanning it over a live
# job DESCRIPTION (not a title) demands much higher precision -- a full page
# of prose easily contains an incidental "force multiplier" (matches a bare
# "multiplier", the EOR platform's name) or a boilerplate privacy-policy URL
# slug like ".../global-employee-and-contractor-privacy-policy.pdf" (matches
# bare "contractor"). Both were caught live: dropped the collision-prone bare
# tokens (contractor, eor, multiplier, omnipresent, b2b) and kept only named
# EOR platforms distinctive enough not to appear by accident, plus explicit
# contractor-hiring phrases that require real surrounding context.
_EOR_LIVE_RE = re.compile(
    r"\b(deel|remote\.com|oysterhr|oyster hr|velocity global|papaya global|"
    r"globalization partners|g-p\.com|justworks|rippling global|"
    r"employer of record|1099 contractor|freelance contract|"
    r"hire[sd]? as an? (?:contractor|1099)|"
    r"no (?:visa )?sponsorship required|does not require (?:visa )?sponsorship)\b",
    re.IGNORECASE,
)


def decide_verdict(*, is_ai: bool, ai_reason: str, seniority_ok: bool, seniority_reason: str,
                    policy: str, geo_evidence: str, eor_confirmed: bool, work_auth_text: str) -> tuple[str, str]:
    """Never trusts the shortlist's own pre-filter band -- only what was
    actually found on the live posting (geo_evidence / eor_confirmed)."""
    india_evidence = bool(_INDIA_RE.search(geo_evidence or ""))
    neg_auth = _NEGATIVE_AUTH_RE.search(work_auth_text)
    # "Does not offer visa sponsorship" / "US citizens only" is US-immigration
    # boilerplate -- it says nothing about a role the LIVE posting's own
    # location field already confirms is India-located or India-remote (e.g.
    # Docker's "Senior Solutions Engineer (India)", wrongly REJECTED on this
    # exact disclaimer before this fix). Only reject on it when geo hasn't
    # already cleared the candidate via explicit India evidence.
    if neg_auth and not india_evidence:
        return "REJECTED", f"work-authorization block: {neg_auth.group(0)!r}"
    if not is_ai:
        return "REJECTED", f"relevance: {ai_reason}"
    if not seniority_ok:
        return "REJECTED", f"seniority: {seniority_reason}"

    if policy in ("onsite", "hybrid"):
        if india_evidence:
            return "CONFIRMED", f"India-based {policy} role: {geo_evidence} -- verify relocation/remote terms directly"
        return "REJECTED", f"geo: {policy}, not WFH-compatible -- {geo_evidence}"
    if policy == "remote-region-locked":
        if india_evidence:
            return "CONFIRMED", f"geo: remote, includes India -- {geo_evidence}"
        if eor_confirmed:
            return "CONFIRMED", f"geo: remote (anchored to {geo_evidence}) but EOR/contractor hiring language confirmed live -- may still be hireable via EOR regardless of the stated anchor"
        return "REJECTED", f"geo: remote but region-locked away from India -- {geo_evidence}"
    if policy == "remote-anywhere":
        return "CONFIRMED", f"geo: remote-anywhere confirmed -- {geo_evidence}"
    return "UNCLEAR", f"geo: could not determine eligibility from the live posting -- {geo_evidence}"


def analyze(lead: dict, struct: dict) -> dict:
    title = struct.get("title") or lead.get("title") or ""
    desc = struct.get("description_text") or ""

    is_ai, ai_reason = classify_role(title, desc)
    seniority_ok, seniority_reason = classify_seniority(title, desc)
    policy, geo_evidence = classify_geo(struct)
    work_auth = extract_work_auth(f"{struct.get('location_text','')} {desc}")
    comp = extract_comp(struct)
    eor_confirmed = bool(_EOR_LIVE_RE.search(f"{struct.get('location_text','')} {desc}"))
    verdict, verdict_evidence = decide_verdict(
        is_ai=is_ai, ai_reason=ai_reason, seniority_ok=seniority_ok, seniority_reason=seniority_reason,
        policy=policy, geo_evidence=geo_evidence, eor_confirmed=eor_confirmed, work_auth_text=work_auth,
    )
    return {
        "remote_policy": policy,
        "location_requirement": geo_evidence[:300],
        "work_authorization": work_auth,
        "is_ai_role": is_ai,
        "ai_reason": ai_reason,
        "seniority_ok": seniority_ok,
        "seniority_reason": seniority_reason,
        "comp": comp,
        "verdict": verdict,
        "evidence": verdict_evidence[:400],
        "source": struct.get("source"),
        "final_url": struct.get("final_url"),
    }


# ---------------------------------------------------------------------------
# Orchestration: fetch + analyze every lead, cached + resumable, then persist.
# ---------------------------------------------------------------------------

def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


async def verify_one(client: httpx.AsyncClient, sem: asyncio.Semaphore, lead: dict) -> dict:
    async with sem:
        try:
            struct = await fetch_posting(client, lead)
        except DeadPosting as exc:
            return {
                "job_id": lead["job_id"], "verdict": "DEAD", "evidence": exc.evidence[:400],
                "remote_policy": "", "location_requirement": "", "work_authorization": "",
                "is_ai_role": None, "seniority_ok": None, "comp": "", "source": "",
                "final_url": lead.get("url"), "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        except Exception as exc:  # noqa: BLE001 -- one bad lead must never kill the whole run
            return {
                "job_id": lead["job_id"], "verdict": "UNCLEAR", "evidence": f"internal error: {type(exc).__name__}: {exc}"[:400],
                "remote_policy": "", "location_requirement": "", "work_authorization": "",
                "is_ai_role": None, "seniority_ok": None, "comp": "", "source": "",
                "final_url": lead.get("url"), "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        result = analyze(lead, struct)
        result["job_id"] = lead["job_id"]
        result["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return result


def persist_verdict(conn, result: dict) -> None:
    conn.execute(
        "UPDATE leads SET verify_status=?, verify_evidence=?, verify_checked_at=? WHERE job_id=?",
        (result["verdict"], result.get("evidence", "")[:500], result["checked_at"], result["job_id"]),
    )
    # Audit trail: the verdict + evidence, not just the DB column update -- so
    # the dashboard's activity feed can show WHEN and WHY a lead was verified,
    # not just its current state.
    conn.execute(
        "INSERT INTO events(job_id,action) VALUES(?,?)",
        (result["job_id"], f"verified verdict={result['verdict']} evidence={result.get('evidence', '')[:200]}"),
    )


async def run(shortlist: list[dict], db_path: str, *, fresh: bool, concurrency: int) -> dict:
    cache = {} if fresh else load_cache()
    to_fetch = [lead for lead in shortlist if fresh or lead["job_id"] not in cache]
    print(f"  {len(shortlist)} leads in shortlist, {len(cache)} already cached, {len(to_fetch)} to fetch\n")

    if to_fetch:
        sem = asyncio.Semaphore(concurrency)
        conn = get_connection(db_path)
        done = 0
        async with httpx.AsyncClient(follow_redirects=True) as client:
            tasks = {asyncio.ensure_future(verify_one(client, sem, lead)): lead for lead in to_fetch}
            for coro in asyncio.as_completed(tasks):
                result = await coro
                cache[result["job_id"]] = result
                persist_verdict(conn, result)
                conn.commit()
                save_cache(cache)
                done += 1
                if done % 10 == 0 or done == len(to_fetch):
                    print(f"  ... {done}/{len(to_fetch)} fetched")
    return cache


def _selfcheck() -> None:
    """Docker's "Senior Solutions Engineer (India)" was wrongly REJECTED on a
    US-visa-sponsorship disclaimer even though the live posting's own
    location field said India -- this pins that exact regression."""
    common = dict(is_ai=True, ai_reason="ok", seniority_ok=True, seniority_reason="ok", eor_confirmed=False)
    verdict, evidence = decide_verdict(
        policy="onsite", geo_evidence="Bengaluru, India",
        work_auth_text="We are not able to sponsor visas at this time.", **common,
    )
    assert verdict == "CONFIRMED", f"India-located role must not be rejected on US visa boilerplate: {evidence}"

    # A genuinely US-only role with the same disclaimer must still reject.
    verdict, evidence = decide_verdict(
        policy="remote-region-locked", geo_evidence="United States only",
        work_auth_text="We do not offer visa sponsorship.", **common,
    )
    assert verdict == "REJECTED", f"non-India role with a real auth block must still reject: {evidence}"


def main() -> int:
    _selfcheck()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=None, help="database file (defaults to the installed app's)")
    parser.add_argument("--limit", type=int, default=None, help="only verify the first N shortlist leads (smoke test)")
    parser.add_argument("--fresh", action="store_true", help="ignore the cache and re-verify everything")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY)
    args = parser.parse_args()

    db_path = run_scrape.resolve_db(args.db)
    print(f"  DB: {db_path}")
    run_migrations(db_path)  # adds verify_status/verify_evidence/verify_checked_at if missing

    leads = get_all_leads(db_path)
    shortlist = sg.filtered_ranked_leads(leads)
    if args.limit:
        shortlist = shortlist[: args.limit]

    cache = asyncio.run(run(shortlist, db_path, fresh=args.fresh, concurrency=args.concurrency))

    counts: dict[str, int] = {}
    for lead in shortlist:
        v = cache.get(lead["job_id"], {}).get("verdict", "UNCLEAR")
        counts[v] = counts.get(v, 0) + 1
    total = len(shortlist)
    confirmed = counts.get("CONFIRMED", 0)
    print(f"\n  Verified {total} leads: CONFIRMED={confirmed} REJECTED={counts.get('REJECTED', 0)} "
          f"UNCLEAR={counts.get('UNCLEAR', 0)} DEAD={counts.get('DEAD', 0)}")
    if total:
        print(f"  Confirm rate: {confirmed / total * 100:.1f}%")
    print(f"  Cache: {CACHE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
