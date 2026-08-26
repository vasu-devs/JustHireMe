"""Unit tests for generation/orchestrator.py — the generate-for-a-lead use case.

The transactional rule under test: a lead is only ever reported "approved" if
save_asset_package actually persisted. Everything softer (outreach fields,
contact lookup) degrades to a recorded error instead of failing the run.
"""

from __future__ import annotations

import asyncio
import types

import pytest

from core.errors import NotFoundError, UnprocessableError
from generation.orchestrator import (
    GENERATION_RETRY_AFTER_SECONDS,
    GenerationOrchestrator,
    is_transient_generation_error,
)

PACKAGE = {
    "resume": "resume.pdf",
    "cover_letter": "cover.pdf",
    "selected_projects": ["p1"],
    "keyword_coverage": {"coverage_pct": 80},
    "founder_message": "hi",
}


# core.generation_readiness gates on substance: >=40 chars and >=10 words of
# non-URL context, so the fixture carries a realistic description.
DESCRIPTION = (
    "We are hiring a backend engineer to build and operate Python services, "
    "design APIs, and mentor the team on testing and reliability practices."
)


def _lead(**kw):
    base = {"job_id": "j1", "title": "Staff Backend Engineer", "company": "Acme",
            "url": "https://x/1", "description": DESCRIPTION, "status": "discovered"}
    base.update(kw)
    return base


def _repo(lead=None, fail=()):
    state = {"statuses": [], "saved": [], "outreach": [], "contacts": []}

    class Leads:
        def get_lead_by_id(self, _job_id):
            return dict(lead) if lead else None

        def update_lead_status(self, _job_id, status):
            state["statuses"].append(status)

        def save_asset_package(self, *args):
            if "save" in fail:
                raise RuntimeError("db locked")
            state["saved"].append(args)

        def update_outreach_fields(self, _job_id, fields):
            if "outreach" in fail:
                raise RuntimeError("db locked")
            state["outreach"].append(fields)

        def save_contact_lookup(self, _job_id, contacts):
            if "contacts" in fail:
                raise RuntimeError("db locked")
            state["contacts"].append(contacts)

        def save_lead(self, new_lead):
            state.setdefault("new", []).append(new_lead)

    class Templates:
        def resolve_template_content(self, template_id):
            if template_id == "broken":
                raise RuntimeError("no such template")
            return "TEMPLATE"

    class Settings:
        def get_setting(self, _key, default=""):
            return default

        def get_settings(self):
            return {}

    class Profile:
        def get_profile(self):
            return {}

    repo = types.SimpleNamespace(
        leads=Leads(), resume_templates=Templates(), settings=Settings(), profile=Profile()
    )
    repo._state = state
    return repo


def _service(error=None, package=None):
    class Service:
        async def generate_with_contacts(self, _lead, template=""):
            if error:
                raise error
            return types.SimpleNamespace(package=dict(package or PACKAGE), contact_lookup={"primary": "a@b.c"})

    return Service()


def _jobs():
    seen = {"updates": []}

    class Jobs:
        def create(self, *_a, **_k):
            return types.SimpleNamespace(job_id="job-1")

        def update(self, *_a, **kw):
            seen["updates"].append(kw)

    jobs = Jobs()
    jobs.seen = seen
    return jobs


def _collector():
    sent: list[dict] = []

    async def notify(message):
        sent.append(message)

    return notify, sent


# ------------------------------------------------------------- classification


@pytest.mark.parametrize("exc, transient", [
    (ConnectionError("net"), True),
    (TimeoutError("slow"), True),
    (TimeoutError(), True),
    (ValueError("bad template"), False),
    (KeyError("missing"), False),
])
def test_transient_classification(exc, transient):
    assert is_transient_generation_error(exc) is transient


# -------------------------------------------------------------- happy path


@pytest.mark.asyncio
async def test_generate_persists_and_returns_the_enriched_lead():
    repo = _repo(_lead())
    notify, sent = _collector()
    lead = await GenerationOrchestrator(repo, _service(), _jobs()).generate("j1", notify)

    assert lead["status"] == "approved"
    assert lead["resume_asset"] == "resume.pdf"
    assert lead["contact_lookup"] == {"primary": "a@b.c"}
    assert lead["generation_job_id"] == "job-1"
    assert repo._state["saved"], "the package must be persisted"
    assert [m.get("event") for m in sent if m.get("event")] == ["gen_start", "gen_done"]


@pytest.mark.asyncio
async def test_generate_marks_tailoring_before_the_slow_work():
    repo = _repo(_lead())
    notify, _ = _collector()
    await GenerationOrchestrator(repo, _service(), _jobs()).generate("j1", notify)
    assert repo._state["statuses"][0] == "tailoring"


@pytest.mark.asyncio
async def test_generate_only_writes_outreach_fields_that_exist():
    repo = _repo(_lead())
    notify, _ = _collector()
    await GenerationOrchestrator(repo, _service(), _jobs()).generate("j1", notify)
    assert repo._state["outreach"] == [{"outreach_reply": "hi"}]


# ------------------------------------------------------------------ failures


@pytest.mark.asyncio
async def test_generate_raises_not_found_for_an_unknown_lead():
    notify, sent = _collector()
    with pytest.raises(NotFoundError):
        await GenerationOrchestrator(_repo(None), _service(), _jobs()).generate("nope", notify)
    assert sent[0]["event"] == "gen_error"


