"""Unit tests for leads/service.py — the lead lifecycle business layer.

Exercised directly against a fake repository, so these assert the domain rules
(filtering, validation, error types, asset resolution) rather than HTTP.
"""

from __future__ import annotations

import types

import pytest

from core.errors import NotFoundError, UnprocessableError, ValidationError
from leads.service import LeadService, safe_job_id, versioned_assets


def _lead(job_id="j1", **kw):
    base = {"job_id": job_id, "title": "Engineer", "company": "Acme", "kind": "job",
            "status": "discovered", "score": 50, "url": "https://x/1"}
    base.update(kw)
    return base


def _repo(leads=None, events=None, feedback_examples=None):
    store = {"leads": list(leads or []), "events": list(events or []), "calls": []}

    class Leads:
        def get_all_leads(self):
            return list(store["leads"])

        def get_lead_by_id(self, job_id):
            return next((dict(row) for row in store["leads"] if row["job_id"] == job_id), None)

        def delete_lead(self, job_id):
            if not any(row["job_id"] == job_id for row in store["leads"]):
                raise LookupError(job_id)
            store["calls"].append(("delete", job_id))

        def update_lead_status(self, job_id, status):
            if job_id == "missing":
                raise LookupError(job_id)
            if status == "bogus":
                raise ValueError("invalid status")
            store["calls"].append(("status", job_id, status))

        def save_lead_feedback(self, job_id, feedback, note):
            if feedback == "bogus":
                raise ValueError("invalid feedback")
            return None if job_id == "missing" else _lead(job_id, feedback=feedback, note=note)

        def update_lead_followup(self, job_id, now, due):
            store["calls"].append(("followup", job_id, now, due))
            return None if job_id == "missing" else _lead(job_id, followup_due=due)

        def save_lead(self, lead):
            store["leads"].append(lead)

        def classify_pending_seniority(self, classify_fn):
            # Real implementation persists a DB column; the fake repo has no
            # column to backfill, so just prove list_leads() actually calls
            # this (see test_list_leads_calls_seniority_backfill_before_read).
            store["calls"].append(("classify_pending_seniority", classify_fn))
            return 0

        def get_due_followups(self, limit, now):
            store["calls"].append(("due", limit, now))
            return store["leads"][:limit]

        def cleanup_bad_leads(self, limit, dry_run):
            store["calls"].append(("cleanup", limit, dry_run))
            return {"scanned": 10, "candidates": 2, "items": [{"job_id": "j1"}]}

        def mark_applied(self, job_id):
            store["calls"].append(("applied", job_id))

    class Events:
        def get_events(self, limit, job_id=None):
            store["calls"].append(("events", limit, job_id))
            return store["events"][:limit]

    class Feedback:
        def get_feedback_training_examples(self):
            return feedback_examples or []

    repo = types.SimpleNamespace(leads=Leads(), events=Events(), feedback=Feedback())
    repo._store = store
    return repo


# ------------------------------------------------------------------ validation


@pytest.mark.parametrize("job_id", ["ok-1", "A_b-9", "x" * 128])
def test_safe_job_id_accepts_plain_ids(job_id):
    assert safe_job_id(job_id) == job_id


@pytest.mark.parametrize("job_id", ["", "../etc/passwd", "a/b", "a b", "x" * 129, "a;b"])
def test_safe_job_id_rejects_anything_path_like(job_id):
    with pytest.raises(ValidationError):
        safe_job_id(job_id)


# --------------------------------------------------------------------- listing


@pytest.mark.asyncio
async def test_list_leads_returns_only_jobs_and_annotates_seniority():
    repo = _repo([_lead("j1"), _lead("c1", kind="contact")])
    result = await LeadService(repo).list_leads()
    assert [row["job_id"] for row in result] == ["j1"]
    assert "seniority_level" in result[0]


@pytest.mark.asyncio
async def test_list_leads_filters_by_status_and_min_score():
    repo = _repo([
        _lead("a", status="applied", score=90),
        _lead("b", status="discovered", score=30),
        _lead("c", status="discovered", score=80),
    ])
    service = LeadService(repo)
    assert {row["job_id"] for row in await service.list_leads(status="discovered")} == {"b", "c"}
    assert {row["job_id"] for row in await service.list_leads(min_score=80)} == {"a", "c"}


