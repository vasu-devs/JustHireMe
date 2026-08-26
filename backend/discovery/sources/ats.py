from __future__ import annotations
import asyncio
import html as html_lib
import json
import logging
import re

import httpx

from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse

from discovery.normalizer import clean_text, strip_html_text
from discovery.sources.common import current_listing_active_hint, json_get, json_post, text_get, text_lead, xml_get

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
    "himalayas.app",
    "teamtailor.com",
    "breezy.hr",
    "pinpointhq.com",
    "bamboohr.com",
    "rippling.com",
    "zohorecruit.com",
    "zohorecruit.in",
    "freshteam.com",
    "keka.com",
    "oraclecloud.com",
    "eightfold.ai",
    "icims.com",
    "avature.net",
    "jobs.jobvite.com",
)
_SMARTRECRUITERS_TECH_TITLE = re.compile(
    r"\b(software|systems?|developer|programmer|data engineer|data science|data scientist|"
    r"machine learning|artificial intelligence|\bai\b|\bml\b|cloud|devops|site reliability|"
    r"sre|security|cyber|quality assurance|test engineer|embedded|firmware|compiler|platform|"
    r"backend|frontend|full[ -]?stack|android|ios|mobile|integration architect|"
    r"integration engineer|support engineer|technical support)\b",
    re.I,
)
_SMARTRECRUITERS_SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|manager|director|architect|head|vice president|vp)\b",
    re.I,
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
        desc = strip_html_text(job.get("content") or "")
        loc_field = job.get("location")
        primary_location = (
            clean_text(str(loc_field.get("name") or ""))
            if isinstance(loc_field, dict)
            else clean_text(str(loc_field or ""))
        )
        office_locations: list[str] = []
        office_names: list[str] = []
        for office in job.get("offices") or []:
            if not isinstance(office, dict):
                continue
            office_location = office.get("location")
            if isinstance(office_location, dict):
                office_location = office_location.get("name")
            normalized_location = clean_text(str(office_location or ""))
            normalized_name = clean_text(str(office.get("name") or ""))
            if normalized_location:
                office_locations.append(normalized_location)
            if normalized_name:
                office_names.append(normalized_name)
        location_parts = [primary_location, *office_locations]
        if not primary_location or re.fullmatch(
            r"(?:multiple|various) locations?", primary_location, re.I
        ):
            location_parts.extend(office_names)
        location = "; ".join(dict.fromkeys(value for value in location_parts if value))
        if location:
            desc = (desc + f"\nLocation: {location}").strip()
        results.append(text_lead({
            "title": job.get("title", ""),
            "company": slug,
            "url": job.get("absolute_url", ""),
            "platform": "greenhouse",
            "description": desc,
            "posted_date": "",
            "updated_at": updated,
            "location": location,
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
        categories = job.get("categories") or {}
        primary_location = clean_text(str(
            categories.get("location") or ""
        )) if isinstance(categories, dict) else ""
        all_locations = categories.get("allLocations") or [] if isinstance(categories, dict) else []
        if not isinstance(all_locations, list):
            all_locations = []
        location = "; ".join(dict.fromkeys(filter(None, [
            primary_location,
            *(clean_text(str(value)) for value in all_locations),
        ])))
        workplace = clean_text(str(job.get("workplaceType") or "")).lower()
        if workplace not in {"remote", "hybrid", "onsite", "on-site"}:
            workplace = ""
        if workplace == "on-site":
            workplace = "onsite"
        list_sections = job.get("lists") or []
        if not isinstance(list_sections, list):
            list_sections = []
        list_text = "\n".join(
            filter(None, (
                strip_html_text(str(section.get("content") or ""))
                for section in list_sections
                if isinstance(section, dict)
            ))
        )
        salary = job.get("salaryRange") if isinstance(job.get("salaryRange"), dict) else {}
        salary_min = salary.get("min")
        salary_max = salary.get("max")
        salary_currency = clean_text(str(salary.get("currency") or ""))
        salary_interval = clean_text(str(salary.get("interval") or ""))
        salary_interval_label = {
            "per-year-salary": "per year",
            "per-month-salary": "per month",
            "per-week-salary": "per week",
            "per-day-salary": "per day",
            "per-hour-salary": "per hour",
        }.get(salary_interval, salary_interval.replace("-", " "))
        salary_line = ""
        if salary_min is not None or salary_max is not None:
            bounds = " - ".join(str(value) for value in (salary_min, salary_max) if value is not None)
            salary_line = " ".join(filter(None, [
                "Salary:", salary_currency, bounds, salary_interval_label,
            ]))
        commitment = clean_text(str(categories.get("commitment") or "")) if isinstance(categories, dict) else ""
        parts = [
            job.get("descriptionBodyPlain") or job.get("descriptionPlain", ""),
            job.get("openingPlain", ""),
            list_text,
            job.get("additionalPlain", ""),
            job.get("salaryDescriptionPlain", ""),
            f"Employment type: {commitment}" if commitment else "",
            salary_line,
            f"Workplace: {workplace}" if workplace else "",
        ]
        source_meta = {
            "ats": "lever",
            "slug": slug,
            "job_id": clean_text(str(job.get("id") or "")),
            "country": clean_text(str(job.get("country") or "")),
            "location": location,
            "workplace_type": workplace,
            "commitment": commitment,
            "department": clean_text(str(categories.get("department") or "")) if isinstance(categories, dict) else "",
            "team": clean_text(str(categories.get("team") or "")) if isinstance(categories, dict) else "",
            "all_locations": [clean_text(str(value)) for value in all_locations if clean_text(str(value))],
            "apply_url": clean_text(str(job.get("applyUrl") or "")),
            "hosted_url": clean_text(str(job.get("hostedUrl") or "")),
            "salary_minimum": salary_min,
            "salary_maximum": salary_max,
            "salary_currency": salary_currency,
            "salary_interval": salary_interval,
        }
        source_meta = {
            key: value
            for key, value in source_meta.items()
            if value is not None and value != "" and value != []
        }
        results.append(text_lead({
            "title": job.get("text", ""),
            "company": slug,
            "url": job.get("hostedUrl", ""),
            "platform": "lever",
            "description": clean_text("\n".join(parts)),
            "posted_date": created,
            "location": location,
            "workplace": workplace,
            "source_meta": source_meta,
        }))
    return results


def _ashby_location(job: dict) -> str:
    locations: list[str] = []
    rows = [job, *(job.get("secondaryLocations") or [])]
    for row in rows:
        if not isinstance(row, dict):
            continue
        address = row.get("address") if isinstance(row.get("address"), dict) else {}
        postal = address.get("postalAddress") if isinstance(address.get("postalAddress"), dict) else {}
        parts = [
            clean_text(str(postal.get(key) or ""))
            for key in ("addressLocality", "addressRegion", "addressCountry")
        ]
        label = ", ".join(dict.fromkeys(value for value in parts if value))
        if not label:
            label = clean_text(str(row.get("locationName") or row.get("location") or ""))
        if label and label not in locations:
            locations.append(label)
    return "; ".join(locations)


async def scrape_ashby(slug: str) -> list[dict]:
    data = await json_get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    results = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if job.get("isListed") is False:
            continue
        title = clean_text(str(job.get("title") or ""))
        if not title:
            continue
        posted = job.get("publishedAt") or job.get("publishedDate") or ""
        updated = job.get("updatedAt") or ""
        desc = strip_html_text(job.get("descriptionHtml") or job.get("descriptionPlain") or "")
        location = _ashby_location(job)
        workplace_raw = clean_text(str(job.get("workplaceType") or ""))
        if bool(job.get("isRemote")) or workplace_raw.lower() == "remote":
            workplace = "remote"
        elif workplace_raw.lower() == "hybrid":
            workplace = "hybrid"
        elif workplace_raw.lower() in {"onsite", "on-site"}:
            workplace = "onsite"
        else:
            workplace = ""
        if location:
            desc = (desc + f"\nLocation: {location}").strip()
        if workplace:
            desc = (desc + f"\nWorkplace: {workplace}").strip()
        url = job.get("jobUrl") or job.get("applyUrl") or f"https://jobs.ashbyhq.com/{slug}/{job.get('id', '')}"
        apply_url = job.get("applyUrl") or url
        job_id = str(job.get("id") or "")
        results.append(text_lead({
            "title": title,
            "company": slug,
            "url": url,
            "apply_url": apply_url,
            "platform": "ashby",
            "description": desc,
            "posted_date": posted,
            "updated_at": updated,
            "location": location,
            "workplace": workplace,
            "active_hint": "active",
            "source_meta": {
                "ats": "ashby",
                "slug": slug,
                "id": job_id,
                "is_listed": job.get("isListed") is not False,
                "job_url": clean_text(str(url)),
                "apply_url": clean_text(str(apply_url)),
                "department": clean_text(str(job.get("department") or "")),
                "team": clean_text(str(job.get("team") or "")),
                "employment_type": clean_text(str(job.get("employmentType") or "")),
            },
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

    # Workable emits one row per location for the same requisition. Collapse
    # those rows before canonicalization so the source record retains every
    # advertised location instead of whichever city happened to appear first.
    grouped: dict[str, list[dict]] = {}
    for index, job in enumerate(jobs if isinstance(jobs, list) else []):
        if not isinstance(job, dict):
            continue
        code = str(job.get("shortcode") or job.get("code") or job.get("id") or "").strip()
        group_key = code or str(job.get("url") or job.get("application_url") or index)
        grouped.setdefault(group_key, []).append(job)

    company_name = str(data.get("name") or "").strip() if isinstance(data, dict) else ""
    results = []
    for variants in grouped.values():
        job = variants[0]
        posted = (
            job.get("published_on")
            or job.get("published")
            or job.get("created_at")
            or ""
        )
        updated = job.get("updated_at") or ""
        locations: list[str] = []
        for variant in variants:
            location_data = variant.get("location") or variant.get("locations") or {}
            location_rows = location_data if isinstance(location_data, list) else [location_data]
            variant_found = False
            for location_row in location_rows:
                if isinstance(location_row, dict):
                    parts: list[str] = []
                    for key in ("city", "region", "state", "country"):
                        value = str(location_row.get(key) or "").strip()
                        if value and value not in parts:
                            parts.append(value)
                    location = ", ".join(parts)
                else:
                    location = str(location_row or "").strip()
                if location:
                    variant_found = True
                    if location not in locations:
                        locations.append(location)
            if not variant_found:
                fallback = ", ".join(
                    str(variant.get(key) or "").strip()
                    for key in ("city", "state", "country")
                    if variant.get(key)
                )
                if fallback and fallback not in locations:
                    locations.append(fallback)
        location = "; ".join(locations)
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
            "company": company_name or slug,
            "url": url,
            "apply_url": job.get("application_url") or url,
            "platform": "workable",
            "description": desc,
            "posted_date": posted,
            "updated_at": updated,
            "location": location,
            "workplace": "remote" if any(bool(row.get("telecommuting")) for row in variants) else "",
            "source_meta": {"ats": "workable", "slug": slug, "id": str(code)},
        }))
    return results


def _smartrecruiters_label(job: dict, field: str) -> str:
    value = job.get(field)
    return clean_text(str(value.get("label") or "")) if isinstance(value, dict) else ""


async def scrape_smartrecruiters(
    slug: str,
    *,
    country_code: str = "",
    technical_only: bool = False,
    exclude_senior: bool = False,
) -> list[dict]:
    """Page a public SmartRecruiters board and enrich each public job ad.

    The collection endpoint caps responses at 100 rows. Detail requests add the
    job description, qualifications, experience level, employment type, precise
    workplace mode, apply URL, and provider identifiers. Candidate-form schemas
    are deliberately not requested or retained.
    """
    base = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    page_size = 100
    offset = 0
    postings_by_id: dict[str, dict] = {}
    while offset < 5_000:
        params = {"limit": str(page_size), "offset": str(offset)}
        if country_code:
            params["country"] = country_code.lower()
        data = await json_get(base, params)
        page = data.get("content", []) if isinstance(data, dict) else []
        rows = page if isinstance(page, list) else []
        for index, job in enumerate(rows):
            if not isinstance(job, dict):
                continue
            title = clean_text(str(job.get("name") or ""))
            location = job.get("location") if isinstance(job.get("location"), dict) else {}
            advertised_country = clean_text(str(location.get("country") or "")).lower()
            if country_code and advertised_country != country_code.lower():
                continue
            if technical_only and not _SMARTRECRUITERS_TECH_TITLE.search(title.replace("_", " ")):
                continue
            if exclude_senior and _SMARTRECRUITERS_SENIOR_TITLE.search(title.replace("_", " ")):
                continue
            job_id = str(job.get("id") or job.get("uuid") or "").strip()
            stable_key = job_id or f"offset:{offset + index}"
            postings_by_id.setdefault(stable_key, job)
        total = int(data.get("totalFound") or 0) if isinstance(data, dict) else 0
        offset += len(rows)
        if not rows or len(rows) < page_size or (total and offset >= total):
            break

    semaphore = asyncio.Semaphore(6)

    async def enrich(job: dict) -> dict:
        job_id = str(job.get("id") or "").strip()
        if not job_id:
            return job
        detail_url = str(job.get("ref") or f"{base}/{job_id}").strip()
        try:
            async with semaphore:
                detail = await json_get(detail_url)
        except Exception as log_exc:
            logging.getLogger(__name__).warning(
                "SmartRecruiters detail fallback for %s/%s: %s",
                slug,
                job_id,
                log_exc,
            )
            return job
        if not isinstance(detail, dict) or not detail.get("id"):
            return job
        return {**job, **detail}

    detailed = await asyncio.gather(*(enrich(job) for job in postings_by_id.values()))
    results = []
    for job in detailed:
        if not isinstance(job, dict):
            continue
        posted = job.get("releasedDate") or ""
        loc = job.get("location") or {}
        location = clean_text(str(loc.get("fullLocation") or "")) if isinstance(loc, dict) else ""
        if not location:
            location = ", ".join(
                str(loc.get(k, "")) for k in ("city", "region", "country")
                if isinstance(loc, dict) and loc.get(k)
            )
        workplace = ""
        if isinstance(loc, dict):
            if loc.get("remote"):
                workplace = "remote"
            elif loc.get("hybrid"):
                workplace = "hybrid"
            elif location:
                workplace = "onsite"
        company = (job.get("company") or {}).get("name") if isinstance(job.get("company"), dict) else ""
        job_id = str(job.get("id") or "")
        url = str(job.get("postingUrl") or "").strip()
        if not url:
            url = (
                f"https://jobs.smartrecruiters.com/{slug}/{job_id}"
                if job_id
                else f"https://jobs.smartrecruiters.com/{slug}"
            )
        job_ad = job.get("jobAd") if isinstance(job.get("jobAd"), dict) else {}
        sections = job_ad.get("sections") if isinstance(job_ad.get("sections"), dict) else {}
        description_parts: list[str] = []
        for section in sections.values():
            if not isinstance(section, dict):
                continue
            section_text = strip_html_text(str(section.get("text") or ""))
            section_title = clean_text(str(section.get("title") or ""))
            if section_text:
                description_parts.append(
                    f"{section_title}: {section_text}" if section_title else section_text
                )

        industry = _smartrecruiters_label(job, "industry")
        department = _smartrecruiters_label(job, "department")
        function = _smartrecruiters_label(job, "function")
        employment_type = _smartrecruiters_label(job, "typeOfEmployment")
        experience_level = _smartrecruiters_label(job, "experienceLevel")
        language = _smartrecruiters_label(job, "language")
        compensation = job.get("compensation") if isinstance(job.get("compensation"), dict) else {}
        compensation_min = compensation.get("min")
        compensation_max = compensation.get("max")
        compensation_text = ""
        if compensation_min or compensation_max:
            compensation_text = " ".join(str(value) for value in (
                compensation_min,
                compensation_max,
                compensation.get("currency"),
                compensation.get("period"),
            ) if value not in (None, ""))
        facts = [
            f"Industry: {industry}" if industry else "",
            f"Department: {department}" if department else "",
            f"Function: {function}" if function else "",
            f"Employment type: {employment_type}" if employment_type else "",
            f"Experience level: {experience_level}" if experience_level else "",
            f"Language: {language}" if language else "",
            f"Compensation: {compensation_text}" if compensation_text else "",
            f"Location: {location}" if location else "",
            f"Workplace: {workplace}" if workplace else "",
        ]
        desc = "\n".join(value for value in [*description_parts, *facts] if value).strip()
        if not desc:
            desc = clean_text(str(job.get("name") or ""))
        results.append(text_lead({
            "title": job.get("name", ""),
            "company": company or slug,
            "url": url,
            "apply_url": str(job.get("applyUrl") or url),
            "platform": "smartrecruiters",
            "description": desc,
            "posted_date": posted,
            "location": location,
            "workplace": workplace,
            "active_hint": "active" if job.get("active") is not False else "closed",
            "attribution": f"https://jobs.smartrecruiters.com/{slug}",
            "source_meta": {
                "ats": "smartrecruiters",
                "slug": slug,
                "id": job_id,
                "uuid": clean_text(str(job.get("uuid") or "")),
                "job_id": clean_text(str(job.get("jobId") or "")),
                "job_ad_id": clean_text(str(job.get("jobAdId") or "")),
                "reference_number": clean_text(str(job.get("refNumber") or "")),
                "active": job.get("active") is not False,
                "api_ref": clean_text(str(job.get("ref") or "")),
                "posting_url": clean_text(str(job.get("postingUrl") or url)),
                "apply_url": clean_text(str(job.get("applyUrl") or url)),
                "industry": industry,
                "department": department,
                "function": function,
                "employment_type": employment_type,
                "experience_level": experience_level,
                "language": language,
                "country_code": clean_text(str(loc.get("country") or ""))
                if isinstance(loc, dict)
                else "",
            },
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
            "description": desc,
            "posted_date": posted,
            "location": location,
            "source_meta": {"ats": "recruitee", "slug": slug},
        }))
    return results


async def scrape_personio(slug: str, tld: str = "") -> list[dict]:
    """Scrape a Personio tenant. With no explicit TLD (the watchlist / ats: form
    carries none), try .com then .de so a .de-only tenant isn't silently missed."""
    candidates = [tld.lstrip(".")] if tld else ["com", "de"]
    last_error: Exception | None = None
    successful_fetch = False
    for candidate in candidates:
        try:
            results = await _scrape_personio_at(slug, candidate)
            successful_fetch = True
        except Exception as exc:
            last_error = exc
            continue
        if results:
            return results
    if not successful_fetch and last_error is not None:
        raise last_error
    return []


async def _scrape_personio_at(slug: str, tld: str) -> list[dict]:
    from defusedxml import ElementTree as DefusedET

    tld = (tld or "com").lstrip(".")
    base = f"https://{slug}.jobs.personio.{tld}"
    xml = await xml_get(f"{base}/xml")
    try:
        root = DefusedET.fromstring(xml)
    except Exception as exc:
        raise ValueError(f"invalid Personio XML for {slug}.{tld}") from exc
    results = []
    for pos in root.iter("position"):
        def _text(tag: str, node=pos) -> str:
            el = node.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""

        posted = _text("createdAt")
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
            "description": clean_text("\n".join(desc_parts)),
            "posted_date": posted,
            "location": location,
            "source_meta": {"ats": "personio", "slug": slug},
        }))
    return results


_HIMALAYAS_SEGMENT_PARAMS = {
    "intern-india-eligible": {"country": "IN", "employment_type": "Intern"},
    "entry-level-full-time-india-eligible": {
        "country": "IN",
        "employment_type": "Full Time",
        "seniority": "Entry-level",
    },
}


def _epoch_iso(value: object) -> str:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat() if value else ""
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def _himalayas_location(restrictions: list[str]) -> str:
    if not restrictions:
        return "Worldwide"
    rendered = ", ".join(restrictions)
    if len(rendered) <= 1000:
        return rendered
    india_eligible = any(value.strip().lower() in {"in", "india"} for value in restrictions)
    eligibility = "India eligible; " if india_eligible else ""
    return f"Remote; {eligibility}{len(restrictions)} listed countries (full list retained in source metadata)"


def _himalayas_lead(job: dict) -> dict:
    restrictions = [str(value) for value in (job.get("locationRestrictions") or []) if value]
    # The rendered job page explicitly treats an absent restriction as worldwide.
    location = _himalayas_location(restrictions)
    timezones = [str(value) for value in (job.get("timezoneRestrictions") or [])]
    seniority = [str(value) for value in (job.get("seniority") or []) if value]
    categories = [str(value) for value in (job.get("categories") or []) if value]
    parent_categories = [str(value) for value in (job.get("parentCategories") or []) if value]
    employment_type = str(job.get("employmentType") or "").strip()
    currency = str(job.get("currency") or "").strip()
    salary_period = str(job.get("salaryPeriod") or "").strip()
    low, high = job.get("minSalary"), job.get("maxSalary")
    salary = ""
    if low is not None or high is not None:
        low_text, high_text = str(low or ""), str(high or "")
        amount = low_text if low_text == high_text or not high_text else (
            f"{low_text}-{high_text}" if low_text else high_text
        )
        salary = " ".join(value for value in (currency, amount, salary_period) if value)

    description_parts = [
        strip_html_text(job.get("description") or job.get("excerpt") or ""),
        f"Location: {location}",
        "Workplace: remote",
        f"Employment type: {employment_type}" if employment_type else "",
        f"Seniority: {', '.join(seniority)}" if seniority else "",
        f"Compensation: {salary}" if salary else "",
        f"Hiring timezones (UTC): {', '.join(timezones)}" if timezones else "",
        f"Categories: {', '.join(categories)}" if categories else "",
    ]
    url = str(job.get("applicationLink") or job.get("guid") or "").strip()
    return text_lead({
        "title": job.get("title", ""),
        "company": job.get("companyName", ""),
        "url": url,
        "apply_url": url,
        "attribution": url,
        "platform": "himalayas",
        "description": "\n".join(part for part in description_parts if part).strip(),
        "posted_date": _epoch_iso(job.get("pubDate")),
        "deadline": _epoch_iso(job.get("expiryDate")),
        "location": location,
        "workplace": "remote",
        "active_hint": current_listing_active_hint("himalayas"),
        "source_meta": {
            "ats": "himalayas",
            "id": str(job.get("guid") or "").strip(),
            "slug": str(job.get("companySlug") or "").strip(),
            "company_logo": str(job.get("companyLogo") or "").strip(),
            "employment_type": employment_type,
            "seniority": seniority,
            "location_restrictions": restrictions,
            "timezone_restrictions": timezones,
            "categories": categories,
            "parent_categories": parent_categories,
            "min_salary": low,
            "max_salary": high,
            "salary_period": salary_period,
            "currency": currency,
        },
    })


