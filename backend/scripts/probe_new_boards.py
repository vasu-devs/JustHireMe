#!/usr/bin/env python
"""Discover live Teamtailor / Rippling / Breezy / Pinpoint / BambooHR boards.

Same idea as ``probe_ai_boards.py`` (which covers greenhouse/lever/ashby): guess
company slugs against each platform's public jobs endpoint, keep whatever
answers with real postings. A wrong guess 404s (or comes back empty) harmlessly,
so breadth costs nothing but a request.

    python scripts/probe_new_boards.py             # probe everything
    python scripts/probe_new_boards.py --only breezy

Writes ``core/new_boards.json``; ``run_scrape.py`` reads it the same way it
reads ``ai_boards.json``.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Slugs are each platform's tenant handle -- usually the bare company name, a
# hyphenated variant, or (for Rippling/BambooHR, which are HRIS-first) the name
# of whoever runs payroll through them. Wrong guesses 404 harmlessly.
COMPANIES = {
    # Teamtailor: Nordic/EU-heavy per its own marketing -- Nordic tech, fintech,
    # climate and staffing companies are the heaviest users.
    "teamtailor": [
        "doodle", "epidemicsound", "storytel", "trustpilot", "voi", "northvolt",
        "einride", "tink", "kry", "livi", "deliverect", "vivino", "gorillas",
        "choco", "lunar", "bunq", "zettle", "budbee", "instabox", "budgetbakers",
        "billogram", "fortnox", "younited", "qasa", "hemnet", "kivra", "bynder",
        "mentimeter", "soundtrack", "sinch", "recorded", "detectify", "truecaller",
        "yubico", "epidemic-sound", "flowe", "matsmart", "karma", "toca-boca",
        "king", "mojang", "paradox", "avalanche-studios", "sharpr", "wrknest",
        "getaccept", "funnel", "quinyx", "tictail", "brite", "billecta", "pleo",
        "gelato", "meltwater", "cint", "vipps", "remarkable", "klarna", "trustly",
        "izettle", "bambora", "anyfin", "lendo", "bokio", "visma", "kolonial",
        "oda", "too-good-to-go", "toogoodtogo", "wolt-drive", "yepstr",
        "housingAnywhere", "housinganywhere", "swappie", "wrknest", "bolt",
        "glovo", "delivery-hero", "hellofresh", "flink", "gorillas-io",
        "zencargo", "ovoenergy", "bulb", "octopus-energy", "primer",
        "griffin", "tide-bank", "cleo-ai", "yolt", "vivid-money", "n26",
    ],
    # Rippling doubles as HRIS + ATS, so the tenant slug is whoever's payroll
    # runs through it -- skews US tech/startup rather than any one vertical.
    "rippling": [
        "rippling", "notion", "ramp", "ramp-network", "ro", "lattice", "vanta",
        "webflow", "gusto", "carta", "gem", "attentive", "clearco", "deel",
        "brex", "mercury", "checkr", "papayaglobal", "affirm", "faire", "gopuff",
        "flexport", "samsara", "chime", "opendoor", "gemini", "kraken", "circle",
        "anduril", "shield-ai", "saronic", "modern-treasury", "highspot",
        "figma", "canva", "grammarly", "airtable", "loom", "miro", "clari",
        "outreach", "gong", "drift", "intercom", "amplitude", "mixpanel",
        "segment", "front", "superhuman", "linear", "vercel", "netlify",
    ],
    # Breezy skews small/early-stage startups -- and many boards sit behind
    # AWS WAF's JS challenge (a plain GET gets a 202 empty challenge response,
    # not a 404), so this platform's real hit-rate is expected to be low.
    "breezy": [
        "breezy", "clearbit", "baremetrics", "processstreet", "userlist",
        "hotjar", "olark", "codeship", "wpengine", "carta", "close",
        "convertkit", "buffer", "helpscout", "wistia", "vidyard", "testdouble",
        "clevertech", "toptal", "andela", "turing", "gitlab", "automattic",
        "invisionapp", "zapier", "typeform", "mixmax", "front", "calendly",
        "loom", "airtable", "notion", "figma", "canva", "grammarly",
    ],
    # Pinpoint is UK-recruiting-software-first -- customer base skews UK/EU.
    "pinpoint": [
        "pinpoint", "cazoo", "monzo", "gocardless", "thetradedesk", "depop",
        "freetrade", "octopusenergy", "trainline", "gymshark", "boohoo", "thg",
        "checkout", "wagestream", "wise", "revolut", "starlingbank", "zopa",
        "onfido", "curve", "tide", "cleo", "moneybox", "nutmeg", "plum",
        "chip", "pension-bee", "pensionbee", "farewill", "lendinvest",
        "funding-circle", "fundingcircle", "improbable", "graphcore", "darktrace",
    ],
    # BambooHR is broad SMB HRIS -- generic mid-size tech/services companies.
    "bamboohr": [
        "multiplier", "asana", "freshbooks", "wave", "front", "envato",
        "close", "helpjuice", "unbounce", "hubstaff", "toggl", "typeform",
        "livechat", "flexport", "instawork", "betterup", "headspace", "calm",
        "noom", "oscar", "justworks", "gusto", "rippling", "deel", "remote",
        "papayaglobal", "multiplier-hq", "oyster", "velocity-global",
        "globalization-partners", "gp", "letsdeel", "airbase", "ramp",
        "brex", "mercury", "carta", "pilot", "bench", "gusto-inc",
    ],
}

ENDPOINTS = {
    "teamtailor": "https://{slug}.teamtailor.com/jobs.json",
    "rippling": "https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs",
    "breezy": "https://{slug}.breezy.hr/json",
    "pinpoint": "https://{slug}.pinpointhq.com/postings.json",
    "bamboohr": "https://{slug}.bamboohr.com/jobs/embed2.php",
}

CONCURRENCY = 20
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 (JustHireMe board probe)",
    "Accept": "application/json, text/html;q=0.8, */*;q=0.5",
}

# BambooHR's embed fragment is HTML, not JSON -- each open posting is one
# `bhrPositionID_<id>` list item.
_BAMBOO_JOB_RE = re.compile(r"bhrPositionID_\d+")


def _count(provider: str, r: httpx.Response) -> int:
    if provider == "bamboohr":
        return len(_BAMBOO_JOB_RE.findall(r.text))
    try:
        payload = r.json()
    except ValueError:
        return 0
    if provider in ("rippling", "breezy"):
        return len(payload) if isinstance(payload, list) else 0
    if provider == "teamtailor":
        return len(payload.get("items", [])) if isinstance(payload, dict) else 0
    if provider == "pinpoint":
        return len(payload.get("data", [])) if isinstance(payload, dict) else 0
    return 0


async def probe(client: httpx.AsyncClient, sem: asyncio.Semaphore,
                 provider: str, slug: str) -> dict | None:
    url = ENDPOINTS[provider].format(slug=slug)
    async with sem:
        try:
            r = await client.get(url)
        except Exception:
            return None
    if r.status_code != 200:
        return None
    count = _count(provider, r)
    if count <= 0:
        return None
    return {"provider": provider, "slug": slug, "jobs": count}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=sorted(ENDPOINTS), help="probe one provider")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "core" / "new_boards.json"))
    args = parser.parse_args()

    providers = [args.only] if args.only else list(ENDPOINTS)
    total_slugs = sum(len(COMPANIES[p]) for p in providers)
    sem = asyncio.Semaphore(CONCURRENCY)
    print(f"  probing {total_slugs} (provider, slug) pairs across {len(providers)} platform(s)")

    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=HEADERS) as client:
        results = await asyncio.gather(
            *(probe(client, sem, p, s) for p in providers for s in COMPANIES[p])
        )

    live = [r for r in results if r]
    # Same company guessed for two providers keeps whichever carries more jobs.
    best: dict[str, dict] = {}
    for row in live:
        key = f"{row['provider']}:{row['slug']}"
        current = best.get(key)
        if not current or row["jobs"] > current["jobs"]:
            best[key] = row
    rows = sorted(best.values(), key=lambda r: -r["jobs"])

    for r in rows:
        print(f"  OK  {r['provider']:11} {r['slug']:20} {r['jobs']:5} jobs")

    Path(args.out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\n  {len(rows)}/{total_slugs} live boards, {sum(r['jobs'] for r in rows):,} jobs -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