@pytest.mark.asyncio
async def test_list_leads_beginner_filter_keeps_only_junior_levels():
    repo = _repo([
        _lead("a", source_meta={"seniority_level": "fresher"}),
        _lead("b", source_meta={"seniority_level": "senior"}),
    ])
    result = await LeadService(repo).list_leads(beginner_only=True)
    assert [row["job_id"] for row in result] == ["a"]


@pytest.mark.asyncio
async def test_list_leads_calls_seniority_backfill_before_read():
    """GET /api/v1/leads used to re-run classify_job_seniority for every lead
    with no cached value on every request (~43s for 6,516 leads -- the bug
    this fixes). list_leads() must trigger the persisted-cache backfill
    (data.sqlite.leads.classify_pending_seniority) before reading, so a
    second request never re-classifies leads the first one already cached."""
    repo = _repo([_lead("a")])
    await LeadService(repo).list_leads()
    calls = [c for c in repo._store["calls"] if c[0] == "classify_pending_seniority"]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_list_leads_paginates_and_reports_totals():
    repo = _repo([_lead(f"j{i}") for i in range(25)])
    page = await LeadService(repo).list_leads(page=2, limit=10)
    assert page["total"] == 25 and page["pages"] == 3 and page["page"] == 2
    assert len(page["items"]) == 10


@pytest.mark.asyncio
async def test_list_leads_clamps_an_abusive_page_size():
    repo = _repo([_lead(f"j{i}") for i in range(5)])
    page = await LeadService(repo).list_leads(page=1, limit=10_000)
    assert page["limit"] == 1000


@pytest.mark.asyncio
async def test_get_lead_raises_not_found():
    with pytest.raises(NotFoundError):
        await LeadService(_repo()).get_lead("nope")


@pytest.mark.asyncio
async def test_export_csv_has_a_header_and_one_row_per_lead():
    repo = _repo([_lead("a"), _lead("b")])
    csv_text = await LeadService(repo).export_csv()
    lines = [line for line in csv_text.splitlines() if line.strip()]
    assert lines[0].startswith("job_id,title,company")
    assert len(lines) == 3


@pytest.mark.asyncio
async def test_list_activity_clamps_the_limit():
    repo = _repo(events=[{"job_id": "a", "action": "scan"}] * 50)
    await LeadService(repo).list_activity(limit=-5)
    assert ("events", 1, None) in repo._store["calls"]
    await LeadService(repo).list_activity(limit=99_999)
    assert ("events", 1000, None) in repo._store["calls"]


# ---------------------------------------------------------------------- writes


@pytest.mark.asyncio
async def test_delete_lead_maps_lookup_error_to_not_found():
    with pytest.raises(NotFoundError):
        await LeadService(_repo()).delete_lead("gone")


@pytest.mark.asyncio
async def test_update_status_maps_storage_errors_to_domain_errors():
    service = LeadService(_repo([_lead("j1")]))
    assert await service.update_status("j1", "applied") == {"job_id": "j1", "status": "applied"}
    with pytest.raises(NotFoundError):
        await service.update_status("missing", "applied")
    with pytest.raises(ValidationError):
        await service.update_status("j1", "bogus")


@pytest.mark.asyncio
async def test_save_feedback_rejects_a_bad_value_and_a_missing_lead():
    service = LeadService(_repo([_lead("j1")]))
    assert (await service.save_feedback("j1", "up", "note"))["feedback"] == "up"
    with pytest.raises(ValidationError):
        await service.save_feedback("j1", "bogus")
    with pytest.raises(NotFoundError):
        await service.save_feedback("missing", "up")


@pytest.mark.asyncio
async def test_schedule_followup_clamps_days_into_range():
    repo = _repo([_lead("j1")])
    service = LeadService(repo)
    await service.schedule_followup("j1", 0)      # falsy -> the 5-day default
    await service.schedule_followup("j1", -3)     # negative -> clamped up to 1
    await service.schedule_followup("j1", 9999)   # -> clamped down to 60
    await service.schedule_followup("j1", 7)      # in range -> untouched
    followups = [c for c in repo._store["calls"] if c[0] == "followup"]
    from datetime import datetime

    spans = [(datetime.fromisoformat(c[3]) - datetime.fromisoformat(c[2])).days for c in followups]
    assert spans == [5, 1, 60, 7]


@pytest.mark.asyncio
async def test_schedule_followup_raises_for_a_missing_lead():
    with pytest.raises(NotFoundError):
        await LeadService(_repo()).schedule_followup("missing", 5)


# ---------------------------------------------------------------- manual leads


