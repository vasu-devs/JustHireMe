from __future__ import annotations

import json
from datetime import datetime, timezone

from data.sqlite.connection import connect, init_sql
from data.sqlite.opportunities import (
    create_scan_run,
    finish_scan_run,
    candidate_funnel_metrics,
    candidate_application_profile_status,
    get_candidate_profile,
    get_candidate_application_profile,
    get_latest_scan_run,
    link_lead_to_opportunity,
    list_candidate_events,
    list_candidate_source_health,
    list_canonical_opportunities,
    list_candidate_profiles,
    list_candidate_opportunities,
    save_candidate_profile,
    save_candidate_source_health,
    save_candidate_application_profile,
    record_candidate_event,
    reconcile_missing_direct_opportunities,
    save_candidate_decisions,
    save_pipeline_result,
)
from opportunities.eligibility import CandidateConstraints
from opportunities.pipeline import process_leads


NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def _pipeline():
    return process_leads(
        [{
            "title": "Software Engineering Intern",
            "company": "Acme",
            "url": "https://job-boards.greenhouse.io/acme/jobs/123",
            "platform": "greenhouse",
            "location": "Bengaluru, India",
            "description": "Paid software internship for 2027 graduates building Python APIs.",
            "source_meta": {"slug": "acme", "job_id": "123", "source_target_id": "greenhouse:acme"},
        }],
        candidate=CandidateConstraints(candidate_id="friend-1", graduation_year=2027),
        observed_at=NOW,
    )


def test_pipeline_persistence_is_idempotent_and_keeps_decisions_local(tmp_path) -> None:
    db_path = str(tmp_path / "opportunities.db")
    result = _pipeline()
    save_pipeline_result(result, candidate_id="friend-1", db_path=db_path)
    save_pipeline_result(result, candidate_id="friend-1", db_path=db_path)

    conn = connect(db_path)
    try:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "opportunity_source_records",
                "canonical_opportunities",
                "opportunity_observations",
                "candidate_opportunity_decisions",
            )
        }
        payload = conn.execute("SELECT payload_json FROM opportunity_source_records").fetchone()[0]
    finally:
        conn.close()
    assert counts == {
        "opportunity_source_records": 1,
        "canonical_opportunities": 1,
        "opportunity_observations": 1,
        "candidate_opportunity_decisions": 1,
    }
    assert "Paid software internship" in payload

    # Historical rule versions stay auditable but must never duplicate or
    # override the newest candidate queue decision.
    opportunity_id = result.opportunities[0].opportunity.opportunity_id
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO candidate_opportunity_decisions(
                tenant_id,candidate_id,opportunity_id,rule_version,eligibility,decision,payload_json
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                "00000000-0000-0000-0000-000000000001", "friend-1", opportunity_id,
                "1", "ineligible", "skip", '{"decision":"skip"}',
            ),
        )
        conn.commit()
    finally:
        conn.close()

    queue = list_candidate_opportunities("friend-1", decision="apply_now", db_path=db_path)
    assert len(queue) == 1
    assert queue[0]["applicability"]["decision"] == "apply_now"


def test_decision_only_rescore_does_not_rewrite_canonical_identity(tmp_path) -> None:
    db_path = str(tmp_path / "decision-only.db")
    result = _pipeline()
    save_pipeline_result(result, candidate_id="friend-1", db_path=db_path)
    conn = connect(db_path)
    try:
        canonical_before = conn.execute(
            "SELECT * FROM canonical_opportunities"
        ).fetchall()
        aliases_before = conn.execute(
            "SELECT * FROM opportunity_identity_aliases ORDER BY identity_key"
        ).fetchall()
    finally:
        conn.close()

    assert save_candidate_decisions(
        result,
        candidate_id="friend-1",
        db_path=db_path,
    ) == {"decisions": 1}

    conn = connect(db_path)
    try:
        assert conn.execute("SELECT * FROM canonical_opportunities").fetchall() == canonical_before
        assert conn.execute(
            "SELECT * FROM opportunity_identity_aliases ORDER BY identity_key"
        ).fetchall() == aliases_before
    finally:
        conn.close()


