from __future__ import annotations

from evals.company_benchmark import (
    collect_company_benchmark,
    load_company_benchmark,
    validate_company_benchmark,
)


def test_existing_source_inventory_can_seed_a_real_benchmark() -> None:
    records = collect_company_benchmark(limit=120)
    assert len(records) >= 100
    assert not validate_company_benchmark(records)
    assert len({record["company_id"] for record in records}) == len(records)
    assert {record["provider"] for record in records} >= {"greenhouse", "ashby", "lever", "workday"}
    assert all(record["review_status"] == "needs_review" for record in records)
    assert all(record["scan_target"].startswith("ats:") for record in records)
    assert any(record["scan_target"].startswith("ats:workday:") for record in records)


def test_checked_in_benchmark_matches_schema() -> None:
    records = load_company_benchmark()
    assert len(records) == 120
    assert not validate_company_benchmark(records)
    assert all(record["careers_url"].startswith("https://") for record in records)
