import json
import os
import re
import urllib.parse
import urllib.request

from core.logging import get_logger

_log = get_logger(__name__)


ATS_HOSTS = {
    "boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.ashbyhq.com",
    "apply.workable.com",
    "wellfound.com",
    "linkedin.com",
    "www.linkedin.com",
    "indeed.com",
    "www.indeed.com",
}


CONTACT_PRIORITY = (
    "founder",
    "co-founder",
    "ceo",
    "cto",
    "head of engineering",
    "vp engineering",
    "engineering manager",
    "hiring manager",
    "recruiter",
    "talent",
    "people",
    "hr",
)


def _setting(settings: dict, *keys: str) -> str:
    for key in keys:
        value = settings.get(key)
        if value:
            return str(value).strip()
    return ""


def _domain_from_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url if "://" in url else f"https://{url}")
    except Exception:
        return ""
    host = (parsed.netloc or "").lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if not host or host in ATS_HOSTS:
        return ""
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def _domain_from_meta(lead: dict) -> str:
    meta: dict = lead.get("source_meta") if isinstance(lead.get("source_meta"), dict) else {}
    for key in ("company_domain", "domain", "website"):
        domain = _domain_from_url(str(meta.get(key) or ""))
        if domain:
            return domain
    return ""


def _infer_company_domain(lead: dict, settings: dict) -> str:
    override = _setting(settings, "contact_lookup_domain", "company_domain_override")
    if override:
        return _domain_from_url(override)
    return _domain_from_meta(lead) or _domain_from_url(str(lead.get("url") or ""))


def _json_get(url: str, headers: dict | None = None, timeout: int = 12) -> dict:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "JustHireMe/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw or "{}")


def _clean_contact(raw: dict) -> dict:
    first = str(raw.get("first_name") or "").strip()
    last = str(raw.get("last_name") or "").strip()
    name = " ".join(part for part in [first, last] if part).strip()
    if not name:
        name = str(raw.get("name") or "").strip()
    return {
        "name": name,
        "first_name": first or name.split(" ")[0] if name else "",
        "title": str(raw.get("position") or raw.get("title") or "").strip(),
        "email": str(raw.get("value") or raw.get("email") or "").strip(),
        "linkedin_url": str(raw.get("linkedin") or raw.get("linkedin_url") or "").strip(),
        "confidence": raw.get("confidence") or 0,
        "source": "hunter",
    }


def _contact_score(contact: dict) -> tuple[int, int]:
    hay = f"{contact.get('title','')} {contact.get('name','')}".lower()
    priority = 0
    for idx, term in enumerate(CONTACT_PRIORITY):
        if term in hay:
            priority = max(priority, len(CONTACT_PRIORITY) - idx)
    confidence = int(contact.get("confidence") or 0)
    return priority, confidence


def _hunter_contacts(domain: str, key: str) -> list[dict]:
    params = urllib.parse.urlencode({"domain": domain, "api_key": key, "limit": 10})
    url = f"https://api.hunter.io/v2/domain-search?{params}"
    data = _json_get(url)
    emails = ((data.get("data") or {}).get("emails") or [])
    contacts = [_clean_contact(item) for item in emails if item.get("value")]
    contacts.sort(key=_contact_score, reverse=True)
    return contacts[:5]