def test_proven_syndicated_duplicates_consolidate_history_to_stable_id(tmp_path) -> None:
    db_path = str(tmp_path / "syndicated-merge.db")
    candidate = CandidateConstraints(candidate_id="friend-1", graduation_year=2027)
    body = (
        "Canonical builds Ubuntu for public cloud, data science, AI, and IoT. "
        "Junior kernel engineers write high quality C and Rust, ship security patches, "
        "test drivers, and collaborate with a distributed engineering team. " * 8
    )
    direct_lead = {
        "title": "Junior Linux Kernel Engineer - Ubuntu",
        "company": "Canonical",
        "url": "https://job-boards.greenhouse.io/canonical/jobs/5370815",
        "platform": "greenhouse",
        "location": "Home Based - Worldwide",
        "description": body,
    }
    aggregate_lead = {
        "title": "Junior Linux Kernel Engineer - Ubuntu",
        "company": "canonical",
        "url": "https://himalayas.app/companies/canonical/jobs/junior-linux-kernel-engineer-ubuntu",
        "platform": "himalayas",
        "location": "Canada, Germany, India, United Kingdom, United States",
        "description": (
            body
            + " Originally posted on Himalayas Location: Canada, Germany, India "
            + "Workplace: remote Employment type: Full Time"
        ),
    }
    direct = process_leads([direct_lead], candidate=candidate, observed_at=NOW)
    # Seed the historical duplicate with materially different content to model
    # a legacy index created before cross-scan syndication reconciliation.
    legacy_aggregate_lead = {
        **aggregate_lead,
        "description": "A legacy, incomplete aggregator excerpt about an unrelated team. " * 20,
    }
    aggregate = process_leads([legacy_aggregate_lead], candidate=candidate, observed_at=NOW)
    save_pipeline_result(direct, candidate_id="friend-1", db_path=db_path)
    save_pipeline_result(aggregate, candidate_id="friend-1", db_path=db_path)
    stable_id = direct.opportunities[0].opportunity.opportunity_id
    duplicate_id = aggregate.opportunities[0].opportunity.opportunity_id
    assert stable_id != duplicate_id

    init_sql(db_path)
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO leads(job_id,title,tenant_id,opportunity_id) VALUES(?,?,?,?)",
            ("lead-syndicated", "Kernel role", "00000000-0000-0000-0000-000000000001", duplicate_id),
        )
        conn.commit()
    finally:
        conn.close()

    record_candidate_event(
        "friend-1",
        duplicate_id,
        "tracked",
        occurred_at=NOW.isoformat(),
        db_path=db_path,
    )

    combined = process_leads(
        [direct_lead, aggregate_lead],
        candidate=candidate,
        observed_at=NOW,
    )
    assert len(combined.opportunities) == 1
    save_pipeline_result(combined, candidate_id="friend-1", db_path=db_path)

    conn = connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM canonical_opportunities").fetchone()[0] == 1
        # The legacy excerpt remains immutable alongside the later authoritative
        # and corrected aggregator observations.
        assert conn.execute("SELECT COUNT(*) FROM opportunity_observations").fetchone()[0] == 3
        target_id = conn.execute("SELECT opportunity_id FROM canonical_opportunities").fetchone()[0]
        assert target_id in {stable_id, duplicate_id}
        assert {
            row[0] for row in conn.execute("SELECT opportunity_id FROM opportunity_identity_aliases")
        } == {target_id}
        assert conn.execute(
            "SELECT opportunity_id FROM leads WHERE job_id=?", ("lead-syndicated",)
        ).fetchone()[0] == target_id
        assert conn.execute(
            "SELECT opportunity_id FROM candidate_opportunity_events"
        ).fetchone()[0] == target_id
        assert conn.execute(
            "SELECT COUNT(DISTINCT opportunity_id) FROM candidate_opportunity_decisions"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_reordered_syndication_reconciles_against_existing_history(tmp_path) -> None:
    db_path = str(tmp_path / "historical-reordered.db")
    candidate = CandidateConstraints(candidate_id="friend-1", graduation_year=2027)
    sections = [
        "Netomi builds customer experience automation with artificial intelligence. " * 14,
        "The engineer designs TypeScript services, Python APIs, and distributed systems. " * 14,
        "The role owns testing, observability, code reviews, and production reliability. " * 14,
    ]
    aggregate_lead = {
        "title": "SDE I FullStack",
        "company": "netomi",
        "url": "https://himalayas.app/companies/netomi/jobs/sde-i-fullstack",
        "platform": "himalayas",
        "location": "India; Remote",
        "description": (
            "".join(reversed(sections))
            + " Originally posted on Himalayas Location: India Workplace: remote"
        ),
    }
    direct_lead = {
        "title": "SDE I FullStack",
        "company": "Netomi",
        "url": "https://jobs.lever.co/netomi/abc",
        "platform": "lever",
        "location": "Gurugram, India",
        "description": "".join(sections),
    }
    aggregate = process_leads([aggregate_lead], candidate=candidate, observed_at=NOW)
    direct = process_leads([direct_lead], candidate=candidate, observed_at=NOW)
    first = save_pipeline_result(aggregate, candidate_id="friend-1", db_path=db_path)
    second = save_pipeline_result(direct, candidate_id="friend-1", db_path=db_path)

    conn = connect(db_path)
    try:
        payload = conn.execute(
            "SELECT payload_json FROM canonical_opportunities"
        ).fetchone()[0]
        canonical = json.loads(payload)
        counts = {
            "canonicals": conn.execute("SELECT COUNT(*) FROM canonical_opportunities").fetchone()[0],
            "observations": conn.execute("SELECT COUNT(*) FROM opportunity_observations").fetchone()[0],
        }
    finally:
        conn.close()

    assert first["provider_yield"]["himalayas"]["new_canonical_opportunities"] == 1
    assert second["provider_yield"]["lever"]["new_canonical_opportunities"] == 0
    assert counts == {"canonicals": 1, "observations": 2}
    assert canonical["canonical_apply_url"] == direct_lead["url"]
    assert any(key.startswith("syndicated:") for key in canonical["identity_keys"])


def test_persistence_keeps_distinct_same_tenant_requisition_ids(tmp_path) -> None:
    db_path = str(tmp_path / "provider-identity.db")
    candidate = CandidateConstraints(candidate_id="friend-1", graduation_year=2027)
    common = {
        "title": "Software Engineering Intern",
        "company": "Bosch",
        "platform": "smartrecruiters",
        "location": "Bengaluru, India",
        "description": "Paid software internship building Python APIs.",
    }
    first = process_leads(
        [{
            **common,
            "url": "https://jobs.smartrecruiters.com/BoschGroup/111",
            "source_meta": {"slug": "BoschGroup", "job_id": "111"},
        }],
        candidate=candidate,
        observed_at=NOW,
    )
    second = process_leads(
        [{
            **common,
            "url": "https://jobs.smartrecruiters.com/BoschGroup/222",
            "source_meta": {"slug": "BoschGroup", "job_id": "222"},
        }],
        candidate=candidate,
        observed_at=NOW,
    )

    save_pipeline_result(first, candidate_id="friend-1", db_path=db_path)
    save_pipeline_result(second, candidate_id="friend-1", db_path=db_path)

    conn = connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM canonical_opportunities").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM opportunity_observations").fetchone()[0] == 2
        assert conn.execute(
            "SELECT COUNT(*) FROM opportunity_identity_aliases WHERE identity_key LIKE 'provider:%'"
        ).fetchone()[0] == 2
    finally:
        conn.close()