async def scrape_himalayas(
    segment: str = "all-india-eligible",
    *,
    max_pages: int = 500,
) -> list[dict]:
    """Page exhaustive India-eligible remote intern and entry-level searches."""
    segments = list(_HIMALAYAS_SEGMENT_PARAMS) if segment == "all-india-eligible" else [segment]
    by_url: dict[str, dict] = {}
    for segment_name in segments:
        base_params = _HIMALAYAS_SEGMENT_PARAMS.get(segment_name)
        if base_params is None:
            continue
        for page in range(1, max(1, max_pages) + 1):
            params = {
                **base_params,
                "exclude_worldwide": "false",
                "sort": "recent",
                "page": str(page),
            }
            data = await json_get("https://himalayas.app/jobs/api/search", params)
            jobs = data.get("jobs", []) if isinstance(data, dict) else []
            if not jobs:
                break
            for job in jobs:
                if isinstance(job, dict):
                    lead = _himalayas_lead(job)
                    if lead.get("url"):
                        by_url[str(lead["url"])] = lead
            limit = int(data.get("limit") or len(jobs) or 20)
            total = int(data.get("totalCount") or 0)
            if page * limit >= total:
                break
    return list(by_url.values())


async def scrape_teamtailor(slug: str) -> list[dict]:
    data = await json_get(f"https://{slug}.teamtailor.com/jobs.json")
    items = data.get("items", []) if isinstance(data, dict) else []
    results = []
    for job in items if isinstance(items, list) else []:
        if not isinstance(job, dict):
            continue
        posted = job.get("date_published") or ""
        posting = job.get("_jobposting") if isinstance(job.get("_jobposting"), dict) else {}
        org = posting.get("hiringOrganization") if isinstance(posting.get("hiringOrganization"), dict) else {}
        company = str(org.get("name") or "").strip() or slug
        locations = []
        for node in posting.get("jobLocation") or []:
            addr = node.get("address") if isinstance(node, dict) else None
            if isinstance(addr, dict):
                bits = [str(addr.get(k) or "") for k in ("addressLocality", "addressCountry")]
                locations.append(", ".join(b for b in bits if b))
        location = "; ".join(place for place in locations if place)
        # The JSON Feed's content_html already carries the FULL posting -- the
        # per-job detail page other ATSs need a second fetch for is redundant here.
        desc = strip_html_text(job.get("content_html") or "")
        if location:
            desc = (desc + f"\nLocation: {location}").strip()
        results.append(text_lead({
            "title": job.get("title", ""),
            "company": company,
            "url": job.get("url", ""),
            "platform": "teamtailor",
            "description": desc,
            "posted_date": posted,
            "location": location,
            "source_meta": {"ats": "teamtailor", "slug": slug},
        }))
    return results


async def scrape_rippling(slug: str, limit: int = 60) -> list[dict]:
    """Scrape a Rippling ATS board.

    The list call returns the WHOLE board with no server-side paging or
    filter, so ``limit`` is applied client-side purely to bound how many
    per-posting detail calls this makes -- one request per job, same tradeoff
    ``scrape_workday`` documents for its own detail fetch.

    No recency gate: the only timestamp Rippling exposes is ``createdOn``,
    which is set once and never bumped (verified: a job still open today
    carried a 2023 createdOn) -- filtering on it would silently drop almost
    every live posting. The board listing itself is already the live/open
    set, same reasoning as Pinpoint below, which has no date field at all.
    """
    jobs = await json_get(f"https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs")
    results = []
    for job in (jobs if isinstance(jobs, list) else [])[:max(1, limit)]:
        if not isinstance(job, dict):
            continue
        job_uuid = job.get("uuid") or ""
        if not job_uuid:
            continue
        try:
            detail = await json_get(
                f"https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs/{job_uuid}"
            )
        except Exception as log_exc:
            logging.getLogger(__name__).warning('suppressed exception in backend/discovery/sources/ats.py:scrape_rippling: %s', log_exc)
            detail = None
        detail = detail if isinstance(detail, dict) else {}
        posted = detail.get("createdOn") or ""
        desc_fields = detail.get("description") if isinstance(detail.get("description"), dict) else {}
        desc = strip_html_text("\n".join(str(desc_fields.get(k) or "") for k in ("role", "company")))
        locations = detail.get("workLocations") or []
        if not locations:
            work_loc = job.get("workLocation") or {}
            label = work_loc.get("label") if isinstance(work_loc, dict) else ""
            locations = [label] if label else []
        location = ", ".join(str(place) for place in locations if place)
        if location:
            desc = (desc + f"\nLocation: {location}").strip()
        company = detail.get("companyName") or slug
        results.append(text_lead({
            "title": job.get("name", ""),
            "company": company,
            "url": job.get("url", ""),
            "platform": "rippling",
            "description": desc,
            "posted_date": posted,
            "location": location,
            "source_meta": {"ats": "rippling", "slug": slug},
        }))
    return results


