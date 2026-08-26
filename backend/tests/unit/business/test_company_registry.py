from __future__ import annotations

from catalog.company_registry import production_company_targets


def test_production_registry_is_bounded_unique_and_expands_workday_queries() -> None:
    # Exercise the real default production bound. India-priority admissions may
    # legitimately grow, but the default slice must still retain provider
    # diversity rather than only doing so in the 500-target audit inventory.
    targets = production_company_targets(limit=120)
    assert targets
    assert len({target.target_id for target in targets}) == len(targets)
    assert all(target.scan_target.startswith("ats:") for target in targets)
    workday = [target for target in targets if target.provider == "workday"]
    assert workday
    assert {target.scan_target.rsplit(":", 1)[-1] for target in workday} == {"india-cse"}
    assert {target.parser_version for target in workday} == {"2"}
    assert {
        target.parser_version for target in targets if target.provider == "ashby"
    } == {"2"}
    assert {
        target.parser_version for target in targets if target.provider == "smartrecruiters"
    } == {"2"}
    assert {
        target.parser_version for target in targets if target.provider == "oraclehcm"
    } == {"2"}
    assert {
        target.parser_version for target in targets if target.provider == "eightfold"
    } == {"2"}
    assert {
        target.parser_version for target in targets if target.provider == "icims"
    } == {"2"}
    assert {
        target.parser_version for target in targets if target.provider == "avature"
    } == {"2"}
    assert {
        target.parser_version for target in targets if target.provider == "jobvite"
    } == {"2"}
    assert {
        target.parser_version for target in targets if target.provider == "jibe"
    } == {"2"}
    assert any(target.provider == "greenhouse" for target in targets)
    assert any(target.provider == "ashby" for target in targets)
    assert {"rippling", "teamtailor", "pinpoint", "breezy", "bamboohr"} <= {
        target.provider for target in targets
    }
    assert any(
        target.scan_target == "ats:zohorecruit:mavq:com"
        for target in production_company_targets(limit=500)
    )
    assert {
        "mavq", "fireblazeaischool", "faveohelpdesk", "synoriq",
        "heliostechlabs", "uavmarketplace", "numatix",
        "businesswebsolutions", "gridverse", "botmakerstech",
        "omni-reach", "hyperhorizon", "career", "quicko", "aatmia",
    } <= {
        target.company_id.split(":", 1)[-1]
        for target in production_company_targets(limit=500)
        if target.provider == "zohorecruit"
    }
    assert {
        "indianpix-people", "restat", "creditsaisonin-talent", "codvo-team",
        "anaxee", "sarvm", "myrufarm", "intugine", "outoftheblue",
        "digitap", "smartxtech", "aurochs", "cashflo-talent", "cesltd", "ecsme",
    } <= {
        target.company_id.split(":", 1)[-1]
        for target in production_company_targets(limit=500)
        if target.provider == "freshteam"
    }
    assert {
        "comprinno", "vajrorap", "solytics", "bebetta", "evolve",
        "popclub", "codewinglet", "thewholetruthfoods", "adit",
    } <= {
        target.company_id.split(":", 1)[-1]
        for target in production_company_targets(limit=500)
        if target.provider == "keka"
    }
    assert {
        ("lever", "paytm"),
        ("greenhouse", "inmobi"),
        ("ashby", "sarvam"),
        ("greenhouse", "devrev"),
        ("greenhouse", "slice"),
        ("lever", "hevodata"),
        ("greenhouse", "hackerrank"),
        ("lever", "porter"),
        ("lever", "netomi"),
        ("lever", "zeta"),
        ("lever", "mindtickle"),
        ("greenhouse", "appfire"),
        ("greenhouse", "observeai"),
        ("greenhouse", "sumologic"),
        ("greenhouse", "cloudsek"),
        ("greenhouse", "groww"),
        ("lever", "portcast"),
        ("greenhouse", "jumio"),
        ("workday", "fox"),
        ("workday", "iqvia"),
        ("workday", "dentsuaegis"),
        ("lever", "drivetrain"),
        ("ashby", "altimate"),
        ("smartrecruiters", "eurofins"),
        ("smartrecruiters", "wabtec"),
        ("greenhouse", "instawork"),
        ("greenhouse", "mfsgtechnologiesindia"),
        ("greenhouse", "yipitdatajobs"),
        ("workday", "automationanywhere"),
        ("workday", "revvity"),
    } <= {
        (target.provider, target.company_id.split(":", 1)[-1])
        for target in production_company_targets(limit=500)
    }

    scan_targets = {
        target.scan_target for target in production_company_targets(limit=500)
    }
    assert {
        "ats:workday:fox:wd1:Domestic:india-cse",
        "ats:workday:iqvia:wd1:IQVIA:india-cse",
        "ats:workday:dentsuaegis:wd3:DAN_GLOBAL:india-cse",
        "ats:smartrecruiters:Eurofins:india-cse",
        "ats:smartrecruiters:Wabtec:india-cse",
        "ats:workday:automationanywhere:wd5:AutomationAnywhereJobs:india-cse",
        "ats:workday:revvity:wd103:External:india-cse",
        "ats:oraclehcm:kpmg:ejgk.fa.em2.oraclecloud.com:CX_3:kpmg.com",
        "ats:oraclehcm:coherent:hcwp.fa.us2.oraclecloud.com:CX_8001:coherent.com",
        "ats:oraclehcm:wsp:emit.fa.ca3.oraclecloud.com:CX_2001:wsp.com",
        "ats:eightfold:eightfold:app.eightfold.ai:volkscience.com",
        "ats:eightfold:fortive:fortive.eightfold.ai:fortive.com",
        "ats:eightfold:vodafone:vodafone.eightfold.ai:vodafone.com",
        "ats:icims:seismic:in-careers-seismic.icims.com:seismic.com",
        "ats:avature:synopsys:synopsys.avature.net:careers:synopsys.com",
        "ats:avature:xerox:xerox.avature.net:en_US/careers:xerox.com",
        "ats:jobvite:barracuda-networks-inc:barracuda.com",
        "ats:jibe:amd:careers.amd.com:careers-home:en-us:amd.com",
    } <= scan_targets


def test_production_registry_uses_live_replacements_and_omits_retired_pairs() -> None:
    targets = production_company_targets(limit=500)
    pairs = {(target.provider, target.company_id.split(":", 1)[-1]) for target in targets}

    assert {
        ("ashby", "ema"),
        ("greenhouse", "phonepe"),
        ("greenhouse", "attentive"),
        ("greenhouse", "doordashindia"),
        ("greenhouse", "doordashusa"),
        ("greenhouse", "sourcegraph91"),
        ("ashby", "benchling"),
        ("ashby", "perplexity"),
        ("workable", "huggingface"),
        ("workable", "starling-bank"),
        ("workday", "nvidia"),
        ("workday", "adobe"),
        ("workday", "paypal"),
        ("workday", "visa"),
    } <= pairs
    assert not {
        ("greenhouse", "doordash"),
        ("greenhouse", "hashicorp"),
        ("greenhouse", "benchling"),
        ("greenhouse", "sentry"),
        ("greenhouse", "sourcegraph"),
        ("greenhouse", "deliveroo"),
        ("greenhouse", "starlingbank"),
        ("ashby", "replicate"),
        ("ashby", "anthropic"),
        ("ashby", "perplexityai"),
        ("ashby", "huggingface"),
        ("lever", "attentive"),
        ("workable", "wearedevelopers"),
        ("smartrecruiters", "bosch"),
        ("smartrecruiters", "visa"),
    } & pairs
