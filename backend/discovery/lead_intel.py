import hashlib
import re
from urllib.parse import urlparse
from core.logging import get_logger

_log = get_logger(__name__)


TECH_TERMS = (
    "ai", "agent", "agents", "llm", "rag", "chatbot", "automation", "openai",
    "claude", "python", "fastapi", "react", "nextjs", "next.js", "typescript",
    "api", "saas", "mvp", "backend", "frontend", "full-stack", "full stack",
)

TECH_LABELS = {
    "ai": "AI",
    "agent": "AI agents",
    "agents": "AI agents",
    "llm": "LLM",
    "rag": "RAG",
    "chatbot": "chatbot",
    "automation": "automation",
    "openai": "OpenAI",
    "claude": "Claude",
    "python": "Python",
    "fastapi": "FastAPI",
    "react": "React",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "typescript": "TypeScript",
    "api": "API",
    "saas": "SaaS",
    "mvp": "MVP",
    "backend": "backend",
    "frontend": "frontend",
    "full-stack": "full-stack",
    "full stack": "full-stack",
}

INTENT_TERMS = (
    "hiring", "job opening", "open role", "role available", "we're hiring",
    "we are hiring", "is hiring", "apply", "help wanted", "internship",
    "junior", "entry level", "new grad", "graduate",
)

JOB_TERMS = (
    "hiring", "job opening", "open role", "full-time", "full time",
    "part-time", "part time", "apply", "salary", "remote",
)

URGENCY_TERMS = (
    "asap", "urgent", "today", "tomorrow", "this week", "immediately",
    "quickly", "next 48", "soon",
)

NOISE_TERMS = (
    "course", "newsletter", "tutorial", "podcast", "giveaway",
    "airdrop", "meme", "crypto",
)


def lead_id(prefix: str, value: str) -> str:
    return hashlib.md5(f"{prefix}:{value}".encode()).hexdigest()[:16]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def matched_terms(text: str, terms: tuple[str, ...], limit: int = 5) -> list[str]:
    return [term for term in terms if term in text][:limit]


def budget_from_text(text: str) -> str:
    patterns = [
        r"\$\s?\d[\d,]*(?:\s*(?:-|to)\s*\$?\s?\d[\d,]*)?(?:\s*/?\s*(?:hr|hour|day|week|month))?",
        r"(?:budget|rate|salary)\s*[:\-]\s*([^\n.;,]{2,90})",
    ]
    for pat in patterns:
        match = re.search(pat, text or "", flags=re.I)
        if match:
            value = match.group(1) if match.lastindex else match.group(0)
            return value.strip(" .;-")[:120]
    return ""


def tech_stack_from_text(text: str) -> list[str]:
    lower = clean_text(text).lower()
    found = [TECH_LABELS.get(term, term) for term in TECH_TERMS if term in lower]
    return list(dict.fromkeys(found))[:10]


def urgency_from_text(text: str) -> str:
    lower = clean_text(text).lower()
    urgent = matched_terms(lower, URGENCY_TERMS, limit=3)
    if urgent:
        return ", ".join(urgent)
    return ""


def location_from_text(text: str) -> str:
    clean = clean_text(text)
    lower = clean.lower()
    if "remote" in lower:
        if "us remote" in lower or "remote us" in lower or "remote (us" in lower:
            return "Remote US"
        if "india" in lower:
            return "Remote India"
        return "Remote"
    patterns = [
        r"(?:location|based in|onsite|hybrid)\s*[:\-]?\s*([A-Z][A-Za-z .,/+-]{2,80})",
        r"\b(San Francisco|New York|London|Berlin|Bengaluru|Bangalore|Mumbai|Delhi|Toronto|Singapore)\b",
    ]
    for pat in patterns:
        match = re.search(pat, clean, flags=re.I)
        if match:
            return match.group(1).strip(" .")[:120]
    return ""


def company_from_text(text: str, fallback: str = "Manual Lead") -> str:
    for line in str(text or "").splitlines():
        match = re.match(r"\s*(?:company|client|startup)\s*[:\-]\s*(.+?)\s*$", line, flags=re.I)
        if match:
            value = match.group(1).strip(" .-|")
            if value:
                return value[:120]
    clean = clean_text(text)
    patterns = [
        r"(?:company|client|startup)\s*[:\-]\s*([A-Za-z0-9 .&_-]{2,80})",
        r"\bat\s+([A-Z][A-Za-z0-9 .&_-]{2,80})",
        r"^([A-Z][A-Za-z0-9 .&_-]{2,80})\s+\|\s+",
    ]
    for pat in patterns:
        match = re.search(pat, clean, flags=re.I)
        if match:
            return match.group(1).strip(" .-|")[:120]
    return fallback


def classify_kind(text: str, default: str = "job") -> str:
    lower = clean_text(text).lower()
    if has_any(lower, JOB_TERMS):
        return "job"
    return "job"


