"""Unified production coverage: company ATSs plus keyless public market feeds."""

from __future__ import annotations

from catalog.company_registry import production_company_targets
from catalog.source_registry import SourceTarget
from discovery.sources.aggregator import scrape_arbeitnow_target, scrape_themuse_target
from discovery.sources.ats import scrape_target as scrape_ats_target
from discovery.sources.rss import (
    scrape_jobicy_api,
    scrape_remoteok,
    scrape_remotive,
    scrape_working_nomads,
    scrape_rss,
)
from discovery.sources.hackernews import scrape_hn_hiring
from discovery.sources.official import (
    scrape_aicte_cse_internships,
    scrape_amazon_india_cse,
    scrape_atlassian_india_cse,
    scrape_deliveroo_india,
    scrape_dell_india_cse,
    scrape_google_india_early_career,
    scrape_ibm_india_early_career,
    scrape_microsoft_india_cse,
    scrape_oracle_india_early_cse,
    scrape_qualcomm_india_early_career,
    scrape_swiggy_india_cse,
    scrape_ycombinator_startups,
    scrape_zeqo_early_career,
)


_MARKET_TARGETS = (
    # Hyreo's public Greenhouse board carries recruiter/client roles (including
    # explicitly named Udaan openings), so it must not be represented as an
    # employer-direct source even though each requisition has a stable apply URL.
    SourceTarget(
        target_id="marketplace:hyreo-greenhouse",
        provider="greenhouse",
        scan_target="ats:greenhouse:hyreo",
    ),
    # A public, high-volume Indian hiring marketplace hosted on Zoho Recruit.
    # It is kept out of the company-direct inventory because many postings are
    # recruiter-mediated or employer-anonymous, while still offering a stable
    # first-party apply surface, publication dates, descriptions and locations.
    SourceTarget(
        target_id="marketplace:testhiring-zohorecruit",
        provider="zohorecruit",
        scan_target="ats:zohorecruit:testhiring:in",
    ),
    # These tenant-branded public boards expose PeoplePlus as the page-title
    # organization. Keep the truthful recruiter/intermediary attribution instead
    # of presenting the listings as employer-direct Quadeye or Spikewell feeds.
    SourceTarget(
        target_id="marketplace:quadeye-peopleplus-zohorecruit",
        provider="zohorecruit",
        scan_target="ats:zohorecruit:quadeye:in",
    ),
    SourceTarget(
        target_id="marketplace:spikewell-peopleplus-zohorecruit",
        provider="zohorecruit",
        scan_target="ats:zohorecruit:spikewell:in",
    ),
    # Recruiter-mediated client roles on Weekday's public Lever board. The
    # source remains marketplace-labelled; Lever exposes stable requisitions,
    # full responsibilities, structured salary/workplace, and a direct apply URL.
    SourceTarget(
        target_id="marketplace:weekdayworks-lever",
        provider="lever",
        scan_target="ats:lever:weekdayworks",
    ),
    SourceTarget(
        target_id="arbeitnow:cse-early-career",
        provider="arbeitnow",
        scan_target=(
            "aggregator:arbeitnow:software developer engineer machine learning "
            "artificial intelligence data devops cloud security cybersecurity qa "
            "automation frontend backend full stack mobile intern internship "
            "graduate junior new grad trainee apprentice@@India"
        ),
    ),
    *(
        SourceTarget(
            target_id=f"{provider}:{target_id}",
            provider=provider,
            scan_target=f"aggregator:{provider}:{query}@@India",
        )
        for provider in ("themuse",)
        for target_id, query in (
            ("software-intern-india", "software engineering intern"),
            ("ai-ml-intern-india", "machine learning AI intern"),
            ("new-grad-india", "software engineer new grad"),
        )
    ),
    SourceTarget(
        target_id="remote:himalayas-intern-india-eligible",
        provider="himalayas",
        scan_target="ats:himalayas:intern-india-eligible",
    ),
    SourceTarget(
        target_id="remote:himalayas-entry-level-full-time-india-eligible",
        provider="himalayas",
        scan_target="ats:himalayas:entry-level-full-time-india-eligible",
    ),
    SourceTarget(target_id="remote:remoteok", provider="remoteok", scan_target="market:remoteok"),
    SourceTarget(
        target_id="remote:remotive-intern",
        provider="remotive",
        scan_target="https://remotive.com/api/remote-jobs?search=intern",
    ),
    SourceTarget(
        target_id="remote:jobicy-intern",
        provider="jobicy",
        scan_target="https://jobicy.com/api/v2/remote-jobs?count=50&tag=intern",
    ),
    SourceTarget(
        target_id="remote:workingnomads",
        provider="workingnomads",
        scan_target="market:workingnomads",
    ),
    SourceTarget(
        target_id="remote:weworkremotely",
        provider="weworkremotely",
        scan_target="https://weworkremotely.com/remote-jobs.rss",
    ),
    SourceTarget(
        target_id="community:hn-hiring",
        provider="hn_hiring",
        scan_target="market:hn-hiring",
    ),
    SourceTarget(
        target_id="startup:ycombinator-india-software",
        provider="ycombinator",
        scan_target="market:ycombinator:india",
    ),
    SourceTarget(
        target_id="startup:ycombinator-remote-software",
        provider="ycombinator",
        scan_target="market:ycombinator:remote",
    ),
    SourceTarget(
        target_id="official:deliveroo-india",
        company_id="deliveroo",
        provider="deliveroo",
        scan_target="market:deliveroo-india",
    ),
    SourceTarget(
        target_id="official:zeqo-early-career",
        company_id="zeqo",
        provider="zeqo",
        scan_target="market:zeqo-early-career",
    ),
    # AICTE's National Internship Portal is an official public marketplace,
    # not an employer-direct board. The adapter admits only paid technical
    # cards, enriches them from public detail pages, and never reads or stores
    # login/application-form data.
    SourceTarget(
        target_id="public:aicte-paid-cse-internships",
        provider="aicte",
        scan_target="market:aicte-paid-cse-internships",
        parser_version="2",
    ),
    SourceTarget(
        target_id="official:ibm-india-early-career",
        company_id="ibm",
        provider="ibm",
        scan_target="market:ibm-india-early-career",
    ),
    SourceTarget(
        target_id="official:amazon-india-cse",
        company_id="amazon",
        provider="amazon",
        scan_target="market:amazon-india-cse",
    ),
    SourceTarget(
        target_id="official:microsoft-india-cse",
        company_id="microsoft",
        provider="microsoft",
        scan_target="market:microsoft-india-cse",
    ),
    SourceTarget(
        target_id="official:google-india-early-career",
        company_id="google",
        provider="google",
        scan_target="market:google-india-early-career",
    ),
    SourceTarget(
        target_id="official:qualcomm-india-early-career",
        company_id="qualcomm",
        provider="qualcomm",
        scan_target="market:qualcomm-india-early-career",
    ),
    SourceTarget(
        target_id="official:atlassian-india-cse",
        company_id="atlassian",
        provider="atlassian",
        scan_target="market:atlassian-india-cse",
    ),
    SourceTarget(
        target_id="official:razorpay-greenhouse",
        company_id="razorpay",
        provider="greenhouse",
        scan_target="ats:greenhouse:razorpaysoftwareprivatelimited",
    ),
    SourceTarget(
        target_id="official:freshworks-smartrecruiters",
        company_id="freshworks",
        provider="smartrecruiters",
        scan_target="ats:smartrecruiters:Freshworks",
    ),
    SourceTarget(
        target_id="official:oracle-india-early-cse",
        company_id="oracle",
        provider="oracle",
        scan_target="market:oracle-india-early-cse",
    ),
    SourceTarget(
        target_id="official:swiggy-india-cse",
        company_id="swiggy",
        provider="swiggy",
        scan_target="market:swiggy-india-cse",
    ),
    SourceTarget(
        target_id="official:dell-india-cse",
        company_id="dell",
        provider="dell",
        scan_target="market:dell-india-cse",
    ),
    SourceTarget(
        target_id="official:boschgroup-smartrecruiters",
        company_id="boschgroup",
        provider="smartrecruiters",
        scan_target="ats:smartrecruiters:BoschGroup:india-cse",
    ),
)


