"""Score every unscored lead with the deterministic CGFE engine (no LLM, no cost).

Leads ingested outside a normal scan land at score 0, and the UI sorts by
score, so they stay invisible until this runs.

    cd backend && uv run python scripts/rescore_unscored.py
"""
import asyncio
import json
import sqlite3
import sys
import time
sys.path.insert(0, '.')
from core.paths import app_data_dir
DB = str(app_data_dir() / 'crm.db')

from core.config import profile_for_discovery  # noqa: E402
from data.sqlite.leads import get_all_leads, update_lead_score  # noqa: E402
from ranking.service import create_ranking_service  # noqa: E402

conn = sqlite3.connect(DB)
prof = json.loads(conn.execute("SELECT val FROM settings WHERE key='profile_snapshot_json'").fetchone()[0])
cfg = {k: v for k, v in conn.execute('SELECT key,val FROM settings')}
prof = profile_for_discovery(prof, cfg)
conn.close()

async def main():
    svc = create_ranking_service()
    leads = [lead for lead in get_all_leads() if int(lead.get('score') or 0) == 0]
    print(f'  unscored leads: {len(leads)}', flush=True)
    done = 0
    t0 = time.time()
    sem = asyncio.Semaphore(12)

    async def one(lead):
        nonlocal done
        async with sem:
            try:
                r = await svc.evaluate_lead(lead, prof, cfg, use_llm=False)
                await asyncio.to_thread(
                    update_lead_score, lead['job_id'], r['score'], r.get('reason', ''),
                    r.get('match_points', []), r.get('gaps', []),
                    preserve_status=True, scored_by=r.get('scored_by', ''),
                )
            except Exception:
                pass
            done += 1
            if done % 400 == 0:
                print(f'    {done}/{len(leads)}  ({time.time()-t0:.0f}s)', flush=True)

    await asyncio.gather(*(one(lead) for lead in leads))
    print(f'  scored {done} in {time.time()-t0:.0f}s', flush=True)

asyncio.run(main())