@pytest.mark.asyncio
async def test_generate_refuses_a_lead_that_is_not_ready():
    """A URL-only lead has no description to tailor against."""
    lead = _lead(description="https://x/1", source_meta={"input_url_only": True, "needs_job_description": True})
    notify, _ = _collector()
    with pytest.raises(UnprocessableError):
        await GenerationOrchestrator(_repo(lead), _service(), _jobs()).generate("j1", notify)


@pytest.mark.asyncio
async def test_a_failed_asset_save_fails_the_whole_generation():
    """Otherwise the UI shows success while the DB still says tailoring."""
    repo = _repo(_lead(), fail=("save",))
    notify, sent = _collector()
    with pytest.raises(RuntimeError):
        await GenerationOrchestrator(repo, _service(), _jobs()).generate("j1", notify)
    assert repo._state["statuses"][-1] == "discovered"   # reverted, not approved
    assert any(m.get("event") == "gen_error" for m in sent)


@pytest.mark.asyncio
async def test_soft_persistence_failures_are_recorded_but_do_not_fail_the_run():
    repo = _repo(_lead(), fail=("outreach", "contacts"))
    notify, _ = _collector()
    lead = await GenerationOrchestrator(repo, _service(), _jobs()).generate("j1", notify)
    errors = lead["source_meta"]["generation_persistence_errors"]
    assert len(errors) == 2 and lead["status"] == "approved"


@pytest.mark.asyncio
async def test_a_transient_failure_keeps_the_lead_retryable():
    repo = _repo(_lead())
    notify, sent = _collector()
    orchestrator = GenerationOrchestrator(repo, _service(error=ConnectionError("net down")), _jobs())
    with pytest.raises(ConnectionError):
        await orchestrator.generate("j1", notify)

    assert repo._state["statuses"][-1] == "tailoring"
    update = [m for m in sent if m.get("type") == "LEAD_UPDATED"][-1]
    assert update["data"]["source_meta"]["retry_after"] == GENERATION_RETRY_AFTER_SECONDS


@pytest.mark.asyncio
async def test_a_permanent_failure_reverts_to_discovered():
    repo = _repo(_lead())
    notify, sent = _collector()
    orchestrator = GenerationOrchestrator(repo, _service(error=ValueError("bad template")), _jobs())
    with pytest.raises(ValueError):
        await orchestrator.generate("j1", notify)

    assert repo._state["statuses"][-1] == "discovered"
    update = [m for m in sent if m.get("type") == "LEAD_UPDATED"][-1]
    assert "retry_after" not in update["data"]["source_meta"]


# ------------------------------------------------------------------ templates


@pytest.mark.asyncio
async def test_an_explicitly_chosen_template_that_fails_to_load_is_an_error():
    """Silently generating with a different layout would misrepresent the output."""
    notify, _ = _collector()
    with pytest.raises(UnprocessableError, match="broken"):
        await GenerationOrchestrator(_repo(_lead()), _service(), _jobs()).generate(
            "j1", notify, template_id="broken"
        )


@pytest.mark.asyncio
async def test_no_template_id_falls_back_to_the_legacy_setting(monkeypatch):
    repo = _repo(_lead())

    def boom(_template_id):
        raise RuntimeError("resolve failed")

    repo.resume_templates.resolve_template_content = boom
    notify, _ = _collector()
    lead = await GenerationOrchestrator(repo, _service(), _jobs()).generate("j1", notify)
    assert lead["status"] == "approved"      # degraded to the built-in layout


# ----------------------------------------------------------------- start/manual


@pytest.mark.asyncio
async def test_start_returns_the_queued_lead_immediately():
    repo = _repo(_lead())
    notify, sent = _collector()
    queued = await GenerationOrchestrator(repo, _service(), _jobs()).start("j1", notify)
    assert queued["status"] == "tailoring"
    assert sent[0]["type"] == "LEAD_UPDATED"


@pytest.mark.asyncio
async def test_start_raises_for_a_missing_lead():
    notify, _ = _collector()
    with pytest.raises(NotFoundError):
        await GenerationOrchestrator(_repo(None), _service(), _jobs()).start("nope", notify)


@pytest.mark.asyncio
async def test_generate_quietly_swallows_failures_already_broadcast():
    repo = _repo(_lead())
    notify, sent = _collector()
    orchestrator = GenerationOrchestrator(repo, _service(error=ValueError("boom")), _jobs())
    await orchestrator.generate_quietly("j1", notify)   # must not raise
    assert any(m.get("event") == "gen_error" for m in sent)


@pytest.mark.asyncio
async def test_manual_generate_requires_text_or_url():
    from core.errors import ValidationError

    notify, _ = _collector()
    with pytest.raises(ValidationError):
        await GenerationOrchestrator(_repo(None), _service(), _jobs()).create_manual_and_generate("", "  ", notify)


@pytest.mark.asyncio
async def test_manual_generate_returns_a_queued_lead_and_a_runner():
    notify, _ = _collector()
    queued = await GenerationOrchestrator(_repo(_lead()), _service(), _jobs()).create_manual_and_generate(
        f"Staff Engineer at Acme\n{DESCRIPTION}", "https://acme.com/jobs/1", notify
    )
    assert queued["lead"]["status"] == "tailoring"
    assert callable(queued["run"])
