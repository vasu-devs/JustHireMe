from __future__ import annotations

import asyncio

from evals.public_review_queue import (
    collect_review_queue,
    make_review_entry,
    select_diverse_boards,
    select_diverse_entries,
)


def _company(provider: str, slug: str) -> dict:
    return {
        "company_id": f"{provider}:{slug}",
        "name": slug.title(),
        "provider": provider,
        "scan_target": f"ats:{provider}:{slug}",
        "careers_url": f"https://example.test/{slug}",
        "inventory_source": "unit",
    }


def test_board_selection_round_robins_providers() -> None:
    records = [
        _company("greenhouse", "one"),
        _company("greenhouse", "two"),
        _company("ashby", "three"),
        _company("lever", "four"),
        _company("workday", "five"),
    ]
    selected = select_diverse_boards(records, 4)
    assert {record["provider"] for record in selected} == {"greenhouse", "ashby", "lever", "workday"}


def test_review_entry_keeps_excerpt_hash_and_proposed_label_honest() -> None:
    description = "Remote worldwide paid software internship. " + ("Build Python services. " * 100)
    entry = make_review_entry(
        {
            "title": "Software Engineering Intern",
            "company": "Acme",
            "url": "https://example.test/jobs/1",
            "platform": "greenhouse",
            "location": "Remote — Worldwide",
            "description": description,
        },
        _company("greenhouse", "acme"),
        observed_at="2026-08-24T00:00:00Z",
    )
    assert entry["review_status"] == "unreviewed"
    assert entry["automated_labels_are_proposed"] is True
    assert "expected" not in entry
    assert entry["proposed_category"] == "remote_india_eligible"
    assert len(entry["posting"]["description_excerpt"]) <= 600
    assert len(entry["posting"]["description_sha256"]) == 64
    assert entry["posting"]["description_excerpt"] != description


def test_collection_deduplicates_urls_and_records_source_failures() -> None:
    records = [_company("greenhouse", "ok"), _company("lever", "broken")]

    async def fake_scraper(target: str) -> list[dict]:
        if "broken" in target:
            raise RuntimeError("provider unavailable")
        lead = {
            "title": "Graduate Software Engineer",
            "company": "Acme",
            "url": "https://example.test/jobs/42",
            "platform": "greenhouse",
            "location": "Bengaluru, India",
            "description": "Entry-level software engineering role for 2027 graduates.",
        }
        return [lead, dict(lead)]

    result = asyncio.run(collect_review_queue(records, scraper=fake_scraper, max_records=10))
    assert len(result.entries) == 1
    assert result.entries[0]["review_status"] == "unreviewed"
    assert len(result.errors) == 1
    assert "provider unavailable" in result.errors[0]
    assert result.boards_requested == 2
    assert result.boards_attempted == 2
    assert result.boards_succeeded == 1
    assert result.candidate_pool_size == 1


def test_generic_technical_roles_do_not_enter_early_career_queue() -> None:
    records = [_company("greenhouse", "acme")]

    async def fake_scraper(_target: str) -> list[dict]:
        return [
            {
                "title": "Software Engineer",
                "company": "Acme",
                "url": "https://example.test/jobs/general",
                "location": "Remote",
                "description": "Build distributed systems from anywhere.",
            },
            {
                "title": "Software Engineering Intern",
                "company": "Acme",
                "url": "https://example.test/jobs/intern",
                "location": "Bengaluru, India",
                "description": "Paid internship for final-year students.",
            },
        ]

    result = asyncio.run(collect_review_queue(records, scraper=fake_scraper, max_records=10))
    assert [entry["posting"]["url"] for entry in result.entries] == [
        "https://example.test/jobs/intern"
    ]


def test_description_office_mentions_do_not_override_posting_location() -> None:
    entry = make_review_entry(
        {
            "title": "AI Engineer Intern",
            "company": "Acme",
            "url": "https://example.test/jobs/sf-intern",
            "platform": "greenhouse",
            "location": "San Francisco, CA",
            "description": "Our global company also has teams in Bengaluru, India.",
        },
        _company("greenhouse", "acme"),
        observed_at="2026-08-24T00:00:00Z",
    )
    assert entry["proposed_category"] == "closed_or_ambiguous"
    assert "india_signal" not in entry["proposed_tags"]


def test_collection_scans_all_boards_before_diverse_selection() -> None:
    records = [_company("ashby", "large"), _company("lever", "small")]

    async def fake_scraper(target: str) -> list[dict]:
        slug = "large" if "large" in target else "small"
        count = 20 if slug == "large" else 1
        return [
            {
                "title": "Software Engineering Intern",
                "company": slug.title(),
                "url": f"https://example.test/{slug}/{index}",
                "location": "Bengaluru, India",
                "description": "Internship for computer science students.",
            }
            for index in range(count)
        ]

    result = asyncio.run(
        collect_review_queue(
            records,
            scraper=fake_scraper,
            max_records=4,
            max_per_board=10,
            max_per_company=3,
        )
    )
    assert result.boards_attempted == 2
    assert result.boards_succeeded == 2
    assert result.candidate_pool_size == 11
    assert {entry["company_benchmark_id"] for entry in result.entries} == {
        "ashby:large",
        "lever:small",
    }


def test_entry_selection_round_robins_categories_and_companies() -> None:
    entries: list[dict] = []
    for company_id, category, count in (
        ("greenhouse:one", "india_internship", 5),
        ("lever:two", "india_internship", 1),
        ("ashby:three", "seniority_trap", 5),
    ):
        entries.extend(
            {
                "company_benchmark_id": company_id,
                "proposed_category": category,
                "posting": {"url": f"https://example.test/{company_id}/{index}"},
            }
            for index in range(count)
        )
    selected = select_diverse_entries(entries, 4, max_per_company=2)
    assert {entry["proposed_category"] for entry in selected} == {
        "india_internship",
        "seniority_trap",
    }
    assert {entry["company_benchmark_id"] for entry in selected} == {
        "greenhouse:one",
        "lever:two",
        "ashby:three",
    }


def test_entry_selection_caps_negative_category_to_corpus_target() -> None:
    entries = [
        {
            "company_benchmark_id": f"ashby:company-{index % 4}",
            "proposed_category": "seniority_trap",
            "posting": {"url": f"https://example.test/senior/{index}"},
        }
        for index in range(100)
    ]
    selected = select_diverse_entries(entries, 100, max_per_company=100)
    assert len(selected) == 30