_LDJSON_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
_BREEZY_DESC_RE = re.compile(r'<div class="description">(.*?)<div class="apply-container"', re.S)
_OG_DESC_RE = re.compile(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](?P<content>[^"\']*)["\']', re.I)


def _ldjson_job_description(html: str) -> str:
    """schema.org JobPosting description, if the page embeds one server-side."""
    for match in _LDJSON_RE.finditer(html):
        try:
            payload = json.loads(match.group(1))
        except ValueError:
            continue
        for node in payload if isinstance(payload, list) else [payload]:
            if isinstance(node, dict) and node.get("@type") == "JobPosting" and node.get("description"):
                return strip_html_text(str(node["description"]))
    return ""


def _og_description(html: str) -> str:
    """Last-resort fallback for detail pages that render the real description
    client-side (React/Angular shell, nothing server-rendered): the
    og:description meta tag, which is real page content but capped short for
    social-share cards -- a summary, not the full posting."""
    match = _OG_DESC_RE.search(html)
    return strip_html_text(match.group("content")) if match else ""


async def _breezy_description(url: str) -> str:
    """Breezy's list endpoint carries no description; the per-job detail PAGE
    embeds it either as schema.org JobPosting JSON-LD (newer template), a
    plain ``.description`` HTML block (the older/default template, which
    carries no JSON-LD at all), or -- on a React/Angular shell that renders
    the body client-side -- only the truncated og:description summary.
    ``xml_get`` is reused purely as a generic "fetch + retry, return raw text"
    helper here; the page is HTML, not XML, but Breezy ignores the Accept
    header and serves the same markup either way.
    """
    try:
        html = await xml_get(url)
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/discovery/sources/ats.py:scrape_breezy: %s', log_exc)
        return ""
    if desc := _ldjson_job_description(html):
        return desc
    block = _BREEZY_DESC_RE.search(html)
    if block and strip_html_text(block.group(1)):
        return strip_html_text(block.group(1))
    return _og_description(html)


async def scrape_breezy(slug: str) -> list[dict]:
    positions = await json_get(f"https://{slug}.breezy.hr/json")
    results = []
    for job in positions if isinstance(positions, list) else []:
        if not isinstance(job, dict):
            continue
        posted = job.get("published_date") or ""
        loc = job.get("location") or {}
        location = str(loc.get("name") or "").strip() if isinstance(loc, dict) else str(loc or "")
        url = job.get("url", "")
        desc = await _breezy_description(url) if url else ""
        if location:
            desc = (desc + f"\nLocation: {location}").strip()
        company = job.get("company") if isinstance(job.get("company"), dict) else {}
        results.append(text_lead({
            "title": job.get("name", ""),
            "company": str(company.get("name") or "").strip() or slug,
            "url": url,
            "platform": "breezy",
            "description": desc,
            "posted_date": posted,
            "location": location,
            "source_meta": {"ats": "breezy", "slug": slug},
        }))
    return results


async def scrape_pinpoint(slug: str) -> list[dict]:
    data = await json_get(f"https://{slug}.pinpointhq.com/postings.json")
    postings = data.get("data", []) if isinstance(data, dict) else []
    results = []
    for job in postings if isinstance(postings, list) else []:
        if not isinstance(job, dict):
            continue
        # No date field anywhere on this payload -- nothing to gate on recency.
        loc = job.get("location") or {}
        location = str(loc.get("name") or "").strip() if isinstance(loc, dict) else str(loc or "")
        desc = strip_html_text("\n".join(str(job.get(k) or "") for k in (
            "description", "key_responsibilities", "skills_knowledge_expertise",
        )))
        if location:
            desc = (desc + f"\nLocation: {location}").strip()
        results.append(text_lead({
            "title": job.get("title", ""),
            "company": slug,
            "url": job.get("url", ""),
            "platform": "pinpoint",
            "description": desc,
            "posted_date": "",
            "location": location,
            "source_meta": {"ats": "pinpoint", "slug": slug},
        }))
    return results


_BAMBOO_JOB_RE = re.compile(
    r'<li id="bhrPositionID_(?P<id>\d+)"[^>]*>\s*<a[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    # Real markup line-wraps attributes ("<span\n\t\tclass=...>"), so tolerate
    # whitespace/other attributes between the tag name and `class=`.
    r'(?:\s*<span[^>]*class="BambooHR-ATS-Location"[^>]*>(?P<location>.*?)</span>)?',
    re.S,
)


async def scrape_bamboohr(slug: str) -> list[dict]:
    """Scrape a BambooHR careers board.

    ``embed2.php`` returns an HTML FRAGMENT (a `<ul>` of postings grouped by
    department), not JSON -- parsed with a targeted regex rather than a full
    HTML parser, matching how ``_scrape_personio_at`` hand-walks its XML.
    """
    base = f"https://{slug}.bamboohr.com"
    fragment = await xml_get(f"{base}/jobs/embed2.php")
    results = []
    for match in _BAMBOO_JOB_RE.finditer(fragment):
        job_id = match.group("id")
        title = strip_html_text(match.group("title") or "")
        location = strip_html_text(match.group("location") or "")
        href = (match.group("href") or "").strip()
        url = f"https:{href}" if href.startswith("//") else (href or f"{base}/careers/{job_id}")
        try:
            detail_html = await xml_get(f"{base}/careers/{job_id}")
        except Exception as log_exc:
            logging.getLogger(__name__).warning('suppressed exception in backend/discovery/sources/ats.py:scrape_bamboohr: %s', log_exc)
            detail_html = ""
        # Some tenants render the detail page as a JS shell with nothing but
        # the JobPosting JSON-LD (or not even that) server-side -- fall back to
        # the og:description summary, then the bare list title, rather than a
        # loud failure for a single missing description.
        desc = _ldjson_job_description(detail_html) or _og_description(detail_html) or title
        if location:
            desc = (desc + f"\nLocation: {location}").strip()
        results.append(text_lead({
            "title": title,
            "company": slug,
            "url": url,
            "platform": "bamboohr",
            "description": desc,
            "posted_date": "",
            "location": location,
            "source_meta": {"ats": "bamboohr", "slug": slug},
        }))
    return results


class _ZohoRecruitPageParser(HTMLParser):
    """Extract the public job payload embedded in a Zoho Recruit career page.

    Zoho renders an ordinary public career board, but serializes the complete
    current-job collection into an HTML-escaped hidden input instead of a public
    JSON endpoint.  ``HTMLParser`` decodes entities in attribute values for us,
    avoiding both a brittle mega-regex and any protected/OAuth API.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self._in_title = False
        self._title_parts: list[str] = []

    @property
    def page_title(self) -> str:
        return clean_text(" ".join(self._title_parts))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self._in_title = True
            return
        if tag.lower() != "input":
            return
        values = {str(key).lower(): value for key, value in attrs}
        raw = values.get("value") or ""
        if not raw.lstrip().startswith("["):
            return
        try:
            candidate = json.loads(raw)
        except (TypeError, ValueError):
            return
        if not isinstance(candidate, list):
            return
        jobs = [row for row in candidate if isinstance(row, dict) and (
            row.get("Posting_Title") or row.get("Job_Opening_Name")
        )]
        if jobs:
            self.rows.extend(jobs)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and data.strip():
            self._title_parts.append(data.strip())


def _zoho_recruit_company(page_title: str, slug: str) -> str:
    """Recover the employer label without accepting a recruiter/contact field."""
    title = clean_text(html_lib.unescape(page_title or ""))
    for pattern in (
        r"^(?:careers?|jobs?|opportunities)\s*(?:at|@|[-|:])\s*",
        r"\s*(?:[-|:]\s*)?careers?$",
        r"\s*(?:[-|:]\s*)?jobs?$",
    ):
        title = re.sub(pattern, "", title, flags=re.I).strip(" -|:")
    if title and title.lower() not in {"career", "careers", "job", "jobs", "zoho recruit"}:
        return title
    return re.sub(r"[-_]", " ", slug).strip() or slug


def _zoho_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


_ZOHO_DETAIL_TECH_TITLE = re.compile(
    r"\b(software|systems?|developer|engineer|qa|quality assurance|test(?:ing)?|"
    r"artificial intelligence|ai|machine learning|ml|data|devops|cloud|cyber|security|"
    r"full[ -]?stack|front[ -]?end|back[ -]?end|flutter|android|ios|mobile|robotics|"
    r"programmer|technical)\b",
    re.I,
)
_ZOHO_DETAIL_EXCLUDE_TITLE = re.compile(
    r"\b(senior|sr\.?|lead|manager|director|architect|trainer|teacher|faculty|sales|marketing)\b",
    re.I,
)
_ZOHO_JOBS_LITERAL = re.compile(
    r"var\s+jobs\s*=\s*JSON\.parse\('((?:\\.|[^'\\])*)'\)",
    re.S,
)
_ZOHO_JS_ESCAPE = re.compile(r"\\(x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|.)", re.S)
_ZOHO_APPLY_CONTROL = re.compile(
    r"mailto:|\bapply now\b|\bapply for this job\b|\bsubmit application\b",
    re.I,
)
_ZOHO_UNAVAILABLE = re.compile(
    r"\b(job|position|role)\s+(?:is\s+)?no longer available\b|"
    r"\bposition has been filled\b|\bno longer accepting applications\b|"
    r"\bpage not found\b",
    re.I,
)
_ZOHO_DETAIL_VERIFY_LIMIT = 60


def _decode_zoho_js_string(value: str) -> str:
    """Decode the JavaScript string literal passed to ``JSON.parse`` safely."""
    escapes = {
        "\\": "\\", '"': '"', "'": "'", "/": "/",
        "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
    }

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token.startswith("x"):
            return chr(int(token[1:], 16))
        if token.startswith("u"):
            return chr(int(token[1:], 16))
        return escapes.get(token, f"\\{token}")

    return _ZOHO_JS_ESCAPE.sub(replace, value)


def _zoho_detail_job(page: str, job_id: str) -> dict:
    match = _ZOHO_JOBS_LITERAL.search(page)
    if not match or len(match.group(1)) > 500_000:
        return {}
    try:
        rows = json.loads(_decode_zoho_js_string(match.group(1)))
    except (TypeError, ValueError):
        return {}
    if not isinstance(rows, list):
        return {}
    return next(
        (
            row for row in rows
            if isinstance(row, dict) and str(row.get("id") or "").strip() == job_id
        ),
        {},
    )


def _zoho_detail_page_is_live(page: str, title: str) -> bool:
    """Require the public detail handoff to expose this exact applicable role."""
    visible = html_lib.unescape(page)
    normalized_page = re.sub(r"\s+", " ", visible).casefold()
    normalized_title = re.sub(
        r"\s+",
        " ",
        html_lib.unescape(title),
    ).strip().casefold()
    return bool(
        normalized_title
        and normalized_title in normalized_page
        and _ZOHO_APPLY_CONTROL.search(visible)
        and not _ZOHO_UNAVAILABLE.search(visible)
    )


async def scrape_zoho_recruit(slug: str, tld: str = "com") -> list[dict]:
    """Read a tenant's public Zoho Recruit career board without OAuth."""
    slug = slug.strip().lower()
    tld = tld.strip().lower().lstrip(".") or "com"
    if not slug or tld not in {"com", "in"}:
        return []
    host = f"{slug}.zohorecruit.{tld}"
    board_url = f"https://{host}/jobs/Careers"
    page = await text_get(board_url)
    parser = _ZohoRecruitPageParser()
    parser.feed(page)
    company = _zoho_recruit_company(parser.page_title, slug)

    # A Zoho collection can retain published-looking rows after their detail
    # handoff has become a generic career page. Verify every current row for
    # normal-sized boards. On unusually large marketplace boards, keep the
    # request budget bounded and prioritize the technical/early-career rows this
    # product can actually surface. No application form schema or candidate data
    # is requested or persisted.
    published_rows = [
        row
        for row in parser.rows
        if str(row.get("id") or "").strip()
        and ("Publish" not in row or _zoho_truthy(row.get("Publish")))
    ]
    if len(published_rows) <= _ZOHO_DETAIL_VERIFY_LIMIT:
        detail_candidates = published_rows
    else:
        detail_candidates = [
            row
            for row in published_rows
            if (
                _ZOHO_DETAIL_TECH_TITLE.search(str(
                    row.get("Posting_Title") or row.get("Job_Opening_Name") or ""
                ))
                or re.search(
                    r"\b(intern(?:ship)?|graduate|trainee|apprentice|new[ -]?grad)\b",
                    str(row.get("Job_Type") or ""),
                    re.I,
                )
            )
            and not _ZOHO_DETAIL_EXCLUDE_TITLE.search(str(
                row.get("Posting_Title") or row.get("Job_Opening_Name") or ""
            ))
        ][:_ZOHO_DETAIL_VERIFY_LIMIT]
    detail_semaphore = asyncio.Semaphore(6)

    async def enrich(row: dict) -> tuple[str, dict, bool | None]:
        job_id = str(row.get("id") or "").strip()
        title = clean_text(str(row.get("Posting_Title") or row.get("Job_Opening_Name") or ""))
        try:
            async with detail_semaphore:
                detail_page = await text_get(f"{board_url}/{job_id}")
        except Exception as exc:
            logging.getLogger(__name__).info(
                "Zoho Recruit detail fallback for %s/%s: %s", slug, job_id, exc
            )
            return job_id, {}, None
        detail_live = _zoho_detail_page_is_live(detail_page, title)
        if not detail_live:
            return job_id, {}, False
        detail = _zoho_detail_job(detail_page, job_id)
        if not detail:
            summary = _og_description(detail_page)
            detail = {"Job_Description": summary} if summary else {}
        return job_id, detail, True

    detail_results = await asyncio.gather(*(enrich(row) for row in detail_candidates))
    details = {job_id: detail for job_id, detail, _ in detail_results}
    detail_liveness = {job_id: live for job_id, _, live in detail_results}

    results: list[dict] = []
    seen: set[str] = set()
    for row in parser.rows:
        # Publish=false is an explicit closed/private signal. Missing Publish is
        # accepted because some public-board schemas omit it entirely.
        if "Publish" in row and not _zoho_truthy(row.get("Publish")):
            continue
        job_id = clean_text(str(row.get("id") or row.get("Job_Opening_ID") or ""))
        if detail_liveness.get(job_id) is False:
            continue
        if details.get(job_id):
            row = {**row, **details[job_id]}
        title = clean_text(str(row.get("Posting_Title") or row.get("Job_Opening_Name") or ""))
        if not job_id or not title or job_id in seen:
            continue
        seen.add(job_id)
        location_parts = [
            clean_text(str(row.get(key) or ""))
            for key in ("City", "State", "Country")
        ]
        location = ", ".join(dict.fromkeys(value for value in location_parts if value))
        remote = _zoho_truthy(row.get("Remote_Job"))
        job_type = clean_text(str(row.get("Job_Type") or ""))
        salary = clean_text(str(row.get("Salary") or ""))
        work_experience = clean_text(str(row.get("Work_Experience") or ""))
        workplace = "remote" if remote else ("onsite" if location else "")
        description = "\n".join(filter(None, [
            strip_html_text(str(row.get("Job_Description") or "")) or title,
            f"Employment type: {job_type}" if job_type else "",
            f"Experience: {work_experience}" if work_experience else "",
            f"Salary: {salary}" if salary else "",
            f"Workplace: {workplace}" if workplace else "",
        ]))
        source_meta = {
            "ats": "zohorecruit",
            "slug": slug,
            "tld": tld,
            "job_id": job_id,
            "job_type": job_type,
            "industry": clean_text(str(row.get("Industry") or "")),
            "department": clean_text(str(row.get("Department") or "")),
            "city": location_parts[0],
            "state": location_parts[1],
            "country": location_parts[2],
            "remote_job": remote,
            "workplace_type": workplace,
            "date_opened": clean_text(str(row.get("Date_Opened") or "")),
            "salary": salary,
            "work_experience": work_experience,
            "postal_code": clean_text(str(row.get("Zip_Code") or row.get("Zip/Postal_Code") or "")),
            "publish": _zoho_truthy(row.get("Publish")) if "Publish" in row else None,
            "is_locked": _zoho_truthy(row.get("Is_Locked")) if "Is_Locked" in row else None,
            "keep_on_career_site": (
                _zoho_truthy(row.get("Keep_on_Career_Site"))
                if "Keep_on_Career_Site" in row else None
            ),
            "board_url": board_url,
            "public_detail_verified": detail_liveness.get(job_id),
        }
        source_meta = {key: value for key, value in source_meta.items() if value not in {"", None}}
        results.append(text_lead({
            "title": title,
            "company": company,
            "url": f"{board_url}/{job_id}",
            "platform": "zohorecruit",
            "description": description,
            "posted_date": source_meta.get("date_opened", ""),
            "location": location or ("Remote" if remote else ""),
            "workplace": workplace,
            "active_hint": "active",
            "source_meta": source_meta,
        }))
    return results


class _FreshteamBoardParser(HTMLParser):
    """Parse current public job cards from a Freshteam career board.

    Freshteam renders the open-job collection server-side.  The ``/jobs/{id}``
    link and ``data-portal-*`` attributes are the stable public contract used by
    its own filters, so we avoid scraping presentation-only whitespace.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self._row: dict | None = None
        self._field_stack: list[str] = []
        self._legacy_rows: dict[str, dict] = {}
        self._legacy_anchor = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "a":
            href = values.get("href", "")
            match = re.match(r"^/jobs/([^/?#]+)(?:/[^?#]*)?", href)
            classes = set(values.get("class", "").split())
            if match and "heading" in classes:
                self._row = {
                    "job_id": match.group(1),
                    "href": href,
                    "portal_title": values.get("data-portal-title", ""),
                    "location": values.get("data-portal-location", ""),
                    "job_type_id": values.get("data-portal-job-type", ""),
                    "remote": values.get("data-portal-remote-location", "").lower() == "true",
                    "title_parts": [],
                    "summary_parts": [],
                    "location_info_parts": [],
                }
                self._field_stack = []
                self._legacy_anchor = False
                return
            # Older/custom Freshteam themes render the title, summary and
            # location as separate anchors pointing to the same stable job ID.
            # Merge those anchors instead of emitting four duplicate records.
            legacy_field = next((
                (class_name, field_name)
                for class_name, field_name in (
                    ("job-title", "title_parts"),
                    ("job-desc", "summary_parts"),
                    ("location-info", "location_info_parts"),
                )
                if class_name in classes
            ), None)
            if match and legacy_field:
                job_id = match.group(1)
                row = self._legacy_rows.get(job_id)
                if row is None:
                    row = {
                        "job_id": job_id,
                        "href": href,
                        "portal_title": "",
                        "location": "",
                        "job_type_id": "",
                        "remote": False,
                        "title_parts": [],
                        "summary_parts": [],
                        "location_info_parts": [],
                    }
                    self._legacy_rows[job_id] = row
                    self.rows.append(row)
                self._row = row
                self._field_stack = [legacy_field[1]]
                self._legacy_anchor = True
                return
        if self._row is not None and tag.lower() == "div":
            classes = set(values.get("class", "").split())
            field = ""
            if "job-title" in classes:
                field = "title_parts"
            elif "job-desc" in classes:
                field = "summary_parts"
            elif "location-info" in classes:
                field = "location_info_parts"
            self._field_stack.append(field)

    def handle_data(self, data: str) -> None:
        if self._row is None or not self._field_stack:
            return
        field = next((value for value in reversed(self._field_stack) if value), "")
        value = clean_text(data)
        if field and value:
            self._row[field].append(value)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if (
            self._row is not None and not self._legacy_anchor
            and tag == "div" and self._field_stack
        ):
            self._field_stack.pop()
        if self._row is not None and tag == "a":
            if not self._legacy_anchor:
                self.rows.append(self._row)
            self._row = None
            self._field_stack = []
            self._legacy_anchor = False


class _FreshteamJsonLdParser(HTMLParser):
    def __init__(self) -> None:
        # Character references inside script elements are text belonging to the
        # JSON string. Leave them encoded until after json.loads; unescaping first
        # can introduce unquoted double quotes into a description.
        super().__init__(convert_charrefs=False)
        self.documents: list[str] = []
        self._capturing = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        values = {key.lower(): (value or "") for key, value in attrs}
        if values.get("type", "").strip().lower() == "application/ld+json":
            self._capturing = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._capturing:
            self.documents.append("".join(self._parts).strip())
            self._capturing = False
            self._parts = []


def _freshteam_job_posting(page: str) -> dict:
    parser = _FreshteamJsonLdParser()
    parser.feed(page)

    def find(value: object) -> dict:
        if isinstance(value, dict):
            kind = value.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if any(str(item or "").lower() == "jobposting" for item in kinds):
                return value
            graph = value.get("@graph")
            if isinstance(graph, list):
                for child in graph:
                    result = find(child)
                    if result:
                        return result
        elif isinstance(value, list):
            for child in value:
                result = find(child)
                if result:
                    return result
        return {}

    for document in parser.documents:
        try:
            result = find(json.loads(document))
        except (TypeError, ValueError):
            continue
        if result:
            return result
    return {}


def _freshteam_address(value: object) -> tuple[str, dict[str, str]]:
    locations = value if isinstance(value, list) else [value]
    labels: list[str] = []
    fields: dict[str, str] = {}
    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address")
        if not isinstance(address, dict):
            address = {}
        current = {
            "street_address": clean_text(str(address.get("streetAddress") or "")),
            "address_locality": clean_text(str(address.get("addressLocality") or "")),
            "address_region": clean_text(str(address.get("addressRegion") or "")),
            "postal_code": clean_text(str(address.get("postalCode") or "")),
            "address_country": clean_text(str(address.get("addressCountry") or "")),
        }
        fields.update({key: item for key, item in current.items() if item and key not in fields})
        label = ", ".join(dict.fromkeys(
            item for item in (
                current["street_address"], current["address_locality"],
                current["address_region"], current["address_country"],
            ) if item
        ))
        if label and label not in labels:
            labels.append(label)
    return "; ".join(labels), fields


def _freshteam_timestamp(value: object) -> str:
    raw = clean_text(str(value or ""))
    if not raw:
        return ""
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S UTC").replace(
            tzinfo=timezone.utc
        ).isoformat()
    except ValueError:
        return raw


_FRESHTEAM_PUBLIC_JSONLD_FIELDS = {
    "applicantLocationRequirements": "applicant_location_requirements",
    "baseSalary": "base_salary",
    "directApply": "direct_apply",
    "educationRequirements": "education_requirements",
    "experienceRequirements": "experience_requirements",
    "incentiveCompensation": "incentive_compensation",
    "industry": "industry",
    "jobLocationType": "job_location_type",
    "occupationalCategory": "occupational_category",
    "qualifications": "qualifications",
    "skills": "skills",
}


def _freshteam_public_jsonld(detail: dict) -> dict:
    """Keep selected schema.org job facts, excluding form/applicant content."""
    result = {
        target: detail[source]
        for source, target in _FRESHTEAM_PUBLIC_JSONLD_FIELDS.items()
        if source in detail and detail[source] is not None and detail[source] != ""
    }
    jsonld_url = clean_text(str(detail.get("url") or ""))
    if jsonld_url:
        result["jsonld_url"] = jsonld_url
    organization = detail.get("hiringOrganization")
    if isinstance(organization, dict):
        employer_url = clean_text(str(organization.get("sameAs") or organization.get("url") or ""))
        if employer_url:
            result["employer_url"] = employer_url
    return result


async def scrape_freshteam(slug: str) -> list[dict]:
    """Read a tenant's public, current Freshteam career board and JSON-LD.

    Only public employer pages are requested.  The applicant form, candidate
    fields, CSRF token and submission endpoints are deliberately never read or
    used. Presence on the board is authoritative active evidence at scan time.
    """
    slug = slug.strip().lower()
    if not slug or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        return []
    board_url = f"https://{slug}.freshteam.com/jobs"
    board_page = await text_get(board_url)
    parser = _FreshteamBoardParser()
    parser.feed(board_page)

    # A board may contain hundreds of roles, but every detail page is a small
    # first-party request and carries substantially more evidence than the card.
    # Keep concurrency polite and cap pathological tenants without discarding
    # ordinary boards. Cards beyond the cap still retain their current-board data.
    detail_semaphore = asyncio.Semaphore(6)

    async def load_detail(row: dict) -> tuple[str, dict]:
        job_id = str(row.get("job_id") or "")
        try:
            async with detail_semaphore:
                page = await text_get(f"https://{slug}.freshteam.com{row['href']}")
        except Exception as exc:
            logging.getLogger(__name__).info(
                "Freshteam detail fallback for %s/%s: %s", slug, job_id, exc
            )
            return job_id, {}
        return job_id, _freshteam_job_posting(page)

    detail_rows = parser.rows[:500]
    details = dict(await asyncio.gather(*(load_detail(row) for row in detail_rows)))
    results: list[dict] = []
    seen: set[str] = set()
    for row in parser.rows:
        job_id = clean_text(str(row.get("job_id") or ""))
        if not job_id or job_id in seen:
            continue
        seen.add(job_id)
        detail = details.get(job_id) or {}
        title = clean_text(str(detail.get("title") or " ".join(row["title_parts"])))
        if not title:
            continue
        organization = detail.get("hiringOrganization")
        company = (
            clean_text(str(organization.get("name") or ""))
            if isinstance(organization, dict) else ""
        ) or re.sub(r"[-_]", " ", slug).strip()
        structured_location, address_fields = _freshteam_address(detail.get("jobLocation"))
        card_location_parts = [
            clean_text(str(item)) for item in row.get("location_info_parts") or [] if item
        ]
        card_work_type = card_location_parts[-1] if len(card_location_parts) > 1 else ""
        card_location = card_location_parts[0] if len(card_location_parts) > 1 else ""
        board_location = clean_text(str(row.get("location") or "")) or card_location
        remote = (
            row.get("remote") is True
            or str(detail.get("remote") or "").lower() == "true"
            or board_location.lower() == "remote"
        )
        location = board_location or structured_location or ("Remote" if remote else "")
        employment_type = detail.get("employmentType")
        if isinstance(employment_type, list):
            employment_type = ", ".join(clean_text(str(item)) for item in employment_type if item)
        employment_type = clean_text(str(employment_type or ""))
        card_work_type = card_work_type or clean_text(" ".join(row.get("location_info_parts") or []))
        # Freshteam entity-encodes the HTML fragment for JSON-LD and then the
        # fragment itself may contain ordinary HTML entities. Decode the outer
        # layer only after JSON parsing; strip_html_text handles the inner layer.
        description = strip_html_text(html_lib.unescape(str(detail.get("description") or "")))
        if not description:
            description = clean_text(" ".join(row.get("summary_parts") or [])) or title
        date_posted_raw = clean_text(str(detail.get("datePosted") or ""))
        source_meta = {
            "ats": "freshteam",
            "slug": slug,
            "job_id": job_id,
            "job_type_id": clean_text(str(row.get("job_type_id") or "")),
            "employment_type": employment_type or card_work_type,
            "remote_job": remote,
            "workplace_type": "remote" if remote else "onsite",
            "board_location": board_location,
            "structured_location": structured_location,
            "date_posted": _freshteam_timestamp(date_posted_raw),
            "date_posted_raw": date_posted_raw,
            "valid_through": clean_text(str(detail.get("validThrough") or "")),
            "board_url": board_url,
            **address_fields,
            **_freshteam_public_jsonld(detail),
        }
        source_meta = {
            key: value for key, value in source_meta.items()
            if value is not None and value != ""
        }
        results.append(text_lead({
            "title": title,
            "company": company,
            "url": f"https://{slug}.freshteam.com{row['href']}",
            "platform": "freshteam",
            "description": description,
            "posted_date": source_meta.get("date_posted", ""),
            "deadline": _freshteam_timestamp(source_meta.get("valid_through", "")),
            "location": location,
            "workplace": "remote" if remote else "onsite",
            "active_hint": "active",
            "source_meta": source_meta,
        }))
    return results


_KEKA_TENANT_IDENTIFIER = re.compile(
    r"/ats/documents/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/careerportal/",
    re.I,
)
_KEKA_JOB_TYPES = {1: "Part Time", 2: "Full Time"}
_KEKA_REMOTE_LOCATION = re.compile(r"\b(remote|work from home|wfh|virtual)\b", re.I)
_KEKA_DESCRIPTION_LOCATION = re.compile(
    r"\blocation\s*:\s*(.{2,120}?)(?=\s+(?:type|job type|employment type|"
    r"experience|department|function|duration|about|role)\s*:|[.;\n]|$)",
    re.I,
)


def _keka_location_facts(value: object) -> tuple[str, list[dict], str]:
    """Render Keka's public structured locations without inventing a work mode."""
    if not isinstance(value, list):
        return "", [], ""
    locations: list[dict] = []
    labels: list[str] = []
    remote_count = 0
    for raw in value:
        if not isinstance(raw, dict):
            continue
        location = {
            key: item
            for key, item in {
                "id": raw.get("id"),
                "name": clean_text(str(raw.get("name") or "")),
                "city": clean_text(str(raw.get("city") or "")),
                "state": clean_text(str(raw.get("state") or "")),
                "country_code": clean_text(str(raw.get("countryCode") or "")),
                "country": clean_text(str(raw.get("countryName") or "")),
            }.items()
            if item is not None and item != ""
        }
        if not location:
            continue
        locations.append(location)
        searchable = " ".join(str(item) for item in location.values())
        is_remote = bool(_KEKA_REMOTE_LOCATION.search(searchable))
        remote_count += int(is_remote)
        if is_remote:
            label = "Remote"
            geography = ", ".join(dict.fromkeys(
                str(location.get(key) or "")
                for key in ("state", "country")
                if location.get(key)
            ))
            if geography:
                label = f"{label}, {geography}"
        else:
            label = ", ".join(dict.fromkeys(
                str(location.get(key) or "")
                for key in ("city", "state", "country")
                if location.get(key)
            )) or clean_text(str(location.get("name") or ""))
        if label and label not in labels:
            labels.append(label)
    workplace = ""
    if locations:
        if remote_count == len(locations):
            workplace = "remote"
        elif remote_count:
            workplace = "remote or onsite"
        else:
            workplace = "onsite"
    return "; ".join(labels), locations, workplace


async def scrape_keka(slug: str) -> list[dict]:
    """Read a tenant's public Keka current-job collection.

    The tenant identifier is discovered from the public career shell rather
    than hard-coded. Only the public active-job and organization-info endpoints
    are requested; application forms, questions and candidate endpoints are
    deliberately outside this adapter.
    """
    slug = slug.strip().lower()
    if not slug or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        return []
    board_url = f"https://{slug}.keka.com/careers"
    shell = await text_get(board_url)
    identifier_match = _KEKA_TENANT_IDENTIFIER.search(shell)
    tenant_identifier = identifier_match.group(1).lower() if identifier_match else ""
    if tenant_identifier:
        jobs_api_url = (
            f"{board_url}/api/embedjobs/default/active/{tenant_identifier}"
        )
        portal_generation = "embedded"
    else:
        # Keka's current 2026 portal renders the employer shell server-side and
        # resolves the tenant from the host, so no public UUID appears in HTML.
        jobs_api_url = f"{board_url}/api/jobs/default/active"
        portal_generation = "native_2026"
    organization_api_url = f"{board_url}/api/organization/default/careerportalinfo"
    gathered_results = await asyncio.gather(
        json_get(jobs_api_url),
        json_get(organization_api_url),
        return_exceptions=True,
    )
    jobs_result: object = gathered_results[0]
    organization_result: object = gathered_results[1]
    if isinstance(jobs_result, BaseException):
        raise jobs_result
    jobs = jobs_result if isinstance(jobs_result, list) else []
    organization = organization_result if isinstance(organization_result, dict) else {}
    company = clean_text(str(
        organization.get("name") or organization.get("shortName") or ""
    )) or re.sub(r"[-_]", " ", slug).strip()
    employer_url = clean_text(str(organization.get("companyWebsite") or ""))
    employer_domain = ""
    if employer_url:
        employer_domain = (urlparse(
            employer_url if "://" in employer_url else f"https://{employer_url}"
        ).hostname or "").lower()
        if employer_domain.startswith("www."):
            employer_domain = employer_domain[4:]

    results: list[dict] = []
    seen: set[str] = set()
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = clean_text(str(job.get("id") or ""))
        title = clean_text(str(job.get("title") or ""))
        if not job_id or not title or job_id in seen:
            continue
        seen.add(job_id)
        location, structured_locations, workplace = _keka_location_facts(
            job.get("jobLocations")
        )
        description = strip_html_text(job.get("description") or job.get("excerpt") or "")
        description_location = ""
        if not location and (location_match := _KEKA_DESCRIPTION_LOCATION.search(description)):
            description_location = clean_text(location_match.group(1)).rstrip(" ,;:-")
            location = description_location
            if location:
                workplace = "remote" if _KEKA_REMOTE_LOCATION.search(location) else "onsite"
        experience = clean_text(str(job.get("experience") or ""))
        try:
            job_type_id = int(job.get("jobType"))
        except (TypeError, ValueError):
            job_type_id = 0
        employment_type = _KEKA_JOB_TYPES.get(job_type_id, "")
        published_on = clean_text(str(job.get("publishedOn") or ""))
        skills = [
            clean_text(str(item))
            for item in (job.get("skillNames") or [])
            if clean_text(str(item))
        ] if isinstance(job.get("skillNames"), list) else []
        salary = job.get("salaryRange") if isinstance(job.get("salaryRange"), dict) else {}
        salary_format = clean_text(str(job.get("salaryRangeFormat") or ""))
        description_parts = [
            description or title,
            f"Location: {location}" if location else "",
            f"Workplace: {workplace}" if workplace else "",
            f"Employment type: {employment_type}" if employment_type else "",
            f"Experience: {experience}" if experience else "",
            f"Salary: {salary_format}" if salary_format else "",
            f"Skills: {', '.join(skills)}" if skills else "",
        ]
        source_meta = {
            "ats": "keka",
            "slug": slug,
            "tenant_identifier": tenant_identifier,
            "portal_generation": portal_generation,
            "job_id": job_id,
            "department_identifier": clean_text(str(job.get("departmentIdentifier") or "")),
            "department_name": clean_text(str(job.get("departmentName") or "")),
            "job_type_id": job_type_id or None,
            "employment_type": employment_type,
            "experience": experience,
            "remote_job": "remote" in workplace,
            "workplace_type": workplace,
            "date_posted": published_on,
            "published_since_days": job.get("publishedSinceDays"),
            "job_locations": structured_locations,
            "description_location": description_location,
            "salary_minimum": salary.get("minimum"),
            "salary_maximum": salary.get("maximum"),
            "salary_currency": clean_text(str(salary.get("currency") or "")),
            "salary_period_id": salary.get("salaryPeriod"),
            "salary_culture": clean_text(str(salary.get("cultureInfo") or "")),
            "salary_range_format": salary_format,
            "skills": skills,
            "board_url": board_url,
            "jobs_api_url": jobs_api_url,
            "employer_url": employer_url,
            "employer_domain": employer_domain,
        }
        source_meta = {
            key: value for key, value in source_meta.items()
            if value is not None and value != "" and value != []
        }
        url = f"{board_url}/jobdetails/{job_id}"
        results.append(text_lead({
            "title": title,
            "company": company,
            "url": url,
            "apply_url": url,
            "attribution": url,
            "platform": "keka",
            "description": "\n".join(
                part for part in description_parts if part
            ).strip(),
            "posted_date": published_on,
            "location": location,
            "workplace": workplace,
            "active_hint": "active",
            "source_meta": source_meta,
        }))
    return results


_ORACLEHCM_HOST = re.compile(
    r"^[a-z0-9-]+\.fa\.[a-z0-9-]+\.oraclecloud\.com$",
    re.I,
)
_ORACLEHCM_SITE = re.compile(r"^CX_\d+$", re.I)
_ORACLEHCM_EARLY_SEARCHES = (
    "intern", "graduate", "trainee", "apprentice",
)
_ORACLEHCM_TECH_SEARCHES = (
    "software", "data", "machine learning", "artificial intelligence",
    "cyber", "cloud", "devops", "quality assurance",
)
_ORACLEHCM_TECHNICAL = re.compile(
    r"\b(software|developer|programmer|computer science|information technology|"
    r"information and communications technology|\bICT\b|data (?:engineer|science|scientist|"
    r"analyst|analytics)|analytics?|machine learning|artificial intelligence|\bAI\b|\bML\b|"
    r"cloud|devops|site reliability|\bSRE\b|security|cyber|identity and access|\bIAM\b|"
    r"quality assurance|quality engineer|\bQA\b|test (?:automation|development|engineer)|"
    r"automation engineer|"
    r"embedded|firmware|compiler|systems? engineer|platform engineer|backend|frontend|"
    r"full[ -]?stack|android|\biOS\b|mobile developer|database|\bSQL\b|\bSAP\b|"
    r"oracle (?:cloud|database|applications?)|\bERP\b|digital engineering|technology systems?)\b",
    re.I,
)
_ORACLEHCM_EARLY_TITLE = re.compile(
    r"\b(interns?(?:hip)?|apprentice(?:ship)?|graduate|trainee|fresher|campus|"
    r"entry[ -]?level|junior|engineer\s+(?:i|1)|sde\s*(?:i|1))\b",
    re.I,
)
_ORACLEHCM_SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead(?:er)?|manager|director|architect|head|"
    r"vice president|vp)\b",
    re.I,
)
_ORACLEHCM_COMPANY_NAMES = {
    "kpmg": "KPMG",
    "wsp": "WSP",
}
_EIGHTFOLD_HOST = re.compile(r"^[a-z0-9-]+\.eightfold\.ai$", re.I)
_EIGHTFOLD_SEARCHES = (
    "intern", "graduate", "apprentice", "software", "developer", "data",
    "machine learning", "artificial intelligence", "cyber", "cloud", "devops",
    "quality assurance",
)
_EIGHTFOLD_JSON_LD = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.I | re.S,
)
_EIGHTFOLD_COMPANY_NAMES = {
    "micron": "Micron Technology",
}
_ICIMS_HOST = re.compile(r"^[a-z0-9-]+\.icims\.com$", re.I)
_ICIMS_JOB_PATH = re.compile(r"^/jobs/(\d+)/[^/]+/job/?$", re.I)
_ICIMS_COMPANY_NAMES = {
    "powerschool": "PowerSchool",
    "waters": "Waters Corporation",
}
_ICIMS_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/136 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
}
_AVATURE_HOST = re.compile(r"^[a-z0-9-]+\.avature\.net$", re.I)
_AVATURE_PORTAL = re.compile(
    r"^(?:(?:[a-z]{2}_[a-z]{2})/)?(?:careers|jobs)$", re.I,
)
_AVATURE_COMPANY_NAMES = {
    "synopsys": "Synopsys",
    "xerox": "Xerox",
}
_JOBVITE_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$", re.I)
_JOBVITE_JOB_PATH = re.compile(
    r"^/([a-z0-9][a-z0-9-]{0,79})/job/([a-z0-9_-]+)/?$", re.I,
)
_JOBVITE_INDIA = re.compile(
    r"\b(India|Bengaluru|Bangalore|Hyderabad|Pune|Chennai|Noida|Gurugram|"
    r"Gurgaon|Kolkata|Mumbai|Delhi|Ahmedabad|Jaipur|Kochi|Thiruvananthapuram)\b",
    re.I,
)
_SUCCESSFACTORS_SITE_HOST = re.compile(
    r"^(?!-)(?:[a-z0-9-]+\.)+[a-z]{2,63}$", re.I,
)
_SUCCESSFACTORS_CAREER_HOST = re.compile(
    r"^(?:career\d+\.successfactors\.(?:com|eu)|"
    r"[a-z0-9-]+-career\.hcm\.ondemand\.com)$", re.I,
)
_SUCCESSFACTORS_COMPANY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$", re.I)
_SUCCESSFACTORS_LOCALE = re.compile(r"^[a-z]{2}_[A-Z]{2}$")
_SUCCESSFACTORS_COMPANY_NAMES = {
    "danfossas": "Danfoss",
    "sap": "SAP",
    "abtetrap01": "Tetra Pak",
}
_SUCCESSFACTORS_XML_COMPANY_IDS = {"sap": "SAP"}
_SUCCESSFACTORS_SEARCHES = (
    "intern", "graduate", "entry level", "associate", "software", "data",
    "machine learning", "artificial intelligence", "cloud", "devops", "security",
)
_JIBE_HOST = re.compile(r"^(?!-)(?:[a-z0-9-]+\.)+[a-z]{2,63}$", re.I)
_JIBE_CLIENT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$", re.I)
_JIBE_CONTEXT = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$", re.I)
_JIBE_LOCALE = re.compile(r"^[a-z]{2}-[a-z]{2}$", re.I)
_JIBE_COMPANY_NAMES = {"amd": "Advanced Micro Devices, Inc."}


