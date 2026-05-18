from __future__ import annotations

import re


_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
_ROLE_OR_STACK_RE = re.compile(
    r"\b(engineer|developer|designer|analyst|scientist|intern|software|backend|frontend|full[- ]?stack|"
    r"data|ai|ml|python|fastapi|react|typescript|java|c\+\+|sql|api|llm|rag)\b",
    re.I,
)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _without_urls(value: object) -> str:
    return _clean(_URL_RE.sub(" ", str(value or "")))


def _is_url_only(value: object) -> bool:
    text = _clean(value)
    if not text:
        return False
    remainder = _URL_RE.sub(" ", text)
    remainder = re.sub(r"[\s|,;:(){}\[\]\-_/]+", "", remainder)
    return not remainder


def lead_generation_blocker(lead: dict) -> str:
    """Return a user-facing reason when a lead is too thin to generate safely."""
    meta: dict = lead.get("source_meta") if isinstance(lead.get("source_meta"), dict) else {}
    title = _clean(lead.get("title"))
    company = _clean(lead.get("company"))
    description = _clean(lead.get("description"))
    reason = _clean(lead.get("reason"))
    match_points = " ".join(str(item or "") for item in lead.get("match_points", []) or [])
    non_url_context = _without_urls("\n".join([title, company, description, reason, match_points]))

    if meta.get("input_url_only") or meta.get("needs_job_description"):
        return "Paste the job description before generating. A URL alone is not enough evidence for a truthful resume."
    if _is_url_only(title) and (not description or _is_url_only(description)):
        return "Paste the job description before generating. The current lead only contains a URL."
    if not description and not reason and not match_points:
        return "Paste the job description before generating. The current lead has no role requirements to tailor against."
    if len(non_url_context) < 35 or not _ROLE_OR_STACK_RE.search(non_url_context):
        return "Paste a fuller job description before generating so the resume can be tailored without guessing."
    return ""
