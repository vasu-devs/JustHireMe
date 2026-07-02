from __future__ import annotations
import logging

from datetime import datetime, timezone
from urllib.parse import urlparse

from discovery.normalizer import clean_text, is_recent, strip_html_text
from discovery.sources.common import json_get, text_lead, xml_get

# Keyless, direct public JSON/XML job-board APIs. Preferred over the fragile
# Google-dork -> browser -> LLM path: no key, no browser, stable schema.
_ATS_HOSTS = (
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "workable.com",
    "smartrecruiters.com",
    "recruitee.com",
    "jobs.personio.",  # {slug}.jobs.personio.com / .de
)


def is_ats_target(target: str) -> bool:
    lower = target.lower()
    if lower.startswith("ats:"):
        return True
    if not lower.startswith(("http://", "https://")):
        return False
    return any(host in lower for host in _ATS_HOSTS)


async def scrape_greenhouse(slug: str) -> list[dict]:
    data = await json_get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", {"content": "true"})
    if not isinstance(data, dict):
        return []
    results = []
    for job in data.get("jobs", []):
        # A single non-dict element (proxy/CDN-mangled response) must not abort the
        # whole board — skip it and keep the valid postings. (Mirrors scrape_workable.)
        if not isinstance(job, dict):
            continue
        updated = job.get("updated_at") or ""
        if updated and not is_recent(updated):
            continue
        desc = strip_html_text(job.get("content") or "")
        loc_field = job.get("location")
        location = ", ".join(
            loc.get("name", "")
            for loc in (job.get("offices") or [])
            if isinstance(loc, dict) and loc.get("name")
        ) or (loc_field.get("name", "") if isinstance(loc_field, dict) else "")
        if location:
            desc = (desc + f"\nLocation: {location}").strip()
        results.append(text_lead({
            "title": job.get("title", ""),
            "company": slug,
            "url": job.get("absolute_url", ""),
            "platform": "greenhouse",
            "description": desc[:1200],
            "posted_date": updated,
            "source_meta": {"ats": "greenhouse", "slug": slug},
        }))
    return results


async def scrape_lever(slug: str) -> list[dict]:
    data = await json_get(f"https://api.lever.co/v0/postings/{slug}", {"mode": "json"})
    results = []
    for job in data if isinstance(data, list) else []:
        if not isinstance(job, dict):
            continue
        created = ""
        if job.get("createdAt"):
            try:
                created = datetime.fromtimestamp(int(job["createdAt"]) / 1000, tz=timezone.utc).isoformat()
            except Exception as log_exc:
                logging.getLogger(__name__).warning('suppressed exception in backend/discovery/sources/ats.py:scrape_lever: %s', log_exc)
                created = str(job.get("createdAt"))
        if created and not is_recent(created):
            continue
        parts = [
            job.get("descriptionPlain", ""),
            job.get("additionalPlain", ""),
            " ".join(str(x) for x in (job.get("categories") or {}).values() if x),
        ]
        results.append(text_lead({
            "title": job.get("text", ""),
            "company": slug,
            "url": job.get("hostedUrl", ""),
            "platform": "lever",
            "description": clean_text("\n".join(parts))[:1200],
            "posted_date": created,
            "source_meta": {"ats": "lever", "slug": slug},
        }))
    return results


async def scrape_ashby(slug: str) -> list[dict]:
    data = await json_get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    results = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        posted = job.get("publishedDate") or job.get("updatedAt") or ""
        if posted and not is_recent(posted):
            continue
        desc = strip_html_text(job.get("descriptionHtml") or job.get("descriptionPlain") or "")
        location = job.get("locationName") or ""
        if location:
            desc = (desc + f"\nLocation: {location}").strip()
        url = job.get("jobUrl") or job.get("applyUrl") or f"https://jobs.ashbyhq.com/{slug}/{job.get('id', '')}"
        results.append(text_lead({
            "title": job.get("title", ""),
            "company": slug,
            "url": url,
            "platform": "ashby",
            "description": desc[:1200],
            "posted_date": posted,
            "source_meta": {"ats": "ashby", "slug": slug},
        }))
    return results


