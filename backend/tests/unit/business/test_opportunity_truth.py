from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from opportunities.canonicalize import (
    canonicalize_url,
    identity_keys,
    parse_provider_datetime,
    provider_requisition_id,
    source_record_from_lead,
)
from opportunities.deduplicate import canonicalize_observations
from opportunities.lifecycle import resolve_lifecycle
from opportunities.models import ActiveHint, LiveStatus, SourceKind


NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def _lead(url: str, **overrides) -> dict:
    return {
        "title": "Software Engineering Intern",
        "company": "Acme",
        "url": url,
        "platform": "greenhouse",
        "location": "Bengaluru, India",
        "description": "Build Python services with the platform team.",
        **overrides,
    }


def test_canonical_url_removes_tracking_but_keeps_identity_query() -> None:
    url = "http://Job-Boards.Greenhouse.io/acme/jobs/123/?gh_src=camp&utm_campaign=x&gh_jid=123#apply"
    assert canonicalize_url(url) == "https://job-boards.greenhouse.io/acme/jobs/123?gh_jid=123"


def test_smartrecruiters_slug_and_summary_urls_share_a_stable_identity() -> None:
    summary = "https://jobs.smartrecruiters.com/Freshworks/744000143102264"
    detail = (
        "https://jobs.smartrecruiters.com/Freshworks/"
        "744000143102264-specialist-data-platform-engineering?oga=true"
    )
    assert canonicalize_url(summary) == canonicalize_url(detail)
    assert provider_requisition_id(detail, "smartrecruiters") == "744000143102264"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://acme.wd5.myworkdayjobs.com/External/job/India/R4042696", "R4042696"),
        ("https://acme.wd5.myworkdayjobs.com/External/job/India/Intern_R4042696", "R4042696"),
        ("https://acme.wd5.myworkdayjobs.com/External/job/India/Role_JR-202613434", "JR-202613434"),
    ],
)
def test_workday_requisition_identity_handles_real_slugged_urls(url: str, expected: str) -> None:
    assert provider_requisition_id(url, "workday") == expected


def test_source_record_preserves_full_description_and_content_hash() -> None:
    description = "Python systems. " * 500
    record = source_record_from_lead(
        _lead("https://job-boards.greenhouse.io/acme/jobs/123", description=description),
        observed_at=NOW,
        raw_payload={"id": 123, "description": description},
    )
    assert record.provider_requisition_id == "123"
    assert record.description_full == " ".join(description.split())
    assert len(record.description_sha256) == 64
    assert len(record.raw_payload_sha256) == 64
    assert any(key == "provider:greenhouse:123" for key in identity_keys(record))


def test_source_record_retains_bounded_public_metadata_without_private_form_data() -> None:
    record = source_record_from_lead(
        _lead(
            "https://job-boards.greenhouse.io/acme/jobs/123",
            source_meta={
                "slug": "acme",
                "employment_type": "Intern",
                "base_salary": {"currency": "INR", "min": 40_000, "max": 60_000},
                "location_restrictions": ["India", "Singapore"],
                "candidate_email": "must-not-persist@example.test",
                "application_questions": ["must not persist"],
                "access_token": "must-not-persist",
            },
        ),
        observed_at=NOW,
    )

    assert record.public_metadata == {
        "slug": "acme",
        "employment_type": "Intern",
        "base_salary": {"currency": "INR", "min": 40_000, "max": 60_000},
        "location_restrictions": ["India", "Singapore"],
    }


def test_hacker_news_hiring_is_preserved_as_community_evidence() -> None:
    record = source_record_from_lead(
        _lead("https://news.ycombinator.com/item?id=123", platform="hn_hiring"),
        observed_at=NOW,
    )
    assert record.source_kind == SourceKind.COMMUNITY
    assert record.active_hint == ActiveHint.UNKNOWN


def test_exact_provider_identity_merges_sources_and_retains_observations() -> None:
    first = source_record_from_lead(
        _lead("https://boards.greenhouse.io/acme/jobs/123?gh_src=one"),
        observed_at=NOW,
    )
    second = source_record_from_lead(
        _lead("https://job-boards.greenhouse.io/acme/jobs/123?gh_jid=123", description="Updated detail"),
        observed_at=NOW + timedelta(hours=1),
    )
    opportunities = canonicalize_observations([first, second])
    assert len(opportunities) == 1
    assert len(opportunities[0].observations) == 2
    assert "provider:greenhouse:123" in opportunities[0].dedupe_reasons


