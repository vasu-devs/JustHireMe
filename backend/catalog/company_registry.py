"""Production target inventory for the early-career opportunity engine.

This deliberately owns no benchmark/review semantics.  It converts the same
curated runtime seed inventories used by discovery into bounded, de-duplicated
ATS targets suitable for an actual candidate scan.
"""

from __future__ import annotations

import json
from pathlib import Path

from catalog.query_matrix import expand_early_career_targets
from catalog.source_registry import SourceTarget
from core import company_seeds


_CORE = Path(__file__).resolve().parents[1] / "core"
_SUPPORTED = {
    "greenhouse", "lever", "ashby", "workable", "smartrecruiters",
    "recruitee", "personio", "teamtailor", "rippling", "breezy",
    "pinpoint", "bamboohr",
    "zohorecruit", "freshteam", "keka",
    "oraclehcm",
    "eightfold",
    "icims",
    "avature",
    "jobvite",
    "jibe",
}
_DIVERSITY_ANCHOR_PROVIDERS = (
    "rippling", "teamtailor", "pinpoint", "breezy", "bamboohr",
)

# Company-direct boards observed carrying India early-career technical roles on
# 2026-08-24. They are intentionally scanned before the broad global inventory;
# stale boards remain harmless because source health records zero/failure state.
_INDIA_PRIORITY: tuple[tuple[str, str, dict], ...] = (
    # Verified live on 2026-08-25. Ema carried a paid, India-remote AI/Data
    # resident internship for final-year CS students; PhonePe is retained as a
    # high-value India watch board even when its current technical intern count
    # is zero.
    ("ashby", "ema", {}),
    ("greenhouse", "phonepe", {}),
    ("greenhouse", "nirmata", {}),
    ("greenhouse", "enterpret", {}),
    ("greenhouse", "headoutcareers", {}),
    ("ashby", "composio", {}),
    ("ashby", "evaratus", {}),
    # Public boards verified live on 2026-08-25. Outmarket explicitly lists
    # Remote India AI engineering, and Merkle Science carries final-year
    # Bangalore engineering internships (including bond language that must be
    # safety-filtered).
    ("ashby", "outmarket", {}),
    ("lever", "merklescience", {}),
    ("lever", "epifi", {}),
    ("workday", "viavisolutions", {"host": "wd1", "site": "careers"}),
    ("workday", "unisys", {"host": "wd5", "site": "External"}),
    ("workday", "cae", {"host": "wd3", "site": "career"}),
    # Country-faceted connector targets: one bounded India/CSE plan per tenant.
    ("workday", "nvidia", {"host": "wd5", "site": "NVIDIAExternalCareerSite"}),
    ("workday", "adobe", {"host": "wd5", "site": "external_experienced"}),
    ("workday", "paypal", {"host": "wd1", "site": "jobs"}),
    ("workday", "visa", {"host": "wd5", "site": "Visa_Early_Careers"}),
    # Oracle Recruiting Cloud enterprise tenants verified from their
    # first-party Candidate Experience redirects and public job APIs on
    # 2026-08-26. The generic adapter retains current India CSE/AI internships
    # plus a bounded non-senior technical fallback and rechecks detail liveness.
    ("oraclehcm", "kpmg", {
        "host": "ejgk.fa.em2.oraclecloud.com", "site": "CX_3", "domain": "kpmg.com",
    }),
    ("oraclehcm", "coherent", {
        "host": "hcwp.fa.us2.oraclecloud.com", "site": "CX_8001", "domain": "coherent.com",
    }),
    ("oraclehcm", "wsp", {
        "host": "emit.fa.ca3.oraclecloud.com", "site": "CX_2001", "domain": "wsp.com",
    }),
    # Eightfold PCS-X boards verified through full public JobPosting details on
    # 2026-08-26. The admitted cohort currently yields a Bangalore AI-SDET
    # 1-year stretch, a fresh Bengaluru Associate Data Scientist, a Mobile QA
    # 2-year stretch, and a Pune video-test 2-year stretch. Micron was audited
    # but not admitted: its umbrella internship is correctly non-specific and
    # its remaining manufacturing graduate rows only need review.
    ("eightfold", "eightfold", {
        "host": "app.eightfold.ai", "domain": "volkscience.com",
    }),
    ("eightfold", "fortive", {
        "host": "fortive.eightfold.ai", "domain": "fortive.com",
    }),
    ("eightfold", "vodafone", {
        "host": "vodafone.eightfold.ai", "domain": "vodafone.com",
    }),
    # Public iCIMS search + JobPosting details verified on 2026-08-26. Seismic
    # currently yields a live Hyderabad Software Engineer II two-year stretch;
    # Orange, Applied Systems, StoneX, Waters, and PowerSchool were audited but
    # not admitted because their current CSE rows are experienced-only or zero.
    ("icims", "seismic", {
        "host": "in-careers-seismic.icims.com", "domain": "seismic.com",
    }),
    # Public Avature India scans verified through same-host detail pages on
    # 2026-08-26. Synopsys exposes a complete 141-row India facet and currently
    # yields two Bengaluru Salesforce developer observations with a two-year
    # bar. Xerox's branded portal has no country facet, so the adapter combines
    # its public India search with exact Country fields and currently yields a
    # Kolkata software-engineering watch role. IBM was audited but not admitted:
    # its portal answered automated public requests with an empty HTTP 202.
    ("avature", "synopsys", {
        "host": "synopsys.avature.net", "portal": "careers", "domain": "synopsys.com",
    }),
    ("avature", "xerox", {
        "host": "xerox.avature.net", "portal": "en_US/careers", "domain": "xerox.com",
    }),
    # Jobvite's server-rendered board and same-host JobPosting details were
    # verified live on 2026-08-26. Barracuda currently yields two Bangalore
    # CSE/security roles within the representative candidate's two-year stretch
    # policy. Genpact and Progress were audited but not admitted because their
    # current relevant yield is zero.
    ("jobvite", "barracuda-networks-inc", {"domain": "barracuda.com"}),
    # Jibe/iCIMS Attract's first-party India facet and locale-specific public
    # detail API were verified on 2026-08-26. AMD currently yields a fresh
    # Bangalore hybrid security-testing role within the three-year stretch
    # policy; experienced silicon/AI rows remain visible but are skipped.
    ("jibe", "amd", {
        "host": "careers.amd.com", "context": "careers-home",
        "locale": "en-us", "domain": "amd.com",
    }),
    # India internships observed on employer-owned ATS pages on 2026-08-25;
    # community indexes are used only to discover these direct boards.
    ("workday", "warnerbros", {"host": "wd5", "site": "directshare"}),
    ("workday", "redhat", {"host": "wd5", "site": "Jobs"}),
    ("workday", "lilly", {"host": "wd115", "site": "CMP"}),
    ("greenhouse", "glance", {}),
    # Indian startup boards discovered from community pointers and verified on
    # their employer-owned public Zoho Recruit career pages on 2026-08-25.
    ("zohorecruit", "mavq", {"tld": "com"}),
    ("zohorecruit", "fireblazeaischool", {"tld": "in"}),
    ("zohorecruit", "faveohelpdesk", {"tld": "in"}),
    ("zohorecruit", "synoriq", {"tld": "com"}),
    ("zohorecruit", "heliostechlabs", {"tld": "com"}),
    ("zohorecruit", "uavmarketplace", {"tld": "in"}),
    ("zohorecruit", "numatix", {"tld": "in"}),
    ("zohorecruit", "businesswebsolutions", {"tld": "in"}),
    ("zohorecruit", "gridverse", {"tld": "in"}),
    ("zohorecruit", "botmakerstech", {"tld": "in"}),
    ("zohorecruit", "omni-reach", {"tld": "in"}),
    ("zohorecruit", "hyperhorizon", {"tld": "in"}),
    ("zohorecruit", "career", {"tld": "com"}),
    ("zohorecruit", "quicko", {"tld": "in"}),
    ("zohorecruit", "aatmia", {"tld": "in"}),
    # Public Freshteam boards verified live on 2026-08-25. This cohort spans
    # direct India internships, India-remote roles and early-career full-time
    # CSE/AI work. Unsafe/unpaid listings remain observable but are rejected by
    # the opportunity decision layer rather than silently hidden at ingestion.
    ("freshteam", "indianpix-people", {}),
    ("freshteam", "restat", {}),
    ("freshteam", "creditsaisonin-talent", {}),
    ("freshteam", "codvo-team", {}),
    ("freshteam", "anaxee", {}),
    ("freshteam", "sarvm", {}),
    ("freshteam", "myrufarm", {}),
    ("freshteam", "intugine", {}),
    ("freshteam", "outoftheblue", {}),
    ("freshteam", "digitap", {}),
    ("freshteam", "smartxtech", {}),
    ("freshteam", "aurochs", {}),
    ("freshteam", "cashflo-talent", {}),
    ("freshteam", "cesltd", {}),
    ("freshteam", "ecsme", {}),
    # Keka's public current-job feed exposes unusually complete first-party
    # evidence: stable requisition IDs, full descriptions, structured India
    # locations, experience, salary ranges, skills and publication timestamps.
    # Verified live 2026-08-25; these boards currently carry CSE/AI internships
    # or 0-1 year technical roles rather than merely historical search results.
    ("keka", "comprinno", {}),
    ("keka", "vajrorap", {}),
    ("keka", "solytics", {}),
    ("keka", "bebetta", {}),
    ("keka", "evolve", {}),
    ("keka", "popclub", {}),
    ("keka", "codewinglet", {}),
    ("keka", "thewholetruthfoods", {}),
    ("keka", "adit", {}),
    # Same-day public ATS probes on 2026-08-26. This wave deliberately keeps
    # both positive-yield boards and major India watch boards whose current
    # openings are senior: future early-career roles become visible on the next
    # free scan without needing another code release.
    ("lever", "paytm", {}),
    ("greenhouse", "inmobi", {}),
    ("ashby", "sarvam", {}),
    ("greenhouse", "devrev", {}),
    ("greenhouse", "slice", {}),
    ("lever", "hevodata", {}),
    ("greenhouse", "hackerrank", {}),
    ("lever", "porter", {}),
    ("lever", "netomi", {}),
    ("lever", "zeta", {}),
    ("lever", "mindtickle", {}),
    ("greenhouse", "appfire", {}),
    ("greenhouse", "observeai", {}),
    ("greenhouse", "sumologic", {}),
    ("greenhouse", "cloudsek", {}),
    ("greenhouse", "groww", {}),
    # Candidate-admission wave on 2026-08-26. Portcast currently carries a
    # zero-experience, India-eligible remote Data Analyst internship. Jumio and
    # the three Workday tenants produced bounded India technical stretch roles
    # through the live source APIs, so they extend the early-career/full-time
    # fallback without admitting the zero-yield boards from the same audit.
    ("lever", "portcast", {}),
    ("greenhouse", "jumio", {}),
    ("workday", "fox", {"host": "wd1", "site": "Domestic"}),
    ("workday", "iqvia", {"host": "wd1", "site": "IQVIA"}),
    ("workday", "dentsuaegis", {"host": "wd3", "site": "DAN_GLOBAL"}),
    # Positive-yield admission wave on 2026-08-26. Drivetrain currently has
    # two India-remote engineering internships. Altimate adds a Bengaluru data
    # engineering stretch. Eurofins and Wabtec use the provider-side India/CSE
    # collection filter so their large global boards do not waste detail calls;
    # both currently carry multiple Bengaluru 2-3 year technical stretches.
    ("lever", "drivetrain", {}),
    ("ashby", "altimate", {}),
    ("smartrecruiters", "Eurofins", {"mode": "india-cse"}),
    ("smartrecruiters", "Wabtec", {"mode": "india-cse"}),
    # Positive-yield admission waves 15-16 on 2026-08-26. Instawork currently
    # carries Bengaluru robotics/AI hardware and QA internships. MFSG's
    # India-specific tenant carries a Hyderabad-remote QA internship; the
    # larger Momentum tenant republishes the same role and is deliberately not
    # admitted as a duplicate. YipitData adds paid India-remote data QA entry
    # roles and bounded 1-2 year data/software stretches. Automation Anywhere
    # and Revvity add live India SDET and AI internships through Workday.
    ("greenhouse", "instawork", {}),
    ("greenhouse", "mfsgtechnologiesindia", {}),
    ("greenhouse", "yipitdatajobs", {}),
    (
        "workday",
        "automationanywhere",
        {"host": "wd5", "site": "AutomationAnywhereJobs"},
    ),
    ("workday", "revvity", {"host": "wd103", "site": "External"}),
    # Positive-yield India internship admission wave 18 on 2026-08-26.
    # Mactores currently exposes four India-remote cloud/DevOps/full-stack/agent
    # internships. The Zoho tenants add current Chennai, Bengaluru and Mangaluru
    # software, full-stack, Python, AR/VR, QA and mobile internships. Quadeye and
    # Spikewell are intentionally absent here: their public board title identifies
    # PeoplePlus as the hiring intermediary, so they are marketplace-labelled in
    # market_registry rather than represented as employer-direct sources.
    ("lever", "mactores", {}),
    ("zohorecruit", "talkinglands", {"tld": "in"}),
    ("zohorecruit", "indeadesignsystems", {"tld": "com"}),
    ("zohorecruit", "melss", {"tld": "in"}),
    ("zohorecruit", "madhifoundation", {"tld": "in"}),
    ("zohorecruit", "citygreens", {"tld": "in"}),
    ("zohorecruit", "kots", {"tld": "in"}),
    # Positive-yield India internship/early-career admission wave 19. Every
    # board was replayed through rule 33 after live detail verification. The
    # admitted set currently carries India software, data/analytics, AI,
    # IT-operations, Android, and embedded internships or bounded stretches.
    ("ashby", "almabase", {}),
    ("ashby", "josys", {}),
    ("zohorecruit", "iide", {"tld": "in"}),
    ("zohorecruit", "ceew", {"tld": "in"}),
    ("zohorecruit", "stutzen", {"tld": "com"}),
    ("zohorecruit", "galaxeye-pranitgalaxeyespace", {"tld": "in"}),
    ("zohorecruit", "futuristiclabs", {"tld": "in"}),
    ("zohorecruit", "perceptive-analytics", {"tld": "com"}),
    ("zohorecruit", "infusory", {"tld": "com"}),
    # Wave 20: Embark GCC has a currently active Bangalore systems internship.
    # Brainwonders is deliberately retained as a safety-watch board: its fresh
    # AI internship defers the advertised benefit until successful completion
    # of a mandatory tenure, which Rule 34 blocks rather than recommends.
    ("zohorecruit", "embarkgcc", {"tld": "in"}),
    ("smartrecruiters", "Brainwonders", {}),
)

