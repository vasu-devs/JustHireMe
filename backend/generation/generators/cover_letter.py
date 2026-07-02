from __future__ import annotations

import re

from generation.generators.base import GeneratedAsset, _DocPackage
from generation.generators.outreach_email import _fallback_outreach
from generation.generators.resume import _fallback_package, _rank_projects, _resume_needs_fallback


_COVER_HEADING_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*cover\s+letter(?:\s*(?:for|to|[-:])\s*[^\n*]+)?\s*(?:\*\*)?\s*:?\s*$"
)
_COVER_SALUTATION_RE = re.compile(
    r"(?im)^\s*(?:(?:dear|hello|hi)\s+(?:the\s+)?[a-z0-9&.,' /\-]{2,90}|to\s+whom\s+it\s+may\s+concern|to\s+(?:the\s+)?(?:hiring|recruiting|talent|people|engineering|product|founding|founder)[a-z0-9&.,' /\-]{0,70})\s*,?\s*$"
)
_RESUME_HEADING_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*resume(?:\s*(?:for|to|[-:])\s*[^\n*]+)?\s*(?:\*\*)?\s*:?\s*$"
)


def _strip_doc_heading(text: str, heading: str) -> str:
    if heading.lower() == "cover letter":
        pattern = _COVER_HEADING_RE
    elif heading.lower() == "resume":
        pattern = _RESUME_HEADING_RE
    else:
        pattern = re.compile(
            rf"(?im)^\s*(?:#{{1,6}}\s*)?(?:\*\*)?\s*{re.escape(heading)}\s*(?:\*\*)?\s*:?\s*$"
        )
    return pattern.sub("", text, count=1).strip()


def _is_trivial_doc(text: str, kind: str) -> bool:
    cleaned = re.sub(r"(?im)^\s*(?:#{1,6}\s*)?(resume|cover\s+letter)\s*:?\s*$", "", text or "")
    cleaned = re.sub(r"[*_`#>\-\s]+", " ", cleaned).strip()
    alpha = re.sub(r"[^A-Za-z]+", "", cleaned)
    if not alpha:
        return True
    # A useful cover letter needs more than a salutation/signoff stub.
    if kind == "cover" and len(cleaned) < 120:
        return True
    return kind == "resume" and len(cleaned) < 160


def _split_cover_from_resume(text: str) -> tuple[str, str]:
    source = text or ""
    matches = [
        match
        for pattern in (_COVER_HEADING_RE, _COVER_SALUTATION_RE)
        for match in [pattern.search(source)]
        if match
    ]
    match = min(matches, key=lambda item: item.start()) if matches else None
    if not match:
        return source, ""
    resume = source[:match.start()].strip()
    cover = source[match.start():].strip()
    return resume, cover


def _shorten_chars(text: str, limit: int) -> str:
    """Trim to <= limit chars on a word boundary (clean for copy-paste)."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:-–—")


def _shorten_words(text: str, max_words: int) -> str:
    text = (text or "").strip()
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(" ,;:-")


def _normalize_package(package: _DocPackage, profile: dict, lead: dict, template: str = "") -> _DocPackage:
    """Defensively split combined LLM output into two real documents."""
    resume = package.resume_markdown or ""
    cover = package.cover_letter_markdown or ""

    resume_without_cover, extracted_cover = _split_cover_from_resume(resume)
    if extracted_cover:
        resume = resume_without_cover
        if _is_trivial_doc(cover, "cover"):
            cover = extracted_cover

    # Some models put both documents in the cover field instead.
    cover_resume, cover_only = _split_cover_from_resume(cover)
    if cover_only:
        if _is_trivial_doc(resume, "resume") and not _is_trivial_doc(cover_resume, "resume"):
            resume = cover_resume
        cover = cover_only

    resume = _strip_doc_heading(resume, "Resume")
    cover = _strip_doc_heading(cover, "Cover Letter")

    fallback = None
    if _is_trivial_doc(resume, "resume") or _is_trivial_doc(cover, "cover"):
        fallback = _fallback_package(profile, lead, template=template)
    if _is_trivial_doc(resume, "resume") and fallback:
        resume = fallback.resume_markdown
    if _is_trivial_doc(cover, "cover") and fallback:
        cover = fallback.cover_letter_markdown
    if _resume_needs_fallback(resume, lead):
        fallback = fallback or _fallback_package(profile, lead, template=template)
        resume = fallback.resume_markdown
        package.selected_projects = []

    selected = [str(p).strip() for p in package.selected_projects if str(p).strip()]
    if not selected:
        selected = [
            p.get("title", "") for p in _rank_projects(profile, lead, limit=4) if p.get("title")
        ]
    if not selected and fallback:
        selected = fallback.selected_projects

    package.resume_markdown = resume.strip()
    package.cover_letter_markdown = cover.strip()
    package.selected_projects = selected

    # Ensure outreach messages have sensible fallbacks
    needs_outreach_fb = (
        not package.founder_message or len(package.founder_message.strip()) < 30
        or not package.linkedin_note or len(package.linkedin_note.strip()) < 20
        or not package.cold_email or len(package.cold_email.strip()) < 30
    )
    if needs_outreach_fb:
        ofb = _fallback_outreach(profile, lead)
        if not package.founder_message or len(package.founder_message.strip()) < 30:
            package.founder_message = ofb["founder_message"]
        if not package.linkedin_note or len(package.linkedin_note.strip()) < 20:
            package.linkedin_note = ofb["linkedin_note"]
        if not package.cold_email or len(package.cold_email.strip()) < 30:
            package.cold_email = ofb["cold_email"]

    # Enforce the documented caps on EVERY path. The accepted-LLM outreach was
    # never truncated, so an over-limit LinkedIn note (LinkedIn hard-caps the
    # connection note at 300 chars) was copied verbatim and rejected downstream.
    package.founder_message = _shorten_chars(package.founder_message, 280)
    package.linkedin_note = _shorten_chars(package.linkedin_note, 300)
    package.cold_email = _shorten_words(package.cold_email, 150)
    return package


class CoverLetterGenerator:
    name = "cover_letter"

    def generate(self, lead: dict, profile: dict, config: dict | None = None) -> GeneratedAsset:
        template = (config or {}).get("template", "")
        package = _fallback_package(profile, lead, template)
        return {"type": self.name, "text": package.cover_letter_markdown}
