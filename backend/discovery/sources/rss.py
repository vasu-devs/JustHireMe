from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import defusedxml.ElementTree as ET
import httpx

from discovery.sources.net import guarded_async_client
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from discovery.normalizer import clean_text, is_recent, looks_role_like, strip_html_text
from discovery.sources.common import retry_after_seconds

SOURCE_CAPS = {
    "hn_hiring": 25,
    "hn": 20,
    "remoteok": 45,
    "remotive": 45,
    "jobicy": 45,
    "weworkremotely": 40,
    "rss": 35,
}


def is_rss_target(u: str) -> bool:
    clean = u.lower().split("?", 1)[0].rstrip("/")
    return clean.endswith((".rss", ".xml", "/rss", "/feed"))


def platform_from_url(u: str, fallback: str = "scout") -> str:
    host = urlparse(u).netloc.lower()
    if "remoteok.com" in host:
        return "remoteok"
    if "remotive.com" in host:
        return "remotive"
    if "jobicy.com" in host:
        return "jobicy"
    if "weworkremotely.com" in host:
        return "weworkremotely"
    if "greenhouse.io" in host:
        return "greenhouse"
    if "lever.co" in host:
        return "lever"
    if "ashbyhq.com" in host:
        return "ashby"
    if "workable.com" in host:
        return "workable"
    return fallback


def lead_source(item: dict) -> str:
    platform = str(item.get("platform") or "").strip().lower()
    if platform:
        return platform
    url = str(item.get("url") or "")
    return platform_from_url(url, "scout")


def source_cap(item: dict) -> int:
    return SOURCE_CAPS.get(lead_source(item), 60)


def http_headers(source: str) -> dict:
    return {
        "User-Agent": f"JustHireMe {source} scout",
        "Accept": "application/json, application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7",
    }


