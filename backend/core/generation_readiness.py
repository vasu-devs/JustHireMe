from __future__ import annotations

import re


_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)

# A truthful tailored resume needs real role context to work from, not just a
# bare title or URL. We gate on the *substance* of the non-URL text (its length
# and word count) rather than a keyword whitelist. JustHireMe tailors resumes
# for every field — finance, healthcare, education, trades, the arts — so an
# earlier software/tech keyword requirement wrongly blocked legitimate non-tech
# descriptions (e.g. a "Financial Aid Advisor" posting). See issue #92.
_MIN_CONTEXT_CHARS = 40
_MIN_CONTEXT_WORDS = 10


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
    if len(non_url_context) < _MIN_CONTEXT_CHARS or len(non_url_context.split()) < _MIN_CONTEXT_WORDS:
        return "Paste a fuller job description before generating so the resume can be tailored without guessing."
    return ""
