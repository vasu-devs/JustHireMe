from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from data.sqlite import paid_sources
from data.sqlite.opportunities import list_candidate_opportunities, save_pipeline_result
from opportunities.eligibility import CandidateConstraints
from opportunities.pipeline import process_leads


def test_atomic_reservations_never_exceed_hard_request_cap(tmp_path) -> None:
    db_path = str(tmp_path / "paid-cap.db")

    def reserve(index: int) -> dict:
        return paid_sources.reserve_request(
            "serpapi",
            run_id="run-1",
            target_id=f"target-{index}",
            daily_request_cap=3,
            monthly_request_cap=10,
            db_path=db_path,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(12)))
    assert sum(bool(row["allowed"]) for row in results) == 3
    assert {row.get("reason") for row in results if not row["allowed"]} == {"daily_request_cap"}
    usage = paid_sources.provider_usage("serpapi", db_path=db_path)
    assert usage["requests_today"] == 3
    assert usage["requests_month"] == 3


def test_estimated_spend_cap_rejects_next_request(tmp_path) -> None:
    db_path = str(tmp_path / "paid-spend.db")
    first = paid_sources.reserve_request(
        "adzuna", run_id="run-1", target_id="one",
        daily_request_cap=10, monthly_request_cap=10,
        estimated_cost_usd=0.6, daily_spend_cap_usd=1.0,
        db_path=db_path,
    )
    second = paid_sources.reserve_request(
        "adzuna", run_id="run-1", target_id="two",
        daily_request_cap=10, monthly_request_cap=10,
        estimated_cost_usd=0.6, daily_spend_cap_usd=1.0,
        db_path=db_path,
    )
    assert first["allowed"] is True
    assert second == {
        "allowed": False,
        "reason": "daily_spend_cap",
        "requests_today": 1,
        "requests_month": 1,
        "estimated_spend_today_usd": 0.6,
        "estimated_spend_month_usd": 0.6,
    }


def test_yield_telemetry_aggregates_without_credentials(tmp_path) -> None:
    db_path = str(tmp_path / "paid-yield.db")
    paid_sources.save_scan_yield("run-1", "friend-1", {"jooble": {
        "source_records": 12,
        "canonical_opportunities": 8,
        "new_canonical_opportunities": 5,
        "eligible_opportunities": 4,
        "net_new_eligible_opportunities": 2,
    }}, db_path=db_path)
    usage = paid_sources.provider_usage("jooble", db_path=db_path)
    assert usage["net_new_eligible_yield_percent"] == 50.0
    assert usage["source_records"] == 12


def test_new_aggregator_keeps_existing_canonical_id_and_is_not_net_new(tmp_path) -> None:
    db_path = str(tmp_path / "identity-alias.db")
    candidate = CandidateConstraints(candidate_id="friend-1", graduation_year=2027)
    url = "https://acme.example/jobs/123"
    direct = process_leads([{
        "title": "Software Engineering Intern",
        "company": "Acme",
        "url": url,
        "platform": "greenhouse",
        "location": "Bengaluru, India",
        "description": "Paid software internship for 2027 graduates building Python services.",
        "source_meta": {"job_id": "123"},
    }], candidate=candidate)
    first = save_pipeline_result(direct, candidate_id="friend-1", db_path=db_path)
    original_id = direct.opportunities[0].opportunity.opportunity_id
    assert first["provider_yield"]["greenhouse"]["net_new_eligible_opportunities"] == 1

    paid = process_leads([{
        "title": "Software Engineering Intern",
        "company": "Acme",
        "url": url,
        "platform": "serpapi",
        "location": "Bengaluru, India",
        "description": "Paid software internship for 2027 graduates building Python services.",
        "source_meta": {"id": "google-job-9"},
    }], candidate=candidate)
    second = save_pipeline_result(paid, candidate_id="friend-1", db_path=db_path)
    queue = list_candidate_opportunities("friend-1", db_path=db_path)
    assert len(queue) == 1
    assert queue[0]["opportunity"]["opportunity_id"] == original_id
    providers = {row["provider"] for row in queue[0]["opportunity"]["observations"]}
    assert providers == {"greenhouse", "serpapi"}
    assert second["provider_yield"]["serpapi"]["net_new_eligible_opportunities"] == 0
