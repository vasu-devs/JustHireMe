from __future__ import annotations

import asyncio

from catalog import market_registry


def test_market_registry_combines_company_direct_and_keyless_feeds() -> None:
    targets = market_registry.production_market_targets(company_limit=10)
    providers = {target.provider for target in targets}
    assert {
        "greenhouse", "ashby", "lever", "arbeitnow", "themuse", "himalayas", "remoteok",
        "remotive", "jobicy", "workingnomads", "weworkremotely", "hn_hiring",
        "ycombinator",
        "amazon", "deliveroo", "google", "microsoft", "qualcomm",
        "atlassian", "dell", "oracle", "swiggy",
        "zeqo", "aicte",
    } <= providers
    assert len({target.target_id for target in targets}) == len(targets)
    scan_targets = {target.scan_target for target in targets}
    assert "ats:greenhouse:razorpaysoftwareprivatelimited" in scan_targets
    assert "ats:smartrecruiters:Freshworks" in scan_targets
    assert "ats:smartrecruiters:BoschGroup:india-cse" in scan_targets
    assert "ats:ashby:outmarket" in scan_targets
    assert "ats:lever:merklescience" in scan_targets
    full_scan_targets = {
        target.scan_target
        for target in market_registry.production_market_targets(company_limit=500)
    }
    assert "ats:workday:warnerbros:wd5:directshare:india-cse" in full_scan_targets
    assert "ats:workday:redhat:wd5:Jobs:india-cse" in full_scan_targets
    assert "ats:workday:lilly:wd115:CMP:india-cse" in full_scan_targets
    assert "ats:greenhouse:glance" in full_scan_targets
    assert "ats:lever:weekdayworks" in full_scan_targets
    assert "ats:greenhouse:hyreo" in full_scan_targets
    assert "ats:lever:hevodata" in full_scan_targets
    assert "ats:ashby:sarvam" in full_scan_targets
    assert "ats:lever:portcast" in full_scan_targets
    assert "ats:greenhouse:jumio" in full_scan_targets
    assert "ats:workday:fox:wd1:Domestic:india-cse" in full_scan_targets
    assert "ats:workday:iqvia:wd1:IQVIA:india-cse" in full_scan_targets
    assert "ats:workday:dentsuaegis:wd3:DAN_GLOBAL:india-cse" in full_scan_targets
    assert "ats:lever:drivetrain" in full_scan_targets
    assert "ats:ashby:altimate" in full_scan_targets
    assert "ats:smartrecruiters:Eurofins:india-cse" in full_scan_targets
    assert "ats:smartrecruiters:Wabtec:india-cse" in full_scan_targets
    assert "ats:greenhouse:instawork" in full_scan_targets
    assert "ats:greenhouse:mfsgtechnologiesindia" in full_scan_targets
    assert "ats:greenhouse:yipitdatajobs" in full_scan_targets
    assert (
        "ats:workday:automationanywhere:wd5:AutomationAnywhereJobs:india-cse"
        in full_scan_targets
    )
    assert "ats:workday:revvity:wd103:External:india-cse" in full_scan_targets
    assert "market:aicte-paid-cse-internships" in full_scan_targets
    assert "ats:lever:mactores" in full_scan_targets
    assert "ats:zohorecruit:talkinglands:in" in full_scan_targets
    assert "ats:zohorecruit:quadeye:in" in full_scan_targets
    assert "ats:zohorecruit:spikewell:in" in full_scan_targets
    assert "ats:zohorecruit:indeadesignsystems:com" in full_scan_targets
    assert "ats:zohorecruit:melss:in" in full_scan_targets
    assert "ats:zohorecruit:madhifoundation:in" in full_scan_targets
    assert "ats:zohorecruit:citygreens:in" in full_scan_targets
    assert "ats:zohorecruit:kots:in" in full_scan_targets
    assert "ats:ashby:almabase" in full_scan_targets
    assert "ats:ashby:josys" in full_scan_targets
    assert "ats:zohorecruit:iide:in" in full_scan_targets
    assert "ats:zohorecruit:ceew:in" in full_scan_targets
    assert "ats:zohorecruit:stutzen:com" in full_scan_targets
    assert "ats:zohorecruit:galaxeye-pranitgalaxeyespace:in" in full_scan_targets
    assert "ats:zohorecruit:futuristiclabs:in" in full_scan_targets
    assert "ats:zohorecruit:perceptive-analytics:com" in full_scan_targets
    assert "ats:zohorecruit:infusory:com" in full_scan_targets
    assert "ats:zohorecruit:embarkgcc:in" in full_scan_targets
    assert "ats:smartrecruiters:Brainwonders" in full_scan_targets
    assert "ats:oraclehcm:kpmg:ejgk.fa.em2.oraclecloud.com:CX_3:kpmg.com" in full_scan_targets
    assert (
        "ats:oraclehcm:coherent:hcwp.fa.us2.oraclecloud.com:CX_8001:coherent.com"
        in full_scan_targets
    )
    assert "ats:oraclehcm:wsp:emit.fa.ca3.oraclecloud.com:CX_2001:wsp.com" in full_scan_targets
    assert "ats:eightfold:eightfold:app.eightfold.ai:volkscience.com" in full_scan_targets
    assert "ats:eightfold:fortive:fortive.eightfold.ai:fortive.com" in full_scan_targets
    assert "ats:eightfold:vodafone:vodafone.eightfold.ai:vodafone.com" in full_scan_targets
    assert "ats:icims:seismic:in-careers-seismic.icims.com:seismic.com" in full_scan_targets
    assert (
        "ats:avature:synopsys:synopsys.avature.net:careers:synopsys.com"
        in full_scan_targets
    )
    assert (
        "ats:avature:xerox:xerox.avature.net:en_US/careers:xerox.com"
        in full_scan_targets
    )
    assert (
        "ats:jobvite:barracuda-networks-inc:barracuda.com"
        in full_scan_targets
    )
    assert (
        "ats:jibe:amd:careers.amd.com:careers-home:en-us:amd.com"
        in full_scan_targets
    )