# Keep underrepresented ATS families exercised in the default bounded run. The
# entries come from the probed runtime inventory; health tracking detects drift.
_PROVIDER_PRIORITY: tuple[tuple[str, str, dict], ...] = (
    # Live replacements for stale provider/tenant pairs confirmed during the
    # 2026-08-25 full-market scan.  Keeping these near the front makes them
    # visible even in deliberately bounded scans.
    ("greenhouse", "attentive", {}),
    ("greenhouse", "doordashindia", {}),
    ("greenhouse", "doordashusa", {}),
    ("greenhouse", "sourcegraph91", {}),
    ("ashby", "benchling", {}),
    ("ashby", "perplexity", {}),
    ("workable", "huggingface", {}),
    ("workable", "starling-bank", {}),
    ("rippling", "rippling", {}),
    ("teamtailor", "doodle", {}),
    ("pinpoint", "improbable", {}),
    ("breezy", "breezy", {}),
    ("bamboohr", "multiplier", {}),
)

# Exact provider/tenant pairs that returned a confirmed missing-board response
# in the 2026-08-25 live baseline.  This is deliberately not a generic
# zero-result deny-list: healthy boards with no matching roles must remain in
# the market scan.  Current replacements are listed above where available.
_RETIRED_TARGETS: frozenset[tuple[str, str]] = frozenset({
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
})


