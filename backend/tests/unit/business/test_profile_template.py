# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs
"""Regression tests for C3: profile template endpoint must not crash when the
bundled JSON file is missing or corrupt (e.g. a packaged build that didn't
ship it)."""

import json
import logging
import tempfile
from pathlib import Path

import pytest

from api.routers import ingestion
from paths import BACKEND_ROOT


@pytest.fixture
def scratch_dir():
    """A scratch directory that avoids pytest's tmp_path fixture, which is
    unusable on some Windows hosts due to perms on the shared pytest temp root."""
    with tempfile.TemporaryDirectory(prefix="jhm-tmpl-") as d:
        yield Path(d)

BACKEND = BACKEND_ROOT
REAL_TEMPLATE = BACKEND / "data" / "profile_schema_example.json"
_LOG = logging.getLogger("test")

_TOP_KEYS = {
    "candidate",
    "identity",
    "skills",
    "experience",
    "projects",
    "education",
    "certifications",
    "achievements",
}


def test_default_template_has_expected_shape():
    default = ingestion._default_profile_template()
    assert _TOP_KEYS.issubset(default.keys())
    assert isinstance(default["skills"], list)


def test_read_missing_file_returns_default(scratch_dir):
    missing = scratch_dir / "does_not_exist.json"
    result = ingestion._read_profile_template(missing, _LOG)
    assert result == ingestion._default_profile_template()


def test_read_corrupt_file_returns_default(scratch_dir):
    corrupt = scratch_dir / "corrupt.json"
    corrupt.write_text("{ not valid json", encoding="utf-8")
    result = ingestion._read_profile_template(corrupt, _LOG)
    assert result == ingestion._default_profile_template()


def test_read_valid_file_returns_its_contents(scratch_dir):
    good = scratch_dir / "good.json"
    payload = {"candidate": {"name": "X"}, "skills": []}
    good.write_text(json.dumps(payload), encoding="utf-8")
    assert ingestion._read_profile_template(good, _LOG) == payload


def test_bundled_template_exists_and_is_valid():
    # If this fails, the packaging data entry (backend.spec) is the safety net,
    # but the source file should always be present in the repo.
    assert REAL_TEMPLATE.exists()
    data = json.loads(REAL_TEMPLATE.read_text(encoding="utf-8"))
    assert _TOP_KEYS.issubset(data.keys())


def test_default_keys_cover_real_template_keys():
    """The fallback default should not drop fields the real template advertises."""
    data = json.loads(REAL_TEMPLATE.read_text(encoding="utf-8"))
    real_keys = {k for k in data if not k.startswith("$")}
    assert real_keys.issubset(ingestion._default_profile_template().keys())
