"""Lead hygiene: mojibake repair, RemoteOK anti-spam strip, title gates,
boilerplate description rejection, HN role-first parsing, and the stored-row
repair (normalize_stored_leads) â€” regression tests for failure modes measured
in the real stored corpus.

The normalize_stored_leads test runs its real-SQLite assertions in a clean
subprocess (like test_sqlite_settings.py) so the `sqlite3` fake installed by
regression_support in the shared test process can't contaminate it.

Mojibake fixtures are built with chr() so this file stays pure ASCII.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import uuid
from pathlib import Path
from typing import ClassVar
from unittest import mock

from discovery.normalizer import hn_company_role, looks_role_like
from discovery.quality_gate import evaluate_lead_quality, is_boilerplate_description
from discovery.sources import github_jobs, rss

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path(__file__).resolve().parent / ".scratch-lead-hygiene"

# UTF-8 bytes read as cp1252: right single quote and e-acute.
MOJ_APOSTROPHE = chr(0xE2) + chr(0x20AC) + chr(0x2122)
MOJ_E_ACUTE = chr(0xC3) + chr(0xA9)
RIGHT_QUOTE = chr(0x2019)
E_ACUTE = chr(0xE9)

SPAM_BLURB = (
    "Please mention the word **PLEASANTLY** and tag RMTQ0LjIwMy4xNzQuNTM= when applying "
    "to show you read the job post completely. This is a beta feature to avoid spam applicants."
)


# --- mojibake repair ---------------------------------------------------------

def test_repair_mojibake_fixes_cp1252_round_trip():
    assert rss.repair_mojibake("We" + MOJ_APOSTROPHE + "re hiring") == "We" + RIGHT_QUOTE + "re hiring"
    assert rss.repair_mojibake("Telef" + MOJ_E_ACUTE + "nica") == "Telef" + E_ACUTE + "nica"


def test_repair_mojibake_leaves_clean_and_lossy_text_alone():
    assert rss.repair_mojibake("Senior Backend Engineer") == "Senior Backend Engineer"
    # Genuine accented text without mojibake markers is untouched.
    accented = "caf" + E_ACUTE
    assert rss.repair_mojibake(accented) == accented
    # Genuine non-cp1252 content (CJK) would be dropped by the round trip:
    # keep the original even though it carries a marker sequence.
    cjk = chr(0x65E5) + chr(0x672C) + " Engineer " + MOJ_E_ACUTE
    assert rss.repair_mojibake(cjk) == cjk


# --- RemoteOK anti-spam strip ------------------------------------------------

def test_strip_remoteok_noise_removes_antispam_paragraph():
    cleaned_form = "Build APIs.\n" + SPAM_BLURB + "\nLocation: Remote"
    out = rss.strip_remoteok_noise(cleaned_form)
    assert "Please mention" not in out
    assert "Build APIs." in out
    assert "Location: Remote" in out

    html_form = "<p>Build APIs</p><p>" + SPAM_BLURB + "</p><p>Perks and benefits</p>"
    out = rss.strip_remoteok_noise(html_form)
    assert "Please mention" not in out
    assert "Perks and benefits" in out


# --- RemoteOK title gate + description cleanup (source wiring) ---------------

class _FakeRemoteOKResponse:
    status_code = 200
    headers: ClassVar[dict] = {}
    encoding = None

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _fake_async_client(payload):
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            return _FakeRemoteOKResponse(payload)

    return _Client


def test_scrape_remoteok_drops_junk_titles_and_cleans_descriptions():
    payload = [
        {"legal": "notice"},
        {"position": "Danny", "url": "https://remoteok.com/l/1", "company": "X", "description": "text"},
        {"position": "Replace with job title", "url": "https://remoteok.com/l/2", "company": "X", "description": "text"},
        {"position": "CHANGE THE WORLD", "url": "https://remoteok.com/l/3", "company": "X", "description": "text"},
        {
            "position": "Senior Backend Engineer",
            "url": "https://remoteok.com/l/4",
            "company": "Acme",
            "description": "<p>Build APIs in Python.</p><p>" + SPAM_BLURB + "</p>",
        },
        {
            "position": "We" + MOJ_APOSTROPHE + "re hiring: Data Analyst",
            "url": "https://remoteok.com/l/5",
            "company": "Beta",
            "description": "Analyze data.",
        },
    ]
    with mock.patch.object(rss.httpx, "AsyncClient", _fake_async_client(payload)):
        leads = asyncio.run(rss.scrape_remoteok())

    titles = [lead["title"] for lead in leads]
    assert titles == ["Senior Backend Engineer", "We" + RIGHT_QUOTE + "re hiring: Data Analyst"]
    desc = leads[0]["description"]
    assert "Please mention" not in desc
    assert "Build APIs in Python." in desc


# --- boilerplate description rejection ---------------------------------------

def test_boilerplate_description_signatures_rejected():
    for desc in (
        "See this and similar jobs on LinkedIn.",
        "Skip to main content Skip to footer",
        "There are no articles in this category. If subcategories display, they may have articles.",
        "Fill In Job Description Here",
        "Morbi tristique senectus et netus et malesuada fames.",
        "Lorem ipsum dolor sit amet.",
        "Forgotten your password? Request a new one here.",
        # keyboard mash: 42-char alpha run with zero vowels
        "zxcvbnmsdfghjklqwrtypzxcvbnmsdfghjklqwrtyp keyboard mash",
    ):
        assert is_boilerplate_description(desc), desc


def test_real_descriptions_pass_boilerplate_check():
    assert not is_boilerplate_description(
        "Mercy Hospital is hiring an ICU registered nurse for our critical-care "
        "unit. Full-time onsite role. Apply with your nursing license and references."
    )
    assert not is_boilerplate_description("")


def test_quality_gate_zero_scores_boilerplate():
    verdict = evaluate_lead_quality({
        "title": "Software Engineer",
        "company": "Acme",
        "url": "https://example.com/jobs/1",
        "platform": "rss",
        "description": "See this and similar jobs on LinkedIn",
    })
    assert verdict["accepted"] is False
    assert verdict["score"] == 0
    assert "boilerplate" in verdict["reason"]


# --- HN company/role parsing -------------------------------------------------

def test_hn_company_role_role_first_posts():
    # Role-first with only noise after it: the role must not become the company.
    company, title = hn_company_role("Engineering Manager | Remote | Full-time\nWe build developer tools.")
    assert title == "Engineering Manager"
    assert company == ""

    # Role-first with the company in a later segment.
    company, title = hn_company_role("Senior Data Engineer | Acme Robotics | Remote")
    assert (company, title) == ("Acme Robotics", "Senior Data Engineer")


def test_hn_company_role_company_first_unchanged():
    company, title = hn_company_role("Acme AI | Backend Engineer | Remote | Python, FastAPI\nWe are hiring.")
    assert (company, title) == ("Acme AI", "Backend Engineer")

    # A company-only first segment ("AI" is not an occupation noun) must NOT be
    # promoted to the role.
    company, title = hn_company_role("Acme AI | Remote | Python, FastAPI\nWe ship LLM tools.")
    assert company == "Acme AI"
    assert title == "Hiring at Acme AI"


def test_hn_line_scan_rejects_emails_and_fragments():
    text = (
        "AcmeCorp\n"
        "engineer@acme.com\n"
        "we are looking for people to join\n"
        "Backend Engineer\n"
        "Remote friendly"
    )
    company, title = hn_company_role(text)
    assert (company, title) == ("AcmeCorp", "Backend Engineer")

    # No usable role line at all: fall back instead of storing an email.
    company, title = hn_company_role("SomeCo\nhataginow@gmail.com\ncontact us via email")
    assert title == "Hiring at SomeCo"


# --- short role tokens require word boundaries -------------------------------

def test_short_role_tokens_require_word_boundaries():
    assert not looks_role_like("hataginow@gmail.com")
    assert not looks_role_like("html templates")
    assert not looks_role_like("update database")
    assert looks_role_like("AI Engineer")
    assert looks_role_like("ML Ops")
    assert looks_role_like("QA")
    assert looks_role_like("Data Analyst")


# --- GitHub issues source: hiring gate ---------------------------------------

def test_github_hiring_gate():
    assert github_jobs.looks_like_hiring_issue("Hiring: Head Chef", "We are hiring a chef. Apply with portfolio.")
    assert github_jobs.looks_like_hiring_issue("Open position: ML Engineer", "Salary range included.")
    assert not github_jobs.looks_like_hiring_issue("[BUG] crash when saving", "Steps to reproduce the crash")
    assert not github_jobs.looks_like_hiring_issue("error: cannot import module", "Traceback follows")
    assert not github_jobs.looks_like_hiring_issue("Proposal: new plugin API", "Design discussion")
    assert not github_jobs.looks_like_hiring_issue("Weekly sync notes", "Merged PRs and TODOs")


def test_scrape_github_filters_bug_reports():
    payload = {
        "items": [
            {
                "title": "[BUG] scraper crashes on startup",
                "body": "error: stack trace attached",
                "html_url": "https://github.com/a/b/issues/1",
                "updated_at": "",
                "repository_url": "https://api.github.com/repos/a/b",
                "labels": [],
            },
            {
                "title": "Hiring: Backend Engineer (remote)",
                "body": "We are hiring. Apply with CV. Salary listed.",
                "html_url": "https://github.com/c/d/issues/2",
                "updated_at": "",
                "repository_url": "https://api.github.com/repos/c/d",
                "labels": [{"name": "hiring"}],
            },
        ]
    }

    async def fake_json_get(url, params=None):
        return payload

    with mock.patch.object(github_jobs, "json_get", new=fake_json_get):
        leads = asyncio.run(github_jobs.scrape_github("github:hiring"))

    assert len(leads) == 1
    assert leads[0]["title"] == "Hiring: Backend Engineer (remote)"


# --- normalize_stored_leads (real SQLite, subprocess) ------------------------

def test_normalize_stored_leads_repairs_and_is_idempotent():
    SCRATCH.mkdir(exist_ok=True)
    db_path = str(SCRATCH / f"leads-{uuid.uuid4().hex}.db")
    first_line = "Acme Robotics | Senior Backend Engineer | Remote | Python, Go"
    script = f"""
