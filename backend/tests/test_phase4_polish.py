# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs
"""Regression tests for Phase 4 polish fixes:

- L1: file upload read happens async (off the event loop).
- L2: LLM base URL validation rejects loopback/private IP variants.
- L3: row_get logs unknown columns at DEBUG and returns the default.
"""

import logging

import pytest

from api.routers import ingestion
from data.sqlite import leads


# ── L1 ──────────────────────────────────────────────────────────────────────

class _FakeUpload:
    def __init__(self, filename, content):
        self.filename = filename
        self._content = content
        self.read_calls = 0

    async def read(self, size=-1):
        # Mirror Starlette's UploadFile.read(size): return the full content on
        # the first call, then EOF, so the chunked _read_capped terminates.
        self.read_calls += 1
        if self.read_calls == 1:
            return self._content
        return b""


@pytest.mark.asyncio
async def test_temp_upload_reads_async_and_writes_file():
    upload = _FakeUpload("resume.pdf", b"%PDF-1.4 hello")
    async with ingestion._temp_upload(upload) as path:
        assert path is not None
        assert path.endswith(".pdf")
        with open(path, "rb") as fh:
            assert fh.read() == b"%PDF-1.4 hello"
    # _read_capped streams in chunks until EOF (content chunk + empty terminator).
    assert upload.read_calls >= 1
    # temp file cleaned up on exit
    import os
    assert not os.path.exists(path)


@pytest.mark.asyncio
async def test_temp_upload_yields_none_without_file():
    async with ingestion._temp_upload(None) as path:
        assert path is None


# ── L2 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/v1",
        "http://127.0.0.2/v1",   # any loopback, not just .1
        "http://localhost/v1",
        "http://0.0.0.0/v1",
        "http://[::1]/v1",
        "http://10.0.0.5/v1",    # private
        "http://169.254.1.1/v1",  # link-local
    ],
)
def test_validate_base_url_rejects_local_and_private(url):
    # Skip if the heavy LLM client module can't import (e.g. no instructor).
    client = pytest.importorskip("llm.client")
    with pytest.raises(ValueError):
        client._validate_base_url(url)


def test_validate_base_url_allows_public_host():
    client = pytest.importorskip("llm.client")
    assert client._validate_base_url("https://api.openai.com/v1") == "https://api.openai.com/v1"


# ── L3 ──────────────────────────────────────────────────────────────────────

def test_row_get_returns_value_for_known_dict_key():
    row = {"job_id": "abc", "title": "Engineer"}
    assert leads.row_get(row, "job_id") == "abc"


def test_row_get_unknown_column_logs_debug_and_returns_default(caplog):
    row = ("only-positional",)  # tuple: no string-key access
    with caplog.at_level(logging.DEBUG, logger="data.sqlite.leads"):
        result = leads.row_get(row, "not_a_real_column", default="fallback")
    assert result == "fallback"
    drift = [rec for rec in caplog.records if "not_a_real_column" in rec.getMessage()]
    assert drift, "expected a schema-drift log mentioning the unknown column"
    assert all(rec.levelno == logging.DEBUG for rec in drift), (
        "schema-drift log must be DEBUG, not WARNING"
    )


def test_row_get_known_column_by_position():
    # job_id is the first lead column, so positional access should resolve it.
    row = tuple(f"col{i}" for i in range(len(leads.LEAD_COLUMN_NAMES)))
    assert leads.row_get(row, "job_id") == "col0"
