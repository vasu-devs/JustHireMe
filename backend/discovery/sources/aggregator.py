"""Keyless, field-agnostic job aggregator.

The reliable backbone for "actually return real jobs with zero config". Unlike the
Google-dork -> headless-Chromium -> LLM path (which bot-blocks and needs a working
LLM), these are plain public JSON APIs that need no key and no browser:

  * Arbeitnow  (https://www.arbeitnow.com/api/job-board-api) - global feed, all fields
  * The Muse   (https://www.themuse.com/api/public/jobs)     - broad categories, US-heavy

Both are queried keyless, merged, de-duplicated, and filtered client-side to the
candidate's own role terms so a nurse gets nursing roles and an SRE gets SRE roles
from the SAME code path — no per-field configuration. Each fetcher is independently
fail-safe: a schema change or outage in one never blocks the other, and a total
failure returns [] (the caller records a source error) rather than raising.

Dispatched from free_scout via an ``aggregator:<role query>[@@<location>]`` target,
emitted zero-config by core.config.profile_free_source_targets.
"""

from __future__ import annotations

import logging
import re

from discovery.normalizer import strip_html_text
from discovery.sources.common import retry_after_seconds
from discovery.sources.net import guarded_async_client

_log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "JustHireMe job aggregator",
    "Accept": "application/json",
}

# Role-keyword -> The Muse category. Only categories VERIFIED to return results from
# the live public API (www.themuse.com/api/public/jobs) are used — several plausible
# names ("Nursing", "Installation Maintenance and Repairs", "Restaurant and Food
# Service") return zero, so healthcare maps to "Healthcare" and fields with no valid
# Muse category (trades/hospitality) map to "" and skip The Muse (Arbeitnow +
# community sources cover them). The client-side role filter refines within a category.
_MUSE_CATEGORIES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("nurse", "nursing", "clinical", "doctor", "physician", "medical", "healthcare",
      "therapist", "pharmacist", "dental", "caregiver", "paramedic", "surgeon"), "Healthcare"),
    (("software", "developer", "programmer", "backend", "frontend", "full stack",
      "devops", "sre", "sde", "data scientist", "data engineer", "machine learning",
      "ml engineer", "analyst", "analytics"), "Software Engineering"),
    (("designer", "design", "ux", "ui "), "Design and UX"),
    (("product manager", "product owner"), "Product Management"),
    (("project manager", "program manager", "scrum"), "Project Management"),
    (("marketing", "seo", "growth", "brand", "content"), "Marketing"),
    (("sales", "account executive", "business development"), "Sales"),
    (("accountant", "accounting", "bookkeeper", "auditor", "finance", "financial"), "Accounting and Finance"),
    (("lawyer", "attorney", "paralegal", "legal", "counsel"), "Legal Services"),
    (("teacher", "tutor", "instructor", "professor", "lecturer", "educator", "education"), "Education"),
    (("recruiter", "recruiting", "talent", "human resources", "hr "), "Human Resources and Recruitment"),
    (("customer service", "customer support", "support agent", "help desk"), "Customer Service"),
    (("retail", "cashier", "store associate", "merchandiser"), "Retail"),
    (("writer", "editor", "journalist", "copywriter"), "Writing and Editing"),
    (("social worker", "counselor", "case manager"), "Social Services"),
    (("scientist", "researcher", "laboratory", "biologist", "chemist", "engineer"), "Science and Engineering"),
    (("driver", "warehouse", "logistics", "forklift", "courier"), "Transportation and Logistics"),
)


def _role_terms(role_query: str) -> list[str]:
    """Meaningful tokens + short phrases from the role query for client-side matching."""
    text = (role_query or "").lower()
    tokens = [t for t in re.split(r"[^a-z0-9+#.]+", text) if len(t) >= 3]
    # de-dupe, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _matches_role(text: str, role_terms: list[str]) -> bool:
    if not role_terms:
        return True
    low = (text or "").lower()
    return any(term in low for term in role_terms)


def _muse_category(role_terms: list[str]) -> str:
    joined = " ".join(role_terms)
    for keys, category in _MUSE_CATEGORIES:
        if any(k.strip() in joined for k in keys):
            return category
    return ""


def _desc(*parts: str, limit: int = 1800) -> str:
    text = "\n".join(p.strip() for p in parts if p and p.strip())
    return text[:limit]