def test_same_local_requisition_id_at_different_tenants_does_not_merge() -> None:
    first = source_record_from_lead(
        _lead(
            "https://tenant-one.example.test/job/R123",
            platform="workday",
            company="Tenant One",
            source_meta={"slug": "tenant-one", "job_id": "R123"},
        ),
        observed_at=NOW,
    )
    second = source_record_from_lead(
        _lead(
            "https://tenant-two.example.test/job/R123",
            platform="workday",
            company="Tenant Two",
            source_meta={"slug": "tenant-two", "job_id": "R123"},
        ),
        observed_at=NOW,
    )
    assert len(canonicalize_observations([first, second])) == 2


def test_similar_title_different_requisition_does_not_merge_without_exact_content_identity() -> None:
    first = source_record_from_lead(
        _lead("https://job-boards.greenhouse.io/acme/jobs/123"),
        observed_at=NOW,
    )
    second = source_record_from_lead(
        _lead(
            "https://job-boards.greenhouse.io/acme/jobs/456",
            description="Different team, schedule, and requirements.",
        ),
        observed_at=NOW,
    )
    assert len(canonicalize_observations([first, second])) == 2


def test_exact_content_cannot_merge_distinct_ids_in_same_provider_tenant() -> None:
    first = source_record_from_lead(
        _lead(
            "https://jobs.smartrecruiters.com/BoschGroup/111",
            platform="smartrecruiters",
            source_meta={"slug": "BoschGroup", "job_id": "111"},
        ),
        observed_at=NOW,
    )
    second = source_record_from_lead(
        _lead(
            "https://jobs.smartrecruiters.com/BoschGroup/222",
            platform="smartrecruiters",
            source_meta={"slug": "BoschGroup", "job_id": "222"},
        ),
        observed_at=NOW,
    )

    opportunities = canonicalize_observations([first, second])

    assert len(opportunities) == 2
    assert {row.observations[0].provider_requisition_id for row in opportunities} == {"111", "222"}


def test_near_verbatim_aggregator_copy_merges_with_authoritative_role() -> None:
    body = (
        "Canonical builds Ubuntu for public cloud, data science, AI, and IoT. "
        "Every year we select junior engineers to work on the Linux kernel. "
        "You will write high quality C and Rust, ship security patches, test drivers, "
        "and collaborate with a distributed engineering team. " * 8
    )
    direct = source_record_from_lead(
        _lead(
            "https://job-boards.greenhouse.io/canonical/jobs/5370815",
            company="Canonical",
            title="Junior Linux Kernel Engineer - Ubuntu",
            location="Home Based - Worldwide",
            description=body,
        ),
        observed_at=NOW,
    )
    syndicated = source_record_from_lead(
        _lead(
            "https://himalayas.app/companies/canonical/jobs/junior-linux-kernel-engineer-ubuntu",
            platform="himalayas",
            company="canonical",
            title="Junior Linux Kernel Engineer - Ubuntu",
            location="Canada, Germany, India, United Kingdom, United States",
            description=(
                body
                + " Originally posted on Himalayas Location: Canada, Germany, India "
                + "Workplace: remote Employment type: Full Time"
            ),
        ),
        observed_at=NOW + timedelta(hours=1),
    )

    opportunities = canonicalize_observations([direct, syndicated])
    assert len(opportunities) == 1
    assert len(opportunities[0].observations) == 2
    assert any(reason.startswith("syndicated:") for reason in opportunities[0].dedupe_reasons)


def test_near_verbatim_syndication_does_not_merge_disjoint_countries() -> None:
    body = (
        "Drivetrain builds an AI financial planning platform. Engineering interns "
        "prototype RAG workflows, production APIs, tests, and observable services. " * 12
    )
    india = source_record_from_lead(
        _lead(
            "https://himalayas.app/companies/drivetrain/jobs/gen-ai-intern",
            platform="himalayas",
            company="Drivetrain",
            title="Engineering Intern - Gen AI",
            location="India",
            description=body + " Originally posted on Himalayas Location: India Workplace: remote",
        ),
        observed_at=NOW,
    )
    united_states = source_record_from_lead(
        _lead(
            "https://jobs.lever.co/drivetrain/us-role",
            platform="lever",
            company="drivetrain",
            title="Engineering Intern - Gen AI",
            location="United States",
            description=body,
            source_meta={"slug": "drivetrain", "job_id": "us-role", "country": "US"},
        ),
        observed_at=NOW,
    )

    assert len(canonicalize_observations([india, united_states])) == 2


def test_reordered_near_verbatim_aggregator_copy_merges() -> None:
    sections = [
        "Netomi builds customer experience automation with artificial intelligence. " * 14,
        "The engineer designs TypeScript services, Python APIs, and distributed systems. " * 14,
        "The role owns testing, observability, code reviews, and production reliability. " * 14,
    ]
    direct = source_record_from_lead(
        _lead(
            "https://jobs.lever.co/netomi/abc",
            platform="lever",
            company="Netomi",
            title="SDE I FullStack",
            description="".join(sections),
        ),
        observed_at=NOW,
    )
    syndicated = source_record_from_lead(
        _lead(
            "https://himalayas.app/companies/netomi/jobs/sde-i-fullstack",
            platform="himalayas",
            company="netomi",
            title="SDE I FullStack",
            description=(
                "".join(reversed(sections))
                + " Originally posted on Himalayas Location: India Workplace: remote"
            ),
        ),
        observed_at=NOW + timedelta(hours=1),
    )

    opportunities = canonicalize_observations([direct, syndicated])

    assert len(opportunities) == 1
    assert len(opportunities[0].observations) == 2