def compact(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()


def detail(label: str, value) -> str:
    text = compact(value)
    return f"{label}: {text}" if text else ""


def description(*parts, limit: int = 1600) -> str:
    clean_parts = []
    for part in parts:
        text = strip_html_text(compact(part))
        if text:
            clean_parts.append(text)
    return "\n".join(clean_parts)[:limit].strip()


def salary_from_bounds(low, high, currency: str = "") -> str:
    low_text = compact(low)
    high_text = compact(high)
    if not low_text and not high_text:
        return ""
    prefix = f"{currency} " if currency else ""
    if low_text and high_text:
        return f"{prefix}{low_text}-{high_text}"
    return f"{prefix}{low_text or high_text}"


def feed_entries(root) -> list:
    """Return RSS `<item>` and Atom `<entry>` nodes, namespace-agnostic.

    Many `/feed` and `.xml` targets are Atom feeds; matching only `item`
    silently returned zero leads for them.
    """
    return [
        node
        for node in root.iter()
        if str(node.tag).rsplit("}", 1)[-1].lower() in ("item", "entry")
    ]


def atom_link_href(node) -> str:
    """Atom carries the URL in `<link href=...>` rather than element text."""
    for child in list(node):
        if str(child.tag).rsplit("}", 1)[-1].lower() == "link":
            href = (child.get("href") or "").strip()
            if href:
                return href
    return ""


def xml_text(node, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in list(node):
        local = str(child.tag).rsplit("}", 1)[-1].lower()
        if local in wanted and child.text:
            return child.text.strip()
    return ""


def xml_all_text(node, name: str) -> list[str]:
    wanted = name.lower()
    values: list[str] = []
    for child in list(node):
        local = str(child.tag).rsplit("}", 1)[-1].lower()
        if local == wanted and child.text and child.text.strip():
            values.append(child.text.strip())
    return values


def rss_company_and_role(title: str, platform: str) -> tuple[str, str]:
    clean = strip_html_text(title)
    if not clean:
        return "RSS Feed", ""

    if re.search(r"\s+at\s+", clean, flags=re.I):
        role, company = re.split(r"\s+at\s+", clean, maxsplit=1, flags=re.I)
        return company.strip(" -|:"), role.strip(" -|:")

    if ":" in clean:
        left, right = [part.strip(" -|:") for part in clean.split(":", 1)]
        if platform == "weworkremotely" or looks_role_like(right):
            return left or "RSS Feed", right or clean

    if "|" in clean:
        parts = [part.strip(" -|:") for part in clean.split("|") if part.strip()]
        if len(parts) >= 2:
            if looks_role_like(parts[0]) and not looks_role_like(parts[1]):
                return parts[1], parts[0]
            return parts[0], parts[1]

    return "RSS Feed", clean


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    stop=stop_after_attempt(2),
    reraise=True,
)
async def scrape_rss(u: str) -> list:
    platform = platform_from_url(u, "rss")
    async with guarded_async_client(timeout=30, headers=http_headers(platform), follow_redirects=True) as cx:
        r = await cx.get(u)
        if r.status_code == 429:
            retry_after = retry_after_seconds(r.headers.get("Retry-After"))
            await asyncio.sleep(retry_after)
            r.raise_for_status()
        r.raise_for_status()
        root = ET.fromstring(r.text)

    items = []
    for item in feed_entries(root):
        raw_title = xml_text(item, "title")
        link = xml_text(item, "link", "guid") or atom_link_href(item)
        date_str = xml_text(item, "pubDate", "published", "updated")
        # Match the other adapters: only drop items whose date is present and
        # confirmed stale; undated feed items pass through to the quality gate.
        if date_str and not is_recent(date_str):
            continue
        company, title = rss_company_and_role(raw_title, platform)
        desc = description(
            xml_text(item, "description", "encoded", "summary"),
            detail("Categories", xml_all_text(item, "category")),
            limit=1400,
        )
        items.append({
            "title": title or raw_title,
            "company": company,
            "url": link,
            "platform": platform,
            "description": desc,
            "posted_date": date_str,
            "source_meta": {"source": "rss", "feed": u},
        })
    return items


# UTF-8 bytes read as Windows-1252 leave a telltale lead char (a-circumflex
# U+00E2, A-tilde U+00C3, U+00C2, U+00F0) followed by a char from cp1252's high
# range: U+00E2 U+20AC U+2122 is a mojibake apostrophe, U+00C3 U+00A9 a
# mojibake e-acute.
_MOJIBAKE_RE = re.compile(
    "[\u00c2\u00c3\u00e2\u00f0]"
    "[\u00a0-\u00ff"  # cp1252 0xA0-0xFF map to the same codepoints
    # cp1252 0x80-0x9F map to these scattered punctuation/letter codepoints
    "\u0152\u0153\u0160\u0161\u0178\u017d\u017e\u0192\u02c6\u02dc"
    "\u2018-\u201e\u2020-\u2022\u2013\u2014\u2026\u2030\u2039\u203a\u20ac\u2122]"
)


def _repair_mojibake_once(text: str) -> str:
    encoded = text.encode("cp1252", errors="ignore")
    if len(encoded) != len(text):
        # Every cp1252-encodable char is exactly one byte, so a shorter result
        # means genuine non-cp1252 content (CJK, emoji) the round trip would
        # silently drop — keep the original.
        return text
    try:
        # Strict decode: text that is not ENTIRELY valid UTF-8-read-as-cp1252
        # is not a pure misread. Mixed content ("José" beside real mojibake) or
        # marker lookalikes (Icelandic "Sigurðór" matches the marker regex with
        # no mojibake at all) would lose their real characters under a lenient
        # decode — keep the original instead.
        repaired = encoded.decode("utf-8")
    except UnicodeDecodeError:
        return text
    # ASCII-only count: mojibake chars are themselves alphabetic, so a total-
    # alnum comparison would veto every legitimate repair. Real content the
    # repair must preserve is the ASCII text around the mojibake.
    ascii_alnum = sum(1 for ch in repaired if ch.isascii() and ch.isalnum())
    original_ascii_alnum = sum(1 for ch in text if ch.isascii() and ch.isalnum())
    if not repaired.strip() or ascii_alnum < original_ascii_alnum:
        return text
    return repaired


def repair_mojibake(text: str) -> str:
    """Undo UTF-8-read-as-cp1252 mojibake ("â€™" -> "'", "Ã©" -> "é").

    Only touches text carrying mojibake marker sequences, and keeps the
    original whenever the cp1252 round trip would lose real content. Iterates
    to a fixpoint so double-encoded text repairs fully (and re-running is a
    no-op, which stored-row maintenance relies on).
    """
    if not text:
        return text
    for _ in range(3):
        if not _MOJIBAKE_RE.search(text):
            break
        repaired = _repair_mojibake_once(text)
        if repaired == text:
            break
        text = repaired
    return text


# RemoteOK injects an anti-spam paragraph into every description ("Please
# mention the word **WORD** and tag RMTQ0... when applying to show you read
# the job post ..."). The lookahead ANCHORS on the injection's own markers so
# an employer-authored sentence that happens to start the same way ("please
# mention the word banana and include salary expectations") is never touched;
# the match then runs to the paragraph boundary in raw HTML or cleaned text.
_REMOTEOK_SPAM_RE = re.compile(
    r"please mention the word\b(?=.{0,200}?(?:and tag rmt|to show you read the job post))"
    r".*?(?=\n|</p|<p|$)",
    flags=re.I,
)


def strip_remoteok_noise(text: str) -> str:
    return _REMOTEOK_SPAM_RE.sub("", text or "")


# Role-shaped title patterns beyond the occupation vocabulary: leadership heads
# ("Head of Growth", "VP of Sales"), practice titles by suffix ("Illustrator",
# "Dental Hygienist", "Veterinarian"), and named non-noun roles. Adversarial
# testing showed a strict looks_role_like gate silently dropped 17/47 real
# titles — a false DROP loses a lead forever, a false KEEP just flows on to
# the quality gate, so this tier errs lenient.
_ROLE_HEAD_RE = re.compile(
    r"(?i)\b(head of|vp|vice president|chief|director|lead|manager|master|host|moderator|"
    r"specialist|coordinator|consultant|advisor|analyst|architect|designer|developer|"
    r"engineer|recruiter|writer|editor|producer|hacker|attendant|interpreter)\b"
)
_ROLE_SUFFIX_RE = re.compile(r"(?i)\b\w{4,}(?:ist|ator|ician|arian|grapher|ineer|urse|erapist)s?\b")
_POSTING_SIGNAL_RE = re.compile(r"(?i)\b(hiring|apply|salary|responsibilit\w*|requirement\w*|experience)\b")


def _remoteok_title_ok(title: str, description_text: str) -> bool:
    if looks_role_like(title):
        return True
    if _ROLE_HEAD_RE.search(title) or _ROLE_SUFFIX_RE.search(title):
        return True
    # A title the vocabulary can't classify but whose description reads like a
    # real posting is kept; the quality gate judges the content downstream.
    return bool(_POSTING_SIGNAL_RE.search(description_text or ""))


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    stop=stop_after_attempt(2),
    reraise=True,
)
async def scrape_remoteok() -> list:
    headers = http_headers("remoteok")
    headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    async with httpx.AsyncClient(timeout=30, headers=headers) as cx:
        r = await cx.get("https://remoteok.com/api")
        if r.status_code == 429:
            retry_after = retry_after_seconds(r.headers.get("Retry-After"))
            await asyncio.sleep(retry_after)
            r.raise_for_status()
        r.raise_for_status()
        # RemoteOK's response omits an explicit charset; without forcing UTF-8
        # the body may be decoded as cp1252 and every non-ASCII char arrives
        # as mojibake.
        r.encoding = "utf-8"
        data = r.json()

    results = []
    for j in data:
        if not isinstance(j, dict):
            continue
        title = clean_text(repair_mojibake(str(j.get("position") or "")))
        url = j.get("url", "")
        if not title or not url:
            continue
        # Title hygiene gate: the real feed carries junk titles ("Danny",
        # "Date Posted", "Replace with job title") that are not roles at all.
        if not _remoteok_title_ok(title, str(j.get("description") or "")):
            continue
        epoch = j.get("epoch")
        posted_date = ""
        if epoch:
            posted = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
            if not is_recent(posted.isoformat()):
                continue
            posted_date = posted.isoformat()
        salary = salary_from_bounds(j.get("salary_min"), j.get("salary_max"), "USD")
        desc = description(
            strip_remoteok_noise(repair_mojibake(str(j.get("description") or ""))),
            detail("Location", j.get("location")),
            detail("Tags", j.get("tags")),
            detail("Salary", salary),
            limit=1600,
        )
        results.append({
            "title": title,
            "company": j.get("company", ""),
            "url": url,
            "platform": "remoteok",
            "description": desc,
            "posted_date": posted_date,
            "source_meta": {"source": "remoteok", "tags": j.get("tags") or []},
        })
    return results


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    stop=stop_after_attempt(2),
    reraise=True,
)
async def scrape_remotive(u: str) -> list:
    async with guarded_async_client(timeout=30, headers=http_headers("remotive"), follow_redirects=True) as cx:
        r = await cx.get(u)
        if r.status_code == 429:
            retry_after = retry_after_seconds(r.headers.get("Retry-After"))
            await asyncio.sleep(retry_after)
            r.raise_for_status()
        r.raise_for_status()
        data = r.json()

    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    results = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        posted = job.get("publication_date") or job.get("published_at") or ""
        if posted and not is_recent(str(posted)):
            continue
        title = job.get("title", "")
        company = job.get("company_name", "") or job.get("company", "")
        url = job.get("url", "")
        if not title or not url:
            continue
        desc = description(
            job.get("description", ""),
            detail("Category", job.get("category")),
            detail("Location", job.get("candidate_required_location")),
            detail("Type", job.get("job_type")),
            detail("Salary", job.get("salary")),
            limit=1800,
        )
        results.append({
            "title": title,
            "company": company,
            "url": url,
            "platform": "remotive",
            "description": desc,
            "posted_date": str(posted),
            "source_meta": {
                "source": "remotive",
                "category": job.get("category", ""),
                "location": job.get("candidate_required_location", ""),
            },
        })
    return results


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    stop=stop_after_attempt(2),
    reraise=True,
)
async def scrape_jobicy_api(u: str) -> list:
    async with guarded_async_client(timeout=30, headers=http_headers("jobicy"), follow_redirects=True) as cx:
        r = await cx.get(u)
        if r.status_code == 429:
            retry_after = retry_after_seconds(r.headers.get("Retry-After"))
            await asyncio.sleep(retry_after)
            r.raise_for_status()
        r.raise_for_status()
        data = r.json()

    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    results = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        posted = job.get("pubDate") or job.get("published_at") or job.get("date") or ""
        if posted and not is_recent(str(posted)):
            continue
        title = job.get("jobTitle") or job.get("title") or ""
        company = job.get("companyName") or job.get("company") or ""
        url = job.get("url") or job.get("jobUrl") or ""
        if not title or not url:
            continue
        salary = salary_from_bounds(
            job.get("annualSalaryMin"),
            job.get("annualSalaryMax"),
            job.get("salaryCurrency") or "",
        )
        desc = description(
            job.get("jobDescription") or job.get("jobExcerpt") or job.get("description", ""),
            detail("Industry", job.get("jobIndustry")),
            detail("Location", job.get("jobGeo")),
            detail("Type", job.get("jobType")),
            detail("Level", job.get("jobLevel")),
            detail("Salary", salary),
            limit=1800,
        )
        results.append({
            "title": title,
            "company": company,
            "url": url,
            "platform": "jobicy",
            "description": desc,
            "posted_date": str(posted),
            "source_meta": {
                "source": "jobicy",
                "industry": job.get("jobIndustry", ""),
                "location": job.get("jobGeo", ""),
            },
        })
    return results
