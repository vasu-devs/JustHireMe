#!/usr/bin/env python
"""Global-remote-aware shortlist -- corrected criterion.

``shortlist.py`` filtered to "remote OR India/APAC location", which was
wrong: the candidate is based in India but does NOT need the company to be
in India or APAC. He needs to work from home, from any country, under any
employment mechanism (direct employee, EOR, contractor/B2B), optimising for
pay. Location requirements on the *company* are irrelevant; what matters is
whether an India-resident could actually be hired into the role.

Every lead is classified into a hireability band from its title/location/
description text:

    A  hire-from-anywhere / worldwide / any-timezone remote
    B  company has an India entity or India office
    C  hires via an EOR (Deel, Remote.com, Oyster, ...) or contractor/B2B
    D  region-locked (US-only, must reside in ..., onsite, hybrid, ...)
    U  no signal either way

Only A/B/C are kept; D and U are excluded (D explicitly, U because we have
no evidence the company would hire an India-resident -- absence of a
positive signal is not treated as a green light). Deterministic regex only,
no LLM calls: this is the cheap pre-filter stage over the whole lead table.

    python scripts/shortlist_global.py                 # top 20, human-readable
    python scripts/shortlist_global.py --top 50
    python scripts/shortlist_global.py --json
    python scripts/shortlist_global.py --db path\\to\\crm.db
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_scrape  # noqa: E402  # sibling script, for resolve_db()
from data.sqlite.leads import get_all_leads  # noqa: E402
# Classifier lives in the business layer (leads.shortlist) so reporting.service
# (the dashboard's "Shortlisted" funnel stage) uses the exact same tested rules
# instead of a second copy that could drift.
from leads.shortlist import band_report, classify_geo, filtered_ranked_leads, is_ai_relevant  # noqa: E402, F401


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-n", "--limit", "--top", dest="limit", type=int, default=20, help="how many to show (default 20)")
    parser.add_argument("--db", default=None, help="database file (defaults to the installed app's)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    db_path = run_scrape.resolve_db(args.db)
    leads = get_all_leads(db_path)
    shortlist = filtered_ranked_leads(leads, limit=args.limit)

    if args.json:
        print(json.dumps({"summary": band_report(leads), "shortlist": shortlist}, ensure_ascii=False, default=str))
        return 0

    report = band_report(leads)
    b = report["bands"]
    kept_total = len(filtered_ranked_leads(leads))
    print(f"\n  {report['total']:,} total leads ({report['live']:,} not discarded/rejected)")
    print(f"  AI/LLM-relevant: {report['ai_relevant']:,}")
    print(f"  Geo bands (all non-discarded leads): A(anywhere)={b['A']} B(india entity)={b['B']} "
          f"C(EOR/contractor)={b['C']} D(region-locked, excluded)={b['D']} U(no signal, excluded)={b['U']}")
    print(f"  Shortlist = AI-relevant AND band in {{A,B,C}}: {kept_total:,} leads\n")

    for i, lead in enumerate(shortlist, 1):
        score = int(lead.get("score") or 0)
        sig = int(lead.get("signal_score") or 0)
        band = lead["geo_band"]
        title = str(lead.get("title") or "?")[:55]
        company = str(lead.get("company") or "?")[:24]
        print(f"  {i:>2}. [{score:>3}/{sig:>3}] ({band}) {title:<55} @ {company:<24} {lead.get('url', '')}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