def signal_quality(text: str, default_kind: str = "job") -> dict:
    lower = clean_text(text).lower()
    kind = classify_kind(lower, default_kind)
    tech = matched_terms(lower, TECH_TERMS)
    intent = matched_terms(lower, INTENT_TERMS)
    urgency = matched_terms(lower, URGENCY_TERMS)
    noise = matched_terms(lower, NOISE_TERMS)

    tags: list[str] = []
    reasons: list[str] = []
    score = 18

    if tech:
        score += 25
        tags.extend(tech[:4])
        reasons.append("technical fit: " + ", ".join(tech[:4]))
    if intent:
        score += 24
        tags.extend(intent[:4])
        reasons.append("intent: " + ", ".join(intent[:4]))
    if budget_from_text(text):
        score += 10
        tags.append("budget")
    if urgency:
        score += 12
        tags.append("urgent")
        reasons.append("urgency: " + ", ".join(urgency[:2]))
    if kind == "job":
        score += 6
        tags.append("job")
    if re.search(r"\b(remote|apply|email|dm|reply|proposal)\b", lower):
        score += 5
        tags.append("clear_next_step")
    if noise:
        score -= 20
        reasons.append("noise penalty: " + ", ".join(noise[:2]))

    score = max(0, min(100, score))
    if not reasons:
        reasons.append("manual/free source lead")
    return {
        "kind": kind,
        "score": score,
        "reason": "; ".join(reasons),
        "tags": list(dict.fromkeys(tags)),
    }


def fit_bullets(title: str, text: str) -> list[str]:
    stack = tech_stack_from_text(text)
    bullets = []
    if stack:
        bullets.append("Relevant stack: " + ", ".join(stack[:5]))
    if "automation" in clean_text(text).lower() or "agent" in clean_text(text).lower():
        bullets.append("Can turn ambiguous workflows into a scoped AI automation plan.")
    if "react" in clean_text(text).lower() or "frontend" in clean_text(text).lower():
        bullets.append("Can ship the user-facing interface as well as the backend logic.")
    if "fastapi" in clean_text(text).lower() or "api" in clean_text(text).lower():
        bullets.append("Comfortable building production APIs and integrations.")
    if not bullets:
        bullets.append("Can quickly map requirements, identify risks, and propose a practical first milestone.")
    return bullets[:5]


def proof_snippet(title: str, text: str, kind: str) -> str:
    stack = tech_stack_from_text(text)
    stack_line = ", ".join(stack[:4]) if stack else "AI automation, Python, React"
    return (
        f"Credibility block: my strongest angle for this role is practical shipping across "
        f"{stack_line}, with emphasis on turning product requirements into working systems."
    )


def followup_sequence(company: str, kind: str) -> list[str]:
    label = company or "there"
    return [
        f"Day 2: Follow up with a concise fit summary for {label}.",
        "Day 5: Send a project/proof snippet mapped to the role requirements.",
        "Day 10: Ask whether there is a better contact or application path.",
    ]


def outreach_drafts(title: str, company: str, text: str, kind: str, budget: str = "") -> dict:
    clean = clean_text(text)
    project = title or "the role"
    for term in ("AI agent", "LLM", "RAG", "chatbot", "automation", "FastAPI", "React", "SaaS"):
        if term.lower() in clean.lower():
            project = term
            break
    company_label = company or "there"
    reply = (
        f"This looks aligned with my AI automation, Python, and React work. "
        "Happy to share relevant projects or apply through the right channel."
    )
    dm = (
        f"Hey {company_label}, saw the opening for {project}. "
        "My background is in AI agents, automation, Python/FastAPI, and React. "
        "I can send a tight fit summary plus project links."
    )
    email = (
        f"Subject: {title or project} - relevant AI/product engineering background\n\n"
        f"Hi {company_label},\n\n"
        "I saw the opening and it maps well to my work across AI automation, Python/FastAPI, and React. "
        "I would be happy to share a concise fit summary and relevant project examples.\n\nBest,\n"
    )
    proposal = (
        "Role-fit pitch:\n"
        "1. I can contribute across backend, automation, and product-facing UI.\n"
        "2. I am strongest where ambiguous AI/product workflows need to become reliable shipped systems.\n"
        "3. I can provide project examples aligned with the role requirements."
    )
    return {"reply": reply[:500], "dm": dm[:900], "email": email[:1200], "proposal": proposal[:1200]}


def company_from_url(url: str) -> str:
    try:
        host = urlparse(url if "://" in url else "https://" + url).netloc.lower()
    except Exception:
        host = ""
    host = host.replace("www.", "")
    if not host:
        return "Manual Lead"
    first = host.split(".")[0]
    return first[:1].upper() + first[1:]


def manual_lead_from_text(text: str, url: str = "", default_kind: str = "job") -> dict:
    raw = text or url or ""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    title = next((line for line in lines if len(line) <= 180), "") or "Manual lead"
    company = company_from_text(raw, company_from_url(url))
    budget = budget_from_text(raw)
    quality = signal_quality(raw, default_kind=default_kind)
    kind = quality["kind"]
    outreach = outreach_drafts(title, company, raw, kind, budget)
    stack = tech_stack_from_text(raw)
    urgency = urgency_from_text(raw)
    location = location_from_text(raw)
    bullets = fit_bullets(title, raw)
    source_url = url.strip() or f"manual://{lead_id('manual', raw)}"
    return {
        "job_id": lead_id("manual", source_url + raw[:300]),
        "title": title[:220],
        "company": company,
        "url": source_url,
        "platform": "manual",
        "description": raw[:1200],
        "kind": kind,
        "budget": budget,
        "signal_score": quality["score"],
        "signal_reason": quality["reason"],
        "signal_tags": quality["tags"],
        "outreach_reply": outreach["reply"],
        "outreach_dm": outreach["dm"],
        "outreach_email": outreach["email"],
        "proposal_draft": outreach["proposal"],
        "fit_bullets": bullets,
        "followup_sequence": followup_sequence(company, kind),
        "proof_snippet": proof_snippet(title, raw, kind),
        "tech_stack": stack,
        "location": location,
        "urgency": urgency,
        "source_meta": {
            "source": "manual",
            "tech_stack": stack,
            "location": location,
            "urgency": urgency,
        },
    }
