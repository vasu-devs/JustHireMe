#!/usr/bin/env python
"""Ranked shortlist: what watch_jobs.py found, filtered to what's actually
worth reading.

Filters to (a) AI/LLM-relevant roles and (b) remote-global or India/APAC
postings, then ranks the rest by fit score. This is the view meant to be
read every morning -- ``watch_jobs.py`` just fills the funnel; this narrows it.

    python scripts/shortlist.py                 # top 20, human-readable
    python scripts/shortlist.py -n 10            # top 10
    python scripts/shortlist.py --json            # machine-readable
    python scripts/shortlist.py --db path\\to\\crm.db
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_scrape  # noqa: E402  # sibling script, for resolve_db()
from data.sqlite.leads import get_all_leads  # noqa: E402

# Word-boundary-safe AI/LLM relevance signal. Deliberately broad (better a few
# borderline hits in the list than silently dropping a genuine AI role because
# it says "GenAI" instead of "AI").
_AI_RE = re.compile(
    r"\b("
    r"ai|artificial intelligence|machine learning|ml engineer|ml ops|mlops|"
    r"llm|large language model|genai|generative ai|gpt|claude|anthropic|openai|"
    r"langchain|langgraph|rag|retrieval augmented|nlp|natural language|"
    r"chatbot|conversational ai|voice agent|deep learning|neural network|"
    r"data scientist|prompt engineer|agentic|mcp|computer vision"
    r")\b",
    re.IGNORECASE,
)

_REMOTE_RE = re.compile(
    r"\b(remote|anywhere|worldwide|distributed team|work from home|wfh)\b", re.IGNORECASE
)
_APAC_INDIA_RE = re.compile(
    r"\b("
    r"india|indian|bengaluru|bangalore|hyderabad|pune|mumbai|delhi|gurgaon|gurugram|"
    r"noida|chennai|kolkata|apac|asia pacific|singapore|philippines|manila|vietnam|"
    r"hanoi|ho chi minh|indonesia|jakarta|malaysia|kuala lumpur|thailand|bangkok|"
    r"japan|tokyo|korea|seoul|australia|sydney|melbourne|new zealand|hong kong|taiwan"
    r")\b",
    re.IGNORECASE,
)
# Explicit onsite/US-only/negated-remote exclusions win over an incidental
# "remote" mention elsewhere in the same posting (e.g. "no remote work" still
# contains the word "remote", but is the opposite of a remote-friendly posting).
_US_ONLY_RE = re.compile(
    r"\b(us citizens? only|must be (?:based|located) in the u\.?s\.?|"
    r"authorization to work in the united states|no sponsorship.{0,20}visa|"
    r"onsite only|on-site only|in-office only|must relocate to (?!india)|"
    r"no remote|not remote|without remote|remote (?:is|work is) not (?:available|offered|permitted))\b",
    re.IGNORECASE,
)


def _lead_text(lead: dict) -> str:
    return " ".join([
        str(lead.get("title", "")),
        str(lead.get("location", "")),
        str(lead.get("description", ""))[:1500],
    ])


def is_ai_relevant(lead: dict) -> bool:
    return bool(_AI_RE.search(_lead_text(lead)))


def is_geo_relevant(lead: dict) -> bool:
    text = _lead_text(lead)
    if _US_ONLY_RE.search(text):
        return False
    return bool(_REMOTE_RE.search(text) or _APAC_INDIA_RE.search(text))


def filtered_ranked_leads(leads: list[dict], *, limit: int | None = None) -> list[dict]:
    """AI/LLM-relevant AND (remote-global or India/APAC), highest score first.
    Excludes discarded/rejected leads -- they were already ruled out."""
    kept = [
        lead for lead in leads
        if str(lead.get("status") or "") not in {"discarded", "rejected"}
        and is_ai_relevant(lead)
        and is_geo_relevant(lead)
    ]
    kept.sort(key=lambda lead: int(lead.get("score") or 0), reverse=True)
    return kept[:limit] if limit else kept


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-n", "--limit", type=int, default=20, help="how many to show (default 20)")
    parser.add_argument("--db", default=None, help="database file (defaults to the installed app's)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    db_path = run_scrape.resolve_db(args.db)
    leads = get_all_leads(db_path)
    shortlist = filtered_ranked_leads(leads, limit=args.limit)

    if args.json:
        print(json.dumps(shortlist, ensure_ascii=False, default=str))
        return 0

    print(f"\n  {len(shortlist)} of {len(leads):,} leads (AI/LLM-relevant, remote-global or India/APAC)\n")
    for i, lead in enumerate(shortlist, 1):
        score = int(lead.get("score") or 0)
        title = str(lead.get("title") or "?")[:60]
        company = str(lead.get("company") or "?")[:28]
        print(f"  {i:>2}. [{score:>3}] {title:<60} @ {company:<28} {lead.get('url', '')}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
