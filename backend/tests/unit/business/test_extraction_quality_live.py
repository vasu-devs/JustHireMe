"""OPT-IN live extraction-QUALITY test — asserts WHAT the agent picks, not how much.

The user's complaint was qualitative, not quantitative: the knowledge graph showed
the SAME project twice and listed implementation phrases ("parallel upserts",
"bounded concurrency") as if they were skills. Counting fields can't catch that —
so this test feeds a crafted "character résumé" with deliberate traps through the
REAL ingestion agent + normalization and checks the *content* that comes out:

  - one project written two ways (a plain name AND again with a GitHub link) must
    collapse to a SINGLE project, not two near-duplicate nodes;
  - every genuinely distinct project must survive;
  - real, named skills (Python, FastAPI, PostgreSQL …) must be picked;
  - project implementation details ("parallel upserts", "bounded concurrency",
    "composite indexes") must NOT appear as skills — they describe what was DONE
    in one project, not a transferable competency.

It is gated like the other live smokes: SKIPPED by default / in CI (no subscription)
and SKIPPED if no keyless CLI is on PATH. It exercises the prompt + normalization,
NOT the graph/vector writers (no side effects). Run it with:

    cd backend && JHM_LIVE_CLI=1 uv run python -m pytest tests/test_extraction_quality_live.py -v

Opting in asserts the real agent gets these distinctions right; a wrong pick is a
FAILURE, not a skip.
"""

from __future__ import annotations

import os
import shutil

import pytest

from llm import client

_OPT_IN = os.environ.get("JHM_LIVE_CLI", "").strip().lower() in {"1", "true", "yes", "on"}

pytestmark = pytest.mark.skipif(
    not _OPT_IN,
    reason="opt-in live extraction-quality test: set JHM_LIVE_CLI=1 (needs a logged-in claude/codex subscription)",
)

# A deliberately tricky résumé. Note the traps:
#  - "Vaani" appears in the Projects section AND again in an experience bullet,
#    the second time with a GitHub link -> it is ONE project.
#  - impact lines contain implementation phrases that are NOT skills.
#  - four genuinely distinct projects: Vaani, BranchGPT, MeshSync, LedgerLite.
_RESUME = """
Asha Verma — Backend Engineer
Bengaluru, India

Summary
Backend engineer with 4 years building data-heavy services in Python and TypeScript.

Skills
Python, FastAPI, PostgreSQL, React, Docker, Redis

Experience
Senior Engineer — FlowCorp (2023 - Present)
- Built Vaani (github.com/asha/vaani), a real-time multilingual voice assistant,
  using parallel upserts in PostgreSQL with bounded concurrency to cut write latency.
- Designed composite indexes that sped up the analytics dashboard.

Engineer — DataNimbus (2021 - 2023)
- Shipped MeshSync, a peer-to-peer file sync engine.

Projects
- Vaani — a voice assistant for regional Indian languages. Stack: Python, FastAPI.
- BranchGPT — a Git workflow copilot. Stack: TypeScript, React.
- LedgerLite — a double-entry bookkeeping tool. Stack: Python, SQLite.
"""

# Implementation details from the résumé that must NEVER be classified as skills.
_NOT_SKILLS = ["parallel upserts", "bounded concurrency", "composite indexes"]
# Real, named competencies that the agent should pick.
_REAL_SKILLS = ["python", "fastapi", "postgresql"]
# Distinct projects that must all survive.
_DISTINCT_PROJECTS = ["vaani", "branchgpt", "meshsync", "ledgerlite"]


@pytest.fixture
def use_cli_provider():
    """Point the LLM client at whichever keyless CLI is installed, restoring the
    real repository afterwards (configure_repository is process-global)."""
    from data.repository import create_repository

    def _apply(provider: str):
        class _Settings:
            def get_setting(self, key, default=""):
                return {"llm_provider": provider}.get(key, default)

        class _Repo:
            settings = _Settings()

        client.configure_repository(_Repo())

    yield _apply
    client.configure_repository(create_repository())


def _first_available_cli() -> tuple[str, str] | None:
    for provider, binary in (("claude_cli", "claude"), ("codex_cli", "codex")):
        if shutil.which(binary):
            return provider, binary
    return None


def test_live_extraction_quality(use_cli_provider):
    available = _first_available_cli()
    if available is None:
        pytest.skip("no keyless CLI (claude/codex) on PATH")
    provider, _binary = available
    use_cli_provider(provider)

    from profile.ingestor import run
    from profile.normalization import normalize_candidate_model

    # run() = the LLM extraction; normalize = the structural dedup/skill backstop.
    # Together these produce exactly what the graph writer would persist — without
    # touching the graph/vector stores.
    extracted = run(_RESUME)
    profile = normalize_candidate_model(extracted)

    titles = [str(p.title).lower() for p in profile.projects]
    skills = [str(s.n).lower() for s in profile.skills]

    # 1) Every distinct project survives.
    for name in _DISTINCT_PROJECTS:
        assert any(name in t for t in titles), f"missing project {name!r}; got {titles}"

    # 2) The project written two ways collapses to ONE node, not two.
    vaani_count = sum(1 for t in titles if "vaani" in t)
    assert vaani_count == 1, f"Vaani should appear once (it was listed twice); got {vaani_count} in {titles}"

    # 3) Real, named skills are picked.
    for skill in _REAL_SKILLS:
        assert any(skill == s or skill in s.split() for s in skills), f"missing real skill {skill!r}; got {skills}"

    # 4) Implementation phrases are NOT classified as skills.
    for phrase in _NOT_SKILLS:
        assert not any(phrase in s for s in skills), f"implementation phrase leaked into skills: {phrase!r} in {skills}"
