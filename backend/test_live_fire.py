"""
Live Fire End-to-End Test
Usage: uv run python test_live_fire.py [JOB_URL] [--submit]

JOB_URL  : Target application form (default: Lever public demo)
--submit : Actually click Submit (omit for dry-run)

Examples:
  uv run python test_live_fire.py
  uv run python test_live_fire.py https://jobs.lever.co/leverdemo/abc123 --submit
"""

import hashlib
import os
import sqlite3
import sys
import time

_DEFAULT_URL = (
    "https://boards.greenhouse.io/embed/job_app"
    "?for=greenhouse&token=4027514002"
)

_RESUME = """
Vasudev Siddh
Software Engineer | Hyderabad, India
vasudev82090@gmail.com | +91-9000000000 | linkedin.com/in/vasudevsiddh

Summary
Full-stack engineer with 4 years of experience building production Python and TypeScript
applications. Specialised in FastAPI microservices, React dashboards, and LLM integrations.

Experience
Senior Software Engineer — Acme Corp (2022–Present)
  Led migration of monolith to FastAPI + LangGraph event-driven pipeline processing 50k req/day.
  Built React (TypeScript) real-time dashboard using WebSockets and Framer Motion.
  Skills used: Python, FastAPI, LangGraph, React, TypeScript, PostgreSQL, Docker.

Software Engineer — Beta Systems (2020–2022)
  Developed REST APIs in Python/Django serving 2M monthly active users.
  Integrated OpenAI and Anthropic APIs for document summarisation product.
  Skills used: Python, Django, Redis, PostgreSQL, OpenAI API.

Projects
JustHireMe — Autonomous job-seeking engine
  Tauri 2.0 + React/TS shell wrapping Python FastAPI sidecar. LangGraph orchestration,
  Kùzu graph DB, LanceDB vector store, Playwright browser automation.
  Stack: Python, Rust, TypeScript, React, FastAPI, LangGraph, Playwright.
  Impact: Fully autonomous pipeline from scouting to submission.

Skills
Python, TypeScript, React, FastAPI, LangGraph, Playwright, Docker, PostgreSQL,
SQLite, REST APIs, WebSockets, Anthropic Claude, LLM integrations, Kùzu, LanceDB,
Tauri, Rust (basic), Git, CI/CD.
"""

_IDENTITY = {
    "name":        "Vasudev Siddh",
    "first_name":  "Vasudev",
    "last_name":   "Siddh",
    "email":       "vasudev82090@gmail.com",
    "phone":       "+919000000000",
    "linkedin_url": "https://linkedin.com/in/vasudevsiddh",
    "website":     "https://github.com/vasudevsiddh",
    "github":      "https://github.com/vasudevsiddh",
}


def _h(u: str) -> str:
    return hashlib.md5(u.encode()).hexdigest()[:16]


def _log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def step(n: int, label: str):
    print(f"\n{'─'*60}", flush=True)
    print(f"  STEP {n}: {label}", flush=True)
    print(f"{'─'*60}", flush=True)


def _audit_trail(jid: str):
    from data.sqlite.connection import DEFAULT_DB_PATH as sql
    c = sqlite3.connect(sql)
    rows = c.execute(
        "SELECT ts, action FROM events WHERE job_id=? ORDER BY ts", (jid,)
    ).fetchall()
    lead = c.execute(
        "SELECT title, company, status FROM leads WHERE job_id=?", (jid,)
    ).fetchone()
    c.close()
    print(f"\n{'═'*60}", flush=True)
    print("  AUDIT TRAIL", flush=True)
    print(f"{'═'*60}", flush=True)
    if lead:
        print(f"  Lead   : {lead[0]} @ {lead[1]}", flush=True)
        print(f"  Status : {lead[2]}", flush=True)
    for ts, action in rows:
        print(f"  {ts}  {action}", flush=True)
    print(f"{'═'*60}\n", flush=True)