def test_market_dispatch_routes_aggregators_and_remote_feeds(monkeypatch) -> None:
    seen: list[str] = []

    async def arbeitnow(target: str):
        seen.append(target)
        return [{"title": "Software Intern"}]

    async def themuse(target: str):
        seen.append(target)
        return []

    async def remoteok():
        seen.append("remoteok")
        return []

    async def hn_hiring():
        seen.append("hn_hiring")
        return []

    async def ycombinator(scope: str):
        seen.append(f"ycombinator:{scope}")
        return []

    async def deliveroo_india():
        seen.append("deliveroo_india")
        return []

    async def zeqo_early_career():
        seen.append("zeqo_early_career")
        return []

    async def aicte_cse_internships():
        seen.append("aicte_cse_internships")
        return []

    async def amazon_india_cse():
        seen.append("amazon_india_cse")
        return []

    async def microsoft_india_cse():
        seen.append("microsoft_india_cse")
        return []

    async def google_india_early_career():
        seen.append("google_india_early_career")
        return []

    async def qualcomm_india_early_career():
        seen.append("qualcomm_india_early_career")
        return []

    async def atlassian_india_cse():
        seen.append("atlassian_india_cse")
        return []

    async def oracle_india_early_cse():
        seen.append("oracle_india_early_cse")
        return []

    async def swiggy_india_cse():
        seen.append("swiggy_india_cse")
        return []

    async def dell_india_cse():
        seen.append("dell_india_cse")
        return []

    async def rss(target: str):
        seen.append(target)
        return []

    monkeypatch.setattr(market_registry, "scrape_arbeitnow_target", arbeitnow)
    monkeypatch.setattr(market_registry, "scrape_themuse_target", themuse)
    monkeypatch.setattr(market_registry, "scrape_remoteok", remoteok)
    monkeypatch.setattr(market_registry, "scrape_hn_hiring", hn_hiring)
    monkeypatch.setattr(market_registry, "scrape_ycombinator_startups", ycombinator)
    monkeypatch.setattr(market_registry, "scrape_deliveroo_india", deliveroo_india)
    monkeypatch.setattr(market_registry, "scrape_zeqo_early_career", zeqo_early_career)
    monkeypatch.setattr(
        market_registry,
        "scrape_aicte_cse_internships",
        aicte_cse_internships,
    )
    monkeypatch.setattr(market_registry, "scrape_amazon_india_cse", amazon_india_cse)
    monkeypatch.setattr(market_registry, "scrape_microsoft_india_cse", microsoft_india_cse)
    monkeypatch.setattr(market_registry, "scrape_google_india_early_career", google_india_early_career)
    monkeypatch.setattr(
        market_registry,
        "scrape_qualcomm_india_early_career",
        qualcomm_india_early_career,
    )
    monkeypatch.setattr(market_registry, "scrape_atlassian_india_cse", atlassian_india_cse)
    monkeypatch.setattr(
        market_registry,
        "scrape_oracle_india_early_cse",
        oracle_india_early_cse,
    )
    monkeypatch.setattr(market_registry, "scrape_swiggy_india_cse", swiggy_india_cse)
    monkeypatch.setattr(market_registry, "scrape_dell_india_cse", dell_india_cse)
    monkeypatch.setattr(market_registry, "scrape_rss", rss)
    assert asyncio.run(
        market_registry.scrape_market_target("aggregator:arbeitnow:software intern@@India")
    )
    asyncio.run(market_registry.scrape_market_target("aggregator:themuse:software intern@@India"))
    asyncio.run(market_registry.scrape_market_target("market:remoteok"))
    asyncio.run(market_registry.scrape_market_target("market:hn-hiring"))
    asyncio.run(market_registry.scrape_market_target("market:ycombinator:india"))
    asyncio.run(market_registry.scrape_market_target("market:deliveroo-india"))
    asyncio.run(market_registry.scrape_market_target("market:zeqo-early-career"))
    asyncio.run(market_registry.scrape_market_target("market:aicte-paid-cse-internships"))
    asyncio.run(market_registry.scrape_market_target("market:amazon-india-cse"))
    asyncio.run(market_registry.scrape_market_target("market:microsoft-india-cse"))
    asyncio.run(market_registry.scrape_market_target("market:google-india-early-career"))
    asyncio.run(market_registry.scrape_market_target("market:qualcomm-india-early-career"))
    asyncio.run(market_registry.scrape_market_target("market:atlassian-india-cse"))
    asyncio.run(market_registry.scrape_market_target("market:oracle-india-early-cse"))
    asyncio.run(market_registry.scrape_market_target("market:swiggy-india-cse"))
    asyncio.run(market_registry.scrape_market_target("market:dell-india-cse"))
    asyncio.run(market_registry.scrape_market_target("https://weworkremotely.com/remote-jobs.rss"))
    assert seen == [
        "aggregator:arbeitnow:software intern@@India",
        "aggregator:themuse:software intern@@India",
        "remoteok", "hn_hiring", "ycombinator:india", "deliveroo_india", "zeqo_early_career",
        "aicte_cse_internships",
        "amazon_india_cse",
        "microsoft_india_cse", "google_india_early_career", "qualcomm_india_early_career",
        "atlassian_india_cse",
        "oracle_india_early_cse",
        "swiggy_india_cse",
        "dell_india_cse",
        "https://weworkremotely.com/remote-jobs.rss",
    ]