def test_historical_aggregator_cannot_bridge_two_same_tenant_ids_in_one_save(tmp_path) -> None:
    db_path = str(tmp_path / "historical-provider-bridge.db")
    candidate = CandidateConstraints(candidate_id="friend-1", graduation_year=2027)
    body = (
        "Drivetrain builds an AI financial planning platform. Engineering interns "
        "prototype RAG workflows, production APIs, tests, and observable services. " * 12
    )
    aggregate = process_leads([{
        "title": "Engineering Intern - Gen AI",
        "company": "Drivetrain",
        "url": "https://himalayas.app/companies/drivetrain/jobs/gen-ai-intern",
        "platform": "himalayas",
        "location": "India",
        "description": body + " Originally posted on Himalayas Location: India Workplace: remote",
    }], candidate=candidate, observed_at=NOW)
    save_pipeline_result(aggregate, candidate_id="friend-1", db_path=db_path)

    direct = process_leads([
        {
            "title": "Engineering Intern - Gen AI",
            "company": "drivetrain",
            "url": "https://jobs.lever.co/drivetrain/india-one",
            "platform": "lever",
            "location": "India",
            "description": body,
            "source_meta": {"slug": "drivetrain", "job_id": "india-one"},
        },
        {
            "title": "Engineering Intern - Gen AI",
            "company": "drivetrain",
            "url": "https://jobs.lever.co/drivetrain/india-two",
            "platform": "lever",
            "location": "India",
            "description": body,
            "source_meta": {"slug": "drivetrain", "job_id": "india-two"},
        },
    ], candidate=candidate, observed_at=NOW)
    assert len(direct.opportunities) == 2

    save_pipeline_result(direct, candidate_id="friend-1", db_path=db_path)

    conn = connect(db_path)
    try:
        payloads = [
            json.loads(row[0])
            for row in conn.execute("SELECT payload_json FROM canonical_opportunities")
        ]
    finally:
        conn.close()

    assert len(payloads) == 2
    lever_ids = []
    for payload in payloads:
        lever_ids.append({
            observation["provider_requisition_id"]
            for observation in payload["observations"]
            if observation["provider"] == "lever"
        })
    assert sorted(lever_ids, key=lambda values: sorted(values)) == [
        {"india-one"},
        {"india-two"},
    ]