def main():
    url      = _DEFAULT_URL
    dry_run  = True
    for arg in sys.argv[1:]:
        if arg == "--submit":
            dry_run = False
        elif arg.startswith("http"):
            url = arg

    mode = "DRY RUN (submit button highlighted but NOT clicked)" if dry_run else "LIVE — WILL SUBMIT"
    print(f"\n{'═'*60}", flush=True)
    print("  JustHireMe Live Fire Test", flush=True)
    print(f"  URL  : {url}", flush=True)
    print(f"  Mode : {mode}", flush=True)
    print(f"{'═'*60}", flush=True)

    jid = _h(url)

    step(1, "Ingest candidate profile into graph DB")
    from profile.ingestor import run as ingest
    _log("Calling Claude to extract profile from resume text…")
    profile = ingest(raw=_RESUME)
    _log(f"Ingested: {profile.n} | skills={len(profile.skills)} exp={len(profile.exp)} projects={len(profile.projects)}")

    step(2, "Insert sandbox lead into SQLite")
    from data.repository import create_repository
    from data.sqlite.connection import DEFAULT_DB_PATH as sql
    repo = create_repository()
    save_lead = repo.leads.save_lead
    url_exists = repo.leads.url_exists
    if url_exists(jid):
        _log(f"Lead {jid} already exists — reusing")
    else:
        save_lead(jid, "Software Engineer (Live Fire Demo)", "Demo Corp", url, "greenhouse")
        _log(f"Inserted lead {jid}")

    step(3, "Evaluate lead (GraphRAG scoring)")
    from ranking.evaluator import score as ev_score
    update_lead_score = repo.leads.update_lead_score
    skills = [sk.n for sk in profile.skills]
    _log(f"Scoring against {len(skills)} skills…")
    result = ev_score(
        f"Software Engineer at Demo Corp — {url}",
        skills,
    )
    _log(f"Score: {result['score']}/100")
    _log(f"Reason: {result['reason'][:120]}…")
    for mp in result["match_points"]:
        _log(f"  ✓ {mp}")

    if result["score"] < 85:
        _log("Score < 85: forcing status to 'tailoring' for test continuity")
    update_lead_score(jid, max(result["score"], 85), result["reason"])

    step(4, "Generate tailored PDF asset")
    from generation.generator import run as gen
    lead_data = {
        "job_id":       jid,
        "title":        "Software Engineer (Live Fire Demo)",
        "company":      "Demo Corp",
        "url":          url,
        "platform":     "greenhouse",
        "skills":       skills,
        "match_points": result["match_points"],
        **_IDENTITY,
    }
    _log("Calling Claude to draft tailored resume + cover letter…")
    asset_path = gen(lead_data)
    _log(f"PDF saved: {asset_path}")

    repo.leads.save_asset_path(jid, asset_path)

    step(5, f"Actuator — {'DRY RUN' if dry_run else 'LIVE SUBMIT'}")
    _log("Launching headed Chromium (500ms delay between fields)…")
    from automation.actuator import run as act
    job_data = {**lead_data, **_IDENTITY}
    ok = act(job_data, asset_path, dry_run=dry_run)

    if dry_run:
        _log("Dry run complete — submit button highlighted in red, browser held open 4s")
        _log(f"Fields filled successfully: {ok}")
    else:
        if ok:
            repo.leads.mark_applied(jid)
            _log("Application SUBMITTED")
        else:
            _log("Submit button not found — application NOT submitted")

    step(6, "Audit trail")
    _audit_trail(jid)

    assert os.path.exists(asset_path), f"PDF not found at {asset_path}"
    _log("✓ PDF exists on disk")

    c = sqlite3.connect(sql)
    ev = c.execute("SELECT COUNT(*) FROM events WHERE job_id=?", (jid,)).fetchone()[0]
    c.close()
    assert ev >= 2, f"Expected ≥2 events, got {ev}"
    _log(f"✓ {ev} events in audit log")

    _log("✓ Live Fire test PASSED")


if __name__ == "__main__":
    main()
