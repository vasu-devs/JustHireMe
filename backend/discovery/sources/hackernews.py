from __future__ import annotations

import re
import asyncio
from datetime import datetime, timedelta, timezone
import html

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from discovery.normalizer import hn_company_role, is_recent, looks_like_hn_job_post, strip_html_text
from discovery.sources.common import json_get, text_lead


def is_hn_hiring_story(story: dict) -> bool:
    title = html.unescape(story.get("title") or story.get("story_title") or "").strip()
    return bool(re.match(r"^Ask HN:\s*Who is hiring\?", title, flags=re.I))


async def scrape_hn(raw: str) -> list[dict]:
    query = raw.split(":", 1)[1].strip() if raw.lower().startswith("hn:") else raw.strip()
    query = query or "jobs remote hiring"
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
    data = await json_get("https://hn.algolia.com/api/v1/search_by_date", {
        "query": query,
        "tags": "comment",
        "numericFilters": f"created_at_i>{cutoff}",
        "hitsPerPage": "30",
    })
    if not isinstance(data, dict):
        return []
    results = []
    for hit in data.get("hits", []):
        story_title = hit.get("story_title", "")
        if not re.match(r"^Ask HN:\s*Who is hiring\?", story_title or "", flags=re.I):
            continue
        text = strip_html_text(hit.get("comment_text") or hit.get("story_text") or "")
        if len(text) < 60 or not looks_like_hn_job_post(text):
            continue
        created = hit.get("created_at", "")
        if created and not is_recent(created):
            continue
        company, title = hn_company_role(text, hit.get("author", "HN"))
        url = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        results.append(text_lead({
            "title": title,
            "company": company or hit.get("author", "HN"),
            "url": url,
            "platform": "hn",
            "description": text[:1200],
            "posted_date": created,
            "source_meta": {"source": "hn", "story": story_title},
        }, default_kind="job"))
    return results


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
async def scrape_hn_hiring() -> list:
    search_url = "https://hn.algolia.com/api/v1/search"
    params = {
        "query": "Ask HN: Who is hiring?",
        "tags": "story,ask_hn",
        "numericFilters": "created_at_i>" + str(int((datetime.now(timezone.utc) - timedelta(days=35)).timestamp())),
    }
    async with httpx.AsyncClient(timeout=30) as cx:
        r = await cx.get(search_url, params=params)
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", 15))
            await asyncio.sleep(retry_after)
            r.raise_for_status()
        r.raise_for_status()
        stories = r.json().get("hits", [])

    stories = [s for s in stories if is_hn_hiring_story(s)]
    if not stories:
        return []

    story = max(stories, key=lambda s: s.get("created_at_i", 0))
    story_id = story["objectID"]

    items_url = f"https://hn.algolia.com/api/v1/items/{story_id}"
    async with httpx.AsyncClient(timeout=60) as cx:
        r = await cx.get(items_url)
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", 15))
            await asyncio.sleep(retry_after)
            r.raise_for_status()
        r.raise_for_status()
        data = r.json()

    results = []
    for child in data.get("children", []):
        text = child.get("text", "")
        if not text or len(text) < 50 or not looks_like_hn_job_post(text):
            continue
        created = child.get("created_at", "")
        if not is_recent(created):
            continue
        author = child.get("author", "")
        hn_url = f"https://news.ycombinator.com/item?id={child.get('id', '')}"

        clean_text = strip_html_text(text)
        company, title = hn_company_role(clean_text, author)
        description = clean_text[:1200]

        results.append({
            "title": title,
            "company": company or author,
            "url": hn_url,
            "platform": "hn_hiring",
            "description": description,
            "posted_date": created,
            "source_meta": {"source": "hn_hiring", "story": story.get("title", "")},
        })

    return results