def production_market_targets(*, company_limit: int = 120) -> list[SourceTarget]:
    return [*production_company_targets(limit=company_limit), *_MARKET_TARGETS]


async def scrape_market_target(target: str) -> list[dict]:
    lower = target.lower()
    if lower.startswith("aggregator:arbeitnow:"):
        return await scrape_arbeitnow_target(target)
    if lower.startswith("aggregator:themuse:"):
        return await scrape_themuse_target(target)
    if lower == "market:remoteok":
        return await scrape_remoteok()
    if lower == "market:workingnomads":
        return await scrape_working_nomads()
    if lower == "market:hn-hiring":
        return await scrape_hn_hiring()
    if lower.startswith("market:ycombinator:"):
        return await scrape_ycombinator_startups(lower.rsplit(":", 1)[-1])
    if lower == "market:deliveroo-india":
        return await scrape_deliveroo_india()
    if lower == "market:zeqo-early-career":
        return await scrape_zeqo_early_career()
    if lower == "market:aicte-paid-cse-internships":
        return await scrape_aicte_cse_internships()
    if lower == "market:ibm-india-early-career":
        return await scrape_ibm_india_early_career()
    if lower == "market:amazon-india-cse":
        return await scrape_amazon_india_cse()
    if lower == "market:microsoft-india-cse":
        return await scrape_microsoft_india_cse()
    if lower == "market:google-india-early-career":
        return await scrape_google_india_early_career()
    if lower == "market:qualcomm-india-early-career":
        return await scrape_qualcomm_india_early_career()
    if lower == "market:atlassian-india-cse":
        return await scrape_atlassian_india_cse()
    if lower == "market:oracle-india-early-cse":
        return await scrape_oracle_india_early_cse()
    if lower == "market:swiggy-india-cse":
        return await scrape_swiggy_india_cse()
    if lower == "market:dell-india-cse":
        return await scrape_dell_india_cse()
    if lower.startswith("https://weworkremotely.com/"):
        rows = await scrape_rss(target)
        return [{**row, "workplace": row.get("workplace") or "remote"} for row in rows]
    if lower.startswith("https://remotive.com/api/"):
        return await scrape_remotive(target)
    if lower.startswith("https://jobicy.com/api/"):
        return await scrape_jobicy_api(target)
    return await scrape_ats_target(target)