def test_existing_lead_can_link_to_canonical_opportunity(tmp_path) -> None:
    db_path = str(tmp_path / "link.db")
    init_sql(db_path)
    result = _pipeline()
    save_pipeline_result(result, candidate_id="friend-1", db_path=db_path)
    opportunity_id = result.opportunities[0].opportunity.opportunity_id
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO leads(job_id,title,tenant_id) VALUES(?,?,?)",
            ("lead-1", "Intern", "00000000-0000-0000-0000-000000000001"),
        )
        conn.commit()
    finally:
        conn.close()

    link_lead_to_opportunity("lead-1", opportunity_id, db_path=db_path)
    conn = connect(db_path)
    try:
        linked = conn.execute("SELECT opportunity_id FROM leads WHERE job_id='lead-1'").fetchone()[0]
    finally:
        conn.close()
    assert linked == opportunity_id


def test_candidate_constraints_and_scan_health_persist_locally(tmp_path) -> None:
    db_path = str(tmp_path / "candidate.db")
    profile = CandidateConstraints(
        candidate_id="friend-2",
        graduation_year=2026,
        accepted_india_cities=["Bengaluru", "Pune"],
        spoken_languages=["English", "Hindi"],
    ).model_dump(mode="json")
    save_candidate_profile("friend-2", profile, db_path=db_path)
    assert get_candidate_profile("friend-2", db_path=db_path) == profile
    assert list_candidate_profiles(db_path=db_path)[0]["candidate_id"] == "friend-2"

    run_id = create_scan_run("friend-2", target_count=3, db_path=db_path)
    save_candidate_source_health(
        "friend-2",
        {
            "target_id": "greenhouse:acme",
            "status": "failure",
            "attempted_at": NOW.isoformat(),
        },
        db_path=db_path,
    )
    assert list_candidate_source_health("friend-2", db_path=db_path)[0]["status"] == "failure"
    finish_scan_run(
        run_id,
        "friend-2",
        status="completed",
        payload={"run_id": run_id, "candidate_id": "friend-2", "status": "completed", "opportunities": 1},
        source_health=[{
            "target_id": "greenhouse:acme",
            "status": "success",
            "attempted_at": NOW.isoformat(),
        }],
        db_path=db_path,
    )
    assert get_latest_scan_run("friend-2", db_path=db_path)["opportunities"] == 1
    health = list_candidate_source_health("friend-2", db_path=db_path)
    assert len(health) == 1
    assert health[0]["target_id"] == "greenhouse:acme"
    assert health[0]["status"] == "success"
    conn = connect(db_path)
    try:
        health_count = conn.execute("SELECT COUNT(*) FROM opportunity_source_health").fetchone()[0]
    finally:
        conn.close()
    assert health_count == 1