import sys
sys.path.insert(0, 'backend')
from data.sqlite.connection import get_connection, run_migrations
from discovery.maintenance import normalize_stored_leads

db = {db_path!r}
run_migrations(db)
conn = get_connection(db)

legacy_title = {first_line!r} + " We build warehouse robots and are hiring across the stack right now"
conn.execute(
    "INSERT INTO leads(job_id, title, company, url, platform, description) VALUES(?,?,?,?,?,?)",
    ("hn1", legacy_title, "throwaway", "https://news.ycombinator.com/item?id=1", "hn_hiring",
     {first_line!r} + chr(10) + "We build warehouse robots."),
)
moj_title = "We" + chr(0xE2) + chr(0x20AC) + chr(0x2122) + "re hiring: Senior Engineer"
spam_desc = ("Build APIs." + chr(10)
             + "Please mention the word **PLEASANTLY** and tag RMTQ0LjE= when applying to show you read the job post completely."
             + chr(10) + "Location: Remote")
conn.execute(
    "INSERT INTO leads(job_id, title, company, url, platform, description) VALUES(?,?,?,?,?,?)",
    ("rok1", moj_title, "RemoteCo", "https://remoteok.com/l/1", "remoteok", spam_desc),
)
conn.execute(
    "INSERT INTO leads(job_id, title, company, url, platform, description) VALUES(?,?,?,?,?,?)",
    ("rok2", "Data Analyst", "CleanCo", "https://remoteok.com/l/2", "remoteok", "Analyze data."),
)
conn.commit()

