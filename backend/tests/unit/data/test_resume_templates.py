# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs
"""Tests for the user-managed resume template store and generation resolution.

These run the real-SQLite assertions in a clean subprocess (like
test_sqlite_settings.py) so the `sqlite3` fake installed by regression_support
in the shared test process can't contaminate them.
"""

import subprocess
import sys
import uuid
from pathlib import Path
from paths import REPO_ROOT, TESTS_ROOT

SCRATCH = TESTS_ROOT / ".scratch-templates"


def _run(body: str) -> None:
    SCRATCH.mkdir(exist_ok=True)
    db_path = str(SCRATCH / f"templates-{uuid.uuid4().hex}.db")
    script = (
        "import sys; sys.path.insert(0, 'backend');"
        "from data.sqlite import resume_templates as rt;"
        f"db = {db_path!r};"
        + body
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"subprocess failed:\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}"
    finally:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(db_path + suffix)
            if candidate.exists():
                try:
                    candidate.unlink()
                except OSError:
                    pass


def test_first_template_becomes_default():
    _run(
        "t = rt.create_template('Modern', 'Jane Doe\\nSenior Engineer', 'modern.pdf', db_path=db);"
        "assert t['is_default'] is True;"
        "assert t['char_count'] > 0;"
        "assert t['content'].startswith('Jane Doe')"
    )


def test_listing_excludes_full_content_but_keeps_preview():
    _run(
        "rt.create_template('Modern', 'X' * 1000, db_path=db);"
        "items = rt.list_templates(db_path=db);"
        "assert len(items) == 1;"
        "assert 'content' not in items[0];"
        "assert items[0]['preview'];"
        "assert items[0]['char_count'] == 1000"
    )


def test_set_default_moves_the_flag():
    _run(
        "a = rt.create_template('A', 'alpha', db_path=db);"
        "b = rt.create_template('B', 'beta', db_path=db);"
        "assert a['is_default'] is True and b['is_default'] is False;"
        "assert rt.set_default_template(b['id'], db_path=db) is True;"
        "assert rt.get_template(a['id'], db_path=db)['is_default'] is False;"
        "assert rt.get_template(b['id'], db_path=db)['is_default'] is True"
    )


def test_deleting_default_promotes_another():
    _run(
        "a = rt.create_template('A', 'alpha', db_path=db);"
        "b = rt.create_template('B', 'beta', db_path=db);"
        "assert rt.delete_template(a['id'], db_path=db) is True;"
        "assert rt.get_template(b['id'], db_path=db)['is_default'] is True"
    )


def test_create_rejects_empty_content():
    _run(
        "raised = False;\n"
        "try:\n"
        "    rt.create_template('Empty', '   ', db_path=db)\n"
        "except ValueError:\n"
        "    raised = True\n"
        "assert raised"
    )


def test_resolve_prefers_explicit_then_default():
    _run(
        "a = rt.create_template('A', 'alpha-content', db_path=db);"
        "b = rt.create_template('B', 'beta-content', db_path=db);"
        "assert rt.resolve_template_content(b['id'], db_path=db) == 'beta-content';"
        "assert rt.resolve_template_content('', db_path=db) == 'alpha-content';"
        "assert rt.resolve_template_content('nope', db_path=db) == 'alpha-content'"
    )


def test_resolve_empty_when_no_templates():
    _run("assert rt.resolve_template_content('', db_path=db) == ''")
