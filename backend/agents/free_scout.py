import asyncio
import html
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus, urlparse

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agents.lead_intel import (
    budget_from_text,
    clean_text,
    company_from_url,
    fit_bullets,
    followup_sequence,
    lead_id,
    location_from_text,
    outreach_drafts,
    proof_snippet,
    signal_quality,
    tech_stack_from_text,
    urgency_from_text,
)
from agents.quality_gate import MIN_DEFAULT_QUALITY, attach_quality_metadata, evaluate_lead_quality
from agents.scout import _hn_company_role, _is_recent, _looks_like_hn_job_post, _strip_html_text, classify_job_seniority
from db.client import rank_lead_by_feedback, save_lead, url_exists
from logger import get_logger

_log = get_logger(__name__)

LAST_ERRORS: list[str] = []
LAST_USAGE: dict = {}

DEFAULT_TARGETS = [
    "ats:greenhouse:openai",
    "ats:greenhouse:anthropic",
    "ats:lever:perplexity",
    "github:jobs hiring help wanted",
    "hn:jobs remote hiring",
    "reddit:forhire:hiring job remote",
]

_CONNECTOR_MAX_ITEMS = 60


def split_lines(raw: str | None) -> list[str]:
    out: list[str] = []
    for line in str(raw or "").splitlines():
        line = line.strip().rstrip(",")
        if line and not line.startswith("#"):
            out.append(line)
    return out


def targets_from_settings(raw_targets: str | None, raw_watchlist: str | None) -> list[str]:
    targets = split_lines(raw_targets)
    targets.extend(_ats_targets_from_watchlist(raw_watchlist))
    return targets or DEFAULT_TARGETS


def _dot_get(value, path: str, default=""):
    current = value
    for part in str(path or "").split("."):
        part = part.strip()
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part, default)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if 0 <= idx < len(current) else default
        else:
            return default
    return current


def _parse_json_setting(raw: str | None, fallback):
    text = str(raw or "").strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except Exception as exc:
        LAST_ERRORS.append(f"custom connectors JSON invalid: {exc}")
        return fallback


def _connector_headers(raw_headers: str | None, name: str) -> dict:
    data = _parse_json_setting(raw_headers, {})
    if not isinstance(data, dict):
        return {}
    headers = data.get(name) or data.get("*") or {}
    if not isinstance(headers, dict):
        return {}
    return {str(k): str(v) for k, v in headers.items() if str(k).strip() and str(v).strip()}