first = normalize_stored_leads(db)
assert first == {{"titles_fixed": 2, "descriptions_cleaned": 1}}, first

row = conn.execute("SELECT title, company FROM leads WHERE job_id='hn1'").fetchone()
assert row[0] == "Senior Backend Engineer", repr(row[0])
assert row[1] == "Acme Robotics", repr(row[1])

row = conn.execute("SELECT title, description FROM leads WHERE job_id='rok1'").fetchone()
assert row[0] == "We" + chr(0x2019) + "re hiring: Senior Engineer", ascii(row[0])
assert "please mention" not in row[1].lower(), ascii(row[1])
assert "Build APIs." in row[1] and "Location: Remote" in row[1], ascii(row[1])

row = conn.execute("SELECT title, description FROM leads WHERE job_id='rok2'").fetchone()
assert row[0] == "Data Analyst" and row[1] == "Analyze data."

second = normalize_stored_leads(db)
assert second == {{"titles_fixed": 0, "descriptions_cleaned": 0}}, second
print("OK")
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"subprocess failed:\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}"
    finally:
        for suffix in ("", "-wal", "-shm", ".migration.lock"):
            candidate = Path(db_path + suffix)
            if candidate.exists():
                try:
                    candidate.unlink()
                except OSError:
                    pass



# ── Adversarial-verification regression locks (2026-07-20) ──────────────────