def _extract_manager_name(text: str) -> str:
    patterns = [
        r"hiring manager\s*[:\-]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
        r"recruiter\s*[:\-]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
        r"contact\s*[:\-]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
        r"report(?:s|ing)?\s+to\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "")
        if match:
            return match.group(1).strip()
    return ""


def _proxycurl_linkedin(domain: str, key: str, contact: dict, lead: dict) -> str:
    if contact.get("linkedin_url"):
        return str(contact["linkedin_url"])
    name = contact.get("name") or _extract_manager_name(str(lead.get("description") or ""))
    parts = [p for p in str(name).split() if p]
    if len(parts) < 2:
        return ""
    params = urllib.parse.urlencode({
        "company_domain": domain,
        "first_name": parts[0],
        "last_name": " ".join(parts[1:]),
    })
    url = f"https://nubela.co/proxycurl/api/linkedin/profile/resolve?{params}"
    data = _json_get(url, headers={"Authorization": f"Bearer {key}"})
    return str(data.get("url") or data.get("linkedin_profile_url") or data.get("profile_url") or "")


def _candidate_name(settings: dict, profile: dict) -> str:
    return str(profile.get("n") or settings.get("candidate_name") or settings.get("first_name") or "Candidate").strip()


def _skills_line(lead: dict) -> str:
    stack: list = lead.get("tech_stack") if isinstance(lead.get("tech_stack"), list) else []
    terms = [str(x).strip() for x in stack if str(x).strip()]
    if not terms:
        terms = re.findall(r"\b(?:Python|FastAPI|React|TypeScript|AWS|Docker|Kubernetes|LLM|AI|PostgreSQL|Kafka|CI/CD)\b", str(lead.get("description") or ""), re.I)
    uniq: list[str] = []
    for term in terms:
        clean = term.upper() if term.lower() == "ci/cd" else term
        if clean.lower() not in {x.lower() for x in uniq}:
            uniq.append(clean)
    if not uniq:
        return "the stack and product needs in the role"
    return ", ".join(uniq[:4])


def _personalized_email(lead: dict, contact: dict, settings: dict, profile: dict) -> str:
    title = str(lead.get("title") or "the role").strip()
    company = str(lead.get("company") or "your team").strip()
    first = str(contact.get("first_name") or contact.get("name") or "").split(" ")[0] or "there"
    candidate = _candidate_name(settings, profile)
    skills = _skills_line(lead)
    return (
        f"Subject: Quick note on {title}\n\n"
        f"Hi {first},\n\n"
        f"I saw {company} is hiring for {title}. I generated a tailored application package for the role, "
        f"and the work maps closely to my background in {skills}.\n\n"
        "Could I send over the resume and a short role-fit summary?\n\n"
        f"Best,\n{candidate}"
    )


def run(lead: dict, settings: dict | None = None, profile: dict | None = None) -> dict:
    settings = settings or {}
    profile = profile or {}
    if _setting(settings, "contact_lookup_enabled").lower() in {"0", "false", "off", "no"}:
        return {"status": "disabled", "contacts": []}

    domain = _infer_company_domain(lead, settings)
    if not domain:
        return {"status": "no_domain", "contacts": [], "message": "Could not infer company domain from this job URL."}

    hunter_key = _setting(settings, "hunter_api_key") or os.environ.get("HUNTER_API_KEY", "")
    proxycurl_key = _setting(settings, "proxycurl_api_key") or os.environ.get("PROXYCURL_API_KEY", "")
    if not hunter_key:
        return {"status": "missing_hunter_key", "domain": domain, "contacts": [], "message": "Add a Hunter.io API key in Settings to find company contacts."}

    try:
        contacts = _hunter_contacts(domain, hunter_key)
    except Exception as exc:
        return {"status": "error", "domain": domain, "contacts": [], "message": f"Hunter lookup failed: {exc}"}

    if not contacts:
        return {"status": "not_found", "domain": domain, "contacts": [], "message": "Hunter did not return usable contacts for this domain."}

    primary = contacts[0]
    if proxycurl_key:
        try:
            linkedin = _proxycurl_linkedin(domain, proxycurl_key, primary, lead)
            if linkedin:
                primary["linkedin_url"] = linkedin
        except Exception as exc:
            primary["linkedin_error"] = str(exc)

    primary["personalized_email"] = _personalized_email(lead, primary, settings, profile)
    return {
        "status": "found",
        "domain": domain,
        "primary_contact": primary,
        "contacts": contacts,
    }
