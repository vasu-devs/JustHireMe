"""discovery/maintenance.py — the one-shot repair of stored lead rows.

Runs in a subprocess against a REAL SQLite file: the in-process suite installs a
global sqlite3 fake, which would make the UPDATE counts meaningless.
"""

from __future__ import annotations

import subprocess
import sys

from paths import REPO_ROOT

# A pre-parser HN comment dump stored as a title, plus a RemoteOK row carrying
# the injected anti-spam paragraph and mojibake.
_SEED_AND_REPAIR = '''
import sys
sys.path.insert(0, "backend")
db_path = {db_path!r}

from data.sqlite.connection import get_connection, init_sql
from discovery.maintenance import normalize_stored_leads

init_sql(db_path)
conn = get_connection(db_path)
conn.execute(
    "INSERT INTO leads(job_id, title, company, description, platform) VALUES(?,?,?,?,?)",
    ("hn-1",
     "Acme (YC W20) | Senior Backend Engineer | Remote | Full-time | We are building "
     "the future of widgets and need someone who can own the whole stack end to end",
     "",
     "Acme (YC W20) | Senior Backend Engineer | Remote", "hn_hiring"),
)
conn.execute(
    "INSERT INTO leads(job_id, title, company, description, platform) VALUES(?,?,?,?,?)",
    ("ro-1", "Senior Engineer \\u00e2\\u20ac\\u201c Remote", "Globex",
     "Real duties here.\\nPlease mention the word **BREATHTAKING** and tag RMT0123 when applying "
     "to show you read the job post.\\nPlease mention the word banana and include salary expectations.",
     "remoteok"),
)
conn.commit()

first = normalize_stored_leads(db_path)
second = normalize_stored_leads(db_path)

rows = {{r["job_id"]: r for r in conn.execute(
    "SELECT job_id, title, company, description FROM leads").fetchall()}}

print("FIRST", first)
print("SECOND", second)
print("HN_TITLE", rows["hn-1"]["title"])
print("RO_TITLE", rows["ro-1"]["title"])
print("RO_DESC", repr(rows["ro-1"]["description"]))
'''


def _run(tmp_path) -> dict[str, str]:
    script = _SEED_AND_REPAIR.format(db_path=str(tmp_path / "crm.db"))
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    out: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition(" ")
        out[key] = value
    return out


def test_repair_fixes_rows_once_and_is_idempotent(tmp_path):
    out = _run(tmp_path)

    # Something was repaired on the first pass...
    first = eval(out["FIRST"])  # noqa: S307 - our own printed dict
    assert first["titles_fixed"] + first["descriptions_cleaned"] >= 1

    # ...and the second pass is a no-op, so every install pays the cost once.
    assert eval(out["SECOND"]) == {"titles_fixed": 0, "descriptions_cleaned": 0}  # noqa: S307


def test_hn_comment_dump_title_is_replaced_with_a_real_role(tmp_path):
    out = _run(tmp_path)
    title = out["HN_TITLE"]
    assert len(title) <= 120, "the raw comment dump must not survive as a title"
    assert "|" not in title


def test_remoteok_mojibake_is_repaired_in_the_title(tmp_path):
    out = _run(tmp_path)
    assert "â€“" not in out["RO_TITLE"], "mojibake must be repaired"


def test_remoteok_anti_spam_paragraph_is_stripped(tmp_path):
    out = _run(tmp_path)
    description = out["RO_DESC"]
    assert "BREATHTAKING" not in description
    assert "Real duties here." in description
    assert "\\n\\n" not in description, "the gap left by the strip must be collapsed"


def test_an_employer_authored_sentence_is_not_mistaken_for_the_injection(tmp_path):
    """The strip anchors on RemoteOK's own markers ("and tag RMT…"), so an
    employer sentence that merely starts the same way must survive."""
    out = _run(tmp_path)
    assert "banana" in out["RO_DESC"], "employer-authored text must not be stripped"
