import logging
import asyncio
import hashlib
import os
import re
import threading
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlencode

from discovery.lead_intel import (
    fit_bullets as _fit_bullets,
    followup_sequence as _followup_sequence,
    location_from_text as _location_from_text,
    outreach_drafts as _lead_outreach_drafts,
    proof_snippet as _proof_snippet,
    tech_stack_from_text as _tech_stack_from_text,
    urgency_from_text as _urgency_from_text,
)
from data.repository import create_repository
from automation.lead_store import save_lead_compat as save_lead

_repo = create_repository()
rank_lead_by_feedback = _repo.feedback.rank_lead_by_feedback
url_exists = _repo.leads.url_exists


X_API_BASE = "https://api.x.com/2/tweets/search/recent"
LAST_ERRORS: list[str] = []
LAST_USAGE: dict[str, Any] = {}
# STABILITY: thread-safe scout diagnostics snapshot
_STATE_LOCK = threading.RLock()
# Per-call result sink (see free_scout._RESULT_SINK): lets source_adapters read this
# run()'s usage/errors from a per-call object instead of the shared module globals,
# so overlapping scans don't cross-report each other's diagnostics.
_RESULT_SINK: ContextVar[dict | None] = ContextVar("x_scout_result_sink", default=None)


def _publish_state(errors: list[str], usage: dict[str, Any]) -> None:
    global LAST_ERRORS, LAST_USAGE
    snapshot = dict(usage)
    with _STATE_LOCK:
        LAST_ERRORS = list(errors)
        LAST_USAGE = snapshot
    sink = _RESULT_SINK.get()
    if sink is not None:
        sink["usage"] = snapshot
        sink["errors"] = list(errors)

DEFAULT_QUERIES = [
    '("hiring" OR "job opening" OR "open role") ("AI engineer" OR "software engineer" OR "Python developer") lang:en -is:retweet',
    '("we are hiring" OR "is hiring") ("React developer" OR "backend engineer" OR "full stack engineer") lang:en -is:retweet',
    '("apply" OR "open role") (Python OR React OR FastAPI OR LLM) (remote OR hybrid) lang:en -is:retweet',
]

WATCHLIST_QUERY = (
    '(AI OR "AI agent" OR LLM OR RAG OR automation OR chatbot OR "web app" OR SaaS) '
    '("hiring" OR "job opening" OR "open role" OR "we are hiring" OR "apply") '
    'lang:en -is:retweet'
)

TECH_TERMS = (
    "ai", "agent", "agents", "llm", "rag", "chatbot", "automation", "openai",
    "claude", "langchain", "python", "fastapi", "react", "nextjs", "next.js",
    "typescript", "voice ai", "livekit", "deepgram", "api", "saas", "mvp",
)

ROLE_TERMS = (
    "marketing", "growth", "seo", "content", "sales", "business development",
    "account executive", "product manager", "designer", "design", "ui/ux",
    "data analyst", "data scientist", "analytics", "finance", "accounting",
    "operations", "supply chain", "customer success", "support", "hr",
    "human resources", "recruiter", "talent", "consultant", "manager",
    "associate", "coordinator", "intern", "job", "role",
)

INTENT_TERMS = (
    "hiring", "job opening", "open role", "role available", "we're hiring",
    "we are hiring", "is hiring", "apply", "internship", "new grad",
    "entry level", "junior developer", "graduate engineer",
)

JOB_TERMS = (
    "hiring", "job opening", "open role", "full-time", "full time",
    "part-time", "part time", "role available", "we're hiring",
    "we are hiring", "apply",
)

URGENCY_TERMS = (
    "asap", "urgent", "today", "tomorrow", "this week", "immediately",
    "quickly", "by friday", "next 48", "next week",
)

BUYER_TERMS = (
    "budget", "rate", "paid", "$", "client", "for our", "for my",
    "build for us", "hire", "paying",
)

NOISE_TERMS = (
    "course", "newsletter", "thread", "tutorial", "webinar", "podcast",
    "just launched", "we launched", "i built", "i made", "template",
    "giveaway", "airdrop", "meme", "crypto",
)