def test_syndicated_copy_cannot_bridge_distinct_official_requisition_ids() -> None:
    body = (
        "Acme builds public cloud and AI systems. Engineers write Python, test services, "
        "ship security patches, and collaborate with a distributed engineering team. " * 10
    )
    first = source_record_from_lead(
        _lead(
            "https://job-boards.greenhouse.io/acme/jobs/111",
            title="Software Engineer",
            location="Bengaluru, India",
            description=body,
        ),
        observed_at=NOW,
    )
    syndicated = source_record_from_lead(
        _lead(
            "https://himalayas.app/companies/acme/jobs/software-engineer",
            platform="himalayas",
            title="Software Engineer",
            location="India; Remote",
            description=body + " Originally posted on Himalayas Location: India Workplace: remote",
        ),
        observed_at=NOW,
    )
    second = source_record_from_lead(
        _lead(
            "https://job-boards.greenhouse.io/acme/jobs/222",
            title="Software Engineer",
            location="Bengaluru, India",
            description=body,
        ),
        observed_at=NOW,
    )

    opportunities = canonicalize_observations([first, syndicated, second])

    assert len(opportunities) == 2
    assert sorted(len(row.observations) for row in opportunities) == [1, 2]


def test_same_title_with_materially_different_body_is_not_fuzzy_merged() -> None:
    shared = "Acme hires junior software engineers for a global product team. " * 20
    direct = source_record_from_lead(
        _lead(
            "https://job-boards.greenhouse.io/acme/jobs/123",
            description=shared + ("Build payment APIs in Java. " * 30),
        ),
        observed_at=NOW,
    )
    aggregator = source_record_from_lead(
        _lead(
            "https://himalayas.app/companies/acme/jobs/software-engineering-intern",
            platform="himalayas",
            description=shared + ("Build computer vision models in Python. " * 30),
        ),
        observed_at=NOW + timedelta(hours=1),
    )
    assert len(canonicalize_observations([direct, aggregator])) == 2


def test_lifecycle_keeps_unknown_separate_from_active_and_expired() -> None:
    unknown = source_record_from_lead(
        _lead("https://x.test/jobs/1", platform="community"),
        observed_at=NOW,
    )
    assert resolve_lifecycle([unknown], now=NOW).status == LiveStatus.UNKNOWN

    active = unknown.model_copy(update={"active_hint": ActiveHint.ACTIVE})
    assert resolve_lifecycle([active], now=NOW).status == LiveStatus.ACTIVE

    expired = active.model_copy(update={"deadline_at": NOW - timedelta(days=1)})
    result = resolve_lifecycle([expired], now=NOW)
    assert result.status == LiveStatus.EXPIRED
    assert result.last_verified_active_at == NOW


def test_invalid_description_hash_is_rejected() -> None:
    record = source_record_from_lead(_lead("https://x.test/jobs/1"), observed_at=NOW)
    with pytest.raises(ValueError, match="description_sha256"):
        record.model_copy(update={"description_sha256": "0" * 64}).model_validate(
            {**record.model_dump(), "description_sha256": "0" * 64}
        )


def test_relative_provider_date_is_normalized_without_losing_raw_semantics() -> None:
    parsed = parse_provider_datetime("Posted 3 Days Ago", observed_at=NOW)
    assert parsed == NOW - timedelta(days=3)
    record = source_record_from_lead(
        _lead("https://tenant.example.test/job/R123", platform="workday", posted_date="Posted Today"),
        observed_at=NOW,
    )
    assert record.published_at == NOW
    assert record.provider_published_text == "Posted Today"


def test_provider_day_month_name_dates_are_normalized() -> None:
    assert parse_provider_datetime("22-Aug-2026", observed_at=NOW) == datetime(
        2026, 8, 22, tzinfo=timezone.utc
    )
    assert parse_provider_datetime("30 September 2026", observed_at=NOW) == datetime(
        2026, 9, 30, tzinfo=timezone.utc
    )


def test_unparseable_provider_date_stays_raw_and_structured_date_is_unknown() -> None:
    record = source_record_from_lead(
        _lead("https://x.test/jobs/1", posted_date="Sometime this autumn"),
        observed_at=NOW,
    )
    assert record.published_at is None
    assert record.provider_published_text == "Sometime this autumn"
