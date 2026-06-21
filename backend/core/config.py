from __future__ import annotations
import logging

import os
import re


DEFAULT_JOB_TARGETS = [
    "hn-hiring",
    "https://remoteok.com/api",
    "https://remotive.com/api/remote-jobs",
    "https://jobicy.com/api/v2/remote-jobs?count=50",
    "https://jobicy.com/feed/newjobs",
    "https://weworkremotely.com/remote-jobs.rss",
    "site:boards.greenhouse.io",
    "site:jobs.lever.co",
    "site:jobs.ashbyhq.com",
    "site:apply.workable.com",
    "site:wellfound.com/jobs",
    "site:linkedin.com/jobs",
    "site:indeed.com/jobs",
    "site:glassdoor.com/Job",
    "site:jobs.smartrecruiters.com",
    "site:workdayjobs.com",
    "site:naukri.com",
    "site:instahyre.com",
    "site:cutshort.io/jobs",
]

INDIA_JOB_TARGETS = [
    "site:wellfound.com/jobs India",
    "site:cutshort.io/jobs India startup",
    "site:instahyre.com jobs India",
    "site:naukri.com jobs India",
    "site:foundit.in jobs India",
    "site:internshala.com/jobs India",
    "site:linkedin.com/jobs India",
    "site:indeed.com/jobs India",
    "site:glassdoor.co.in Job India",
    "site:boards.greenhouse.io India",
    "site:jobs.lever.co India",
    "site:jobs.ashbyhq.com India",
    "site:apply.workable.com India",
]

BLOCKED_JOB_TARGET_MARKERS = (
    "freelance",
    "upwork",
    "freelancer.com",
    "fiverr",
    "contra.com",
    "peopleperhour",
    "guru.com",
    "truelancer",
    "codementor",
    "toptal",
)