def _inventory(name: str) -> list[dict]:
    try:
        value = json.loads((_CORE / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def production_company_targets(*, limit: int = 120) -> list[SourceTarget]:
    """Return a deterministic company-direct target set.

    Workday tenants are placed early because they cover large Indian employers
    and GCCs that startup-heavy Greenhouse/Ashby inventories miss. Each Workday
    tenant is expanded into one bounded, India-faceted CSE discovery plan.
    """
    candidates: list[tuple[str, str, dict]] = [*_INDIA_PRIORITY, *_PROVIDER_PRIORITY]
    for provider, slug in company_seeds._TECH_SEEDS:
        candidates.append((provider, slug, {}))
    for board in company_seeds._load_workday_boards():
        tenant = str(board.get("tenant") or "").strip()
        if tenant:
            candidates.append(("workday", tenant, board))
    for filename in ("ai_boards.json", "new_boards.json"):
        for row in _inventory(filename):
            provider = str(row.get("provider") or "").strip().lower()
            slug = str(row.get("slug") or "").strip()
            if provider in _SUPPORTED and slug:
                candidates.append((provider, slug, row))

    bounded_limit = max(1, min(int(limit or 120), 500))
    targets: list[SourceTarget] = []
    seen: set[tuple[str, str]] = set()
    for provider, slug, extra in candidates:
        provider = provider.lower()
        key = (provider, slug.lower())
        if (
            key in seen
            or key in _RETIRED_TARGETS
            or (provider != "workday" and provider not in _SUPPORTED)
        ):
            continue
        seen.add(key)
        if provider == "workday":
            host = str(extra.get("host") or "wd5")
            site = str(extra.get("site") or "External")
            scan_target = f"ats:workday:{slug}:{host}:{site}:intern"
        elif provider == "zohorecruit":
            tld = str(extra.get("tld") or "com").strip().lower()
            scan_target = f"ats:zohorecruit:{slug}:{tld}"
        elif provider == "smartrecruiters" and extra.get("mode"):
            mode = str(extra.get("mode") or "").strip().lower()
            scan_target = f"ats:smartrecruiters:{slug}:{mode}"
        elif provider == "oraclehcm":
            host = str(extra.get("host") or "").strip().lower()
            site = str(extra.get("site") or "").strip().upper()
            domain = str(extra.get("domain") or "").strip().lower()
            scan_target = f"ats:oraclehcm:{slug}:{host}:{site}:{domain}"
        elif provider == "eightfold":
            host = str(extra.get("host") or "").strip().lower()
            domain = str(extra.get("domain") or "").strip().lower()
            scan_target = f"ats:eightfold:{slug}:{host}:{domain}"
        elif provider == "icims":
            host = str(extra.get("host") or "").strip().lower()
            domain = str(extra.get("domain") or "").strip().lower()
            scan_target = f"ats:icims:{slug}:{host}:{domain}"
        elif provider == "avature":
            host = str(extra.get("host") or "").strip().lower()
            portal = str(extra.get("portal") or "careers").strip("/")
            domain = str(extra.get("domain") or "").strip().lower()
            scan_target = f"ats:avature:{slug}:{host}:{portal}:{domain}"
        elif provider == "jobvite":
            domain = str(extra.get("domain") or "").strip().lower()
            scan_target = f"ats:jobvite:{slug}:{domain}"
        elif provider == "jibe":
            host = str(extra.get("host") or "").strip().lower()
            context = str(extra.get("context") or "careers-home").strip().lower()
            locale = str(extra.get("locale") or "en-us").strip().lower()
            domain = str(extra.get("domain") or "").strip().lower()
            scan_target = f"ats:jibe:{slug}:{host}:{context}:{locale}:{domain}"
        else:
            scan_target = f"ats:{provider}:{slug}"
        targets.append(SourceTarget(
            target_id=f"{provider}:{slug}".lower(),
            company_id=f"{provider}:{slug}".lower(),
            provider=provider,
            scan_target=scan_target,
            parser_version="2" if provider in {
                "ashby", "avature", "eightfold", "icims", "jibe", "jobvite", "oraclehcm", "smartrecruiters",
                "workday",
            } else "1",
        ))
        if len(targets) >= 500:
            break

    if len(targets) > bounded_limit:
        if bounded_limit >= 120:
            # India-priority admissions grow continuously. Reserve one proven
            # live anchor for each otherwise underrepresented ATS family so a
            # new India board cannot silently erase provider diversity from the
            # bounded default scan.
            anchors = [
                next(target for target in targets if target.provider == provider)
                for provider in _DIVERSITY_ANCHOR_PROVIDERS
            ]
            anchor_ids = {target.target_id for target in anchors}
            selected = [
                target for target in targets if target.target_id not in anchor_ids
            ][:bounded_limit - len(anchors)]
            targets = [*selected, *anchors]
        else:
            targets = targets[:bounded_limit]
    return expand_early_career_targets(targets)