@pytest.mark.asyncio
async def test_manual_lead_requires_text_or_url():
    with pytest.raises(ValidationError):
        await LeadService(_repo()).create_manual_lead("   ", "")


@pytest.mark.asyncio
async def test_manual_lead_is_saved_and_returned():
    repo = _repo()
    lead = await LeadService(repo).create_manual_lead(
        "Staff Engineer\nCompany: Acme\nPython", "https://acme.com/jobs/1"
    )
    assert lead["kind"] == "job"
    assert repo._store["leads"], "the lead must be persisted"


@pytest.mark.asyncio
async def test_manual_lead_survives_a_failing_feedback_ranker():
    """Ranking is an enhancement — a slow/failed rank must not lose the paste."""
    class Ranking:
        async def apply_feedback(self, _lead, _examples):
            raise RuntimeError("ranker down")

    repo = _repo()
    lead = await LeadService(repo, Ranking()).create_manual_lead("Engineer at Acme", "https://a/1")
    assert lead["source_meta"]["feedback_learning_error"] == "ranker down"
    assert repo._store["leads"]


@pytest.mark.asyncio
async def test_manual_lead_rejects_a_non_job_paste(monkeypatch):
    monkeypatch.setattr("leads.service.manual_lead_from_text", lambda *a, **k: {"kind": "contact"})
    with pytest.raises(UnprocessableError):
        await LeadService(_repo()).create_manual_lead("hello", "")


# --------------------------------------------------------------------- assets


def test_versioned_assets_groups_by_version_newest_first(tmp_path):
    for name in ("j1_v1.pdf", "j1_v2.pdf", "j1_cl_v2.pdf", "unrelated.pdf", "j2_v1.pdf"):
        (tmp_path / name).write_bytes(b"%PDF")
    versions = versioned_assets("j1", str(tmp_path))
    assert [v["version"] for v in versions] == [2, 1]
    assert "cover_letter" in versions[0] and "resume" in versions[0]
    assert "cover_letter" not in versions[1]


def test_versioned_assets_is_empty_for_a_missing_directory():
    assert versioned_assets("j1", "/definitely/not/here") == []


@pytest.mark.asyncio
async def test_resolve_pdf_returns_the_stored_resume(tmp_path):
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF")
    repo = _repo([_lead("j1", resume_asset=str(pdf))])
    path, filename = await LeadService(repo).resolve_pdf("j1", "resume", None)
    assert path == str(pdf) and filename == "j1_resume.pdf"


@pytest.mark.asyncio
async def test_resolve_pdf_reports_which_document_is_missing(tmp_path):
    repo = _repo([_lead("j1", resume_asset=str(tmp_path / "gone.pdf"))])
    service = LeadService(repo)
    with pytest.raises(NotFoundError, match="Resume not generated yet"):
        await service.resolve_pdf("j1", "resume", None)
    with pytest.raises(NotFoundError, match="Cover letter not generated yet"):
        await service.resolve_pdf("j1", "cover_letter", None)


@pytest.mark.asyncio
async def test_resolve_pdf_finds_a_specific_version(tmp_path):
    (tmp_path / "j1_v3.pdf").write_bytes(b"%PDF")
    repo = _repo([_lead("j1", resume_asset=str(tmp_path / "j1_v1.pdf"))])
    path, _ = await LeadService(repo).resolve_pdf("j1", "resume", 3)
    assert path.endswith("j1_v3.pdf")


# -------------------------------------------------------------------- cleanup


@pytest.mark.asyncio
async def test_cleanup_broadcasts_start_updates_and_done():
    sent: list[dict] = []

    async def notify(message):
        sent.append(message)

    repo = _repo([_lead("j1")])
    result = await LeadService(repo).cleanup(limit=50, dry_run=False, notify=notify)

    assert result["candidates"] == 2
    events = [m.get("event") for m in sent]
    assert events[0] == "cleanup_start" and events[-1] == "cleanup_done"
    assert any(m.get("type") == "LEAD_UPDATED" for m in sent)


@pytest.mark.asyncio
async def test_cleanup_dry_run_does_not_push_lead_updates():
    sent: list[dict] = []

    async def notify(message):
        sent.append(message)

    await LeadService(_repo([_lead("j1")])).cleanup(limit=50, dry_run=True, notify=notify)
    assert not any(m.get("type") == "LEAD_UPDATED" for m in sent)
    assert "would discard" in sent[-1]["msg"]