async def _scrape_custom_connector(connector: dict, raw_headers: str | None = None) -> list[dict]:
    name = str(connector.get("name") or "custom").strip()[:80] or "custom"
    url = str(connector.get("url") or "").strip()
    method = str(connector.get("method") or "GET").upper()
    if method != "GET":
        LAST_ERRORS.append(f"{name}: only GET custom connectors are supported right now")
        return []
    if not url.startswith(("https://", "http://")):
        LAST_ERRORS.append(f"{name}: connector URL must start with http:// or https://")
        return []

    headers = {
        "User-Agent": "JustHireMe custom connector",
        "Accept": "application/json",
        **_connector_headers(raw_headers, name),
    }
    params = connector.get("params") if isinstance(connector.get("params"), dict) else None
    async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as cx:
        r = await cx.get(url, params=params)
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", 15))
            await asyncio.sleep(retry_after)
            r.raise_for_status()
        r.raise_for_status()
        payload = r.json()

    items = _dot_get(payload, str(connector.get("items_path") or ""), payload)
    if isinstance(items, dict):
        items = items.get("items") or items.get("jobs") or items.get("results") or []
    if not isinstance(items, list):
        LAST_ERRORS.append(f"{name}: items_path did not resolve to a list")
        return []

    fields = connector.get("fields") if isinstance(connector.get("fields"), dict) else {}
    defaults = {
        "title": "title",
        "company": "company",
        "url": "url",
        "description": "description",
        "posted_date": "posted_date",
        "location": "location",
        "budget": "budget",
    }
    mapping = {**defaults, **{str(k): str(v) for k, v in fields.items()}}
    results: list[dict] = []
    for item in items[:_CONNECTOR_MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        posted = str(_dot_get(item, mapping.get("posted_date", ""), "") or "")
        if posted and not _is_recent(posted):
            continue
        title = str(_dot_get(item, mapping.get("title", ""), "") or "").strip()
        lead_url = str(_dot_get(item, mapping.get("url", ""), "") or "").strip()
        if not title or not lead_url:
            continue
        desc = clean_text(str(_dot_get(item, mapping.get("description", ""), "") or ""))
        location = str(_dot_get(item, mapping.get("location", ""), "") or "")
        budget = str(_dot_get(item, mapping.get("budget", ""), "") or "")
        if location:
            desc = (desc + f"\nLocation: {location}").strip()
        if budget:
            desc = (desc + f"\nBudget: {budget}").strip()
        results.append(_text_lead({
            "title": title,
            "company": str(_dot_get(item, mapping.get("company", ""), "") or name),
            "url": lead_url,
            "platform": f"connector:{name}",
            "description": desc[:1600],
            "posted_date": posted,
            "location": location,
            "budget": budget,
            "source_meta": {"source": "custom_connector", "connector": name},
        }))
    return results


def _ats_targets_from_watchlist(raw: str | None) -> list[str]:
    targets: list[str] = []
    for line in split_lines(raw):
        parts = [p.strip() for p in re.split(r"[,|]", line) if p.strip()]
        if len(parts) == 1 and parts[0].startswith(("http://", "https://")):
            targets.append(parts[0])
            continue
        if len(parts) < 2:
            continue
        provider = parts[0].lower()
        slug = parts[1]
        if provider in {"greenhouse", "gh"}:
            targets.append(f"ats:greenhouse:{slug}")
        elif provider == "lever":
            targets.append(f"ats:lever:{slug}")
        elif provider == "ashby":
            targets.append(f"ats:ashby:{slug}")
        elif provider == "workable":
            targets.append(f"ats:workable:{slug}")
    return targets


def _text_lead(item: dict, default_kind: str = "job") -> dict:
    text = "\n".join(str(item.get(k, "")) for k in ("title", "company", "description", "url"))
    quality = signal_quality(text, default_kind=default_kind)
    kind = item.get("kind") or quality["kind"]
    budget = item.get("budget") or budget_from_text(text)
    title = item.get("title", "")
    company = item.get("company", "")
    outreach = outreach_drafts(title, company, text, kind, budget)
    stack = item.get("tech_stack") or tech_stack_from_text(text)
    location = item.get("location") or location_from_text(text)
    urgency = item.get("urgency") or urgency_from_text(text)
    meta = dict(item.get("source_meta") or {})
    if stack:
        meta.setdefault("tech_stack", stack)
    if location:
        meta.setdefault("location", location)
    if urgency:
        meta.setdefault("urgency", urgency)
    candidate = {**item, "kind": kind, "description": item.get("description", "")}
    meta.setdefault("seniority_level", classify_job_seniority(candidate))
    return {
        **item,
        "kind": kind,
        "budget": budget,
        "signal_score": quality["score"],
        "signal_reason": quality["reason"],
        "signal_tags": quality["tags"],
        "outreach_reply": outreach["reply"],
        "outreach_dm": outreach["dm"],
        "outreach_email": outreach["email"],
        "proposal_draft": outreach["proposal"],
        "fit_bullets": fit_bullets(title, text),
        "followup_sequence": followup_sequence(company, kind),
        "proof_snippet": proof_snippet(title, text, kind),
        "tech_stack": stack,
        "location": location,
        "urgency": urgency,
        "source_meta": meta,
    }


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
async def _json_get(url: str, params: dict | None = None) -> dict | list:
    headers = {
        "User-Agent": "JustHireMe free-source scout",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as cx:
        r = await cx.get(url, params=params)
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", 15))
            await asyncio.sleep(retry_after)
            r.raise_for_status()
        r.raise_for_status()
        return r.json()


async def _scrape_greenhouse(slug: str) -> list[dict]:
    data = await _json_get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", {"content": "true"})
    results = []
    for job in data.get("jobs", []):
        updated = job.get("updated_at") or ""
        if updated and not _is_recent(updated):
            continue
        desc = _strip_html_text(job.get("content") or "")
        location = ", ".join(
            loc.get("name", "")
            for loc in (job.get("offices") or [])
            if isinstance(loc, dict) and loc.get("name")
        ) or (job.get("location") or {}).get("name", "")
        if location:
            desc = (desc + f"\nLocation: {location}").strip()
        results.append(_text_lead({
            "title": job.get("title", ""),
            "company": slug,
            "url": job.get("absolute_url", ""),
            "platform": "greenhouse",
            "description": desc[:1200],
            "posted_date": updated,
            "source_meta": {"ats": "greenhouse", "slug": slug},
        }))
    return results


async def _scrape_lever(slug: str) -> list[dict]:
    data = await _json_get(f"https://api.lever.co/v0/postings/{slug}", {"mode": "json"})
    results = []
    for job in data if isinstance(data, list) else []:
        created = ""
        if job.get("createdAt"):
            try:
                created = datetime.fromtimestamp(int(job["createdAt"]) / 1000, tz=timezone.utc).isoformat()
            except Exception:
                created = str(job.get("createdAt"))
        if created and not _is_recent(created):
            continue
        parts = [
            job.get("descriptionPlain", ""),
            job.get("additionalPlain", ""),
            " ".join(str(x) for x in (job.get("categories") or {}).values() if x),
        ]
        results.append(_text_lead({
            "title": job.get("text", ""),
            "company": slug,
            "url": job.get("hostedUrl", ""),
            "platform": "lever",
            "description": clean_text("\n".join(parts))[:1200],
            "posted_date": created,
            "source_meta": {"ats": "lever", "slug": slug},
        }))
    return results


async def _scrape_ashby(slug: str) -> list[dict]:
    data = await _json_get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    results = []
    for job in jobs:
        posted = job.get("publishedDate") or job.get("updatedAt") or ""
        if posted and not _is_recent(posted):
            continue
        desc = _strip_html_text(job.get("descriptionHtml") or job.get("descriptionPlain") or "")
        location = job.get("locationName") or ""
        if location:
            desc = (desc + f"\nLocation: {location}").strip()
        url = job.get("jobUrl") or job.get("applyUrl") or f"https://jobs.ashbyhq.com/{slug}/{job.get('id', '')}"
        results.append(_text_lead({
            "title": job.get("title", ""),
            "company": slug,
            "url": url,
            "platform": "ashby",
            "description": desc[:1200],
            "posted_date": posted,
            "source_meta": {"ats": "ashby", "slug": slug},
        }))
    return results


async def _scrape_workable(slug: str) -> list[dict]:
    try:
        data = await _json_get(f"https://www.workable.com/api/accounts/{slug}", {"details": "true"})
    except Exception:
        data = await _json_get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")

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
        if posted and not _is_recent(posted):
            continue
        location_data = job.get("location") or {}
        if isinstance(location_data, dict):
            location = ", ".join(str(x) for x in location_data.values() if x)
        else:
            location = str(location_data or "")
        desc = clean_text("\n".join([
            _strip_html_text(job.get("description") or job.get("full_description") or ""),
            _strip_html_text(job.get("requirements") or ""),
            _strip_html_text(job.get("benefits") or ""),
            f"Location: {location}" if location else "",
        ]))
        code = job.get("shortcode") or job.get("code") or job.get("id") or ""
        url = (
            job.get("url")
            or job.get("application_url")
            or job.get("shortlink")
            or (f"https://apply.workable.com/{slug}/j/{code}/" if code else f"https://apply.workable.com/{slug}/")
        )
        results.append(_text_lead({
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


def _github_query(raw: str) -> str:
    q = raw.split(":", 1)[1].strip() if raw.lower().startswith("github:") else raw.strip()
    base = q or "jobs hiring help wanted"
    return f'is:issue is:open archived:false updated:>={(datetime.now(timezone.utc) - timedelta(days=30)).date()} {base}'


async def _scrape_github(raw: str) -> list[dict]:
    data = await _json_get("https://api.github.com/search/issues", {
        "q": _github_query(raw),
        "sort": "updated",
        "order": "desc",
        "per_page": "25",
    })
    results = []
    for item in data.get("items", []):
        updated = item.get("updated_at", "")
        if updated and not _is_recent(updated):
            continue
        repo_url = (item.get("repository_url") or "").replace("https://api.github.com/repos/", "https://github.com/")
        repo = repo_url.rsplit("/", 2)[-2:] if repo_url else []
        company = "/".join(repo) if repo else company_from_url(item.get("html_url", ""))
        labels = ", ".join(l.get("name", "") for l in (item.get("labels") or []) if isinstance(l, dict))
        desc = clean_text((item.get("body") or "")[:1000])
        if labels:
            desc = (desc + f"\nLabels: {labels}").strip()
        results.append(_text_lead({
            "title": item.get("title", ""),
            "company": company,
            "url": item.get("html_url", ""),
            "platform": "github",
            "description": desc,
            "posted_date": updated,
            "kind": "job",
            "source_meta": {"source": "github", "repo": company},
        }, default_kind="job"))
    return results


async def _scrape_hn(raw: str) -> list[dict]:
    query = raw.split(":", 1)[1].strip() if raw.lower().startswith("hn:") else raw.strip()
    query = query or "jobs remote hiring"
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
    data = await _json_get("https://hn.algolia.com/api/v1/search_by_date", {
        "query": query,
        "tags": "comment",
        "numericFilters": f"created_at_i>{cutoff}",
        "hitsPerPage": "30",
    })
    results = []
    for hit in data.get("hits", []):
        story_title = hit.get("story_title", "")
        if not re.match(r"^Ask HN:\s*Who is hiring\?", story_title or "", flags=re.I):
            continue
        text = _strip_html_text(hit.get("comment_text") or hit.get("story_text") or "")
        if len(text) < 60 or not _looks_like_hn_job_post(text):
            continue
        created = hit.get("created_at", "")
        if created and not _is_recent(created):
            continue
        company, title = _hn_company_role(text, hit.get("author", "HN"))
        url = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        results.append(_text_lead({
            "title": title,
            "company": company or hit.get("author", "HN"),
            "url": url,
            "platform": "hn",
            "description": text[:1200],
            "posted_date": created,
            "source_meta": {"source": "hn", "story": story_title},
        }, default_kind="job"))
    return results


async def _scrape_reddit(raw: str) -> list[dict]:
    parts = raw.split(":", 2)
    subreddit = parts[1].strip("/") if len(parts) >= 2 and parts[1] else "forhire"
    query = parts[2].strip() if len(parts) >= 3 else "hiring job remote"
    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    data = await _json_get(url, {
        "q": query,
        "restrict_sr": "1",
        "sort": "new",
        "t": "month",
        "limit": "25",
    })
    results = []
    for child in (data.get("data", {}) or {}).get("children", []):
        post = child.get("data", {}) if isinstance(child, dict) else {}
        created = ""
        if post.get("created_utc"):
            created = datetime.fromtimestamp(float(post["created_utc"]), tz=timezone.utc).isoformat()
        if created and not _is_recent(created):
            continue
        text = clean_text("\n".join([post.get("title", ""), post.get("selftext", "")]))
        if len(text) < 40:
            continue
        permalink = post.get("permalink", "")
        results.append(_text_lead({
            "title": post.get("title", ""),
            "company": f"u/{post.get('author', 'reddit')}",
            "url": "https://www.reddit.com" + permalink if permalink else post.get("url", ""),
            "platform": "reddit",
            "description": text[:1200],
            "posted_date": created,
            "source_meta": {"source": "reddit", "subreddit": subreddit},
        }, default_kind="job"))
    return results


async def _scrape_direct_ats_url(url: str) -> list[dict]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/").split("/")
    if "greenhouse.io" in host and path:
        slug = path[-1] if "boards.greenhouse.io" in host else path[0]
        return await _scrape_greenhouse(slug)
    if "lever.co" in host and path:
        return await _scrape_lever(path[0])
    if "ashbyhq.com" in host and path:
        return await _scrape_ashby(path[0])
    if "workable.com" in host and path:
        slug = path[0] if path[0] not in {"j", "api"} else ""
        if slug:
            return await _scrape_workable(slug)
    return []


async def _scrape_target(target: str) -> list[dict]:
    lower = target.lower()
    if lower.startswith("ats:greenhouse:"):
        return await _scrape_greenhouse(target.split(":", 2)[2].strip())
    if lower.startswith("ats:lever:"):
        return await _scrape_lever(target.split(":", 2)[2].strip())
    if lower.startswith("ats:ashby:"):
        return await _scrape_ashby(target.split(":", 2)[2].strip())
    if lower.startswith("ats:workable:"):
        return await _scrape_workable(target.split(":", 2)[2].strip())
    if lower.startswith(("http://", "https://")):
        return await _scrape_direct_ats_url(target)
    if lower.startswith("github:"):
        return await _scrape_github(target)
    if lower.startswith("hn:"):
        return await _scrape_hn(target)
    if lower.startswith("reddit:"):
        return await _scrape_reddit(target)
    if lower.startswith("site:github.com"):
        return await _scrape_github(target.replace("site:github.com", "github:", 1))
    return []


def run(
    raw_targets: str | None = None,
    raw_watchlist: str | None = None,
    raw_custom_connectors: str | None = None,
    raw_custom_headers: str | None = None,
    custom_connectors_enabled: bool = False,
    targets: list[str] | None = None,
    kind_filter: str | None = None,
    max_requests: int = 20,
    min_signal_score: int = MIN_DEFAULT_QUALITY,
) -> list[dict]:
    global LAST_ERRORS, LAST_USAGE
    LAST_ERRORS = []
    wanted = "job"
    all_targets = targets or targets_from_settings(raw_targets, raw_watchlist)
    custom_connectors = []
    if custom_connectors_enabled:
        parsed = _parse_json_setting(raw_custom_connectors, [])
        custom_connectors = parsed if isinstance(parsed, list) else []
        if parsed and not isinstance(parsed, list):
            LAST_ERRORS.append("custom connectors must be a JSON array")
    try:
        cap = max(1, min(int(max_requests or 20), 80))
    except Exception:
        cap = 20
    try:
        min_score = max(0, min(int(min_signal_score or 45), 100))
    except Exception:
        min_score = MIN_DEFAULT_QUALITY
    LAST_USAGE = {"configured": len(all_targets) + len(custom_connectors), "executed": 0, "saved": 0, "filtered": 0}
    leads: list[dict] = []
    seen: set[str] = set()

    for target in all_targets[:cap]:
        try:
            batch = asyncio.run(_scrape_target(target))
            LAST_USAGE["executed"] += 1
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            LAST_ERRORS.append(f"{target}: {detail}")
            continue

        for item in batch:
            if wanted and item.get("kind") != wanted:
                LAST_USAGE["filtered"] += 1
                continue
            item = rank_lead_by_feedback(item)
            quality = evaluate_lead_quality(item, min_quality=min_score)
            item = attach_quality_metadata(item, quality)
            if not quality.get("accepted"):
                LAST_USAGE["filtered"] += 1
                LAST_ERRORS.append(f"filtered {item.get('platform', 'free')}:{item.get('url', '')} - {quality.get('reason', 'quality gate')}")
                continue
            if (item.get("signal_score") or 0) < min_score:
                LAST_USAGE["filtered"] += 1
                continue
            url = item.get("url", "")
            if not url:
                continue
            jid = lead_id(item.get("platform", "free"), url)
            if jid in seen or url_exists(jid):
                continue
            seen.add(jid)
            item["job_id"] = jid
            save_lead(
                jid,
                item.get("title", ""),
                item.get("company", ""),
                url,
                item.get("platform", "free"),
                item.get("description", ""),
                kind=item.get("kind", "job"),
                budget=item.get("budget", ""),
                signal_score=item.get("signal_score", 0),
                signal_reason=item.get("signal_reason", ""),
                signal_tags=item.get("signal_tags", []),
                outreach_reply=item.get("outreach_reply", ""),
                outreach_dm=item.get("outreach_dm", ""),
                outreach_email=item.get("outreach_email", ""),
                proposal_draft=item.get("proposal_draft", ""),
                fit_bullets=item.get("fit_bullets", []),
                followup_sequence=item.get("followup_sequence", []),
                proof_snippet=item.get("proof_snippet", ""),
                tech_stack=item.get("tech_stack", []),
                location=item.get("location", ""),
                urgency=item.get("urgency", ""),
                base_signal_score=item.get("base_signal_score"),
                learning_delta=item.get("learning_delta"),
                learning_reason=item.get("learning_reason", ""),
                source_meta=item.get("source_meta", {}),
                seniority_level=(item.get("source_meta") or {}).get("seniority_level", ""),
            )
            LAST_USAGE["saved"] += 1
            leads.append(item)

    remaining = max(0, cap - LAST_USAGE["executed"])
    for connector in custom_connectors[:remaining]:
        if not isinstance(connector, dict):
            LAST_ERRORS.append("custom connector skipped: each connector must be an object")
            continue
        try:
            batch = asyncio.run(_scrape_custom_connector(connector, raw_custom_headers))
            LAST_USAGE["executed"] += 1
        except Exception as exc:
            name = str(connector.get("name") or "custom")
            detail = str(exc).strip() or type(exc).__name__
            LAST_ERRORS.append(f"{name}: {detail}")
            continue

        for item in batch:
            if wanted and item.get("kind") != wanted:
                LAST_USAGE["filtered"] += 1
                continue
            item = rank_lead_by_feedback(item)
            quality = evaluate_lead_quality(item, min_quality=min_score)
            item = attach_quality_metadata(item, quality)
            if not quality.get("accepted"):
                LAST_USAGE["filtered"] += 1
                LAST_ERRORS.append(f"filtered {item.get('platform', 'connector')}:{item.get('url', '')} - {quality.get('reason', 'quality gate')}")
                continue
            if (item.get("signal_score") or 0) < min_score:
                LAST_USAGE["filtered"] += 1
                continue
            url = item.get("url", "")
            if not url:
                continue
            jid = lead_id(item.get("platform", "connector"), url)
            if jid in seen or url_exists(jid):
                continue
            seen.add(jid)
            item["job_id"] = jid
            save_lead(
                jid,
                item.get("title", ""),
                item.get("company", ""),
                url,
                item.get("platform", "connector"),
                item.get("description", ""),
                kind=item.get("kind", "job"),
                budget=item.get("budget", ""),
                signal_score=item.get("signal_score", 0),
                signal_reason=item.get("signal_reason", ""),
                signal_tags=item.get("signal_tags", []),
                outreach_reply=item.get("outreach_reply", ""),
                outreach_dm=item.get("outreach_dm", ""),
                outreach_email=item.get("outreach_email", ""),
                proposal_draft=item.get("proposal_draft", ""),
                fit_bullets=item.get("fit_bullets", []),
                followup_sequence=item.get("followup_sequence", []),
                proof_snippet=item.get("proof_snippet", ""),
                tech_stack=item.get("tech_stack", []),
                location=item.get("location", ""),
                urgency=item.get("urgency", ""),
                base_signal_score=item.get("base_signal_score"),
                learning_delta=item.get("learning_delta"),
                learning_reason=item.get("learning_reason", ""),
                source_meta=item.get("source_meta", {}),
            )
            LAST_USAGE["saved"] += 1
            leads.append(item)

    if len(all_targets) > cap:
        LAST_ERRORS.append(f"Free-source cap hit: ran {cap} of {len(all_targets)} targets")
    if len(custom_connectors) > remaining:
        LAST_ERRORS.append(f"Custom connector cap hit: ran {remaining} of {len(custom_connectors)} connectors")
    return leads