def test_repair_mojibake_never_deletes_legit_accents():
    from discovery.sources.rss import repair_mojibake
    moji_apostrophe = chr(0xE2) + chr(0x20AC) + chr(0x2122)  # "â€™"
    mixed = "Jos" + chr(0xE9) + " leads engineering. We" + moji_apostrophe + "re hiring."
    # Mixed legit-accent + mojibake text is NOT a pure misread: keep original.
    assert repair_mojibake(mixed) == mixed
    icelandic = "Sigur" + chr(0xF0) + chr(0xF3) + "r hf."  # marker lookalike, no mojibake
    assert repair_mojibake(icelandic) == icelandic
    pure = "We" + moji_apostrophe + "re hiring"
    assert repair_mojibake(pure) == "We" + chr(0x2019) + "re hiring"


def test_strip_remoteok_noise_spares_employer_authored_sentences():
    from discovery.sources.rss import strip_remoteok_noise
    employer = "In your application, please mention the word banana and include salary expectations.\nWe sponsor visas."
    assert strip_remoteok_noise(employer) == employer
    injected = "Great role.\nPlease mention the word **APPLE** and tag RMTQ0 when applying to show you read the job post completely. This is a beta feature.\nApply now."
    cleaned = strip_remoteok_noise(injected)
    assert "APPLE" not in cleaned and "beta feature" not in cleaned
    assert "Great role." in cleaned and "Apply now." in cleaned


def test_remoteok_title_gate_keeps_real_non_noun_titles():
    from discovery.sources.rss import _remoteok_title_ok
    for title in ("Head of Growth", "VP of Sales", "Chief of Staff", "Scrum Master",
                  "Dental Hygienist", "Illustrator", "Videographer", "Community Moderator"):
        assert _remoteok_title_ok(title, ""), title
    assert not _remoteok_title_ok("Danny", "sfvjfoiwupwuwipfuwfpwu")
    assert not _remoteok_title_ok("Sydney", "There are no articles in this category.")


def test_boilerplate_gate_spares_real_jds_mentioning_signatures():
    from discovery.quality_gate import is_boilerplate_description
    accessibility = (
        "We are hiring an accessibility engineer to lead WCAG 2.2 compliance across our product. "
        "You will implement focus management, ARIA landmarks, and a skip to main content link, "
        "and partner with design on inclusive patterns. 4+ years of frontend accessibility work required."
    )
    assert not is_boilerplate_description(accessibility)
    payments = (
        "Payments engineer role: build our card-processing platform, own PCI compliance, ship "
        "reconciliation tooling, and scale settlement pipelines used by thousands of merchants. "
        "Strong Python and Postgres background expected, plus experience with idempotent APIs. "
        "Posted 8:04 AM. See this and similar jobs on LinkedIn."
    )
    assert not is_boilerplate_description(payments)
    assert is_boilerplate_description("Posted 8:04:13 AM. See this and similar jobs on LinkedIn.")
    assert is_boilerplate_description("Skip to main content\nsitemap\nSearch Jobs\nFind Jobs\nCareers portal\n" + "x" * 400)


def test_hn_role_first_requires_pure_role_segment():
    from discovery.normalizer import hn_company_role
    company, title = hn_company_role("Panopto Software | Remote | Python, Go")
    assert company == "Panopto Software"
    assert title == "Hiring at Panopto Software"
    company, title = hn_company_role("Engineers Gate | New York | Onsite")
    assert company == "Engineers Gate"
    company, title = hn_company_role("Designer Brands | Remote | Full-time")
    assert company == "Designer Brands"
    company, title = hn_company_role("Engineering Manager | Remote | Full-time")
    assert title == "Engineering Manager"
    company, title = hn_company_role("Senior Full Stack Engineer | Acme | Remote")
    assert title == "Senior Full Stack Engineer"
    assert company == "Acme"
