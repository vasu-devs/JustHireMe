from __future__ import annotations

from datetime import datetime, timedelta, timezone

from data.sqlite import connection as sqlite_connection
from opportunities.models import SourceRecord
from scripts.audit_live_handoffs import (
    _latest_records,
    assess_handoff,
    authoritative_application_available,
)

sqlite3 = sqlite_connection.sqlite3


def test_live_handoff_requires_exact_title_and_apply_control() -> None:
    result = assess_handoff(
        title="Cloud Infrastructure Engineer (LLM Routing)",
        response_html=(
            "<h2>Cloud Infrastructure Engineer (LLM Routing)</h2>"
            '<a href="mailto:careers@example.invalid">Apply Now</a>'
        ),
        status_code=200,
    )
    assert result == {
        "http_status": 200,
        "exact_title_present": True,
        "apply_control_present": True,
        "unavailable_marker_present": False,
    }


def test_live_handoff_normalizes_provider_formatting_whitespace_in_title() -> None:
    result = assess_handoff(
        title="WEB / APP DEVELOPMENT WITH STIPEND",
        response_html=(
            '<h3 class="job-title">WEB /  APP DEVELOPMENT WITH STIPEND</h3>'
            '<button id="applyBtn">Apply Now</button>'
        ),
        status_code=200,
    )

    assert result["exact_title_present"] is True
    assert result["apply_control_present"] is True


def test_live_handoff_detects_closed_page_even_with_stale_apply_text() -> None:
    result = assess_handoff(
        title="Software Intern",
        response_html="<h1>Software Intern</h1><p>This position has been filled.</p><p>Apply Now</p>",
        status_code=200,
    )
    assert result["unavailable_marker_present"] is True


def test_live_handoff_accepts_authoritative_dynamic_application_state() -> None:
    result = assess_handoff(
        title="Software Intern",
        response_html='<meta property="og:title" content="Software Intern">',
        status_code=200,
        application_available=True,
    )

    assert result["exact_title_present"] is True
    assert result["apply_control_present"] is True


def test_live_handoff_accepts_current_ashby_application_url() -> None:
    record = SourceRecord(
        source_record_id="ashby-current",
        source_target_id="ashby:acme",
        provider="ashby",
        provider_tenant="acme",
        source_url="https://jobs.ashbyhq.com/acme/job-1",
        canonical_source_url="https://jobs.ashbyhq.com/acme/job-1",
        apply_url="https://jobs.ashbyhq.com/acme/job-1/application",
        provider_requisition_id="job-1",
        employer_name="Acme",
        title="Software Intern",
        observed_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        public_metadata={
            "is_listed": True,
            "apply_url": "https://jobs.ashbyhq.com/acme/job-1/application",
        },
    )

    assert authoritative_application_available(record) is True

    record.public_metadata["is_listed"] = False
    assert authoritative_application_available(record) is False


def test_live_handoff_accepts_current_smartrecruiters_api_payload() -> None:
    record = SourceRecord(
        source_record_id="smartrecruiters-current",
        source_target_id="smartrecruiters:acme",
        provider="smartrecruiters",
        provider_tenant="acme",
        source_url="https://jobs.smartrecruiters.com/acme/job-1",
        canonical_source_url="https://jobs.smartrecruiters.com/acme/job-1",
        apply_url="https://jobs.smartrecruiters.com/acme/job-1?oga=true",
        provider_requisition_id="job-1",
        employer_name="Acme",
        title="Software Intern",
        observed_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        public_metadata={
            "active": True,
            "api_ref": "https://api.smartrecruiters.com/v1/companies/acme/postings/job-1",
            "apply_url": "https://jobs.smartrecruiters.com/acme/job-1?oga=true",
        },
    )

    assert authoritative_application_available(
        record,
        live_payload={"active": True, "applyUrl": record.apply_url},
    ) is True
    assert authoritative_application_available(
        record,
        live_payload={"active": False, "applyUrl": record.apply_url},
    ) is False


def test_live_handoff_record_selection_can_be_scoped_to_exact_target(tmp_path) -> None:
    path = tmp_path / "index.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE opportunity_source_records (
            source_record_id TEXT,
            source_target_id TEXT,
            provider TEXT,
            provider_tenant TEXT,
            provider_requisition_id TEXT,
            canonical_source_url TEXT,
            observed_at TEXT,
            payload_json TEXT
        )
        """
    )
    rows = (
        ("lever:portcast", "legacy", "one", ""),
        ("lever:portcast", "current", "one", "R1"),
        ("lever:other", "other", "two", "R2"),
    )
    observed = datetime(2026, 8, 26, tzinfo=timezone.utc)
    for index, (target, record_id, url_id, requisition) in enumerate(rows):
        record = SourceRecord(
            source_record_id=record_id,
            source_target_id=target,
            provider="lever",
            provider_tenant=target.split(":", 1)[1],
            source_url=f"https://jobs.example/{url_id}",
            canonical_source_url=f"https://jobs.example/{url_id}",
            apply_url=f"https://jobs.example/{url_id}",
            provider_requisition_id=requisition,
            employer_name=target,
            title=f"Role {record_id}",
            observed_at=observed + timedelta(minutes=index),
        )
        connection.execute(
            "INSERT INTO opportunity_source_records VALUES (?,?,?,?,?,?,?,?)",
            (
                record.source_record_id,
                record.source_target_id,
                record.provider,
                record.provider_tenant,
                record.provider_requisition_id,
                record.canonical_source_url,
                record.observed_at.isoformat(),
                record.model_dump_json(),
            ),
        )
    connection.commit()
    connection.close()

    selected = _latest_records(path, "lever", target_ids=["LEVER:PORTCAST"])

    assert [(record.source_target_id, record.provider_requisition_id) for record in selected] == [
        ("lever:portcast", "R1")
    ]