async def scrape_workable(slug: str) -> list[dict]:
    try:
        data = await json_get(f"https://www.workable.com/api/accounts/{slug}", {"details": "true"})
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/discovery/sources/ats.py:scrape_workable: %s', log_exc)
        data = await json_get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")

    if isinstance(data, list):
        jobs = data
    elif isinstance(data, dict):
        jobs = data.get("jobs") or data.get("results") or data.get("positions") or []
    else:
        jobs = []

    results = []
    for job in jobs if isinstance(jobs, list) else []:
        if not isinstance(job, dict):
            continue
        posted = (
            job.get("published_on")
            or job.get("published")
            or job.get("created_at")
            or job.get("updated_at")
            or ""
        )
        if posted and not is_recent(posted):
            continue
        location_data = job.get("location") or {}
        if isinstance(location_data, dict):
            location = ", ".join(str(x) for x in location_data.values() if x)
        else:
            location = str(location_data or "")
        desc = clean_text("\n".join([
            strip_html_text(job.get("description") or job.get("full_description") or ""),
            strip_html_text(job.get("requirements") or ""),
            strip_html_text(job.get("benefits") or ""),
            f"Location: {location}" if location else "",
        ]))
        code = job.get("shortcode") or job.get("code") or job.get("id") or ""
        url = (
            job.get("url")
            or job.get("application_url")
            or job.get("shortlink")
            or (f"https://apply.workable.com/{slug}/j/{code}/" if code else f"https://apply.workable.com/{slug}/")
        )
        results.append(text_lead({
            "title": job.get("title") or job.get("full_title") or "",
            "company": slug,
            "url": url,
            "platform": "workable",
            "description": desc[:1200],
            "posted_date": posted,
            "location": location,
            "source_meta": {"ats": "workable", "slug": slug},
        }))
    return results


async def scrape_smartrecruiters(slug: str) -> list[dict]:
    data = await json_get(
        f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", {"limit": "100"}
    )
    postings = data.get("content", []) if isinstance(data, dict) else []
    results = []
    for job in postings if isinstance(postings, list) else []:
        if not isinstance(job, dict):
            continue
        posted = job.get("releasedDate") or ""
        if posted and not is_recent(posted):
            continue
        loc = job.get("location") or {}
        location = ", ".join(
            str(loc.get(k, "")) for k in ("city", "region", "country")
            if isinstance(loc, dict) and loc.get(k)
        )
        company = (job.get("company") or {}).get("name") if isinstance(job.get("company"), dict) else ""
        job_id = str(job.get("id") or "")
        url = f"https://jobs.smartrecruiters.com/{slug}/{job_id}" if job_id else f"https://jobs.smartrecruiters.com/{slug}"
        desc = job.get("name", "")
        if location:
            desc = (desc + f"\nLocation: {location}").strip()
        results.append(text_lead({
            "title": job.get("name", ""),
            "company": company or slug,
            "url": url,
            "platform": "smartrecruiters",
            "description": desc[:1200],
            "posted_date": posted,
            "location": location,
            "source_meta": {"ats": "smartrecruiters", "slug": slug},
        }))
    return results


async def scrape_recruitee(slug: str) -> list[dict]:
    data = await json_get(f"https://{slug}.recruitee.com/api/offers/")
    offers = data.get("offers", []) if isinstance(data, dict) else []
    results = []
    for job in offers if isinstance(offers, list) else []:
        if not isinstance(job, dict):
            continue
        posted = job.get("published_at") or job.get("created_at") or ""
        if posted and not is_recent(posted):
            continue
        location = ", ".join(
            str(job.get(k, "")) for k in ("city", "country") if job.get(k)
        ) or str(job.get("location") or "")
        desc = clean_text("\n".join([
            strip_html_text(job.get("description") or ""),
            strip_html_text(job.get("requirements") or ""),
            f"Location: {location}" if location else "",
        ]))
        url = (
            job.get("careers_url")
            or job.get("careers_apply_url")
            or f"https://{slug}.recruitee.com/o/{job.get('slug', '')}"
        )
        results.append(text_lead({
            "title": job.get("title", ""),
            "company": job.get("company_name") or slug,
            "url": url,
            "platform": "recruitee",
            "description": desc[:1200],
            "posted_date": posted,
            "location": location,
            "source_meta": {"ats": "recruitee", "slug": slug},
        }))
    return results