def _oraclehcm_company_name(slug: str) -> str:
    normalized = clean_text(slug).lower()
    return _ORACLEHCM_COMPANY_NAMES.get(
        normalized,
        " ".join(part.capitalize() for part in re.split(r"[-_]", normalized) if part),
    ) or slug


def _oraclehcm_workplace(value: object) -> str:
    text = clean_text(str(value or ""))
    if re.search(r"remote", text, re.I):
        return "remote"
    if re.search(r"hybrid", text, re.I):
        return "hybrid"
    return "onsite"


async def scrape_oraclehcm(
    slug: str,
    host: str,
    site_number: str,
    employer_domain: str = "",
    *,
    page_size: int = 25,
    max_early_pages_per_query: int = 3,
    max_tech_pages_per_query: int = 2,
    max_results: int = 60,
    max_stretch_results: int = 30,
) -> list[dict]:
    """Discover a bounded India CSE/AI slice of Oracle Recruiting Cloud.

    Oracle's public keyword search is fuzzy (``intern`` also finds
    ``internal``), so provider rows are never trusted as matches by
    themselves. We query a small early-career/CSE matrix, require exact local
    role evidence, de-duplicate requisitions, then fetch only retained public
    details. An empty detail response is treated as a requisition that closed
    between collection and projection and is excluded.

    This endpoint is job-content only. Application-form schemas and candidate
    fields are neither requested nor retained.
    """
    host = clean_text(host).lower().rstrip(".")
    site_number = clean_text(site_number).upper()
    slug = clean_text(slug).lower()
    employer_domain = clean_text(employer_domain).lower()
    page_size = max(1, min(int(page_size), 100))
    max_early_pages_per_query = max(1, min(int(max_early_pages_per_query), 10))
    max_tech_pages_per_query = max(1, min(int(max_tech_pages_per_query), 10))
    max_results = max(1, min(int(max_results), 100))
    max_stretch_results = max(0, min(int(max_stretch_results), max_results))
    if (
        not slug
        or not _ORACLEHCM_HOST.fullmatch(host)
        or not _ORACLEHCM_SITE.fullmatch(site_number)
        or (employer_domain and not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", employer_domain))
    ):
        return []

    base = f"https://{host}/hcmRestApi/resources/latest"
    search_url = f"{base}/recruitingCEJobRequisitions"
    candidates: dict[str, tuple[dict, set[str], bool]] = {}

    def retain(rows: object, query: str) -> None:
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            requisition_id = clean_text(str(row.get("Id") or ""))
            title = clean_text(str(row.get("Title") or ""))
            country = clean_text(str(row.get("PrimaryLocationCountry") or ""))
            location = clean_text(str(row.get("PrimaryLocation") or ""))
            early = bool(_ORACLEHCM_EARLY_TITLE.search(title))
            structured_signal = " ".join(clean_text(str(row.get(field) or "")) for field in (
                "Title", "JobFunction", "JobFamily", "Department",
            ))
            contextual_signal = " ".join((
                structured_signal,
                clean_text(str(row.get("ShortDescriptionStr") or "")),
            ))
            # A non-early stretch must identify its technical discipline in
            # the title/provider taxonomy. Generic roles often mention tools
            # or "technology" in body copy and would otherwise flood CSE.
            technical = bool(_ORACLEHCM_TECHNICAL.search(
                contextual_signal if early else structured_signal
            ))
            if (
                not requisition_id
                or not title
                or country.upper() != "IN"
                or not re.search(r"\bindia\b", location, re.I)
                or not technical
                or _ORACLEHCM_SENIOR_TITLE.search(title)
            ):
                continue
            existing = candidates.get(requisition_id)
            if existing:
                existing[1].add(query)
                candidates[requisition_id] = (existing[0], existing[1], existing[2] or early)
            else:
                candidates[requisition_id] = (row, {query}, early)

    try:
        searches = (
            *((query, max_early_pages_per_query) for query in _ORACLEHCM_EARLY_SEARCHES),
            *((query, max_tech_pages_per_query) for query in _ORACLEHCM_TECH_SEARCHES),
        )
        for query, max_pages in searches:
            for page in range(max(1, max_pages)):
                offset = page * page_size
                finder = ",".join((
                    f"findReqs;siteNumber={site_number}",
                    f"limit={page_size}",
                    f"offset={offset}",
                    "location=India",
                    f"keyword={query}",
                ))
                payload = await json_get(search_url, {
                    "onlyData": "true",
                    "expand": "requisitionList.secondaryLocations",
                    "finder": finder,
                })
                items = payload.get("items") if isinstance(payload, dict) else []
                context = (
                    items[0]
                    if isinstance(items, list) and items and isinstance(items[0], dict)
                    else {}
                )
                rows = context.get("requisitionList") if isinstance(context, dict) else []
                rows = rows if isinstance(rows, list) else []
                retain(rows, query)
                total = int(context.get("TotalJobsCount") or 0) if context else 0
                if not rows or len(rows) < page_size or (total and offset + len(rows) >= total):
                    break
    except Exception as exc:
        logging.getLogger(__name__).info(
            "oraclehcm %s/%s unavailable: %s", host, site_number, exc
        )
        return []

    prioritized = sorted(
        candidates.items(),
        key=lambda item: (
            not item[1][2],
            -int(
                re.sub(r"\D", "", str(item[1][0].get("PostedDate") or ""))[:8] or "0"
            ),
            item[0],
        ),
    )
    early = [item for item in prioritized if item[1][2]]
    stretch = [item for item in prioritized if not item[1][2]][:max_stretch_results]
    selected = [*early, *stretch][:max_results]
    detail_url = f"{base}/recruitingCEJobRequisitionDetails"
    semaphore = asyncio.Semaphore(4)
    company = _oraclehcm_company_name(slug)

    async def project(item: tuple[str, tuple[dict, set[str], bool]]) -> dict | None:
        requisition_id, (row, queries, is_early) = item
        try:
            async with semaphore:
                payload = await json_get(detail_url, {
                    "onlyData": "true",
                    "expand": "all",
                    "finder": f'ById;Id="{requisition_id}",siteNumber={site_number}',
                })
        except Exception as exc:
            logging.getLogger(__name__).info(
                "oraclehcm detail %s/%s unavailable: %s", slug, requisition_id, exc
            )
            return None
        items = payload.get("items") if isinstance(payload, dict) else []
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            return None
        merged = {**row, **items[0]}
        title = clean_text(str(merged.get("Title") or row.get("Title") or ""))
        primary_location = clean_text(str(
            merged.get("PrimaryLocation") or row.get("PrimaryLocation") or "India"
        ))
        secondary_locations: list[str] = []
        secondary = merged.get("secondaryLocations")
        if isinstance(secondary, list):
            for location_row in secondary:
                if not isinstance(location_row, dict):
                    continue
                value = clean_text(str(
                    location_row.get("Name")
                    or location_row.get("LocationName")
                    or location_row.get("PrimaryLocation")
                    or ""
                ))
                if value and re.search(r"\bindia\b", value, re.I):
                    secondary_locations.append(value)
        location = "; ".join(dict.fromkeys(
            value for value in [primary_location, *secondary_locations] if value
        ))
        workplace_raw = clean_text(str(merged.get("WorkplaceType") or ""))
        workplace = _oraclehcm_workplace(f"{workplace_raw} {location}")
        description_sections = [
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
            ("Department", "Department"),
            ("Business unit", "BusinessUnit"),
            ("Legal employer", "LegalEmployer"),
            ("Worker type", "WorkerType"),
            ("Contract type", "ContractType"),
            ("Job type", "JobType"),
            ("Job schedule", "JobSchedule"),
            ("Job shift", "JobShift"),
            ("Study level", "StudyLevel"),
            ("Manager level", "ManagerLevel"),
        )
        facts = [
            *(f"{label}: {clean_text(str(merged.get(field) or ''))}" for label, field in fact_fields
              if clean_text(str(merged.get(field) or ""))),
            f"Location: {location}",
            f"Workplace: {workplace}",
        ]
        job_url = (
            f"https://{host}/hcmUI/CandidateExperience/en/sites/"
            f"{site_number}/job/{requisition_id}"
        )
        source_meta = {
            "ats": "oraclehcm",
            "slug": slug,
            "host": host,
            "site_number": site_number,
            "id": requisition_id,
            "requisition_id": clean_text(str(merged.get("RequisitionId") or "")),
            "employer_domain": employer_domain,
            "discovery_queries": sorted(queries),
            "early_career_title": is_early,
            "legal_employer": clean_text(str(merged.get("LegalEmployer") or "")),
            "legal_employer_id": clean_text(str(merged.get("LegalEmployerId") or "")),
            "business_unit": clean_text(str(merged.get("BusinessUnit") or "")),
            "business_unit_id": clean_text(str(merged.get("BusinessUnitId") or "")),
            "department": clean_text(str(merged.get("Department") or "")),
            "organization": clean_text(str(merged.get("Organization") or "")),
            "organization_id": clean_text(str(merged.get("OrganizationId") or "")),
            "job_function": clean_text(str(merged.get("JobFunction") or "")),
            "job_family": clean_text(str(merged.get("JobFamily") or "")),
            "job_type": clean_text(str(merged.get("JobType") or "")),
            "job_schedule": clean_text(str(merged.get("JobSchedule") or "")),
            "job_shift": clean_text(str(merged.get("JobShift") or "")),
            "worker_type": clean_text(str(merged.get("WorkerType") or "")),
            "contract_type": clean_text(str(merged.get("ContractType") or "")),
            "manager_level": clean_text(str(merged.get("ManagerLevel") or "")),
            "study_level": clean_text(str(merged.get("StudyLevel") or "")),
            "workplace_type": workplace_raw,
            "workplace_type_code": clean_text(str(merged.get("WorkplaceTypeCode") or "")),
            "work_duration_years": merged.get("WorkDurationYears"),
            "work_duration_months": merged.get("WorkDurationMonths"),
            "work_hours": merged.get("WorkHours"),
            "work_days": clean_text(str(merged.get("WorkDays") or "")),
            "domestic_travel_required": clean_text(str(
                merged.get("DomesticTravelRequired") or ""
            )),
            "international_travel_required": clean_text(str(
                merged.get("InternationalTravelRequired") or ""
            )),
            "hot_job": merged.get("HotJobFlag"),
            "trending": merged.get("TrendingFlag"),
            "be_first_to_apply": merged.get("BeFirstToApplyFlag"),
            "secondary_locations": secondary_locations,
        }
        source_meta = {
            key: value for key, value in source_meta.items()
            if value not in (None, "", [])
        }
        return text_lead({
            "title": title,
            "company": company,
            "url": job_url,
            "apply_url": job_url,
            "attribution": job_url,
            "platform": "oraclehcm",
            "description": "\n".join(
                value for value in [*description_sections, *facts] if value
            ).strip(),
            "posted_date": str(row.get("PostedDate") or merged.get("PostedDate") or ""),
            "deadline": str(row.get("PostingEndDate") or merged.get("PostingEndDate") or ""),
            "location": location,
            "workplace": workplace,
            "active_hint": "active",
            "source_meta": source_meta,
        })

    projected = await asyncio.gather(*(project(item) for item in selected))
    return [lead for lead in projected if isinstance(lead, dict)]


def _eightfold_job_schema(raw_html: str) -> dict:
    for match in _EIGHTFOLD_JSON_LD.finditer(raw_html):
        try:
            payload = json.loads(html_lib.unescape(match.group(1)))
        except (TypeError, ValueError):
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") == "JobPosting":
                return node
    return {}


def _eightfold_locations(card: dict) -> tuple[str, list[str]]:
    values: list[str] = []
    location = clean_text(str(card.get("location") or ""))
    if location:
        values.append(location)
    raw_locations = card.get("locations")
    if isinstance(raw_locations, list):
        values.extend(
            clean_text(str(value))
            for value in raw_locations
            if clean_text(str(value))
        )
    standardized = card.get("standardizedLocations")
    standardized_values = (
        [clean_text(str(value)) for value in standardized if clean_text(str(value))]
        if isinstance(standardized, list)
        else []
    )
    return "; ".join(dict.fromkeys(values)), list(dict.fromkeys(standardized_values))


def _eightfold_india_card(card: dict) -> bool:
    location, standardized = _eightfold_locations(card)
    return bool(
        re.search(r"\bindia\b", location, re.I)
        or any(re.search(r"(?:^|,\s*)IN$", value, re.I) for value in standardized)
    )


def _eightfold_company_name(slug: str) -> str:
    normalized = clean_text(slug).lower()
    return _EIGHTFOLD_COMPANY_NAMES.get(
        normalized,
        " ".join(part.capitalize() for part in re.split(r"[-_]", normalized) if part),
    ) or slug


async def _eightfold_json(url: str, params: dict) -> dict:
    raw = await text_get(
        url,
        params,
        request_headers={
            "Accept": "application/json, */*",
            "Referer": url.split("/api/", 1)[0] + "/careers",
        },
    )
    payload = json.loads(raw)
    return payload if isinstance(payload, dict) else {}


async def scrape_eightfold(
    slug: str,
    host: str,
    domain: str,
    *,
    max_search_pages: int = 20,
    max_classic_pages: int = 100,
    max_results: int = 60,
    max_stretch_results: int = 30,
) -> list[dict]:
    """Read a public Eightfold PCS-X or classic tenant for India CSE roles.

    The two live API generations have different response envelopes. PCS-X is
    search-first at ``/api/pcsx/search``; classic is a board-wide paginated
    feed at ``/api/apply/v2/jobs`` whose server page size is fixed at ten.
    Both paths are bounded and locally re-filtered. Only retained cards receive
    a same-host public JobPosting detail request; apply-form APIs are untouched.
    """
    slug = clean_text(slug).lower()
    host = clean_text(host).lower().rstrip(".")
    domain = clean_text(domain).lower()
    max_search_pages = max(1, min(int(max_search_pages), 50))
    max_classic_pages = max(1, min(int(max_classic_pages), 200))
    max_results = max(1, min(int(max_results), 100))
    max_stretch_results = max(0, min(int(max_stretch_results), max_results))
    if (
        not slug
        or not _EIGHTFOLD_HOST.fullmatch(host)
        or not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain)
    ):
        return []

    pcsx_url = f"https://{host}/api/pcsx/search"
    classic_url = f"https://{host}/api/apply/v2/jobs"
    cards: dict[str, tuple[dict, set[str], bool]] = {}

    def retain(rows: object, query: str) -> None:
        if not isinstance(rows, list):
            return
        for card in rows:
            if not isinstance(card, dict):
                continue
            position_id = clean_text(str(card.get("id") or ""))
            title = clean_text(str(card.get("name") or card.get("posting_name") or ""))
            title_signal = title.replace("_", " ")
            is_early = bool(_ORACLEHCM_EARLY_TITLE.search(title_signal))
            is_technical = bool(_ORACLEHCM_TECHNICAL.search(title_signal))
            if (
                not position_id
                or not title
                or not _eightfold_india_card(card)
                or _ORACLEHCM_SENIOR_TITLE.search(title_signal)
                or not (is_early or is_technical)
            ):
                continue
            existing = cards.get(position_id)
            if existing:
                existing[1].add(query)
                cards[position_id] = (
                    existing[0], existing[1], existing[2] or is_early
                )
            else:
                cards[position_id] = (card, {query}, is_early)

    generation = "pcsx"
    try:
        for query in _EIGHTFOLD_SEARCHES:
            start = 0
            for _page in range(max_search_pages):
                payload = await _eightfold_json(pcsx_url, {
                    "domain": domain,
                    "query": query,
                    "location": "India",
                    "start": start,
                })
                data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                rows = data.get("positions") if isinstance(data, dict) else []
                rows = rows if isinstance(rows, list) else []
                retain(rows, query)
                total = int(data.get("count") or 0) if isinstance(data, dict) else 0
                start += len(rows)
                if not rows or len(rows) < 10 or (total and start >= total):
                    break
    except httpx.HTTPStatusError as exc:
        body = clean_text(exc.response.text).lower()
        if exc.response.status_code != 403 or not re.search(
            r"(?:not authorized for pcsx|pcsx is not enabled)", body
        ):
            logging.getLogger(__name__).info(
                "eightfold pcsx %s/%s unavailable: %s", host, domain, exc
            )
            return []
        generation = "classic"
    except (ValueError, json.JSONDecodeError) as exc:
        logging.getLogger(__name__).info(
            "eightfold pcsx %s/%s invalid JSON: %s", host, domain, exc
        )
        return []
    except Exception as exc:
        logging.getLogger(__name__).info(
            "eightfold pcsx %s/%s unavailable: %s", host, domain, exc
        )
        return []

    if generation == "classic":
        try:
            for page in range(max_classic_pages):
                start = page * 10
                payload = await _eightfold_json(classic_url, {
                    "domain": domain,
                    "start": start,
                    "num": 10,
                })
                rows = payload.get("positions")
                rows = rows if isinstance(rows, list) else []
                retain(rows, "classic-board")
                total = int(payload.get("count") or 0)
                if not rows or len(rows) < 10 or (total and start + len(rows) >= total):
                    break
                await asyncio.sleep(0.25)
        except Exception as exc:
            logging.getLogger(__name__).info(
                "eightfold classic %s/%s unavailable: %s", host, domain, exc
            )
            return []

    prioritized = sorted(
        cards.items(),
        key=lambda item: (
            not item[1][2],
            -int(item[1][0].get("postedTs") or item[1][0].get("t_create") or 0),
            item[0],
        ),
    )
    early = [item for item in prioritized if item[1][2]]
    stretch = [item for item in prioritized if not item[1][2]][:max_stretch_results]
    selected = [*early, *stretch][:max_results]
    company = _eightfold_company_name(slug)
    board_url = f"https://{host}/careers?{urlencode({'domain': domain})}"
    semaphore = asyncio.Semaphore(4)

    async def project(item: tuple[str, tuple[dict, set[str], bool]]) -> dict | None:
        position_id, (card, queries, is_early) = item
        position_path = clean_text(str(card.get("positionUrl") or ""))
        if not position_path.startswith("/careers"):
            position_path = f"/careers/job/{position_id}"
        separator = "&" if "?" in position_path else "?"
        detail_url = f"https://{host}{position_path}{separator}{urlencode({'domain': domain})}"
        try:
            async with semaphore:
                raw_html = await text_get(
                    detail_url,
                    request_headers={"Accept-Encoding": "identity"},
                )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {404, 410}:
                return None
            raise
        schema = _eightfold_job_schema(raw_html)
        if not schema:
            return None
        title = clean_text(str(schema.get("title") or card.get("name") or ""))
        location, standardized_locations = _eightfold_locations(card)
        if not title or not location:
            return None
        workplace_raw = clean_text(str(
            card.get("workLocationOption") or card.get("work_location_option") or ""
        )).lower()
        workplace = (
            "remote" if re.search(r"remote|work from home", f"{workplace_raw} {location}", re.I)
            else "hybrid" if re.search(r"hybrid", workplace_raw, re.I)
            else "onsite"
        )
        description = strip_html_text(str(schema.get("description") or ""))
        employment_type = schema.get("employmentType")
        employment_values = (
            employment_type if isinstance(employment_type, list) else [employment_type]
        )
        employment_text = ", ".join(
            clean_text(str(value)).replace("_", " ").title()
            for value in employment_values
            if clean_text(str(value or ""))
        )
        organization = (
            schema.get("hiringOrganization")
            if isinstance(schema.get("hiringOrganization"), dict)
            else {}
        )
        facts = [
            f"Department: {clean_text(str(card.get('department') or ''))}"
            if clean_text(str(card.get("department") or "")) else "",
            f"Business unit: {clean_text(str(card.get('business_unit') or ''))}"
            if clean_text(str(card.get("business_unit") or "")) else "",
            f"Employment type: {employment_text}" if employment_text else "",
            f"Location: {location}",
            f"Workplace: {workplace}",
        ]
        display_id = clean_text(str(
            card.get("displayJobId") or card.get("display_job_id")
            or card.get("atsJobId") or position_id
        ))
        created = card.get("creationTs") or card.get("t_create")
        updated = card.get("postedTs") or card.get("t_update")
        source_meta = {
            "ats": "eightfold",
            "slug": slug,
            "host": host,
            "domain": domain,
            "id": display_id,
            "position_id": position_id,
            "ats_job_id": clean_text(str(card.get("atsJobId") or "")),
            "display_job_id": clean_text(str(card.get("displayJobId") or "")),
            "generation": generation,
            "employer_domain": domain,
            "employer_name": clean_text(str(organization.get("name") or company)),
            "discovery_queries": sorted(queries),
            "early_career_title": is_early,
            "department": clean_text(str(card.get("department") or "")),
            "business_unit": clean_text(str(card.get("business_unit") or "")),
            "standardized_locations": standardized_locations,
            "workplace_type": workplace_raw,
            "location_flexibility": card.get("locationFlexibility"),
            "skills": card.get("skills") if isinstance(card.get("skills"), list) else [],
            "seniority": card.get("seniority"),
            "is_hot": card.get("isHot"),
            "stars": card.get("stars"),
            "creation_epoch_seconds": created,
            "posted_epoch_seconds": updated,
            "employment_type": employment_values,
            "base_salary": schema.get("baseSalary")
            if isinstance(schema.get("baseSalary"), dict) else {},
            "board_url": board_url,
        }
        source_meta = {
            key: value for key, value in source_meta.items()
            if value not in (None, "", [], {})
        }
        posted = str(schema.get("datePosted") or "")
        if not posted and updated:
            try:
                posted = datetime.fromtimestamp(
                    int(updated), tz=timezone.utc
                ).isoformat()
            except (TypeError, ValueError, OSError):
                posted = str(updated)
        return text_lead({
            "title": title,
            "company": company,
            "url": detail_url,
            "apply_url": detail_url,
            "attribution": board_url,
            "platform": "eightfold",
            "description": "\n".join(
                value for value in [description, *facts] if value
            ).strip(),
            "posted_date": posted,
            "deadline": str(schema.get("validThrough") or ""),
            "location": location,
            "workplace": workplace,
            "active_hint": "active",
            "source_meta": source_meta,
        })

    projected = await asyncio.gather(
        *(project(item) for item in selected), return_exceptions=True
    )
    return [lead for lead in projected if isinstance(lead, dict)]


