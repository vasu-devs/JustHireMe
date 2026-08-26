#!/usr/bin/env python
"""Startup roles with a short application path and a fast decision.

Big-company ATS applications are a lottery with a long queue. These are the
opposite: small teams where a human reads the mail, often the founder, and the
loop is days rather than months.

Ranked on signals that actually predict low hassle:
  - a direct email or founder contact in the posting (no ATS form at all)
  - HN "Who is hiring" / small-board origin rather than an enterprise ATS
  - founding / early / first-engineer framing, i.e. a small team
  - genuinely remote wording
  - recency, because "actively hiring now" is the whole point
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB = Path.home() / "AppData" / "Roaming" / "com.vasudev-siddh.justhireme" / "crm.db"

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
FOUNDING = re.compile(r"\b(founding|early|first (engineer|hire)|employee #|seed|pre-seed|YC[ -]?[WSFX]\d{2})\b", re.I)
DIRECT = re.compile(r"\b(email (us|me)|apply by email|reach out|drop (us|me) a (line|note)|dm |write to)\b", re.I)
REMOTE = re.compile(r"\b(remote|anywhere|worldwide|distributed|work from home)\b", re.I)
AI = re.compile(r"\b(AI|LLM|RAG|agent|MCP|LangGraph|GenAI|machine learning|ML)\b", re.I)
SENIOR_OK = re.compile(r"\b(intern|graduate|new grad|junior|entry.level)\b", re.I)
# Boards where a small team posts directly; enterprise ATSs are the hassle.
LIGHT_PLATFORMS = ("hn_hiring", "hn", "remoteok", "arbeitnow", "weworkremotely", "nodesk", "himalayas")


def main() -> int:
    conn = sqlite3.connect(str(DB))
    rows = conn.execute(
        "SELECT job_id, title, company, url, description, platform, score, verify_status "
        "FROM leads WHERE score > 0"
    ).fetchall()

    scored = []
    for _job_id, title, company, url, desc, platform, score, verified in rows:
        blob = f"{title or ''} {desc or ''}"
        if SENIOR_OK.search(title or ""):
            continue
        if not AI.search(blob):
            continue
        if not REMOTE.search(blob):
            continue

        # Ease score: how little friction stands between him and a human.
        ease = 0
        reasons = []
        emails = [e for e in EMAIL.findall(blob) if not e.endswith((".png", ".jpg"))]
        if emails:
            ease += 40
            reasons.append(f"email: {emails[0]}")
        if DIRECT.search(blob):
            ease += 20
            reasons.append("direct outreach invited")
        if (platform or "") in LIGHT_PLATFORMS:
            ease += 25
            reasons.append(f"{platform} (no ATS)")
        if FOUNDING.search(blob):
            ease += 20
            reasons.append("founding/early team")
        if verified == "CONFIRMED":
            ease += 15
            reasons.append("verified live")

        if ease < 40:
            continue
        scored.append((ease + int(score or 0) // 4, ease, int(score or 0), title, company, url, reasons))

    scored.sort(reverse=True)
    print(f"\n  {len(scored)} low-hassle startup roles (of {len(rows):,} scored)\n")
    for _, ease, score, title, company, url, reasons in scored[:25]:
        print(f"  ease {ease:3} | fit {score:3}  {str(title)[:52]}")
        print(f"     {str(company)[:34]:34} {'; '.join(reasons)[:70]}")
        print(f"     {str(url)[:100]}")
        print()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
