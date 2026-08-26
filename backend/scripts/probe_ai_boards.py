#!/usr/bin/env python
"""Discover live Greenhouse / Lever / Ashby boards across the AI industry.

The seeded pool was generic tech. This probes the AI sector specifically — labs,
infra, agent/LLM-tooling, devtools and the AI arms of larger companies — because
that is where an applied-AI profile ranks near the top rather than mid-pack.

    python scripts/probe_ai_boards.py             # probe everything
    python scripts/probe_ai_boards.py --only ashby

Writes ``core/ai_boards.json``; ``run_scrape.py --ai`` reads it.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

# Slugs are the company's ATS handle, usually the bare name. Wrong guesses 404
# harmlessly, so breadth costs nothing but a request.
COMPANIES = [
    # labs + foundation models
    "anthropic", "openai", "cohere", "mistralai", "perplexityai", "runwayml",
    "elevenlabs", "stabilityai", "adept", "sakanaai", "luma", "suno",
    # AI infra + serving
    "scaleai", "weightsandbiases", "huggingface", "replicate", "modallabs",
    "togetherai", "anyscale", "fireworksai", "baseten", "lambdalabs",
    "runpod", "deepinfra", "groq", "cerebras", "sambanova",
    # vector / retrieval / data
    "pinecone", "weaviate", "chroma", "qdrant", "llamaindex", "activeloop",
    "unstructured", "vespa", "elastic", "mongodb", "databricks", "snowflake",
    "confluent", "clickhouse", "supabase", "timescale", "percona", "chainguard",
    # NOTE: "neon" (Neon Postgres) deliberately excluded -- verified live: the
    # "neon" slug on both lever and ashby resolves to Neon Pagamentos, an
    # unrelated Brazilian fintech (Portuguese-language postings, Philippines/
    # Malaysia payment-ops roles), not Neon.tech. A slug collision, not a
    # board; Neon Postgres itself merged into Databricks (already probed).
    # agents, LLM tooling, evals, observability
    "langchain", "crewai", "browserbase", "e2b", "cursor", "codeium", "sourcegraph",
    "humanloop", "braintrust", "langfuse", "arizeai", "galileo", "patronusai",
    "hex", "deepgram", "assemblyai", "gladia", "speechmatics",
    "vapi", "livekit", "retellai", "bland", "sierra", "decagon", "parloa",
    # AI-forward product + devtools
    "vercel", "netlify", "railway", "render", "fly", "planetscale", "temporal",
    "linear", "notion", "figma", "airtable", "retool", "zapier", "make",
    "gitlab", "hashicorp", "docker", "grafana", "datadog", "sentry", "postman",
    "twilio", "stripe", "plaid", "ramp", "brex", "mercury", "rippling",
    "deel", "remote", "gusto", "checkr", "persona", "alloy", "oyster",
    # remote-first / globally-distributed employers
    "automattic", "canonical", "doist", "buffer", "hotjar", "aha", "toptal",
    "andela", "turing", "crossover", "zapier", "close", "aircall", "hopin",
    # bigger AI hirers with India presence
    "nvidia", "salesforce", "atlassian", "servicenow", "workato", "freshworks",
    "zoho", "razorpay", "cred", "swiggy", "zomato", "flipkart", "meesho",
    "sprinklr", "browserstack", "hasura", "chargebee", "whatfix", "darwinbox",
    # India startup/GCC breadth: fintech, SaaS, AI, logistics, consumer tech and
    # developer tools. These are guesses against public ATS collection endpoints;
    # a slug is retained only when that endpoint currently returns real postings.
    "hevodata", "netomi", "hyreo", "appfire", "innovaccer", "sumologic",
    "paytm", "groww", "slice", "zeta", "juspay", "cashfree", "pinelabs",
    "pine-labs", "jupiter", "niyo", "smallcase", "zerodha", "upstox",
    "coinswitch", "coindcx", "acko", "digit", "policybazaar", "fi", "epifi",
    "observeai", "yellowai", "yellow-ai", "moengage", "clevertap", "hackerrank",
    "cloudsek", "sprinto", "devrev", "sarvam", "sarvamai", "krutrim",
    "lambdatest", "mindtickle", "facilio", "leadsquared", "skit", "gnani",
    "zepto", "urbancompany", "dream11", "games24x7", "unacademy", "sharechat",
    "inmobi", "glance", "rapido", "porter", "delhivery", "shiprocket", "locus",
    "blackbuck", "ninjacart", "udaan", "curefit", "practo", "pharmeasy",
    "olaelectric", "ola-electric", "scaler", "evaratus", "nirmata", "headout",
    "headoutcareers", "composio", "ema", "outmarket", "merklescience",
]

ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}

CONCURRENCY = 30
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JustHireMe board probe)", "Accept": "application/json"}


def _count(provider: str, payload) -> int:
    if provider == "lever":
        return len(payload) if isinstance(payload, list) else 0
    if not isinstance(payload, dict):
        return 0
    return len(payload.get("jobs", []))


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
    try:
        count = _count(provider, r.json())
    except ValueError:
        return None
    if count <= 0:
        return None
    return {"provider": provider, "slug": slug, "jobs": count}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=sorted(ENDPOINTS), help="probe one provider")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "core" / "ai_boards.json"))
    args = parser.parse_args()

    providers = [args.only] if args.only else list(ENDPOINTS)
    sem = asyncio.Semaphore(CONCURRENCY)
    print(f"  probing {len(COMPANIES)} companies x {len(providers)} providers")

    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=HEADERS) as client:
        results = await asyncio.gather(
            *(probe(client, sem, p, s) for p in providers for s in COMPANIES)
        )

    live = [r for r in results if r]
    # One company can appear on two ATSs (a stale board plus the live one); keep
    # whichever carries more postings.
    best: dict[str, dict] = {}
    for row in live:
        current = best.get(row["slug"])
        if not current or row["jobs"] > current["jobs"]:
            best[row["slug"]] = row
    rows = sorted(best.values(), key=lambda r: -r["jobs"])

    for r in rows:
        print(f"  OK  {r['provider']:11} {r['slug']:20} {r['jobs']:5} jobs")

    Path(args.out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\n  {len(rows)}/{len(COMPANIES)} live boards, {sum(r['jobs'] for r in rows):,} jobs -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