def test_candidate_application_profile_is_private_and_candidate_scoped(tmp_path) -> None:
    db_path = str(tmp_path / "application-profile.db")
    profile = {
        "n": "Pilot Candidate",
        "s": "Backend engineer building production APIs.",
        "skills": [{"n": "Python"}],
        "projects": [{"title": "API platform"}],
        "identity": {"email": "friend@example.test", "phone": "+91 98765 43210"},
    }
    status = save_candidate_application_profile("friend-1", profile, db_path=db_path)
    assert status["ready"] is True
    assert status["skill_count"] == 1
    assert status["project_count"] == 1
    assert "Pilot Candidate" not in str(status)
    assert get_candidate_application_profile("friend-1", db_path=db_path) == profile
    assert get_candidate_application_profile("friend-2", db_path=db_path) == {}
    assert candidate_application_profile_status("friend-2", db_path=db_path) == {
        "candidate_id": "friend-2",
        "ready": False,
    }


def test_candidate_outcomes_are_immutable_idempotent_and_drive_funnel_metrics(tmp_path) -> None:
    db_path = str(tmp_path / "outcomes.db")
    result = _pipeline()
    save_pipeline_result(result, candidate_id="friend-1", db_path=db_path)
    opportunity_id = result.opportunities[0].opportunity.opportunity_id

    tracked = record_candidate_event(
        "friend-1", opportunity_id, "tracked",
        occurred_at="2026-08-24T12:00:00+00:00",
        idempotency_key="pipeline-track",
        db_path=db_path,
    )
    retry = record_candidate_event(
        "friend-1", opportunity_id, "tracked",
        occurred_at="2026-08-24T12:05:00+00:00",
        idempotency_key="pipeline-track",
        db_path=db_path,
    )
    assert retry["event_id"] == tracked["event_id"]
    for index, event_type in enumerate(("application_submitted", "recruiter_reply", "interview", "offer"), start=1):
        record_candidate_event(
            "friend-1", opportunity_id, event_type,
            occurred_at=f"2026-08-2{4 + index}T12:00:00+00:00",
            db_path=db_path,
        )

    events = list_candidate_events("friend-1", db_path=db_path)
    assert len(events) == 5
    metrics = candidate_funnel_metrics("friend-1", db_path=db_path)
    assert metrics["funnel"] == {
        "tracked": 1,
        "application_started": 0,
        "application_submitted": 1,
        "outreach_sent": 0,
        "meaningful_contacts": 1,
        "screening_processes": 1,
        "interviews": 1,
        "offers": 1,
        "rejections": 0,
        "withdrawn": 0,
    }
    assert metrics["rates"]["interviews_per_20_applications"] == 20.0
    assert metrics["source_outcomes"] == [{
        "provider": "greenhouse",
        "submitted": 1,
        "meaningful_contacts": 1,
        "interviews": 1,
        "offers": 1,
    }]


def test_successful_direct_scan_disappearance_closes_but_seen_or_failed_targets_do_not(tmp_path) -> None:
    db_path = str(tmp_path / "reconcile.db")
    result = _pipeline()
    save_pipeline_result(result, candidate_id="friend-1", db_path=db_path)
    source_record_id = result.source_records[0].source_record_id
    opportunity_id = result.opportunities[0].opportunity.opportunity_id

    assert reconcile_missing_direct_opportunities(
        successful_target_ids=["greenhouse:acme"],
        seen_source_record_ids=[source_record_id],
        observed_at="2026-08-25T00:00:00+00:00",
        db_path=db_path,
    ) == []
    assert reconcile_missing_direct_opportunities(
        successful_target_ids=["greenhouse:other"],
        seen_source_record_ids=[],
        observed_at="2026-08-25T01:00:00+00:00",
        db_path=db_path,
    ) == []

    closed = reconcile_missing_direct_opportunities(
        successful_target_ids=["greenhouse:acme"],
        seen_source_record_ids=[],
        observed_at="2026-08-25T02:00:00+00:00",
        db_path=db_path,
    )
    assert closed == [opportunity_id]
    canonical = list_canonical_opportunities(db_path=db_path)[0]
    assert canonical["lifecycle"]["status"] == "closed"
    assert "absent_from_successful_direct_scan:2026-08-25T02:00:00+00:00" in canonical["lifecycle"]["evidence"]