async def scrape_personio(slug: str, tld: str = "") -> list[dict]:
    """Scrape a Personio tenant. With no explicit TLD (the watchlist / ats: form
    carries none), try .com then .de so a .de-only tenant isn't silently missed."""
    candidates = [tld.lstrip(".")] if tld else ["com", "de"]
    for candidate in candidates:
        results = await _scrape_personio_at(slug, candidate)
        if results:
            return results
    return []


async def _scrape_personio_at(slug: str, tld: str) -> list[dict]:
    from defusedxml import ElementTree as DefusedET

    tld = (tld or "com").lstrip(".")
    base = f"https://{slug}.jobs.personio.{tld}"
    xml = await xml_get(f"{base}/xml")
    try:
        root = DefusedET.fromstring(xml)
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/discovery/sources/ats.py:scrape_personio: %s', log_exc)
        return []
    results = []
    for pos in root.iter("position"):
        def _text(tag: str, node=pos) -> str:
            el = node.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""

        posted = _text("createdAt")
        if posted and not is_recent(posted):
            continue
        title = _text("name")
        location = _text("office")
        desc_parts = [title]
        for jd in pos.iter("jobDescription"):
            value = jd.find("value")
            if value is not None and value.text:
                desc_parts.append(strip_html_text(value.text))
        if location:
            desc_parts.append(f"Location: {location}")
        job_id = _text("id")
        url = f"{base}/job/{job_id}" if job_id else f"{base}/"
        results.append(text_lead({
            "title": title,
            "company": slug,
            "url": url,
            "platform": "personio",
            "description": clean_text("\n".join(desc_parts))[:1200],
            "posted_date": posted,
            "location": location,
            "source_meta": {"ats": "personio", "slug": slug},
        }))
    return results


async def scrape_direct_ats_url(url: str) -> list[dict]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    subdomain = host.split(".")[0]
    path = parsed.path.strip("/").split("/")
    if "greenhouse.io" in host and path:
        # Company is always the FIRST path segment for board hosts — both the bare
        # /{company} board and the /{company}/jobs/{id} detail URL. path[-1] grabbed
        # the job id for detail links and scraped a non-existent board.
        return await scrape_greenhouse(path[0])
    if "lever.co" in host and path:
        return await scrape_lever(path[0])
    if "ashbyhq.com" in host and path:
        return await scrape_ashby(path[0])
    if "workable.com" in host and path:
        slug = path[0] if path[0] not in {"j", "api"} else ""
        if slug:
            return await scrape_workable(slug)
    if "smartrecruiters.com" in host:
        # jobs.smartrecruiters.com/{company}/... or api.smartrecruiters.com/v1/companies/{company}/...
        if "companies" in path:
            idx = path.index("companies")
            if idx + 1 < len(path):
                return await scrape_smartrecruiters(path[idx + 1])
        elif path and path[0]:
            return await scrape_smartrecruiters(path[0])
        return []
    if "recruitee.com" in host and subdomain not in {"www", ""}:
        return await scrape_recruitee(subdomain)
    if "jobs.personio." in host and subdomain not in {"www", ""}:
        # Preserve the tenant's real TLD (.com / .de) instead of hardcoding .com.
        return await scrape_personio(subdomain, host.rsplit(".", 1)[-1] or "com")
    return []


async def scrape_target(target: str) -> list[dict]:
    lower = target.lower()
    if lower.startswith("ats:greenhouse:"):
        return await scrape_greenhouse(target.split(":", 2)[2].strip())
    if lower.startswith("ats:lever:"):
        return await scrape_lever(target.split(":", 2)[2].strip())
    if lower.startswith("ats:ashby:"):
        return await scrape_ashby(target.split(":", 2)[2].strip())
    if lower.startswith("ats:workable:"):
        return await scrape_workable(target.split(":", 2)[2].strip())
    if lower.startswith("ats:smartrecruiters:"):
        return await scrape_smartrecruiters(target.split(":", 2)[2].strip())
    if lower.startswith("ats:recruitee:"):
        return await scrape_recruitee(target.split(":", 2)[2].strip())
    if lower.startswith("ats:personio:"):
        return await scrape_personio(target.split(":", 2)[2].strip())
    if lower.startswith(("http://", "https://")):
        return await scrape_direct_ats_url(target)
    return []