async def _fetch_arbeitnow(role_terms: list[str]) -> list[dict]:
    out: list[dict] = []
    async with guarded_async_client(timeout=30, headers=_HEADERS, follow_redirects=True) as cx:
        r = await cx.get("https://www.arbeitnow.com/api/job-board-api")
        if r.status_code == 429:
            import asyncio
            await asyncio.sleep(retry_after_seconds(r.headers.get("Retry-After")))
            r.raise_for_status()
        r.raise_for_status()
        data = r.json()
    rows = data.get("data", []) if isinstance(data, dict) else []
    for job in rows:
        if not isinstance(job, dict):
            continue
        title = str(job.get("title") or "").strip()
        url = str(job.get("url") or "").strip()
        if not title or not url:
            continue
        tags = job.get("tags") or []
        # Match the TITLE (not tags): Arbeitnow is a broad, Germany-heavy feed and a
        # tag-based match let unrelated roles ("Technical Sales Support" tagged
        # "engineering") through. The role phrase must be in the actual job title.
        if not _matches_role(title, role_terms):
            continue
        location = str(job.get("location") or "").strip()
        remote = "remote" if job.get("remote") else ""
        out.append({
            "title": title,
            "company": str(job.get("company_name") or "").strip(),
            "url": url,
            "platform": "arbeitnow",
            "description": _desc(strip_html_text(str(job.get("description") or "")),
                                 f"Location: {location}" if location else "",
                                 remote),
            "posted_date": "",  # arbeitnow created_at is a unix ts; treat as fresh feed
            "_fresh_source": "aggregator",
            "source_meta": {"source": "arbeitnow", "location": location, "tags": [str(t) for t in tags if t]},
        })
    return out


async def _fetch_themuse(role_terms: list[str]) -> list[dict]:
    category = _muse_category(role_terms)
    if not category:
        # No field-appropriate Muse category (e.g. trades / hospitality). Skip it —
        # querying with no category returns a random slice of everything. Arbeitnow +
        # the community sources cover these fields.
        return []
    out: list[dict] = []
    # The Muse API is 1-INDEXED (page=0 returns empty). Location is intentionally NOT
    # sent: its filter is a US-centric fixed vocabulary and a non-matching value
    # returns zero — ranking scores location fit downstream instead.
    async with guarded_async_client(timeout=30, headers=_HEADERS, follow_redirects=True) as cx:
        for page in ("1", "2"):
            r = await cx.get("https://www.themuse.com/api/public/jobs",
                             params={"page": page, "category": category})
            if r.status_code == 429:
                import asyncio
                await asyncio.sleep(retry_after_seconds(r.headers.get("Retry-After")))
                r.raise_for_status()
            r.raise_for_status()
            data = r.json()
            rows = data.get("results", []) if isinstance(data, dict) else []
            for job in rows:
                if not isinstance(job, dict):
                    continue
                title = str(job.get("name") or "").strip()
                refs = job.get("refs") if isinstance(job.get("refs"), dict) else {}
                url = str((refs or {}).get("landing_page") or "").strip()
                if not title or not url:
                    continue
                # No title role-filter here: the Muse CATEGORY is already the field
                # cut, and legal/clinical titles rarely echo the CV's exact word
                # ("Attorney"/"Counsel" vs "lawyer"). Discovery favours recall; the
                # ranker provides sub-role precision.
                company = ""
                if isinstance(job.get("company"), dict):
                    company = str(job["company"].get("name") or "").strip()
                locs = job.get("locations") or []
                loc_names = ", ".join(str(loc.get("name") or "") for loc in locs if isinstance(loc, dict))
                # A Muse listing is a currently-OPEN role regardless of publication
                # age, so (like an ATS board) don't stale-drop it. Leave posted_date
                # empty and mark the source recency-trusted so the downstream freshness
                # gate keeps it; keep the real date only as informational metadata.
                out.append({
                    "title": title,
                    "company": company,
                    "url": url,
                    "platform": "themuse",
                    "description": _desc(strip_html_text(str(job.get("contents") or "")),
                                         f"Location: {loc_names}" if loc_names else ""),
                    "posted_date": "",
                    "_fresh_source": "aggregator",
                    "source_meta": {"source": "themuse", "location": loc_names,
                                    "published": str(job.get("publication_date") or "")},
                })
    return out


async def scrape_aggregator(role_query: str, location: str = "") -> list[dict]:
    """Query the keyless aggregators for the candidate's role and return normalized leads."""
    role_terms = _role_terms(role_query)
    results: list[dict] = []
    for name, coro in (
        ("arbeitnow", _fetch_arbeitnow(role_terms)),
        ("themuse", _fetch_themuse(role_terms)),
    ):
        try:
            results.extend(await coro)
        except Exception as exc:
            _log.warning("aggregator source %s failed: %s", name, exc)
    # De-dupe by URL, preserving first occurrence.
    seen: set[str] = set()
    deduped: list[dict] = []
    for lead in results:
        key = str(lead.get("url") or "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(lead)
    return deduped


async def scrape_aggregator_target(target: str) -> list[dict]:
    """Dispatch an ``aggregator:<role query>[@@<location>]`` free-scout target."""
    body = target.split(":", 1)[1] if ":" in target else target
    role_query, _, location = body.partition("@@")
    return await scrape_aggregator(role_query.strip(), location.strip())
