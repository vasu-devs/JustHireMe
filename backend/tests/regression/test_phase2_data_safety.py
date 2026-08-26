# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs
"""Regression tests for Phase 2 data-safety fixes:

- H1: ghost re-scoring must call update_lead_score(preserve_status=True).
- H2: Windows migration lock must seek(0) before locking byte 0.
- H3: cover letter resolution must yield text, never a raw path or PDF bytes.
"""

import ast
import tempfile
import logging
from pathlib import Path

import pytest

from api.routers import automation
from paths import BACKEND_ROOT

BACKEND = BACKEND_ROOT
_LOG = logging.getLogger("test")


@pytest.fixture
def scratch_dir():
    with tempfile.TemporaryDirectory(prefix="jhm-p2-") as d:
        yield Path(d)


# ── H1 ──────────────────────────────────────────────────────────────────────

def test_ghost_tick_preserves_lead_status():
    """The update_lead_score call in the ghost tick must pass
    preserve_status=True so background re-scoring never clobbers user status."""
    tree = ast.parse((BACKEND / "automation" / "ghost.py").read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # update_lead_score is passed by reference to asyncio.to_thread(...)
        ref_names = [a.attr for a in node.args if isinstance(a, ast.Attribute)]
        if "update_lead_score" in ref_names:
            kwargs = {kw.arg for kw in node.keywords}
            found.append("preserve_status" in kwargs
                         and any(kw.arg == "preserve_status"
                                 and isinstance(kw.value, ast.Constant)
                                 and kw.value.value is True
                                 for kw in node.keywords))
    assert found, "no update_lead_score call found in automation/ghost.py"
    assert all(found), "ghost_tick update_lead_score must use preserve_status=True"


# ── H2 ──────────────────────────────────────────────────────────────────────

def test_windows_lock_seeks_to_byte_zero():
    """_lock_file / _unlock_file must seek(0) before msvcrt.locking so both
    processes contend for the same byte 0."""
    src = (BACKEND / "data" / "sqlite" / "connection.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    def func_body(name):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        raise AssertionError(f"{name} not found")

    for fn_name in ("_lock_file", "_unlock_file"):
        fn = func_body(fn_name)
        # collect attribute calls in order: expect a seek before a locking call
        seq = [
            n.func.attr
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        ]
        assert "seek" in seq, f"{fn_name} must call seek(0)"
        assert seq.index("seek") < seq.index("locking"), (
            f"{fn_name} must seek(0) before locking()"
        )


# ── H3 ──────────────────────────────────────────────────────────────────────

def test_cover_letter_reads_markdown_sibling(scratch_dir):
    pdf = scratch_dir / "cover.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    md = scratch_dir / "cover.md"
    md.write_text("Dear hiring manager,", encoding="utf-8")
    assert automation.resolve_cover_letter_text(str(pdf), _LOG) == "Dear hiring manager,"


def test_cover_letter_reads_md_when_asset_is_md(scratch_dir):
    md = scratch_dir / "cover.md"
    md.write_text("Hello there", encoding="utf-8")
    assert automation.resolve_cover_letter_text(str(md), _LOG) == "Hello there"


def test_cover_letter_never_returns_raw_path_or_pdf(scratch_dir):
    # Only a PDF exists (no markdown). Must NOT return the path or PDF bytes.
    pdf = scratch_dir / "cover.pdf"
    pdf.write_bytes(b"%PDF-1.4 binary garbage")
    result = automation.resolve_cover_letter_text(str(pdf), _LOG)
    assert result == ""


def test_cover_letter_missing_asset_returns_empty(scratch_dir):
    assert automation.resolve_cover_letter_text(str(scratch_dir / "nope.pdf"), _LOG) == ""
    assert automation.resolve_cover_letter_text("", _LOG) == ""