def _icims_company_name(slug: str) -> str:
    normalized = clean_text(slug).lower()
    return _ICIMS_COMPANY_NAMES.get(
        normalized,
        " ".join(part.capitalize() for part in re.split(r"[-_]", normalized) if part),
    ) or slug


def _icims_html_text(value: object) -> str:
    return clean_text(strip_html_text(html_lib.unescape(str(value or ""))))


def _icims_search_cards(raw_html: str, host: str) -> list[dict]:
    """Parse one public iCIMS hosted-portal result page.

    iCIMS themes vary their class ordering and add attributes to headings, so
    parsing keys off whole class tokens and the authoritative numeric job path.
    Every resolved posting must remain HTTPS and on the exact configured host.
    """
    origin = f"https://{host}"
    cards: list[dict] = []
    for fragment in re.split(r"iCIMS_JobCardItem", str(raw_html), flags=re.I)[1:]:
        href_match = re.search(
            r"href=[\"']([^\"']*/jobs/(\d+)/[^\"'/]+/job(?:\?[^\"']*)?)[\"']",
            fragment,
            re.I,
        )
        title_match = re.search(r"<h3\b[^>]*>(.*?)</h3>", fragment, re.I | re.S)
        if not href_match or not title_match:
            continue
        parsed = urlparse(urljoin(origin, html_lib.unescape(href_match.group(1))))
        path_match = _ICIMS_JOB_PATH.fullmatch(parsed.path)
        if parsed.scheme != "https" or parsed.netloc.lower() != host or not path_match:
            continue
        title = _icims_html_text(title_match.group(1))
        if not title:
            continue
        summary_match = re.search(
            r"<div\b[^>]*class=[\"'][^\"']*(?<![\w-])description(?![\w-])"
            r"[^\"']*[\"'][^>]*>(.*?)</div>",
            fragment,
            re.I | re.S,
        )
        fields: dict[str, str] = {}
        # Some themes place location/requisition pairs in a card header rather
        # than the later dt/dd group (for example Seismic). Capture both forms.
        for pair in re.finditer(
            r"<span\b[^>]*class=[\"'][^\"']*(?<![\w-])field-label(?![\w-])"
            r"[^\"']*[\"'][^>]*>(.*?)</span>\s*<span\b[^>]*>(.*?)</span>",
            fragment,
            re.I | re.S,
        ):
            label = _icims_html_text(pair.group(1))
            value = _icims_html_text(pair.group(2))
            if label and value:
                fields[label] = value
        for tag in re.finditer(
            r"iCIMS_JobHeaderTag.*?<dt\b[^>]*>(.*?)</dt>"
            r".*?<dd\b[^>]*>(.*?)</dd>",
            fragment,
            re.I | re.S,
        ):
            label = _icims_html_text(tag.group(1))
            value = _icims_html_text(tag.group(2))
            if label and value:
                fields[label] = value
        location = "; ".join(dict.fromkeys(
            value for key, value in fields.items()
            if "location" in key.lower() and value
        ))
        cards.append({
            "id": path_match.group(1),
            "title": title,
            "url": f"{origin}{parsed.path.rstrip('/')}",
            "summary": _icims_html_text(summary_match.group(1)) if summary_match else "",
            "location": location,
            "fields": fields,
        })
    return cards


def _icims_schema_locations(schema: dict) -> tuple[list[str], list[dict]]:
    raw_locations = schema.get("jobLocation")
    rows = raw_locations if isinstance(raw_locations, list) else [raw_locations]
    labels: list[str] = []
    public_rows: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        address = row.get("address") if isinstance(row.get("address"), dict) else {}
        parts = [
            clean_text(str(address.get(key) or ""))
            for key in ("addressLocality", "addressRegion", "addressCountry")
        ]
        label = ", ".join(dict.fromkeys(value for value in parts if value))
        if label:
            labels.append(label)
        public_rows.append({
            key: value for key, value in {
                "address_locality": address.get("addressLocality"),
                "address_region": address.get("addressRegion"),
                "address_country": address.get("addressCountry"),
                "postal_code": address.get("postalCode"),
            }.items() if value not in (None, "")
        })
    return list(dict.fromkeys(labels)), public_rows


