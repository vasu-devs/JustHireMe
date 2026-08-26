# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Vasudev Siddh and vasu-devs
"""Regression test for H6: CI/release workflows must reference action versions
that actually exist, and upload/download-artifact must share a major version."""

import re
from pathlib import Path

import pytest
from paths import REPO_ROOT

ROOT = REPO_ROOT
WORKFLOWS = [ROOT / ".github/workflows/ci.yml", ROOT / ".github/workflows/release.yml"]

# Highest existing stable major for each action (as of 2026-06-22; bump when an
# action ships a new major and CI confirms it resolves).
_MAX_MAJOR = {
    "actions/checkout": 7,
    "actions/setup-node": 6,
    "actions/setup-python": 6,
    "actions/upload-artifact": 4,
    "actions/download-artifact": 4,
    "actions/cache": 4,
}

_PIN_RE = re.compile(r"(actions/[a-z-]+)@v(\d+)")


def _pins(text: str):
    return [(name, int(major)) for name, major in _PIN_RE.findall(text)]


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_no_action_pinned_above_existing_major(workflow):
    assert workflow.exists(), f"missing workflow {workflow}"
    bad = [
        f"{name}@v{major}"
        for name, major in _pins(workflow.read_text(encoding="utf-8"))
        if name in _MAX_MAJOR and major > _MAX_MAJOR[name]
    ]
    assert bad == [], f"{workflow.name} pins non-existent action versions: {bad}"


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_upload_and_download_artifact_majors_match(workflow):
    text = workflow.read_text(encoding="utf-8")
    uploads = {m for n, m in _pins(text) if n == "actions/upload-artifact"}
    downloads = {m for n, m in _pins(text) if n == "actions/download-artifact"}
    if uploads and downloads:
        assert uploads == downloads, (
            f"{workflow.name}: upload-artifact {uploads} != download-artifact {downloads}"
        )
