from __future__ import annotations

from datetime import datetime, timezone

from discovery.normalizer import clean_text, is_recent
from discovery.sources.common import json_get, text_lead


async def scrape_reddit(raw: str) -> list[dict]:
    parts = raw.split(":", 2)
    subreddit = parts[1].strip("/") if len(parts) >= 2 and parts[1] else "forhire"
    query = parts[2].strip() if len(parts) >= 3 else "hiring job remote"
    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    data = await json_get(url, {
        "q": query,
        "restrict_sr": "1",
        "sort": "new",
        "t": "month",
        "limit": "25",
    })
    if not isinstance(data, dict):
        return []
    results = []
    for child in (data.get("data", {}) or {}).get("children", []):
        post = child.get("data", {}) if isinstance(child, dict) else {}
        created = ""
        if post.get("created_utc"):
            created = datetime.fromtimestamp(float(post["created_utc"]), tz=timezone.utc).isoformat()
        if created and not is_recent(created):
            continue
        text = clean_text("\n".join([post.get("title", ""), post.get("selftext", "")]))
        if len(text) < 40:
            continue
        permalink = post.get("permalink", "")
        results.append(text_lead({
            "title": post.get("title", ""),
            "company": f"u/{post.get('author', 'reddit')}",
            "url": "https://www.reddit.com" + permalink if permalink else post.get("url", ""),
            "platform": "reddit",
            "description": text[:1200],
            "posted_date": created,
            "source_meta": {"source": "reddit", "subreddit": subreddit},
        }, default_kind="job"))
    return results
