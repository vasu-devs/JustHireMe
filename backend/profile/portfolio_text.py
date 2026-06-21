"""Pure text/URL/noise helpers for portfolio ingestion.

Stateless string and URL utilities (canonicalization, navigation-noise
detection, whitespace normalization, dedup) shared by the portfolio crawl and
extraction modules. No dependency on the rest of the portfolio package, so it
sits at the base of that subsystem's dependency graph.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse


def _canonical_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", parsed.query, ""))


def _same_origin(root: str, other: str) -> bool:
    a = urlparse(root)
    b = urlparse(other)
    return a.scheme in {"http", "https"} and b.scheme in {"http", "https"} and a.netloc.lower() == b.netloc.lower()


def _looks_like_asset(url: str) -> bool:
    return bool(re.search(r"\.(png|jpe?g|gif|webp|svg|pdf|zip|mp4|mov|css|js|ico)(\?|$)", url, re.I))


# Reference-resource taxonomy: which KIND of off-site link a portfolio anchor is.
# This classifies the *type* of resource (a demo video, a writeup, a live deploy)
# so a project's YouTube demo and case-study link survive instead of being thrown
# away as "not same-origin". It is a generic URL taxonomy, not a per-field list.
_REFERENCE_HOSTS: tuple[tuple[str, str], ...] = (
    # recorded demos / walkthroughs
    ("youtube.com", "video"), ("youtu.be", "video"), ("vimeo.com", "video"),
    ("loom.com", "video"), ("wistia.com", "video"), ("streamable.com", "video"),
    # writeups / case studies / docs
    ("medium.com", "writeup"), ("substack.com", "writeup"), ("dev.to", "writeup"),
    ("hashnode.", "writeup"), ("notion.site", "writeup"), ("notion.so", "writeup"),
    ("docs.google.com", "writeup"), ("drive.google.com", "writeup"),
    ("devpost.com", "writeup"), ("producthunt.com", "writeup"),
    # design artefacts
    ("behance.net", "design"), ("dribbble.com", "design"), ("figma.com", "design"),
    # live deployments
    ("vercel.app", "demo"), ("netlify.app", "demo"), ("github.io", "demo"),
    ("pages.dev", "demo"), ("streamlit.app", "demo"), ("herokuapp.com", "demo"),
    ("fly.dev", "demo"), ("onrender.com", "demo"), ("replit.", "demo"), ("codepen.io", "demo"),
    # source code
    ("github.com", "code"), ("gitlab.com", "code"), ("bitbucket.org", "code"),
    # social / profile
    ("linkedin.com", "social"), ("twitter.com", "social"), ("x.com", "social"),
    ("instagram.com", "social"),
)


def _external_ref_kind(url: str) -> str:
    """Return the resource kind for an off-site link (video / writeup / design /
    demo / code / social), or "" if it is not a recognized reference host."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return ""
    for needle, kind in _REFERENCE_HOSTS:
        if needle in host:
            return kind
    return ""


def _normalize_block_text(value: str) -> str:
    value = re.sub(r"\r", "\n", value or "")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _nav_noise(line: str) -> bool:
    lower = line.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", "", lower)
    if len(lower) <= 2:
        return True
    if _is_concatenated_nav(normalized):
        return True
    if lower in {"home", "about", "projects", "work", "portfolio", "contact", "resume", "blog", "menu", "close"}:
        return True
    return bool(
        len(lower.split()) <= 5
        and re.fullmatch(r"(home|about|projects?|work|contact|resume|blog|services?)(\s+[a-z]+)*", lower)
    )


def _is_concatenated_nav(value: str) -> bool:
    if not value or len(value) > 80:
        return False
    tokens = ("home", "about", "projects", "project", "work", "portfolio", "contact", "resume", "blog", "menu", "github", "linkedin")
    remaining = value
    hits = 0
    while remaining:
        match = next((token for token in tokens if remaining.startswith(token)), "")
        if not match:
            return False
        remaining = remaining[len(match):]
        hits += 1
    return hits >= 2


def _first_match(text: str, pattern: str) -> str:
    match = re.search(pattern, text or "")
    return match.group(0) if match else ""


def _same_key(a: str, b: str) -> bool:
    return re.sub(r"[^a-z0-9]+", "", a.lower()) == re.sub(r"[^a-z0-9]+", "", b.lower())


def _repo_title_from_url(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    return parts[1].replace("-", " ").replace("_", " ").title() if len(parts) >= 2 else ""


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        item = _normalize_block_text(str(value))
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out
