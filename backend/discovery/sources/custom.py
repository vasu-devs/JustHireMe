from __future__ import annotations

import asyncio
import json

from discovery.normalizer import clean_text, is_recent
from discovery.sources.common import text_lead
from discovery.sources.net import guarded_async_client

CONNECTOR_MAX_ITEMS = 60


def dot_get(value, path: str, default=""):
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


def parse_json_setting(raw: str | None, fallback, errors: list[str] | None = None):
    text = str(raw or "").strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except Exception as exc:
        if errors is not None:
            errors.append(f"custom connectors JSON invalid: {exc}")
        return fallback


def connector_headers(raw_headers: str | None, name: str, errors: list[str] | None = None) -> dict:
    data = parse_json_setting(raw_headers, {}, errors)
    if not isinstance(data, dict):
        return {}
    headers = data.get(name) or data.get("*") or {}
    if not isinstance(headers, dict):
        return {}
    return {str(k): str(v) for k, v in headers.items() if str(k).strip() and str(v).strip()}


async def scrape_custom_connector(
    connector: dict,
    raw_headers: str | None = None,
    errors: list[str] | None = None,
) -> list[dict]:
    name = str(connector.get("name") or "custom").strip()[:80] or "custom"
    url = str(connector.get("url") or "").strip()
    method = str(connector.get("method") or "GET").upper()
    if method != "GET":
        if errors is not None:
            errors.append(f"{name}: only GET custom connectors are supported right now")
        return []
    if not url.startswith(("https://", "http://")):
        if errors is not None:
            errors.append(f"{name}: connector URL must start with http:// or https://")
        return []

    headers = {
        "User-Agent": "JustHireMe custom connector",
        "Accept": "application/json",
        **connector_headers(raw_headers, name, errors),
    }
    params = connector.get("params") if isinstance(connector.get("params"), dict) else None
    async with guarded_async_client(timeout=30, headers=headers, follow_redirects=True) as cx:
        r = await cx.get(url, params=params)
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", 15))
            await asyncio.sleep(retry_after)
            r.raise_for_status()
        r.raise_for_status()
        payload = r.json()

    items = dot_get(payload, str(connector.get("items_path") or ""), payload)
    if isinstance(items, dict):
        items = items.get("items") or items.get("jobs") or items.get("results") or []
    if not isinstance(items, list):
        if errors is not None:
            errors.append(f"{name}: items_path did not resolve to a list")
        return []

    fields: dict = connector.get("fields") if isinstance(connector.get("fields"), dict) else {}
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
    for item in items[:CONNECTOR_MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        posted = str(dot_get(item, mapping.get("posted_date", ""), "") or "")
        if posted and not is_recent(posted):
            continue
        title = str(dot_get(item, mapping.get("title", ""), "") or "").strip()
        lead_url = str(dot_get(item, mapping.get("url", ""), "") or "").strip()
        if not title or not lead_url:
            continue
        desc = clean_text(str(dot_get(item, mapping.get("description", ""), "") or ""))
        location = str(dot_get(item, mapping.get("location", ""), "") or "")
        budget = str(dot_get(item, mapping.get("budget", ""), "") or "")
        if location:
            desc = (desc + f"\nLocation: {location}").strip()
        if budget:
            desc = (desc + f"\nBudget: {budget}").strip()
        results.append(text_lead({
            "title": title,
            "company": str(dot_get(item, mapping.get("company", ""), "") or name),
            "url": lead_url,
            "platform": f"connector:{name}",
            "description": desc[:1600],
            "posted_date": posted,
            "location": location,
            "budget": budget,
            "source_meta": {"source": "custom_connector", "connector": name},
        }))
    return results