async def scrape_icims(
    slug: str,
    host: str,
    employer_domain: str = "",
    *,
    max_pages: int = 30,
    max_results: int = 60,
    max_stretch_results: int = 30,
) -> list[dict]:
    """Read a bounded public iCIMS board for live India CSE/AI roles.

    Search pages are server-rendered and contain title, summary, location,
    requisition, and public taxonomy fields. Only locally retained India tech
    candidates receive a same-host detail request. A valid public JobPosting
    node is required for liveness and supplies description and dates; no apply
    form, candidate, or question endpoint is accessed.
    """
    slug = clean_text(slug).lower()
    host = clean_text(host).lower().rstrip(".")
    employer_domain = clean_text(employer_domain).lower()
    max_pages = max(1, min(int(max_pages), 30))
    max_results = max(1, min(int(max_results), 100))
    max_stretch_results = max(0, min(int(max_stretch_results), max_results))
    if (
        not slug
        or not _ICIMS_HOST.fullmatch(host)
        or (employer_domain and not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", employer_domain))
    ):
        return []

    board_url = f"https://{host}/jobs/search?ss=1"
    retained: dict[str, tuple[dict, bool]] = {}
    previous_first_id = ""
    reached_end = False
    try:
        for page in range(max_pages):
            raw_html = await text_get(
                f"https://{host}/jobs/search",
                {"ss": "1", "pr": page, "in_iframe": "1"},
                request_headers=_ICIMS_BROWSER_HEADERS,
            )
            cards = _icims_search_cards(raw_html, host)
            if not cards:
                reached_end = True
                break
            if cards[0]["id"] == previous_first_id:
                reached_end = True
                break
            previous_first_id = cards[0]["id"]
            for card in cards:
                title = card["title"]
                location = card["location"]
                if not re.search(r"(?:\bindia\b|(?:^|[\s;,|])IN-)", location, re.I):
                    continue
                fields = card["fields"]
                structured_signal = " ".join((title, *fields.values()))
                is_early = bool(_WORKDAY_EARLY_TITLE.search(title))
                technical_signal = " ".join((structured_signal, card["summary"]))
                is_technical = bool(_ORACLEHCM_TECHNICAL.search(
                    technical_signal if is_early else structured_signal
                ))
                if (
                    not is_technical
                    or _ORACLEHCM_SENIOR_TITLE.search(title)
                    or not (is_early or _ORACLEHCM_TECHNICAL.search(title))
                ):
                    continue
                retained.setdefault(card["id"], (card, is_early))
            if len(cards) < 20:
                reached_end = True
                break
            if page + 1 < max_pages:
                await asyncio.sleep(0.25)
    except Exception as exc:
        logging.getLogger(__name__).info("icims %s unavailable: %s", host, exc)
        return []

    if not reached_end:
        logging.getLogger(__name__).warning(
            "icims %s scan reached the %s-page safety cap", host, max_pages
        )
    prioritized = sorted(
        retained.items(), key=lambda item: (not item[1][1], item[0]),
    )
    early = [item for item in prioritized if item[1][1]]
    stretch = [item for item in prioritized if not item[1][1]][:max_stretch_results]
    selected = [*early, *stretch][:max_results]
    semaphore = asyncio.Semaphore(4)
    fallback_company = _icims_company_name(slug)

    async def project(item: tuple[str, tuple[dict, bool]]) -> dict | None:
        job_id, (card, is_early) = item
        detail_url = card["url"]
        try:
            async with semaphore:
                raw_html = await text_get(
                    detail_url,
                    {"in_iframe": "1"},
                    request_headers=_ICIMS_BROWSER_HEADERS,
                )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {404, 410}:
                return None
            raise
        schema = _eightfold_job_schema(raw_html)
        if not schema:
            return None
        title = clean_text(str(schema.get("title") or card["title"]))
        schema_locations, public_locations = _icims_schema_locations(schema)
        location = card["location"] or "; ".join(schema_locations)
        country_signal = " ".join(
            str(row.get("address_country") or "") for row in public_locations
        )
        if not re.search(
            r"(?:\bindia\b|(?:^|[\s;,|])IN(?:-|$))",
            f"{location} {country_signal}",
            re.I,
        ):
            return None
        job_location_type = clean_text(str(schema.get("jobLocationType") or ""))
        workplace = (
            "remote" if re.search(r"telecommute|remote|work from home", job_location_type, re.I)
            else "hybrid" if re.search(r"hybrid", f"{job_location_type} {location}", re.I)
            else "onsite"
        )
        organization = (
            schema.get("hiringOrganization")
            if isinstance(schema.get("hiringOrganization"), dict) else {}
        )
        company = clean_text(str(organization.get("name") or fallback_company))
        employment_type = schema.get("employmentType")
        employment_values = (
            employment_type if isinstance(employment_type, list) else [employment_type]
        )
        field_facts = [
            f"{key}: {value}" for key, value in card["fields"].items()
            if key.lower() not in {"job locations", "location"}
        ]
        facts = [
            *field_facts,
            f"Location: {location}",
            f"Workplace: {workplace}",
        ]
        same_as = clean_text(str(organization.get("sameAs") or ""))
        source_meta = {
            "ats": "icims",
            "slug": slug,
            "host": host,
            "id": job_id,
            "employer_domain": employer_domain,
            "employer_name": company,
            "employer_same_as": same_as,
            "early_career_title": is_early,
            "additional_fields": card["fields"],
            "structured_locations": public_locations,
            "job_location_type": job_location_type,
            "employment_type": [value for value in employment_values if value],
            "direct_apply": schema.get("directApply"),
            "applicant_location_requirements": schema.get(
                "applicantLocationRequirements"
            ),
            "base_salary": schema.get("baseSalary")
            if isinstance(schema.get("baseSalary"), dict) else {},
            "board_url": board_url,
        }
        source_meta = {
            key: value for key, value in source_meta.items()
            if value not in (None, "", [], {})
        }
        description = strip_html_text(str(schema.get("description") or ""))
        return text_lead({
            "title": title,
            "company": company,
            "url": detail_url,
            "apply_url": detail_url,
            "attribution": board_url,
            "platform": "icims",
            "description": "\n".join(
                value for value in [description, *facts] if value
            ).strip(),
            "posted_date": str(schema.get("datePosted") or ""),
            "deadline": str(schema.get("validThrough") or ""),
            "location": location,
            "workplace": workplace,
            "active_hint": "active",
            "source_meta": source_meta,
        })

    projected = await asyncio.gather(
        *(project(item) for item in selected), return_exceptions=True
    )
    for result in projected:
        if isinstance(result, Exception):
            logging.getLogger(__name__).info(
                "icims %s detail unavailable: %s", host, result
            )
    return [lead for lead in projected if isinstance(lead, dict)]


def _avature_company_name(slug: str) -> str:
    normalized = clean_text(slug).lower()
    return _AVATURE_COMPANY_NAMES.get(
        normalized,
        " ".join(part.capitalize() for part in re.split(r"[-_]", normalized) if part),
    ) or slug


def _avature_job_id(url: str, host: str, portal: str) -> str:
    parsed = urlparse(html_lib.unescape(str(url or "")))
    if parsed.scheme != "https" or parsed.netloc.lower() != host:
        return ""
    expected = f"/{portal}/JobDetail"
    if not parsed.path.lower().startswith(expected.lower()):
        return ""
    suffix = parsed.path[len(expected):].strip("/")
    if suffix:
        final = suffix.rsplit("/", 1)[-1]
        if final.isdigit():
            return final
    query_id = clean_text(str((parse_qs(parsed.query).get("jobId") or [""])[0]))
    return query_id if query_id.isdigit() else ""


def _avature_search_cards(raw_html: str, host: str, portal: str) -> list[dict]:
    cards: list[dict] = []
    for match in re.finditer(
        r"<article\b[^>]*class=[\"'][^\"']*(?<![\w-])article--result(?![\w-])"
        r"[^\"']*[\"'][^>]*>(.*?)</article>",
        str(raw_html),
        re.I | re.S,
    ):
        fragment = match.group(1)
        title_match = re.search(
            r"<h[1-6]\b[^>]*>.*?<a\b[^>]*href=[\"']([^\"']+)"
            r"[\"'][^>]*>(.*?)</a>.*?</h[1-6]>",
            fragment,
            re.I | re.S,
        )
        if not title_match:
            continue
        parsed = urlparse(urljoin(f"https://{host}", html_lib.unescape(title_match.group(1))))
        canonical_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        job_id = _avature_job_id(canonical_url, host, portal)
        title = _icims_html_text(title_match.group(2))
        if not job_id or not title:
            continue
        fields: dict[str, str] = {}
        for pair in re.finditer(
            r"<span\b[^>]*class=[\"'][^\"']*(?:text--bold|field-label)[^\"']*"
            r"[\"'][^>]*>(.*?)</span>\s*([^<]*(?:<(?!/?p\b)[^>]+>[^<]*)*)",
            fragment,
            re.I | re.S,
        ):
            label = _icims_html_text(pair.group(1)).rstrip(":")
            value = _icims_html_text(pair.group(2))
            if label and value:
                fields[label] = value
        for span in re.finditer(
            r"<span\b[^>]*class=[\"'][^\"']*list-item-([a-z0-9_-]+)[^\"']*"
            r"[\"'][^>]*>(.*?)</span>",
            fragment,
            re.I | re.S,
        ):
            key = clean_text(span.group(1)).replace("-", "_")
            value = _icims_html_text(span.group(2))
            if key and value:
                fields.setdefault(key, value)
        apply_url = ""
        for href in re.findall(r"href=[\"']([^\"']+/Login\?[^\"']+)[\"']", fragment, re.I):
            candidate = urlparse(urljoin(f"https://{host}", html_lib.unescape(href)))
            candidate_id = clean_text(str((parse_qs(candidate.query).get("jobId") or [""])[0]))
            if (
                candidate.scheme == "https"
                and candidate.netloc.lower() == host
                and candidate_id == job_id
            ):
                apply_url = candidate.geturl()
                break
        card_text = _icims_html_text(fragment)
        posted_match = re.search(r"\bPosted\s+([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})\b", card_text)
        cards.append({
            "id": job_id,
            "title": title,
            "url": canonical_url,
            "apply_url": apply_url,
            "fields": fields,
            "summary": card_text,
            "posted_date": posted_match.group(1) if posted_match else "",
            "india": bool(re.search(r"\bIndia\b", card_text, re.I)),
        })
    return cards


def _avature_india_facet(raw_html: str) -> tuple[str, str]:
    for select in re.finditer(
        r"<select\b[^>]*name=[\"']([^\"']+)[\"'][^>]*>(.*?)</select>",
        str(raw_html),
        re.I | re.S,
    ):
        india = re.search(
            r"<option\b[^>]*value=[\"']?([^\"' >]+)[\"']?[^>]*>\s*India\s*</option>",
            select.group(2),
            re.I | re.S,
        )
        if india:
            return clean_text(select.group(1)), clean_text(india.group(1))
    return "", ""


def _avature_total(raw_html: str) -> int | None:
    match = re.search(r"\bof\s+([\d,]+)\s+results?\b", str(raw_html), re.I)
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _avature_date(value: object) -> str:
    text = clean_text(str(value or ""))
    for pattern in ("%d-%b-%Y", "%A, %B %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    return text


def _avature_detail_fields(raw_html: str) -> tuple[dict[str, str], list[str]]:
    fields: dict[str, str] = {}
    for pair in re.finditer(
        r"<div\b[^>]*class=[\"'][^\"']*article__content__view__field__label"
        r"[^\"']*[\"'][^>]*>(.*?)</div>\s*"
        r"<div\b[^>]*class=[\"'][^\"']*article__content__view__field__value"
        r"[^\"']*[\"'][^>]*>(.*?)</div>",
        str(raw_html),
        re.I | re.S,
    ):
        label = _icims_html_text(pair.group(1)).rstrip(":")
        value = _icims_html_text(pair.group(2))
        if label and value:
            fields[label] = value
    sections = [
        _icims_html_text(article.group(1))
        for article in re.finditer(r"<article\b[^>]*>(.*?)</article>", str(raw_html), re.I | re.S)
    ]
    return fields, [section for section in sections if section]


async def scrape_avature(
    slug: str,
    host: str,
    portal: str = "careers",
    employer_domain: str = "",
    *,
    max_pages: int = 50,
    max_results: int = 60,
    max_stretch_results: int = 30,
) -> list[dict]:
    """Read a bounded public Avature portal for live India CSE/AI roles.

    A board's own India facet is preferred. Branded portals without that facet
    are narrowed by their public full-text search and still require an exact
    India card/detail signal. Only same-host JobDetail and Login URLs are kept;
    no profile, application-form, question, or candidate endpoint is requested.
    """
    slug = clean_text(slug).lower()
    host = clean_text(host).lower().rstrip(".")
    portal = clean_text(portal).strip("/") or "careers"
    employer_domain = clean_text(employer_domain).lower()
    max_pages = max(1, min(int(max_pages), 60))
    max_results = max(1, min(int(max_results), 100))
    max_stretch_results = max(0, min(int(max_stretch_results), max_results))
    if (
        not slug
        or not _AVATURE_HOST.fullmatch(host)
        or not _AVATURE_PORTAL.fullmatch(portal)
        or (employer_domain and not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", employer_domain))
    ):
        return []

    board_url = f"https://{host}/{portal}/SearchJobs"
    try:
        first_html = await text_get(
            board_url,
            {"jobOffset": 0},
            request_headers=_ICIMS_BROWSER_HEADERS,
        )
    except Exception as exc:
        logging.getLogger(__name__).info("avature %s unavailable: %s", host, exc)
        return []
    facet_name, facet_value = _avature_india_facet(first_html)
    scope = {facet_name: facet_value} if facet_name and facet_value else {"search": "India"}
    retained: dict[str, tuple[dict, bool]] = {}
    pagination_key = "jobOffset"
    page_size = 0
    offset = 0
    previous_first_id = ""
    reached_end = False

    try:
        for page in range(max_pages):
            params = {**scope, pagination_key: offset}
            raw_html = await text_get(
                board_url, params, request_headers=_ICIMS_BROWSER_HEADERS,
            )
            cards = _avature_search_cards(raw_html, host, portal)
            if (
                page == 1
                and cards
                and cards[0]["id"] == previous_first_id
                and pagination_key == "jobOffset"
            ):
                pagination_key = "offset"
                params = {**scope, pagination_key: offset}
                raw_html = await text_get(
                    board_url, params, request_headers=_ICIMS_BROWSER_HEADERS,
                )
                cards = _avature_search_cards(raw_html, host, portal)
            if not cards or cards[0]["id"] == previous_first_id:
                reached_end = True
                break
            previous_first_id = cards[0]["id"]
            if page_size == 0:
                page_size = len(cards)
            for card in cards:
                if not (facet_name or card["india"]):
                    continue
                title = card["title"]
                is_early = bool(_WORKDAY_EARLY_TITLE.search(title))
                if (
                    not _ORACLEHCM_TECHNICAL.search(title)
                    or _ORACLEHCM_SENIOR_TITLE.search(title)
                ):
                    continue
                retained.setdefault(card["id"], (card, is_early))
            total = _avature_total(raw_html)
            if total is not None and offset + len(cards) >= total:
                reached_end = True
                break
            offset += max(page_size, len(cards), 1)
            if page + 1 < max_pages:
                await asyncio.sleep(0.15)
    except Exception as exc:
        logging.getLogger(__name__).info("avature %s scan unavailable: %s", host, exc)
        return []

    if not reached_end:
        logging.getLogger(__name__).warning(
            "avature %s scan reached the %s-page safety cap", host, max_pages
        )
    prioritized = sorted(retained.items(), key=lambda item: (not item[1][1], item[0]))
    early = [item for item in prioritized if item[1][1]]
    stretch = [item for item in prioritized if not item[1][1]][:max_stretch_results]
    selected = [*early, *stretch][:max_results]
    semaphore = asyncio.Semaphore(4)
    fallback_company = _avature_company_name(slug)

    async def project(item: tuple[str, tuple[dict, bool]]) -> dict | None:
        job_id, (card, is_early) = item
        try:
            async with semaphore:
                raw_html = await text_get(
                    card["url"], request_headers=_ICIMS_BROWSER_HEADERS,
                )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {404, 410}:
                return None
            raise
        fields, sections = _avature_detail_fields(raw_html)
        lowered_fields = {key.lower(): value for key, value in fields.items()}
        og_title = re.search(
            r"<meta\b[^>]*property=[\"']og:title[\"'][^>]*content=[\"']([^\"']+)",
            raw_html,
            re.I,
        )
        detail_title = clean_text(
            lowered_fields.get("job title")
            or (_icims_html_text(og_title.group(1)) if og_title else "")
        )
        if not detail_title or detail_title.casefold() != card["title"].casefold():
            return None
        country = lowered_fields.get("country", "")
        if country and not re.search(r"\bIndia\b|^IN$", country, re.I):
            return None
        if not country and not (facet_name or card["india"]):
            return None
        city = lowered_fields.get("city", "")
        state = lowered_fields.get("state/province", "")
        location = ", ".join(dict.fromkeys(
            value for value in (city, state, country or "India") if value
        ))
        remote_eligible = lowered_fields.get("remote eligible", "")
        arrangement = " ".join(
            lowered_fields.get(key, "") for key in (
                "work arrangement", "flexible work options", "workplace type",
            )
        )
        workplace = (
            "hybrid" if re.search(r"\bhybrid\b", arrangement, re.I)
            else "remote" if (
                re.search(r"\b(remote|home.?based|telecommut)\b", arrangement, re.I)
                or re.fullmatch(r"(?i)yes|true|remote", remote_eligible.strip())
            )
            else "onsite"
        )
        description = max(sections, key=len, default="")
        if len(description) < 80:
            return None
        posted_date = (
            lowered_fields.get("date posted")
            or lowered_fields.get("date")
            or card["posted_date"]
        )
        public_fields = {
            key: value for key, value in fields.items()
            if not re.search(r"description|requirements", key, re.I)
        }
        employment_type = [
            lowered_fields[key] for key in (
                "hire type", "working time", "job type", "seniority level", "job level",
            ) if lowered_fields.get(key)
        ]
        facts = [
            *(f"{key}: {value}" for key, value in public_fields.items()),
            f"Location: {location}",
            f"Workplace: {workplace}",
        ]
        source_meta = {
            "ats": "avature",
            "slug": slug,
            "host": host,
            "portal": portal,
            "id": job_id,
            "employer_domain": employer_domain,
            "employer_name": fallback_company,
            "early_career_title": is_early,
            "additional_fields": public_fields,
            "employment_type": employment_type,
            "india_scope": (
                {"facet": facet_name, "value": facet_value}
                if facet_name else {"search": "India"}
            ),
            "pagination_key": pagination_key,
            "board_url": board_url,
        }
        source_meta = {
            key: value for key, value in source_meta.items()
            if value not in (None, "", [], {})
        }
        return text_lead({
            "title": detail_title,
            "company": fallback_company,
            "url": card["url"],
            "apply_url": card["apply_url"] or card["url"],
            "attribution": board_url,
            "platform": "avature",
            "description": "\n".join([description, *facts]).strip(),
            "posted_date": _avature_date(posted_date),
            "location": location,
            "workplace": workplace,
            "active_hint": "active",
            "source_meta": source_meta,
        })

    projected = await asyncio.gather(
        *(project(item) for item in selected), return_exceptions=True,
    )
    for result in projected:
        if isinstance(result, Exception):
            logging.getLogger(__name__).info(
                "avature %s detail unavailable: %s", host, result
            )
    return [lead for lead in projected if isinstance(lead, dict)]


def _jobvite_search_cards(raw_html: str, slug: str) -> list[dict]:
    cards: list[dict] = []
    origin = "https://jobs.jobvite.com"
    for row in re.finditer(
        r"<tr\b[^>]*>\s*<td\b[^>]*class=[\"'][^\"']*jv-job-list-name[^\"']*"
        r"[\"'][^>]*>\s*<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>"
        r"(.*?)</a>\s*</td>\s*<td\b[^>]*class=[\"'][^\"']*"
        r"jv-job-list-location[^\"']*[\"'][^>]*>(.*?)</td>",
        str(raw_html),
        re.I | re.S,
    ):
        parsed = urlparse(urljoin(origin, html_lib.unescape(row.group(1))))
        path_match = _JOBVITE_JOB_PATH.fullmatch(parsed.path)
        title = _icims_html_text(row.group(2))
        location = _icims_html_text(row.group(3))
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != "jobs.jobvite.com"
            or not path_match
            or path_match.group(1).lower() != slug
            or not title
        ):
            continue
        cards.append({
            "id": path_match.group(2),
            "title": title,
            "location": location,
            "url": f"{origin}{parsed.path.rstrip('/')}",
        })
    return cards


def _jobvite_identifier(schema: dict) -> str:
    identifier = schema.get("identifier")
    if isinstance(identifier, dict):
        identifier = identifier.get("value") or identifier.get("name")
    return clean_text(str(identifier or ""))


def _jobvite_schema_locations(schema: dict) -> list[tuple[str, dict]]:
    """Return aligned public labels/fields for every structured location."""
    raw_locations = schema.get("jobLocation")
    rows = raw_locations if isinstance(raw_locations, list) else [raw_locations]
    locations: list[tuple[str, dict]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        address = row.get("address") if isinstance(row.get("address"), dict) else {}
        public = {
            key: value for key, value in {
                "address_locality": address.get("addressLocality"),
                "address_region": address.get("addressRegion"),
                "address_country": address.get("addressCountry"),
                "postal_code": address.get("postalCode"),
                "street_address": address.get("streetAddress"),
                "latitude": (
                    row.get("geo", {}).get("latitude")
                    if isinstance(row.get("geo"), dict) else None
                ),
                "longitude": (
                    row.get("geo", {}).get("longitude")
                    if isinstance(row.get("geo"), dict) else None
                ),
            }.items() if value not in (None, "")
        }
        label = ", ".join(dict.fromkeys(
            clean_text(str(public.get(key) or "")).strip(" ,")
            for key in ("address_locality", "address_region", "address_country")
            if clean_text(str(public.get(key) or "")).strip(" ,")
        ))
        locations.append((label, public))
    return locations


async def scrape_jobvite(
    slug: str,
    employer_domain: str = "",
    *,
    max_results: int = 60,
    max_stretch_results: int = 40,
) -> list[dict]:
    """Read a public Jobvite board and recheck India CSE rows via JobPosting.

    Jobvite boards render their complete public listing as category tables.
    Only India technical rows receive same-host detail requests. The detail must
    retain the board ID/title and a public JobPosting node; application forms,
    saved-job email flows, candidate profiles, and question endpoints are not
    requested.
    """
    slug = clean_text(slug).lower()
    employer_domain = clean_text(employer_domain).lower()
    max_results = max(1, min(int(max_results), 100))
    max_stretch_results = max(0, min(int(max_stretch_results), max_results))
    if (
        not _JOBVITE_SLUG.fullmatch(slug)
        or (employer_domain and not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", employer_domain))
    ):
        return []
    board_url = f"https://jobs.jobvite.com/{slug}"
    try:
        raw_html = await text_get(board_url, request_headers=_ICIMS_BROWSER_HEADERS)
    except Exception as exc:
        logging.getLogger(__name__).info("jobvite %s unavailable: %s", slug, exc)
        return []
    retained: list[tuple[dict, bool]] = []
    for card in _jobvite_search_cards(raw_html, slug):
        title = card["title"]
        location = card["location"]
        is_early = bool(_WORKDAY_EARLY_TITLE.search(title))
        if (
            not _JOBVITE_INDIA.search(location)
            or not _ORACLEHCM_TECHNICAL.search(title)
            or _ORACLEHCM_SENIOR_TITLE.search(title)
        ):
            continue
        retained.append((card, is_early))
    retained.sort(key=lambda item: (not item[1], item[0]["id"]))
    early = [item for item in retained if item[1]]
    stretch = [item for item in retained if not item[1]][:max_stretch_results]
    selected = [*early, *stretch][:max_results]
    semaphore = asyncio.Semaphore(4)

    async def project(item: tuple[dict, bool]) -> dict | None:
        card, is_early = item
        try:
            async with semaphore:
                detail_html = await text_get(
                    card["url"], request_headers=_ICIMS_BROWSER_HEADERS,
                )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {404, 410}:
                return None
            raise
        if re.search(r"job listing no longer exists", detail_html, re.I):
            return None
        schema = _eightfold_job_schema(detail_html)
        if not schema:
            return None
        title = clean_text(str(schema.get("title") or ""))
        identifier = _jobvite_identifier(schema)
        if title.casefold() != card["title"].casefold() or identifier != card["id"]:
            return None
        structured_locations = _jobvite_schema_locations(schema)
        public_locations = [row for _label, row in structured_locations]
        india_locations = [
            (label, row) for label, row in structured_locations
            if re.search(
                r"\bIndia\b|^IN$", str(row.get("address_country") or ""), re.I,
            )
        ]
        # Structured country data is authoritative. Only fall back to the board
        # label when the employer published no structured locations at all.
        if public_locations and not india_locations:
            return None
        if not public_locations and not _JOBVITE_INDIA.search(card["location"]):
            return None
        india_labels = [label for label, _row in india_locations if label]
        location = "; ".join(india_labels) or card["location"]
        job_location_type = clean_text(str(schema.get("jobLocationType") or ""))
        workplace_signal = f"{job_location_type} {card['location']}"
        workplace = (
            "hybrid" if re.search(r"\bhybrid\b", workplace_signal, re.I)
            else "remote" if re.search(r"\b(remote|telecommut|home.?based)\b", workplace_signal, re.I)
            else "onsite"
        )
        organization = schema.get("hiringOrganization")
        if isinstance(organization, dict):
            company = clean_text(str(organization.get("name") or slug))
            employer_same_as = clean_text(str(organization.get("sameAs") or ""))
        else:
            company = clean_text(str(organization or "")) or " ".join(
                part.capitalize() for part in slug.split("-") if part
            )
            employer_same_as = ""
        apply_url = card["url"]
        for href in re.findall(r"href=[\"']([^\"']+/apply(?:\?[^\"']*)?)[\"']", detail_html, re.I):
            parsed = urlparse(urljoin("https://jobs.jobvite.com", html_lib.unescape(href)))
            if (
                parsed.scheme == "https"
                and parsed.netloc.lower() == "jobs.jobvite.com"
                and parsed.path.rstrip("/") == f"/{slug}/job/{card['id']}/apply"
            ):
                apply_url = parsed.geturl()
                break
        employment_type = schema.get("employmentType")
        employment_values = (
            employment_type if isinstance(employment_type, list) else [employment_type]
        )
        base_salary = schema.get("baseSalary")
        source_meta = {
            "ats": "jobvite",
            "slug": slug,
            "host": "jobs.jobvite.com",
            "id": card["id"],
            "employer_domain": employer_domain,
            "employer_name": company,
            "employer_same_as": employer_same_as,
            "early_career_title": is_early,
            "structured_locations": public_locations,
            "job_location_type": job_location_type,
            "employment_type": [value for value in employment_values if value],
            "industry": schema.get("industry"),
            "base_salary": base_salary if isinstance(base_salary, dict) else {},
            "direct_apply": schema.get("directApply"),
            "date_modified": schema.get("dateModified"),
            "occupational_category": schema.get("occupationalCategory"),
            "experience_requirements": schema.get("experienceRequirements"),
            "education_requirements": schema.get("educationRequirements"),
            "qualifications": schema.get("qualifications"),
            "responsibilities": schema.get("responsibilities"),
            "skills": schema.get("skills"),
            "job_benefits": schema.get("jobBenefits"),
            "incentive_compensation": schema.get("incentiveCompensation"),
            "applicant_location_requirements": schema.get(
                "applicantLocationRequirements"
            ),
            "board_url": board_url,
        }
        source_meta = {
            key: value for key, value in source_meta.items()
            if value not in (None, "", [], {})
        }
        description = strip_html_text(str(schema.get("description") or ""))
        if len(description) < 80:
            return None
        return text_lead({
            "title": title,
            "company": company,
            "url": card["url"],
            "apply_url": apply_url,
            "attribution": board_url,
            "platform": "jobvite",
            "description": "\n".join([
                description, f"Location: {location}", f"Workplace: {workplace}",
            ]),
            "posted_date": str(schema.get("datePosted") or ""),
            "deadline": str(schema.get("validThrough") or ""),
            "location": location,
            "workplace": workplace,
            "active_hint": "active",
            "source_meta": source_meta,
        })

    projected = await asyncio.gather(
        *(project(item) for item in selected), return_exceptions=True,
    )
    for result in projected:
        if isinstance(result, Exception):
            logging.getLogger(__name__).info(
                "jobvite %s detail unavailable: %s", slug, result
            )
    return [lead for lead in projected if isinstance(lead, dict)]


class _SuccessFactorsItemPropParser(HTMLParser):
    """Extract text from outer itemprop spans without truncating nested spans."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: dict[str, str] = {}
        self._name = ""
        self._span_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if self._name:
            if tag.lower() == "span":
                self._span_depth += 1
            elif tag.lower() in {"br", "p", "li", "div", "h1", "h2", "h3"}:
                self._parts.append(" ")
            return
        itemprop = clean_text(str(attrs_dict.get("itemprop") or "")).lower()
        if tag.lower() == "span" and itemprop in {"title", "description"}:
            self._name = itemprop
            self._span_depth = 1
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if not self._name or tag.lower() != "span":
            return
        self._span_depth -= 1
        if self._span_depth == 0:
            self.values[self._name] = clean_text(" ".join(self._parts))
            self._name = ""
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._name:
            self._parts.append(data)


def _successfactors_itemprops(raw_html: str) -> dict[str, str]:
    parser = _SuccessFactorsItemPropParser()
    parser.feed(str(raw_html))
    parser.close()
    return parser.values


def _successfactors_fields(raw_html: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    # Career Site Builder permits tenant JavaScript to contain literal HTML
    # templates. They are not visible job facts and can otherwise consume the
    # first real token in a cross-script regex match.
    visible_html = re.sub(
        r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>",
        " ", str(raw_html), flags=re.I | re.S,
    )
    for match in re.finditer(
        r"<span\b[^>]*class=[\"'][^\"']*joblayouttoken-label[^\"']*[\"']"
        r"[^>]*>(.*?)</span>\s*<span\b[^>]*class=[\"'][^\"']*"
        r"rtltextaligneligible[^\"']*[\"'][^>]*>(.*?)</span>",
        visible_html, re.I | re.S,
    ):
        label = _icims_html_text(match.group(1)).replace("\xa0", " ").rstrip(" :")
        value = _icims_html_text(match.group(2)).replace("\xa0", " ")
        if label and value:
            fields[label] = value
    return fields


def _successfactors_date(value: object, locale: str = "en_GB") -> str:
    text = clean_text(str(value or ""))
    localized = "%m/%d/%Y" if locale == "en_US" else "%d/%m/%Y"
    for pattern in (localized, "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    return text


def _successfactors_values(value: object) -> list[str]:
    rows = value if isinstance(value, list) else [value]
    return list(dict.fromkeys(
        clean_text(str(row)).strip(" ,") for row in rows
        if clean_text(str(row)).strip(" ,")
    ))


def _successfactors_india_locations(value: object) -> list[str]:
    locations = [
        row for row in _successfactors_values(value)
        if re.search(r"(?:^|,\s*)(?:IND|IN|India)\s*$", row, re.I)
    ]
    return [
        re.sub(r",\s*(?:IND|IN)\s*$", ", India", row, flags=re.I)
        for row in locations
    ]


def _successfactors_search_detail_url(
    raw_html: str, site_host: str, expected_title: str,
) -> str:
    """Resolve a branded Career Site Builder result to its canonical job URL.

    Some tenants (including SAP) expose the requisition ID in the documented
    XML feed but use a separate opaque CMS ID in public detail URLs. Their
    server-rendered search accepts the requisition ID and publishes the
    canonical link. Require an exact visible title and exact tenant host so a
    stale or noisy search result cannot be attached to the wrong requisition.
    """
    matches: dict[str, str] = {}
    for match in re.finditer(
        r"<a\b[^>]*href=[\"']([^\"']*/job/[^\"']+)[\"'][^>]*>(.*?)</a>",
        str(raw_html), re.I | re.S,
    ):
        href = html_lib.unescape(match.group(1))
        title = _icims_html_text(match.group(2))
        parsed = urlparse(urljoin(f"https://{site_host}", href))
        if (
            parsed.scheme == "https"
            and parsed.netloc.lower() == site_host
            and parsed.path.startswith("/job/")
            and title.casefold() == expected_title.casefold()
        ):
            matches[parsed.path] = parsed.geturl()
    return next(iter(matches.values())) if len(matches) == 1 else ""


async def scrape_successfactors(
    company_id: str,
    site_host: str,
    locale: str = "en_GB",
    employer_domain: str = "",
    *,
    max_pages_per_query: int = 4,
    max_results: int = 60,
    max_stretch_results: int = 40,
) -> list[dict]:
    """Read a public SuccessFactors Career Site Builder board.

    Search uses the JSON service invoked by the visible public career UI. Only
    bounded India CSE candidates receive exact same-host detail requests. A
    matching title, requisition field, full public description, and visible
    exact apply link are required; candidate, talent-community form, and
    application-question endpoints are never requested.
    """
    company_id = clean_text(company_id).lower()
    site_host = clean_text(site_host).lower().rstrip(".")
    locale = clean_text(locale)
    employer_domain = clean_text(employer_domain).lower()
    max_pages_per_query = max(1, min(int(max_pages_per_query), 8))
    max_results = max(1, min(int(max_results), 100))
    max_stretch_results = max(0, min(int(max_stretch_results), max_results))
    if (
        not _SUCCESSFACTORS_COMPANY.fullmatch(company_id)
        or not _SUCCESSFACTORS_SITE_HOST.fullmatch(site_host)
        or not _SUCCESSFACTORS_LOCALE.fullmatch(locale)
        or (employer_domain and not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", employer_domain))
    ):
        return []

    board_url = f"https://{site_host}/search/"
    search_url = f"https://{site_host}/services/recruiting/v1/jobs"
    candidates: dict[str, tuple[dict, set[str], bool]] = {}
    search_error: Exception | None = None
    try:
        for query in _SUCCESSFACTORS_SEARCHES:
            previous_first_id = ""
            for page in range(max_pages_per_query):
                payload = await json_post(search_url, {
                    "keywords": query,
                    "locale": locale,
                    "location": "India",
                    "pageNumber": page,
                    "sortBy": "recent",
                })
                result_rows = (
                    payload.get("jobSearchResult") if isinstance(payload, dict) else []
                )
                result_rows = result_rows if isinstance(result_rows, list) else []
                rows = [
                    item.get("response") for item in result_rows
                    if isinstance(item, dict) and isinstance(item.get("response"), dict)
                ]
                if not rows:
                    break
                first_id = clean_text(str(rows[0].get("id") or ""))
                if first_id and first_id == previous_first_id:
                    break
                previous_first_id = first_id
                for row in rows:
                    job_id = clean_text(str(row.get("id") or ""))
                    title = clean_text(str(row.get("unifiedStandardTitle") or ""))
                    locations = _successfactors_india_locations(
                        row.get("jobLocationShort")
                    )
                    level = " ".join(_successfactors_values(row.get("filter3")))
                    is_early = bool(
                        _WORKDAY_EARLY_TITLE.search(title)
                        or re.search(r"\b(associate|entry|intern|graduate)\b", level, re.I)
                    )
                    if (
                        not job_id
                        or not title
                        or not locations
                        or not _ORACLEHCM_TECHNICAL.search(title)
                        or _ORACLEHCM_SENIOR_TITLE.search(title)
                    ):
                        continue
                    existing = candidates.get(job_id)
                    if existing:
                        existing[1].add(query)
                        candidates[job_id] = (existing[0], existing[1], existing[2] or is_early)
                    else:
                        candidates[job_id] = (row, {query}, is_early)
                total = int(payload.get("totalJobs") or 0) if isinstance(payload, dict) else 0
                if len(rows) < 10 or (total and (page + 1) * 10 >= total):
                    break
    except Exception as exc:
        search_error = exc

    # Some first-party tenants disable the newer JSON service while retaining
    # SuccessFactors' documented external-job XML feed. Discover only the
    # vendor host explicitly declared in the public page and parse it with
    # defusedxml; never infer or probe data-center hosts.
    if not candidates:
        try:
            from defusedxml import ElementTree as DefusedET

            board_html = await text_get(
                board_url, request_headers=_ICIMS_BROWSER_HEADERS,
            )
            sso_match = re.search(
                r"[\"']ssoUrl[\"']\s*:\s*[\"']https://([^/\"']+)",
                board_html, re.I,
            )
            career_host = clean_text(sso_match.group(1)).lower() if sso_match else ""
            if not _SUCCESSFACTORS_CAREER_HOST.fullmatch(career_host):
                raise ValueError("missing trusted SuccessFactors career host")
            raw_xml = await xml_get(
                f"https://{career_host}/career",
                {
                    "company": _SUCCESSFACTORS_XML_COMPANY_IDS.get(
                        company_id, company_id,
                    ),
                    "career_ns": "job_listing_summary",
                    "rcm_site_locale": locale,
                    "resultType": "XML",
                },
            )
            root = DefusedET.fromstring(raw_xml)
            if root.tag != "Job-Listing":
                raise ValueError("invalid SuccessFactors job feed root")
            for node in root.findall("Job"):
                def node_text(name: str, node=node) -> str:
                    child = node.find(name)
                    return clean_text(child.text or "") if child is not None else ""

                fields: dict[str, str] = {}
                for child in list(node):
                    if not str(child.tag).lower().startswith("filter"):
                        continue
                    label = child.findtext("label") or ""
                    value = child.findtext("value") or ""
                    label = clean_text(label)
                    value = clean_text(value)
                    if label and value:
                        fields[label] = value
                if not re.fullmatch(r"India", fields.get("Country", ""), re.I):
                    continue
                job_id = node_text("ReqId")
                title = node_text("JobTitle")
                city = fields.get("Internal Posting Location") or fields.get("City") or ""
                location = f"{city}, India" if city else "India"
                career_status = fields.get("Career Status") or fields.get("Experience Level") or ""
                work_area = fields.get("Work Area") or fields.get("Job Category") or ""
                is_early = bool(
                    _WORKDAY_EARLY_TITLE.search(title)
                    or re.search(
                        r"\b(graduate|student|intern|entry|associate|vocational)\b",
                        career_status, re.I,
                    )
                )
                if (
                    not job_id
                    or not title
                    or not _ORACLEHCM_TECHNICAL.search(f"{title} {work_area}")
                    or _ORACLEHCM_SENIOR_TITLE.search(title)
                ):
                    continue
                candidates[job_id] = ({
                    "id": job_id,
                    "unifiedStandardTitle": title,
                    "unifiedStandardStart": node_text("Posted-Date"),
                    "jobLocationShort": [location],
                    "filter2": [work_area] if work_area else [],
                    "filter3": [career_status] if career_status else [],
                    "_generation": "xml",
                    "_xml_fields": fields,
                }, {"documented-xml-feed"}, is_early)
        except Exception as exc:
            logging.getLogger(__name__).info(
                "successfactors %s/%s unavailable (json=%s, xml=%s)",
                site_host, company_id, search_error, exc,
            )
            return []

    prioritized = sorted(
        candidates.values(), key=lambda item: str(item[0].get("id") or ""),
    )
    prioritized.sort(
        key=lambda item: _successfactors_date(
            item[0].get("unifiedStandardStart") or "", locale,
        ),
        reverse=True,
    )
    prioritized.sort(key=lambda item: not item[2])
    early = [item for item in prioritized if item[2]]
    stretch = [item for item in prioritized if not item[2]][:max_stretch_results]
    selected = [*early, *stretch][:max_results]
    semaphore = asyncio.Semaphore(4)
    company_name = _SUCCESSFACTORS_COMPANY_NAMES.get(
        company_id,
        " ".join(part.capitalize() for part in re.split(r"[-_]", company_id) if part),
    ) or company_id

    async def project(item: tuple[dict, set[str], bool]) -> dict | None:
        row, queries, is_early = item
        job_id = clean_text(str(row.get("id") or ""))
        title = clean_text(str(row.get("unifiedStandardTitle") or ""))
        published_title_path = html_lib.unescape(clean_text(str(
            row.get("unifiedUrlTitle") or row.get("urlTitle") or ""
        )))
        if (
            not published_title_path
            or len(published_title_path) > 240
            or re.search(r"[/\\?#]", published_title_path)
        ):
            published_title_path = re.sub(
                r"-{2,}", "-", title.replace(" ", "-")
            ).strip("-")
        title_path = quote(published_title_path, safe="%:-_.()")
        detail_url = f"https://{site_host}/job/{title_path}/{job_id}-{locale}"
        try:
            async with semaphore:
                if row.get("_generation") == "xml":
                    mapping_html = await text_get(
                        board_url,
                        {"q": job_id, "locationsearch": "India"},
                        request_headers=_ICIMS_BROWSER_HEADERS,
                    )
                    detail_url = _successfactors_search_detail_url(
                        mapping_html, site_host, title,
                    )
                    if not detail_url:
                        return None
                detail_html = await text_get(
                    detail_url, request_headers=_ICIMS_BROWSER_HEADERS,
                )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {404, 410}:
                return None
            raise
        if re.search(r"job (?:is )?no longer (?:available|posted|exists)", detail_html, re.I):
            return None
        itemprops = _successfactors_itemprops(detail_html)
        fields = _successfactors_fields(detail_html)
        detail_title = clean_text(itemprops.get("title") or fields.get("Job Title") or "")
        detail_id = clean_text(fields.get("Req ID") or fields.get("Requisition ID") or "")
        description = clean_text(itemprops.get("description") or "")
        if (
            detail_title.casefold() != title.casefold()
            or detail_id != job_id
            or len(description) < 80
        ):
            return None
        apply_url = ""
        detail_path_parts = [part for part in urlparse(detail_url).path.split("/") if part]
        canonical_page_id = (
            detail_path_parts[-1]
            if row.get("_generation") == "xml" and detail_path_parts
            else job_id
        )
        for href in re.findall(
            r"href=[\"']([^\"']*?/talentcommunity/apply/\d+/(?:\?[^\"']*)?)[\"']",
            detail_html, re.I,
        ):
            parsed = urlparse(urljoin(f"https://{site_host}", html_lib.unescape(href)))
            query_locale = parse_qs(parsed.query).get("locale", [""])[0]
            if (
                parsed.scheme == "https"
                and parsed.netloc.lower() == site_host
                and parsed.path.rstrip("/") == (
                    f"/talentcommunity/apply/{canonical_page_id}"
                )
                and query_locale == locale
            ):
                apply_url = parsed.geturl()
                break
        if not apply_url:
            return None
        india_locations = _successfactors_india_locations(row.get("jobLocationShort"))
        location = "; ".join(india_locations)
        if not location:
            return None
        workplace_raw = clean_text(fields.get("Work Location Type") or "")
        workplace = (
            "hybrid" if re.search(r"hybrid", workplace_raw, re.I)
            else "remote" if re.search(r"remote|home", workplace_raw, re.I)
            else "onsite"
        )
        source_meta = {
            "ats": "successfactors",
            "slug": company_id,
            "host": site_host,
            "id": job_id,
            "canonical_page_id": canonical_page_id,
            "locale": locale,
            "employer_domain": employer_domain,
            "employer_name": company_name,
            "early_career_title": is_early,
            "matched_queries": sorted(queries),
            "search_locations": _successfactors_values(row.get("jobLocationShort")),
            "india_search_locations": india_locations,
            "location_coordinates": [
                coordinate for coordinate in (
                    row.get("jobLocationShortWithCoordinates") or []
                )
                if isinstance(coordinate, dict)
                and _successfactors_india_locations(coordinate.get("value"))
            ],
            "supported_locales": row.get("supportedLocales"),
            "currency": _successfactors_values(row.get("currency")),
            "job_category": _successfactors_values(row.get("filter2")),
            "experience_level": _successfactors_values(row.get("filter3")),
            "portal_generation": row.get("_generation") or "json",
            "canonical_url_resolved_from_public_search": (
                row.get("_generation") == "xml"
            ),
            "xml_fields": row.get("_xml_fields"),
            "employment_type": fields.get("Employment Type"),
            "work_location_type": workplace_raw,
            "business_unit": fields.get("Business Unit") or fields.get("Segment"),
            "detail_fields": fields,
            "board_url": board_url,
        }
        source_meta = {
            key: value for key, value in source_meta.items()
            if value not in (None, "", [], {})
        }
        facts = [f"{key}: {value}" for key, value in fields.items() if key not in {
            "Job Title", "Req ID", "Requisition ID", "Job Location",
        }]
        return text_lead({
            "title": title,
            "company": company_name,
            "url": detail_url,
            "apply_url": apply_url,
            "attribution": board_url,
            "platform": "successfactors",
            "description": "\n".join([description, *facts]),
            "posted_date": _successfactors_date(
                row.get("unifiedStandardStart"), locale,
            ),
            "deadline": _successfactors_date(
                row.get("unifiedStandardEnd"), locale,
            ),
            "location": location,
            "workplace": workplace,
            "active_hint": "active",
            "source_meta": source_meta,
        })

    projected = await asyncio.gather(
        *(project(item) for item in selected), return_exceptions=True,
    )
    for result in projected:
        if isinstance(result, Exception):
            logging.getLogger(__name__).info(
                "successfactors %s detail unavailable: %s", site_host, result
            )
    return [lead for lead in projected if isinstance(lead, dict)]


async def scrape_jibe(
    client_code: str,
    site_host: str,
    context: str = "careers-home",
    locale: str = "en-us",
    employer_domain: str = "",
    *,
    max_pages: int = 25,
    max_results: int = 60,
    max_stretch_results: int = 40,
) -> list[dict]:
    """Read an employer's public Jibe/iCIMS Attract career API.

    The visible search service supplies full job data, but retained rows are
    re-read through the public locale-specific detail endpoint. Identity,
    India location, searchable/applyable state, and an exact public iCIMS
    application URL are all required before a row is emitted.
    """
    client_code = clean_text(client_code).lower()
    site_host = clean_text(site_host).lower().rstrip(".")
    context = clean_text(context).lower()
    locale = clean_text(locale).lower()
    employer_domain = clean_text(employer_domain).lower()
    max_pages = max(1, min(int(max_pages), 40))
    max_results = max(1, min(int(max_results), 100))
    max_stretch_results = max(0, min(int(max_stretch_results), max_results))
    if (
        not _JIBE_CLIENT.fullmatch(client_code)
        or not _JIBE_HOST.fullmatch(site_host)
        or not _JIBE_CONTEXT.fullmatch(context)
        or not _JIBE_LOCALE.fullmatch(locale)
        or (employer_domain and not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", employer_domain))
    ):
        return []

    api_url = f"https://{site_host}/api/jobs"
    board_url = f"https://{site_host}/{context}/jobs"
    candidates: dict[str, tuple[dict, bool]] = {}
    try:
        for page in range(1, max_pages + 1):
            payload = await json_get(api_url, {"location": "India", "page": page})
            rows = payload.get("jobs") if isinstance(payload, dict) else []
            rows = rows if isinstance(rows, list) else []
            for wrapper in rows:
                row = wrapper.get("data") if isinstance(wrapper, dict) else None
                if not isinstance(row, dict):
                    continue
                job_id = clean_text(str(row.get("req_id") or row.get("slug") or ""))
                title = clean_text(str(row.get("title") or ""))
                country = clean_text(str(row.get("country") or ""))
                description = strip_html_text(str(row.get("description") or ""))
                categories = " ".join(_successfactors_values(
                    row.get("categories") or row.get("category")
                ))
                is_early = bool(_ORACLEHCM_EARLY_TITLE.search(
                    f"{title} {description[:2400]}"
                ))
                if (
                    not job_id
                    or not title
                    or not re.fullmatch(r"India", country, re.I)
                    or not _ORACLEHCM_TECHNICAL.search(f"{title} {categories}")
                    or _ORACLEHCM_SENIOR_TITLE.search(title)
                ):
                    continue
                candidates[job_id] = (row, is_early)
            total = int(payload.get("totalCount") or 0) if isinstance(payload, dict) else 0
            display_limit = 10
            filter_data = payload.get("filter") if isinstance(payload, dict) else None
            if isinstance(filter_data, dict):
                display_limit = max(1, int(filter_data.get("displayLimit") or 10))
            if not rows or len(rows) < display_limit or (total and page * display_limit >= total):
                break
    except Exception as exc:
        logging.getLogger(__name__).info("jibe %s unavailable: %s", site_host, exc)
        return []

    prioritized = sorted(
        candidates.values(),
        key=lambda item: clean_text(str(item[0].get("posted_date") or "")),
        reverse=True,
    )
    early = [item for item in prioritized if item[1]]
    stretch = [item for item in prioritized if not item[1]][:max_stretch_results]
    selected = [*early, *stretch][:max_results]
    semaphore = asyncio.Semaphore(4)
    company_name = _JIBE_COMPANY_NAMES.get(
        client_code,
        " ".join(part.capitalize() for part in re.split(r"[-_]", client_code) if part),
    ) or client_code

    async def project(item: tuple[dict, bool]) -> dict | None:
        summary, is_early = item
        job_id = clean_text(str(summary.get("req_id") or summary.get("slug") or ""))
        language = clean_text(str(summary.get("language") or locale)).lower()
        if not _JIBE_LOCALE.fullmatch(language):
            return None
        detail_url = f"{api_url}/{quote(job_id, safe='')}/{language}"
        try:
            async with semaphore:
                detail = await json_get(detail_url)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {404, 410}:
                return None
            raise
        if not isinstance(detail, dict):
            return None
        title = clean_text(str(detail.get("title") or ""))
        detail_id = clean_text(str(detail.get("req_id") or detail.get("slug") or ""))
        detail_client = clean_text(str(detail.get("client_code") or client_code)).lower()
        description = strip_html_text(str(detail.get("description") or ""))
        if (
            detail_id != job_id
            or title.casefold() != clean_text(str(summary.get("title") or "")).casefold()
            or detail_client != client_code
            or detail.get("internal") is True
            or detail.get("searchable") is not True
            or detail.get("applyable") is not True
            or len(description) < 80
            or not re.fullmatch(r"India", clean_text(str(detail.get("country") or "")), re.I)
        ):
            return None
        apply_url = clean_text(str(detail.get("apply_url") or ""))
        apply_parsed = urlparse(apply_url)
        if (
            apply_parsed.scheme != "https"
            or not _ICIMS_HOST.fullmatch(apply_parsed.netloc.lower())
            or not re.match(rf"^/jobs/{re.escape(job_id)}/(?:login|job)/?$", apply_parsed.path, re.I)
        ):
            return None
        location = clean_text(str(
            detail.get("full_location")
            or ", ".join(filter(None, [
                clean_text(str(detail.get("city") or "")),
                clean_text(str(detail.get("state") or "")),
                clean_text(str(detail.get("country") or "")),
            ]))
        ))
        if not _JOBVITE_INDIA.search(location):
            return None
        location_type = clean_text(str(detail.get("location_type") or ""))
        workplace_signal = f"{location_type} {title} {description[:1200]}"
        workplace = (
            "remote" if re.search(r"\bremote\b|work from home", workplace_signal, re.I)
            else "hybrid" if re.search(r"\bhybrid\b", workplace_signal, re.I)
            else "onsite"
        )
        meta = detail.get("meta_data") if isinstance(detail.get("meta_data"), dict) else {}
        icims = meta.get("icims") if isinstance(meta.get("icims"), dict) else {}
        primary_site = (
            icims.get("primary_posted_site_object")
            if isinstance(icims.get("primary_posted_site_object"), dict) else {}
        )
        google = meta.get("googlejobs") if isinstance(meta.get("googlejobs"), dict) else {}
        derived = google.get("derivedInfo") if isinstance(google.get("derivedInfo"), dict) else {}
        source_meta = {
            "ats": "jibe",
            "slug": client_code,
            "host": site_host,
            "context": context,
            "id": job_id,
            "locale": language,
            "employer_domain": employer_domain,
            "employer_name": company_name,
            "early_career_signal": is_early,
            "location_name": detail.get("location_name"),
            "street_address": detail.get("street_address"),
            "city": detail.get("city"),
            "state": detail.get("state"),
            "country": detail.get("country"),
            "country_code": detail.get("country_code"),
            "postal_code": detail.get("postal_code"),
            "location_type": location_type,
            "latitude": detail.get("latitude"),
            "longitude": detail.get("longitude"),
            "additional_locations": detail.get("additional_locations"),
            "categories": detail.get("categories") or detail.get("category"),
            "department": detail.get("department"),
            "tags": {
                key: detail.get(key) for key in ("tags1", "tags2", "tags3", "tags4")
                if detail.get(key) not in (None, "", [])
            },
            "employment_type": detail.get("employment_type"),
            "qualifications": strip_html_text(str(detail.get("qualifications") or "")),
            "responsibilities": strip_html_text(str(detail.get("responsibilities") or "")),
            "benefits": strip_html_text(str(detail.get("benefits") or "")),
            "hiring_organization": detail.get("hiring_organization"),
            "hiring_organization_logo": detail.get("hiring_organization_logo"),
            "languages": detail.get("languages"),
            "internal": detail.get("internal"),
            "external": detail.get("external"),
            "searchable": detail.get("searchable"),
            "applyable": detail.get("applyable"),
            "linkedin_easy_applyable": detail.get("li_easy_applyable"),
            "ats_code": detail.get("ats_code"),
            "hiring_flow_name": detail.get("hiring_flow_name"),
            "frontline_ai_job": detail.get("isFrontLineAIJob"),
            "update_date": detail.get("update_date"),
            "create_date": detail.get("create_date"),
            "icims_public": icims.get("jps_is_public"),
            "icims_date_updated": icims.get("date_updated"),
            "icims_uuid": icims.get("uuid"),
            "icims_revision": icims.get("revision_int"),
            "primary_posted_site": primary_site,
            "google_job_name": google.get("jobName"),
            "google_job_hash": google.get("jobHash"),
            "google_derived_categories": derived.get("jobCategories"),
            "google_derived_locations": derived.get("locations"),
            "import_id": meta.get("import_id"),
            "import_source": meta.get("import_source"),
            "redirect_on_apply": meta.get("redirectOnApply"),
            "gdpr": meta.get("gdpr"),
            "board_url": board_url,
        }
        source_meta = {
            key: value for key, value in source_meta.items()
            if value not in (None, "", [], {})
        }
        extra_sections = [
            ("Qualifications", source_meta.get("qualifications")),
            ("Responsibilities", source_meta.get("responsibilities")),
            ("Benefits", source_meta.get("benefits")),
        ]
        return text_lead({
            "title": title,
            "company": clean_text(str(detail.get("hiring_organization") or company_name)),
            "url": f"https://{site_host}/{context}/jobs/{job_id}?lang={language}",
            "apply_url": apply_url,
            "attribution": board_url,
            "platform": "jibe",
            "description": "\n".join([
                description,
                *(f"{label}: {value}" for label, value in extra_sections if value),
            ]),
            "posted_date": str(detail.get("posted_date") or ""),
            "updated_at": str(
                detail.get("update_date") or icims.get("date_updated") or meta.get("last_mod") or ""
            ),
            "location": location,
            "workplace": workplace,
            "active_hint": "active",
            "source_meta": source_meta,
        })

    projected = await asyncio.gather(
        *(project(item) for item in selected), return_exceptions=True,
    )
    for result in projected:
        if isinstance(result, Exception):
            logging.getLogger(__name__).info(
                "jibe %s detail unavailable: %s", site_host, result,
            )
    return [lead for lead in projected if isinstance(lead, dict)]


async def scrape_direct_ats_url(url: str) -> list[dict]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    subdomain = host.split(".")[0]
    path = parsed.path.strip("/").split("/")
    if host == "jobs.jobvite.com" and path:
        slug = path[1] if path[0].lower() == "careers" and len(path) > 1 else path[0]
        return await scrape_jobvite(slug)
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
    if "himalayas.app" in host:
        return await scrape_himalayas()
    if "teamtailor.com" in host and subdomain not in {"www", ""}:
        return await scrape_teamtailor(subdomain)
    if "breezy.hr" in host and subdomain not in {"www", ""}:
        return await scrape_breezy(subdomain)
    if "pinpointhq.com" in host and subdomain not in {"www", ""}:
        return await scrape_pinpoint(subdomain)
    if "bamboohr.com" in host and subdomain not in {"www", ""}:
        return await scrape_bamboohr(subdomain)
    if "rippling.com" in host:
        # api.rippling.com/platform/api/ats/v1/board/{slug}/... (the API URL) or
        # ats.rippling.com/{slug}/jobs/... (the human-facing board link).
        if "board" in path:
            idx = path.index("board")
            if idx + 1 < len(path):
                return await scrape_rippling(path[idx + 1])
        elif path and path[0]:
            return await scrape_rippling(path[0])
        return []
    if ("zohorecruit.com" in host or "zohorecruit.in" in host) and subdomain not in {"www", ""}:
        return await scrape_zoho_recruit(subdomain, host.rsplit(".", 1)[-1] or "com")
    if "freshteam.com" in host and subdomain not in {"www", ""}:
        return await scrape_freshteam(subdomain)
    if "keka.com" in host and subdomain not in {"www", ""}:
        return await scrape_keka(subdomain)
    if host.endswith(".avature.net") and re.search(r"/(?:SearchJobs|JobDetail)", parsed.path, re.I):
        portal = re.split(r"/(?:SearchJobs|JobDetail)", parsed.path, maxsplit=1, flags=re.I)[0].strip("/")
        return await scrape_avature(subdomain, host, portal)
    if host.endswith(".icims.com"):
        return await scrape_icims(subdomain, host)
    if host.endswith(".eightfold.ai"):
        query = parse_qs(parsed.query)
        domain = clean_text(str((query.get("domain") or [""])[0]))
        if not domain:
            try:
                page = await text_get(url)
            except Exception:
                page = ""
            match = re.search(r'[\"\']domain[\"\']\s*:\s*[\"\']([^\"\']+)', page, re.I)
            domain = clean_text(match.group(1)) if match else ""
        return await scrape_eightfold(subdomain, host, domain)
    if host.endswith(".oraclecloud.com") and "sites" in path:
        idx = path.index("sites")
        site_number = path[idx + 1] if idx + 1 < len(path) else ""
        if not _ORACLEHCM_SITE.fullmatch(site_number):
            # Public employer links commonly use /sites/jobsearch and redirect
            # to /sites/CX_N. The returned shell also declares data-sitenumber,
            # so direct URLs can resolve without browser automation.
            try:
                page = await text_get(url)
            except Exception:
                page = ""
            match = re.search(
                r"(?:data-)?sitenumber\s*=\s*[\"'](CX_\d+)[\"']",
                page,
                re.I,
            )
            site_number = match.group(1).upper() if match else ""
        return await scrape_oraclehcm(subdomain, host, site_number)
    return []


_WORKDAY_INDIA_CSE_QUERY = "india-cse"
_WORKDAY_CSE_SEARCHES = (
    "intern", "graduate", "campus", "entry level", "software", "machine learning", "data",
)
_WORKDAY_TECHNICAL_TITLE = re.compile(
    r"\b(software|developer|programmer|data (?:engineer|scientist)|machine learning|"
    r"artificial intelligence|\bai\b|\bml\b|cloud|devops|site reliability|sre|"
    r"security|cyber|qa|quality assurance|test (?:automation|development)|embedded|"
    r"firmware|compiler|systems? engineer|platform engineer|backend|frontend|full[ -]?stack|"
    r"android|ios|mobile|research engineer)\b",
    re.I,
)
_WORKDAY_SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|manager|director|architect|head|vice president|vp)\b",
    re.I,
)
_WORKDAY_EARLY_TITLE = re.compile(
    r"\b(intern(?:ship)?|co-?op|new\s*grad(?:uate)?|graduate|campus|fresher|"
    r"entry[ -]?level|junior|associate|engineer\s+(?:i|1)|sde\s*(?:i|1))\b",
    re.I,
)
_WORKDAY_EARLY_FACET = re.compile(
    r"\b(intern|new college graduate|graduate|academic|univ(?:ersity)? employment|university)\b",
    re.I,
)


def _workday_india_facet(facets: object) -> tuple[str, list[str]] | None:
    """Return the tenant-specific location facet parameter/ids for India.

    Workday nests location facets one level deeper than ordinary facets, under
    ``locationMainGroup``.  The identifiers are tenant-specific, so discovering
    them from the live response is safer than maintaining brittle constants.
    """
    matches: list[tuple[str, str, bool]] = []

    def collect(values: object) -> None:
        if not isinstance(values, list):
            return
        for facet in values:
            if not isinstance(facet, dict):
                continue
            parameter = clean_text(str(facet.get("facetParameter") or ""))
            facet_descriptor = clean_text(str(facet.get("descriptor") or ""))
            children = facet.get("values")
            if not isinstance(children, list):
                continue
            for value in children:
                if not isinstance(value, dict):
                    continue
                descriptor = clean_text(str(value.get("descriptor") or ""))
                if (
                    (
                        "location" in parameter.lower()
                        or bool(re.search(r"\b(?:country|location)\b", facet_descriptor, re.I))
                    )
                    and re.search(r"\bindia\b", descriptor, re.I)
                    and value.get("id")
                ):
                    matches.append((
                        parameter,
                        str(value["id"]),
                        descriptor.casefold() == "india",
                    ))
                collect([value])

    collect(facets)
    if not matches:
        return None
    # Prefer a single country-level value where offered. Other tenants expose
    # only city-level values (for example "Bangalore, Karnataka, India"); in
    # that case combine every India value from the first matching dimension.
    preferred_parameter = next(
        (parameter for parameter, _id, exact in matches if exact),
        matches[0][0],
    )
    ids = list(dict.fromkeys(
        facet_id
        for parameter, facet_id, _exact in matches
        if parameter == preferred_parameter
    ))
    return preferred_parameter, ids


def _workday_early_career_facets(facets: object) -> list[tuple[str, list[str]]]:
    """Return employer-authored internship/university facet groups."""
    matches: dict[str, list[str]] = {}

    def collect(values: object) -> None:
        if not isinstance(values, list):
            return
        for facet in values:
            if not isinstance(facet, dict):
                continue
            parameter = clean_text(str(facet.get("facetParameter") or ""))
            children = facet.get("values")
            if not isinstance(children, list):
                continue
            for value in children:
                if not isinstance(value, dict):
                    continue
                descriptor = clean_text(str(value.get("descriptor") or ""))
                if (
                    parameter in {"workerSubType", "jobFamilyGroup", "jobFamily", "jobFamilies"}
                    and _WORKDAY_EARLY_FACET.search(descriptor)
                    and value.get("id")
                ):
                    matches.setdefault(parameter, []).append(str(value["id"]))
                collect([value])

    collect(facets)
    preferred_order = {
        "workerSubType": 0,
        "jobFamilyGroup": 1,
        "jobFamily": 2,
        "jobFamilies": 3,
    }
    return sorted(
        ((parameter, list(dict.fromkeys(ids))) for parameter, ids in matches.items()),
        key=lambda item: preferred_order.get(item[0], 99),
    )


async def _workday_india_cse_postings(
    base: str,
    *,
    page_limit: int = 20,
    max_pages_per_query: int = 3,
    max_details: int = 30,
    max_early_details: int = 60,
) -> list[dict]:
    """Discover a bounded, de-duplicated India/CSE slice of a Workday board."""
    seed = await json_post(f"{base}/jobs", {
        "appliedFacets": {}, "limit": page_limit, "offset": 0, "searchText": "",
    })
    facets = seed.get("facets", []) if isinstance(seed, dict) else []
    facet = _workday_india_facet(facets)
    if not facet:
        return []
    facet_parameter, facet_ids = facet
    applied_facets = {facet_parameter: facet_ids}
    early_candidates: dict[str, dict] = {}
    stretch_candidates: dict[str, dict] = {}

    def retain(rows: object, *, employer_marked_early: bool = False) -> None:
        if not isinstance(rows, list):
            return
        for job in rows:
            if not isinstance(job, dict):
                continue
            title = clean_text(str(job.get("title") or ""))
            path = clean_text(str(job.get("externalPath") or ""))
            early_title = bool(_WORKDAY_EARLY_TITLE.search(title))
            if (
                path
                and (_WORKDAY_TECHNICAL_TITLE.search(title) or early_title)
                and not _WORKDAY_SENIOR_TITLE.search(title)
            ):
                destination = (
                    early_candidates
                    if employer_marked_early or early_title
                    else stretch_candidates
                )
                destination.setdefault(path, job)

    # Workday tenants often expose an authoritative worker subtype or university
    # family even when their fuzzy text search does not put "intern" in titles.
    # Exhaust these small India-only slices first and give them the larger budget.
    for early_parameter, early_ids in _workday_early_career_facets(facets):
        early_applied = {**applied_facets, early_parameter: early_ids}
        for page in range(5):
            offset = page * page_limit
            data = await json_post(f"{base}/jobs", {
                "appliedFacets": early_applied,
                "limit": page_limit,
                "offset": offset,
                "searchText": "",
            })
            if not isinstance(data, dict):
                break
            rows = data.get("jobPostings") or []
            if not isinstance(rows, list) or not rows:
                break
            retain(rows, employer_marked_early=True)
            total = int(data.get("total") or 0)
            if len(rows) < page_limit or offset + page_limit >= total:
                break

    for search_text in _WORKDAY_CSE_SEARCHES:
        for page in range(max_pages_per_query):
            offset = page * page_limit
            data = await json_post(f"{base}/jobs", {
                "appliedFacets": applied_facets,
                "limit": page_limit,
                "offset": offset,
                "searchText": search_text,
            })
            if not isinstance(data, dict):
                break
            rows = data.get("jobPostings") or []
            if not isinstance(rows, list) or not rows:
                break
            retain(rows)
            total = int(data.get("total") or 0)
            if len(rows) < page_limit or offset + page_limit >= total:
                break
    early = list(early_candidates.values())[:max_early_details]
    if not early:
        return list(stretch_candidates.values())[:max_details]
    remaining = max(0, max_early_details - len(early))
    return [*early, *list(stretch_candidates.values())[:min(max_details, remaining)]]


async def scrape_workday(tenant: str, host: str, site: str, query: str = "", limit: int = 20) -> list[dict]:
    """Search one Workday tenant.

    Workday is where the enterprise, consultancy and financial-services roles
    live — the .NET/Java/SQL Server work that Greenhouse-hosted startups never
    post. Unlike every other ATS here it is search-first: the list endpoint
    takes a keyword, so this is the one connector that can be pointed at a
    candidate's actual stack instead of pulling a whole board and filtering.

    The list response carries no description, so each posting is fetched
    individually — capped, because that is one request per job.
    """
    base = f"https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}"
    try:
        if query.strip().lower() == _WORKDAY_INDIA_CSE_QUERY:
            postings = await _workday_india_cse_postings(base, page_limit=min(max(1, limit), 20))
        else:
            data = await json_post(f"{base}/jobs", {
                "appliedFacets": {}, "limit": limit, "offset": 0, "searchText": query,
            })
            postings = data.get("jobPostings", []) if isinstance(data, dict) else []
    except Exception as exc:  # a wrong site slug is a 404/422, not a reason to kill the scan
        logging.getLogger(__name__).info("workday %s/%s unavailable: %s", tenant, site, exc)
        return []

    results = []
    for job in postings:
        if not isinstance(job, dict):
            continue
        path = job.get("externalPath") or ""
        posted = job.get("postedOn") or ""
        location = job.get("locationsText") or ""

        desc = ""
        info: dict = {}
        organization: dict = {}
        if path:
            # Search is POST, but the per-posting detail is a plain GET.
            try:
                detail = await json_get(f"{base}{path}")
            except Exception:
                detail = None
            if isinstance(detail, dict):
                info = detail.get("jobPostingInfo") or {}
                info = info if isinstance(info, dict) else {}
                organization = detail.get("hiringOrganization") or {}
                organization = organization if isinstance(organization, dict) else {}
                desc = strip_html_text(info.get("jobDescription") or "")
                location = info.get("location") or location
                posted = info.get("startDate") or info.get("postedOn") or posted

        additional_locations = info.get("additionalLocations") or []
        locations = [location]
        if isinstance(additional_locations, list):
            locations.extend(str(value) for value in additional_locations)
        location = "; ".join(dict.fromkeys(
            clean_text(value) for value in locations if clean_text(value)
        ))

        can_apply = info.get("canApply")
        is_posted = info.get("posted")
        if can_apply is False or is_posted is False:
            active_hint = "closed"
        elif can_apply is True and is_posted is True:
            active_hint = "active"
        else:
            active_hint = None

        country = info.get("country") or {}
        country = country if isinstance(country, dict) else {}
        requisition_location = info.get("jobRequisitionLocation") or {}
        requisition_location = (
            requisition_location if isinstance(requisition_location, dict) else {}
        )
        requisition_country = requisition_location.get("country") or {}
        requisition_country = (
            requisition_country if isinstance(requisition_country, dict) else {}
        )
        external_url = clean_text(str(info.get("externalUrl") or ""))
        job_url = external_url or f"https://{tenant}.{host}.myworkdayjobs.com/{site}{path}"
        source_meta = {
            "ats": "workday",
            "slug": tenant,
            "site": site,
            "query": query,
            "id": clean_text(str(info.get("jobReqId") or "")),
            "internal_posting_id": clean_text(str(info.get("id") or "")),
            "job_posting_id": clean_text(str(info.get("jobPostingId") or "")),
            "job_posting_site_id": clean_text(str(info.get("jobPostingSiteId") or "")),
            "time_type": clean_text(str(info.get("timeType") or "")),
            "posted_relative": clean_text(str(info.get("postedOn") or job.get("postedOn") or "")),
            "start_date": clean_text(str(info.get("startDate") or "")),
            "additional_locations": (
                [clean_text(str(value)) for value in additional_locations if clean_text(str(value))]
                if isinstance(additional_locations, list) else []
            ),
            "country": clean_text(str(
                country.get("descriptor") or requisition_country.get("descriptor") or ""
            )),
            "country_code": clean_text(str(requisition_country.get("alpha2Code") or "")),
            "can_apply": can_apply,
            "posted": is_posted,
            "hiring_organization": clean_text(str(organization.get("name") or "")),
        }
        source_meta = {
            key: value for key, value in source_meta.items()
            if value not in (None, "", [])
        }

        if location:
            desc = (desc + f"\nLocation: {location}").strip()

        results.append(text_lead({
            "title": info.get("title") or job.get("title", ""),
            "company": tenant,
            "url": job_url,
            "apply_url": job_url,
            "platform": "workday",
            "description": desc,
            "posted_date": posted,
            "location": location,
            "active_hint": active_hint,
            "source_meta": source_meta,
        }))
    return results


async def scrape_target(target: str) -> list[dict]:
    lower = target.lower()
    if lower.startswith("ats:jibe:"):
        # ats:jibe:{client}:{host}:{context}:{locale}[:{employer_domain}]
        parts = target.split(":", 7)[2:]
        if len(parts) < 4:
            return []
        return await scrape_jibe(
            parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip(),
            parts[4].strip() if len(parts) > 4 else "",
        )
    if lower.startswith("ats:successfactors:"):
        # ats:successfactors:{company_id}:{site_host}:{locale}[:{employer_domain}]
        parts = target.split(":", 5)[2:]
        if len(parts) < 3:
            return []
        return await scrape_successfactors(
            parts[0].strip(), parts[1].strip(), parts[2].strip(),
            parts[3].strip() if len(parts) > 3 else "",
        )
    if lower.startswith("ats:jobvite:"):
        # ats:jobvite:{slug}[:{employer_domain}]
        parts = target.split(":", 3)[2:]
        if not parts:
            return []
        return await scrape_jobvite(
            parts[0].strip(), parts[1].strip() if len(parts) > 1 else "",
        )
    if lower.startswith("ats:avature:"):
        # ats:avature:{slug}:{host}:{portal}[:{employer_domain}]
        parts = target.split(":", 6)[2:]
        if len(parts) < 3:
            return []
        employer_domain = parts[3].strip() if len(parts) > 3 else ""
        return await scrape_avature(
            parts[0].strip(), parts[1].strip(), parts[2].strip(), employer_domain,
        )
    if lower.startswith("ats:icims:"):
        # ats:icims:{slug}:{host}[:{employer_domain}]
        parts = target.split(":", 5)[2:]
        if len(parts) < 2:
            return []
        employer_domain = parts[2].strip() if len(parts) > 2 else ""
        return await scrape_icims(
            parts[0].strip(), parts[1].strip(), employer_domain
        )
    if lower.startswith("ats:eightfold:"):
        # ats:eightfold:{slug}:{host}:{domain}
        parts = target.split(":", 5)[2:]
        if len(parts) < 3:
            return []
        return await scrape_eightfold(
            parts[0].strip(), parts[1].strip(), parts[2].strip()
        )
    if lower.startswith("ats:oraclehcm:"):
        # ats:oraclehcm:{slug}:{host}:{site_number}[:{employer_domain}]
        parts = target.split(":", 6)[2:]
        if len(parts) < 3:
            return []
        employer_domain = parts[3].strip() if len(parts) > 3 else ""
        return await scrape_oraclehcm(
            parts[0].strip(), parts[1].strip(), parts[2].strip(), employer_domain
        )
    if lower.startswith("ats:workday:"):
        # ats:workday:{tenant}:{host}:{site}[:{query}]
        parts = target.split(":", 5)[2:]
        if len(parts) < 3:
            return []
        query = parts[3].strip() if len(parts) > 3 else ""
        return await scrape_workday(parts[0].strip(), parts[1].strip(), parts[2].strip(), query)
    if lower.startswith("ats:greenhouse:"):
        return await scrape_greenhouse(target.split(":", 2)[2].strip())
    if lower.startswith("ats:lever:"):
        return await scrape_lever(target.split(":", 2)[2].strip())
    if lower.startswith("ats:ashby:"):
        return await scrape_ashby(target.split(":", 2)[2].strip())
    if lower.startswith("ats:workable:"):
        return await scrape_workable(target.split(":", 2)[2].strip())
    if lower.startswith("ats:smartrecruiters:"):
        parts = target.split(":")
        slug = parts[2].strip() if len(parts) > 2 else ""
        mode = parts[3].strip().lower() if len(parts) > 3 else ""
        if mode == "india-cse":
            return await scrape_smartrecruiters(
                slug,
                country_code="in",
                technical_only=True,
                exclude_senior=True,
            )
        return await scrape_smartrecruiters(slug)
    if lower.startswith("ats:recruitee:"):
        return await scrape_recruitee(target.split(":", 2)[2].strip())
    if lower.startswith("ats:personio:"):
        return await scrape_personio(target.split(":", 2)[2].strip())
    if lower.startswith("ats:himalayas"):
        segment = (
            target.split(":", 2)[2].strip()
            if target.count(":") >= 2
            else "all-india-eligible"
        )
        return await scrape_himalayas(segment)
    if lower.startswith("ats:teamtailor:"):
        return await scrape_teamtailor(target.split(":", 2)[2].strip())
    if lower.startswith("ats:rippling:"):
        return await scrape_rippling(target.split(":", 2)[2].strip())
    if lower.startswith("ats:breezy:"):
        return await scrape_breezy(target.split(":", 2)[2].strip())
    if lower.startswith("ats:pinpoint:"):
        return await scrape_pinpoint(target.split(":", 2)[2].strip())
    if lower.startswith("ats:bamboohr:"):
        return await scrape_bamboohr(target.split(":", 2)[2].strip())
    if lower.startswith("ats:zohorecruit:"):
        parts = target.split(":")
        slug = parts[2].strip() if len(parts) > 2 else ""
        tld = parts[3].strip() if len(parts) > 3 else "com"
        return await scrape_zoho_recruit(slug, tld)
    if lower.startswith("ats:freshteam:"):
        return await scrape_freshteam(target.split(":", 2)[2].strip())
    if lower.startswith("ats:keka:"):
        return await scrape_keka(target.split(":", 2)[2].strip())
    if lower.startswith(("http://", "https://")):
        return await scrape_direct_ats_url(target)
    return []
