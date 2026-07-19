from __future__ import annotations

from datetime import datetime, timedelta, timezone

from discovery.normalizer import clean_text, company_from_url, is_recent
from discovery.sources.common import json_get, text_lead


def github_query(raw: str) -> str:
    q = raw.split(":", 1)[1].strip() if raw.lower().startswith("github:") else raw.strip()
    base = q or "jobs hiring help wanted"
    since = (datetime.now(timezone.utc) - timedelta(days=30)).date()
    return f"is:issue is:open archived:false updated:>={since} {base}"


_HIRING_SIGNALS = (
    "hiring", "job", "position", "role", "apply", "salary",
    "we're looking", "we are looking",
)
_ISSUE_MARKERS = ("[bug]", "error:", "proposal", "issue")


def looks_like_hiring_issue(title: str, body: str) -> bool:
    """The GitHub search API returns ISSUES; without this gate the source
    surfaces bug reports as leads. Require a hiring signal in title/body and
    reject issue-tracker markers. Strict on purpose: an empty github
    contribution beats a page of bug reports."""
    text = f"{title}\n{body}".lower()
    if any(marker in text for marker in _ISSUE_MARKERS):
        return False
    return any(signal in text for signal in _HIRING_SIGNALS)


async def scrape_github(raw: str) -> list[dict]:
    data = await json_get("https://api.github.com/search/issues", {
        "q": github_query(raw),
        "sort": "updated",
        "order": "desc",
        "per_page": "25",
    })
    if not isinstance(data, dict):
        return []
    results = []
    for item in data.get("items", []):
        if not looks_like_hiring_issue(str(item.get("title") or ""), str(item.get("body") or "")):
            continue
        updated = item.get("updated_at", "")
        if updated and not is_recent(updated):
            continue
        repo_url = (item.get("repository_url") or "").replace("https://api.github.com/repos/", "https://github.com/")
        repo = repo_url.rsplit("/", 2)[-2:] if repo_url else []
        company = "/".join(repo) if repo else company_from_url(item.get("html_url", ""))
        labels = ", ".join(label.get("name", "") for label in (item.get("labels") or []) if isinstance(label, dict))
        desc = clean_text((item.get("body") or "")[:1000])
        if labels:
            desc = (desc + f"\nLabels: {labels}").strip()
        results.append(text_lead({
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