def _h(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()[:16]


def _int_setting(value, default: int, min_value: int, max_value: int) -> int:
    # `value or ""` treated a legitimate integer 0 as unset (0 is falsy) and fell
    # back to the default — silently overriding a user's explicit x_min_signal_score
    # of 0 ("accept all"). Only None/blank is unset; a real 0 is a valid choice.
    # (Same explicit-0-vs-unset fix free_scout.run already carries.)
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        parsed = int(text)
    except (ValueError, TypeError) as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/automation/x_scout.py:_int_setting: %s', log_exc)
        parsed = default
    return max(min_value, min(parsed, max_value))


def split_queries(raw: str | None) -> list[str]:
    queries: list[str] = []
    for line in str(raw or "").splitlines():
        line = line.strip().rstrip(",")
        if not line or line.startswith("#"):
            continue
        queries.append(line)
    return queries or DEFAULT_QUERIES


def split_watchlist(raw: str | None) -> list[str]:
    handles: list[str] = []
    for line in str(raw or "").replace(",", "\n").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if value.startswith("https://x.com/") or value.startswith("https://twitter.com/"):
            value = value.replace("https://x.com/", "").replace("https://twitter.com/", "").split("/")[0]
        elif "/" in value:
            continue
        value = value.strip().lstrip("@")
        if re.fullmatch(r"[A-Za-z0-9_]{1,15}", value):
            handles.append(value)
    return list(dict.fromkeys(handles))


def build_watchlist_queries(raw_watchlist: str | None) -> list[str]:
    return [f"from:{handle} {WATCHLIST_QUERY}" for handle in split_watchlist(raw_watchlist)]


def build_queries(raw_queries: str | None = None, raw_watchlist: str | None = None) -> list[str]:
    return split_queries(raw_queries) + build_watchlist_queries(raw_watchlist)


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _matched_terms(text: str, terms: tuple[str, ...], limit: int = 4) -> list[str]:
    return [term for term in terms if term in text][:limit]


def classify_post(text: str) -> str | None:
    lower = _collapse_whitespace(text).lower()
    if not lower:
        return None
    if not (_has_any(lower, TECH_TERMS) or _has_any(lower, ROLE_TERMS)):
        return None
    if not _has_any(lower, INTENT_TERMS):
        return None

    if _has_any(lower, NOISE_TERMS) and not _has_any(lower, JOB_TERMS):
        return None

    if _has_any(lower, JOB_TERMS):
        return "job"
    return None


def signal_quality(text: str, user: dict | None = None, kind: str | None = None) -> dict:
    lower = _collapse_whitespace(text).lower()
    tags: list[str] = []
    reasons: list[str] = []
    score = 0

    tech = _matched_terms(lower, TECH_TERMS + ROLE_TERMS)
    intent = _matched_terms(lower, INTENT_TERMS)
    urgency = _matched_terms(lower, URGENCY_TERMS)
    buyer = _matched_terms(lower, BUYER_TERMS)
    noise = _matched_terms(lower, NOISE_TERMS)

    if tech:
        score += 25
        tags.extend(tech[:3])
        reasons.append("role/profile signal: " + ", ".join(tech[:3]))
    if intent:
        score += 25
        tags.extend(intent[:3])
        reasons.append("buyer/hiring intent: " + ", ".join(intent[:3]))
    if kind == "job":
        score += 6
        tags.append("job")
    if urgency:
        score += 15
        tags.append("urgent")
        reasons.append("urgency: " + ", ".join(urgency[:2]))
    if buyer:
        score += 12
        tags.append("buyer")
        reasons.append("commercial signal: " + ", ".join(buyer[:2]))
    if _budget_from_text(text):
        score += 10
        tags.append("budget")
    if re.search(r"\b(dm|email|reply|apply)\b", lower):
        score += 6
        tags.append("clear_next_step")

    followers = ((user or {}).get("public_metrics") or {}).get("followers_count", 0) or 0
    if followers >= 5000:
        score += 4
        tags.append("established_author")
    if (user or {}).get("verified"):
        score += 3
        tags.append("verified_author")
    if noise:
        score -= 22
        reasons.append("noise penalty: " + ", ".join(noise[:2]))

    score = max(0, min(100, score))
    if not reasons:
        reasons.append("X post matched configured search")
    return {
        "score": score,
        "reason": "; ".join(reasons),
        "tags": list(dict.fromkeys(tags)),
    }


def _budget_from_text(text: str) -> str:
    patterns = [
        r"\$\s?\d[\d,]*(?:\s*(?:-|to)\s*\$?\s?\d[\d,]*)?(?:\s*/?\s*(?:hr|hour|day|week|month))?",
        r"(?:budget|rate)\s*[:\-]\s*([^\n.;,]{2,80})",
    ]
    for pat in patterns:
        m = re.search(pat, text or "", flags=re.I)
        if m:
            value = m.group(1) if m.lastindex else m.group(0)
            return value.strip(" .;-")[:120]
    return ""


def _title_from_text(text: str, kind: str) -> str:
    clean = _collapse_whitespace(re.sub(r"https?://\S+", "", text))
    clean = clean[:150].strip(" .")
    if clean:
        return clean
    return "X job lead"


def _tweet_url(tweet: dict, user: dict | None) -> str:
    username = (user or {}).get("username")
    if username:
        return f"https://x.com/{username}/status/{tweet.get('id', '')}"
    return f"https://x.com/i/web/status/{tweet.get('id', '')}"


def _profile_url(user: dict | None) -> str:
    username = (user or {}).get("username")
    return f"https://x.com/{username}" if username else ""


def _outreach_from_lead(text: str, user: dict | None, kind: str, budget: str) -> dict:
    username = (user or {}).get("username", "")
    name = (user or {}).get("name") or (f"@{username}" if username else "there")
    handle = f"@{username}" if username else name
    clean = _collapse_whitespace(text)
    project_hint = "AI/automation build"
    for term in ("AI agent", "LLM", "RAG", "chatbot", "automation", "FastAPI", "React", "SaaS"):
        if term.lower() in clean.lower():
            project_hint = term
            break

    reply = (
        f"{handle} this looks aligned with my AI automation, Python, and React work. "
        "Happy to share relevant projects or apply through the right channel."
    )
    dm = (
        f"Hey {name}, saw the hiring post for {project_hint}. "
        "My background is in AI agents, automation, Python/FastAPI, and React. "
        "I can send a concise fit summary plus project links if you are open to it."
    )
    return {"reply": reply[:500], "dm": dm[:900]}


def _lead_from_tweet(tweet: dict, user: dict | None, kind: str, query: str) -> dict:
    text = _collapse_whitespace(tweet.get("text", ""))
    url = _tweet_url(tweet, user)
    metrics = tweet.get("public_metrics") or {}
    metric_bits = [
        f"likes={metrics.get('like_count', 0)}",
        f"reposts={metrics.get('retweet_count', 0)}",
        f"replies={metrics.get('reply_count', 0)}",
    ]
    created = tweet.get("created_at", "")
    author_bits = []
    if (user or {}).get("description"):
        author_bits.append("Bio: " + _collapse_whitespace((user or {}).get("description", ""))[:240])
    if (user or {}).get("location"):
        author_bits.append("Location: " + str((user or {}).get("location", ""))[:120])
    if _profile_url(user):
        author_bits.append("Profile: " + _profile_url(user))

    description = "\n".join(part for part in [
        text,
        f"Posted: {created}" if created else "",
        "X metrics: " + ", ".join(metric_bits),
        *author_bits,
    ] if part)
    username = (user or {}).get("username", "")
    company = f"@{username}" if username else (user or {}).get("name", "X lead")
    quality = signal_quality(text, user, kind)
    budget = ""
    outreach = _outreach_from_lead(text, user, kind, budget)
    title = _title_from_text(text, kind)
    lead_outreach = _lead_outreach_drafts(title, company, description, kind, budget)
    stack = _tech_stack_from_text(description)
    location = _location_from_text(description)
    urgency = _urgency_from_text(description)
    lead = {
        "job_id": _h(f"x:{tweet.get('id', url)}"),
        "title": title,
        "company": company,
        "url": url,
        "platform": "x",
        "description": description,
        "kind": kind,
        "budget": budget,
        "signal_score": quality["score"],
        "signal_reason": quality["reason"],
        "signal_tags": quality["tags"],
        "outreach_reply": outreach["reply"],
        "outreach_dm": outreach["dm"],
        "outreach_email": lead_outreach["email"],
        "proposal_draft": lead_outreach["proposal"],
        "fit_bullets": _fit_bullets(title, description),
        "followup_sequence": _followup_sequence(company, kind),
        "proof_snippet": _proof_snippet(title, description, kind),
        "tech_stack": stack,
        "location": location,
        "urgency": urgency,
        "source_meta": {
            "query": query,
            "tweet_id": tweet.get("id", ""),
            "created_at": created,
            "tech_stack": stack,
            "location": location,
            "urgency": urgency,
            "author": {
                "id": (user or {}).get("id", ""),
                "username": username,
                "name": (user or {}).get("name", ""),
                "verified": bool((user or {}).get("verified")),
                "followers": ((user or {}).get("public_metrics") or {}).get("followers_count", 0),
                "bio": (user or {}).get("description", ""),
                "location": (user or {}).get("location", ""),
                "url": (user or {}).get("url", ""),
            },
            "metrics": metrics,
        },
    }
    from discovery.normalizer import classify_job_seniority

    lead["source_meta"]["seniority_level"] = classify_job_seniority(lead)
    return lead


async def _search_recent(bearer_token: str, query: str, max_results: int = 50) -> tuple[list[dict], dict[str, dict]]:
    import httpx

    params = {
        "query": query,
        "max_results": str(max(10, min(max_results, 100))),
        "sort_order": "recency",
        "tweet.fields": "author_id,created_at,conversation_id,entities,lang,public_metrics",
        "expansions": "author_id",
        "user.fields": "name,username,verified,public_metrics,description,location,url",
    }
    headers = {"Authorization": f"Bearer {bearer_token}"}
    url = f"{X_API_BASE}?{urlencode(params)}"
    async with httpx.AsyncClient(timeout=30, headers=headers) as cx:
        r = await cx.get(url)
        if r.status_code >= 400:
            detail = r.text[:500]
            raise RuntimeError(f"X API {r.status_code}: {detail}")
        payload = r.json()

    users = {
        str(user.get("id")): user
        for user in payload.get("includes", {}).get("users", [])
        if user.get("id")
    }
    return payload.get("data", []) or [], users


def run(
    bearer_token: str | None = None,
    raw_queries: str | None = None,
    queries: list[str] | None = None,
    kind_filter: str | None = None,
    max_results: int = 50,
    raw_watchlist: str | None = None,
    max_requests: int = 5,
    min_signal_score: int = 55,
) -> list[dict]:
    errors: list[str] = []
    usage: dict[str, Any] = {
        "configured_queries": 0,
        "executed_queries": 0,
        "tweets_seen": 0,
        "saved": 0,
        "filtered": 0,
        "max_requests": max_requests,
    }

    token = bearer_token or os.environ.get("X_BEARER_TOKEN") or os.environ.get("TWITTER_BEARER_TOKEN")
    if not token:
        errors.append("X bearer token is not configured")
        _publish_state(errors, usage)
        return []

    wanted = "job"
    max_requests = _int_setting(max_requests, 5, 1, 50)
    max_results = _int_setting(max_results, 50, 10, 100)
    min_signal_score = _int_setting(min_signal_score, 55, 0, 100)
    leads: list[dict] = []
    seen: set[str] = set()
    targets = queries or build_queries(raw_queries, raw_watchlist)
    usage["configured_queries"] = len(targets)

    for query in targets[:max_requests]:
        try:
            tweets, users = asyncio.run(_search_recent(token, query, max_results=max_results))
            usage["executed_queries"] += 1
            usage["tweets_seen"] += len(tweets)
        except Exception as exc:
            logging.getLogger(__name__).warning('suppressed exception in backend/automation/x_scout.py:run: %s', exc)
            detail = str(exc).strip() or type(exc).__name__
            errors.append(f"{query}: {detail}")
            if "429" in detail:
                break
            continue

        for tweet in tweets:
            kind = classify_post(tweet.get("text", ""))
            if not kind or (wanted and kind != wanted):
                usage["filtered"] += 1
                continue
            lead = _lead_from_tweet(tweet, users.get(str(tweet.get("author_id"))), kind, query)
            lead = rank_lead_by_feedback(lead)
            if lead["signal_score"] < min_signal_score:
                usage["filtered"] += 1
                continue
            if lead["job_id"] in seen or url_exists(lead["job_id"]):
                continue
            seen.add(lead["job_id"])
            save_lead(
                lead["job_id"],
                lead["title"],
                lead["company"],
                lead["url"],
                lead["platform"],
                lead["description"],
                kind=lead["kind"],
                budget=lead["budget"],
                signal_score=lead["signal_score"],
                signal_reason=lead["signal_reason"],
                signal_tags=lead["signal_tags"],
                outreach_reply=lead["outreach_reply"],
                outreach_dm=lead["outreach_dm"],
                outreach_email=lead.get("outreach_email", ""),
                proposal_draft=lead.get("proposal_draft", ""),
                fit_bullets=lead.get("fit_bullets", []),
                followup_sequence=lead.get("followup_sequence", []),
                proof_snippet=lead.get("proof_snippet", ""),
                tech_stack=lead.get("tech_stack", []),
                location=lead.get("location", ""),
                urgency=lead.get("urgency", ""),
                base_signal_score=lead.get("base_signal_score"),
                learning_delta=lead.get("learning_delta"),
                learning_reason=lead.get("learning_reason", ""),
                source_meta=lead["source_meta"],
            )
            usage["saved"] += 1
            leads.append(lead)

    if len(targets) > max_requests:
        errors.append(f"Request cap hit: ran {max_requests} of {len(targets)} X queries")

    _publish_state(errors, usage)
    return leads
