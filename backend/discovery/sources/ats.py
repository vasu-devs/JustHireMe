from __future__ import annotations
import logging

from datetime import datetime, timezone
from urllib.parse import urlparse

from discovery.normalizer import clean_text, is_recent, strip_html_text
from discovery.sources.common import json_get, text_lead


def is_ats_target(target: str) -> bool:
    lower = target.lower()
    if lower.startswith("ats:"):
        return True
    if not lower.startswith(("http://", "https://")):
        return False
    return any(host in lower for host in ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com"))


async def scrape_greenhouse(slug: str) -> list[dict]:
    data = await json_get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", {"content": "true"})
    if not isinstance(data, dict):
        return []
    results = []
    for job in data.get("jobs", []):
        updated = job.get("updated_at") or ""
        if updated and not is_recent(updated):
            continue
        desc = strip_html_text(job.get("content") or "")
        location = ", ".join(
            loc.get("name", "")
            for loc in (job.get("offices") or [])
            if isinstance(loc, dict) and loc.get("name")
        ) or (job.get("location") or {}).get("name", "")
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


async def scrape_direct_ats_url(url: str) -> list[dict]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/").split("/")
    if "greenhouse.io" in host and path:
        slug = path[-1] if "boards.greenhouse.io" in host else path[0]
        return await scrape_greenhouse(slug)
    if "lever.co" in host and path:
        return await scrape_lever(path[0])
    if "ashbyhq.com" in host and path:
        return await scrape_ashby(path[0])
    if "workable.com" in host and path:
        slug = path[0] if path[0] not in {"j", "api"} else ""
        if slug:
            return await scrape_workable(slug)
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
    if lower.startswith(("http://", "https://")):
        return await scrape_direct_ats_url(target)
    return []