def split_configured_targets(raw: str) -> list[str]:
    targets: list[str] = []
    for line in str(raw or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for part in line.split(","):
            target = part.strip()
            if target and not target.startswith("#"):
                targets.append(target)
    return targets


def dedupe_targets(targets: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for target in targets:
        key = target.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(target.strip())
    return out


def job_market_focus(value) -> str:
    focus = str(value or "global").strip().lower()
    return "india" if focus in {"india", "in", "indian", "indian_startups"} else "global"


def is_hn_target(target: str) -> bool:
    lower = target.lower()
    return lower.startswith("hn:") or "hn-hiring" in lower or "hackernews" in lower or "news.ycombinator.com" in lower


def job_targets(raw: str, market_focus: str = "global") -> list[str]:
    focus = job_market_focus(market_focus)
    targets = split_configured_targets(raw)
    if not targets:
        return list(INDIA_JOB_TARGETS if focus == "india" else DEFAULT_JOB_TARGETS)

    filtered: list[str] = []
    for target in targets:
        lower = target.lower()
        if any(marker in lower for marker in BLOCKED_JOB_TARGET_MARKERS):
            continue
        filtered.append(target)

    if focus == "global" and filtered and all(is_hn_target(target) for target in filtered):
        filtered.extend(target for target in DEFAULT_JOB_TARGETS if not is_hn_target(target))

    if focus == "india":
        india_markers = (
            "india",
            "indian",
            "bangalore",
            "bengaluru",
            "mumbai",
            "delhi",
            "gurgaon",
            "gurugram",
            "hyderabad",
            "pune",
            "chennai",
            "noida",
            "cutshort",
            "instahyre",
            "naukri",
            "foundit",
            "internshala",
            "glassdoor.co.in",
        )
        filtered = [target for target in filtered if any(marker in target.lower() for marker in india_markers)]

    fallback = INDIA_JOB_TARGETS if focus == "india" else DEFAULT_JOB_TARGETS
    return dedupe_targets(filtered) or list(fallback)


def desired_position(cfg: dict) -> str:
    for key in ("desired_position", "target_position", "target_role", "onboarding_target_role"):
        value = str(cfg.get(key) or "").strip()
        if value:
            return value
    return ""


def discovery_location(cfg: dict | None, profile: dict | None = None) -> str:
    """The user's job-search location, in priority order:

    explicit setting (any country/city, worldwide) → the profile's own identity
    location (so just ingesting a CV with a city works) → "" (global/remote).
    Generalizes the old binary india/global switch to any region on Earth.
    """
    cfg = cfg or {}
    for key in ("job_location", "job_region", "target_location", "location"):
        value = str(cfg.get(key) or "").strip()
        if value:
            return value
    # Backward-compat: an explicit india market focus implies India.
    if job_market_focus(cfg.get("job_market_focus")) == "india":
        return "India"
    identity = (profile or {}).get("identity") if isinstance(profile, dict) else None
    if isinstance(identity, dict):
        for key in ("city", "location", "region", "country"):
            value = str(identity.get(key) or "").strip()
            if value:
                return value
    return ""


def remote_preference(cfg: dict | None) -> str:
    """One of: remote, hybrid, onsite, any (default any)."""
    value = str((cfg or {}).get("remote_preference") or "").strip().lower()
    return value if value in {"remote", "hybrid", "onsite", "any"} else "any"


def profile_for_discovery(profile: dict | None, cfg: dict) -> dict:
    profile = dict(profile or {})
    desired = desired_position(cfg)
    if desired:
        summary = str(profile.get("s") or "").strip()
        if desired.lower() not in summary.lower():
            profile["s"] = f"{desired}. {summary}".strip()
        else:
            profile["s"] = summary or desired
        profile["desired_position"] = desired
    # Carry resolved location + remote preference so the query planner can target
    # the user's region without every caller threading extra args.
    profile["_discovery_location"] = discovery_location(cfg, profile)
    profile["_remote_preference"] = remote_preference(cfg)
    # The user's free-text "what I'm looking for" preferences steer the scan
    # toward roles they actually want (used by the query planner + evaluator).
    profile["_job_preferences"] = str((cfg or {}).get("job_preferences") or "").strip()
    return profile


def terms_for_discovery(profile: dict, limit: int = 4) -> list[str]:
    terms: list[str] = []
    summary = str(profile.get("desired_position") or profile.get("s") or "").strip()
    if summary:
        terms.append(" ".join(summary.split()[:5]))
    for exp in profile.get("exp", []) or []:
        if isinstance(exp, dict) and exp.get("role"):
            terms.append(str(exp["role"]))
    for skill in profile.get("skills", []) or []:
        if isinstance(skill, dict) and skill.get("n"):
            terms.append(str(skill["n"]))
    for project in profile.get("projects", []) or []:
        if not isinstance(project, dict):
            continue
        if project.get("title"):
            terms.append(str(project["title"]))
        stack = project.get("stack") or []
        stack_items = stack if isinstance(stack, list) else str(stack).split(",")
        terms.extend(str(item) for item in stack_items[:3] if str(item).strip())
    for cert in profile.get("certifications", []) or []:
        if isinstance(cert, dict):
            value = cert.get("title") or cert.get("name") or cert.get("n")
            if value:
                terms.append(str(value))
        elif str(cert or "").strip():
            terms.append(str(cert))
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        term = re.sub(r"\s+", " ", str(term)).strip(" ,.;:-")
        key = term.lower()
        if term and key not in seen:
            seen.add(key)
            out.append(term)
    return out[:limit] or ["jobs"]


def has_profile_discovery_signal(profile: dict | None) -> bool:
    profile = profile or {}
    if str(profile.get("desired_position") or profile.get("s") or "").strip():
        return True
    for exp in profile.get("exp", []) or []:
        if isinstance(exp, dict) and str(exp.get("role") or "").strip():
            return True
    for skill in profile.get("skills", []) or []:
        if isinstance(skill, dict) and str(skill.get("n") or "").strip():
            return True
    for project in profile.get("projects", []) or []:
        if not isinstance(project, dict):
            continue
        stack = project.get("stack") or []
        stack_items = stack if isinstance(stack, list) else str(stack).split(",")
        if any(str(project.get(key) or "").strip() for key in ("title", "impact", "description", "d")):
            return True
        if any(str(item or "").strip() for item in stack_items):
            return True
    for cert in profile.get("certifications", []) or []:
        if isinstance(cert, dict):
            if any(str(cert.get(key) or "").strip() for key in ("title", "name", "n")):
                return True
        elif str(cert or "").strip():
            return True
    return False


def has_explicit_discovery_targets(cfg: dict | None) -> bool:
    cfg = cfg or {}
    target_keys = (
        "job_boards",
        "free_source_targets",
        "company_watchlist",
        "x_search_queries",
        "x_watchlist",
    )
    if any(str(cfg.get(key) or "").strip() for key in target_keys):
        return True
    return truthy(cfg.get("custom_connectors_enabled", "false")) and bool(
        str(cfg.get("custom_connectors") or "").strip()
    )


def profile_free_source_targets(profile: dict) -> str:
    if not has_profile_discovery_signal(profile):
        return ""
    terms = terms_for_discovery(profile, 3)
    role_query = " ".join(terms[:2])
    return "\n".join([
        f"github:{role_query} hiring help wanted",
        f"hn:{role_query} remote hiring",
        f"reddit:forhire:{role_query} hiring job remote",
    ])


def profile_x_queries(profile: dict, market_focus: str = "global") -> str:
    terms = terms_for_discovery(profile, 4)
    role = " OR ".join(f'"{term}"' for term in terms[:3])
    loc_text = str((profile or {}).get("_discovery_location") or "").strip()
    if job_market_focus(market_focus) == "india":
        location = '("India" OR "Indian" OR "Bengaluru" OR "Mumbai" OR "Pune" OR "Hyderabad")'
    elif loc_text:
        # Any region: include the user's location plus remote alternatives.
        location = f'("{loc_text}" OR "remote" OR "hybrid")'
    else:
        location = '("remote" OR "hybrid" OR "global" OR "onsite")'
    return "\n".join([
        f'("hiring" OR "job opening" OR "open role") ({role}) {location} lang:en -is:retweet',
        f'("we are hiring" OR "is hiring" OR "apply") ({role}) lang:en -is:retweet',
    ])


def has_x_token(cfg: dict) -> bool:
    return bool(cfg.get("x_bearer_token") or os.environ.get("X_BEARER_TOKEN") or os.environ.get("TWITTER_BEARER_TOKEN"))


def int_cfg(cfg: dict, key: str, default: int, min_value: int, max_value: int) -> int:
    raw = str(cfg.get(key, "") or "").strip()
    if not raw:
        # An unset/blank setting is normal — use the default silently. (Logging a
        # "suppressed exception" here spammed the activity stream on every scan.)
        value = default
    else:
        try:
            value = int(raw)
        except (ValueError, TypeError):
            logging.getLogger(__name__).debug('int_cfg: non-numeric %r for %r; using default', raw, key)
            value = default
    return max(min_value, min(value, max_value))


def truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def free_sources_enabled(cfg: dict) -> bool:
    # Default ON: the keyless ATS/community APIs (Greenhouse/Lever/Ashby/Workable,
    # GitHub issues, HN, Reddit) are the zero-config backbone of discovery and must
    # run for a brand-new user in any country/field with no API key. An unset OR
    # blank value (e.g. a settings row written empty by the UI) means "not
    # configured" and stays ON; only an explicit falsey value opts out.
    raw = str(cfg.get("free_sources_enabled", "") or "").strip()
    if not raw:
        return True
    return truthy(raw)
