#!/usr/bin/env python
"""Discover which Workday career sites actually exist.

Workday URLs are ``{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}``
and none of those three parts is guessable — a wrong host fails to resolve and a
wrong site 404s. Guessing by hand hit 3 of 9. This probes a matrix instead and
writes the survivors to ``workday_seeds.json``, which ``core/company_seeds.py``
loads.

    python scripts/probe_workday.py            # probe the built-in employer list
    python scripts/probe_workday.py --quick    # hosts wd1/wd5 only

Re-run it when boards go stale; employers do migrate tenants.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

# Employers that actually run .NET/SQL Server/enterprise-cloud shops: insurers,
# banks, IT consultancies, healthcare and retail IT. Deliberately NOT the
# Greenhouse startup set — that pool is already covered and carries no .NET.
EMPLOYERS = [
    # insurance + financial services
    "travelers", "progressive", "nationwide", "libertymutual", "allstate",
    "aig", "metlife", "prudential", "fiserv", "discover", "synchrony",
    "ally", "usbank", "pnc", "truist", "regions", "statefarm", "guardianlife",
    # IT consultancies — Avanade is the Microsoft/.NET joint venture
    "avanade", "accenture", "cognizant", "capgemini", "epam", "globant",
    "thoughtworks", "infosys", "wipro", "dxc", "kyndryl", "slalom", "insight",
    # healthcare IT
    "unitedhealthgroup", "cvshealth", "elevancehealth", "centene", "humana",
    # enterprise tech + retail IT
    "nvidia", "salesforce", "adobe", "autodesk", "dell", "hpe", "cisco",
    "intuit", "paypal", "ebay", "target", "lowes", "nordstrom", "kohls",
]

HOSTS = ["wd1", "wd3", "wd5", "wd2", "wd12", "wd103"]
QUICK_HOSTS = ["wd1", "wd5"]

# Site slugs are per-tenant vanity strings; these patterns cover most of them.
SITE_PATTERNS = [
    "External", "external", "EXT", "Careers", "careers",
    "{t}Careers", "{t}_Careers", "{t}External", "{t}_External",
    "External_Career_Site", "ExternalCareerSite", "{t}ExternalCareerSite",
    "{t}JobSite", "Search", "{t}careers", "GlobalCareers",
]

CONCURRENCY = 24
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JustHireMe board probe)",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


async def _try_site(client: httpx.AsyncClient, tenant: str, host: str, site: str) -> dict | None:
    """One probe. A live board answers 200 with a jobPostings array."""
    url = f"https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    try:
        r = await client.post(url, json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""})
    except Exception:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    if not isinstance(data, dict) or "jobPostings" not in data:
        return None
    return {"tenant": tenant, "host": host, "site": site, "total": data.get("total", 0)}


async def probe_employer(client: httpx.AsyncClient, sem: asyncio.Semaphore,
                         tenant: str, hosts: list[str]) -> dict | None:
    """First live (host, site) wins — an employer has one real board."""
    for host in hosts:
        for pattern in SITE_PATTERNS:
            site = pattern.format(t=tenant.capitalize())
            async with sem:
                found = await _try_site(client, tenant, host, site)
            if found:
                return found
    return None


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="probe hosts wd1/wd5 only")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "core" / "workday_seeds.json"))
    args = parser.parse_args()

    hosts = QUICK_HOSTS if args.quick else HOSTS
    sem = asyncio.Semaphore(CONCURRENCY)
    print(f"  probing {len(EMPLOYERS)} employers x {len(hosts)} hosts x {len(SITE_PATTERNS)} sites")

    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=HEADERS) as client:
        results = await asyncio.gather(
            *(probe_employer(client, sem, t, hosts) for t in EMPLOYERS)
        )

    live = [r for r in results if r]
    live.sort(key=lambda r: -r["total"])
    for r in live:
        print(f"  OK  {r['tenant']:20} {r['host']:6} {r['site']:28} {r['total']:6} jobs")

    out = Path(args.out)
    out.write_text(json.dumps(live, indent=2), encoding="utf-8")
    print(f"\n  {len(live)}/{len(EMPLOYERS)} live boards -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
