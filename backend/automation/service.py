from __future__ import annotations
import logging

import asyncio
import os
import re

from data.repository import Repository, create_repository


def _read_pdf_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/automation/service.py:_read_pdf_text: %s', log_exc)
        return ""


def _pick_first_line(text: str) -> str:
    for line in (text or "").splitlines():
        value = line.strip()
        if value and len(value) <= 80 and "@" not in value and "http" not in value.lower():
            return value
    return ""


def _contact_from_text(text: str) -> dict:
    email = ""
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")
    if match:
        email = match.group(0)

    phone = ""
    match = re.search(r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,5}\d{2,4}", text or "")
    if match:
        phone = match.group(0).strip()

    urls = re.findall(r"(?:https?://)?(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s),;]*)?", text or "")
    linkedin = next((url for url in urls if "linkedin.com" in url.lower()), "")
    github = next((url for url in urls if "github.com" in url.lower()), "")
    website = next((url for url in urls if url not in {linkedin, github} and "@" not in url), "")

    def norm_url(url: str) -> str:
        if not url:
            return ""
        return url if url.startswith(("http://", "https://")) else f"https://{url}"

    return {
        "email": email,
        "phone": phone,
        "linkedin_url": norm_url(linkedin),
        "github": norm_url(github),
        "website": norm_url(website or github or linkedin),
    }


def get_lead_for_fire_sync(job_id: str, repo: Repository | None = None) -> tuple[dict, str]:
    active_repo = repo or create_repository()
    lead, path = active_repo.leads.get_lead_for_fire(job_id)
    if not lead:
        return {}, ""
    if not hasattr(active_repo, "profile"):
        return lead, path

    cover_path = lead.get("cover_letter_path") or ""
    try:
        profile = active_repo.profile.get_profile()
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/automation/service.py:get_lead_for_fire_sync: %s', log_exc)
        profile = {}
    resume_text = _read_pdf_text(path)
    cover_text = _read_pdf_text(cover_path)
    try:
        settings = active_repo.settings.get_settings()
    except Exception as log_exc:
        logging.getLogger(__name__).warning('suppressed exception in backend/automation/service.py:get_lead_for_fire_sync: %s', log_exc)
        settings = {}
    contact = _contact_from_text(
        "\n".join(
            [
                resume_text,
                cover_text,
                profile.get("s", ""),
                "\n".join(str(p.get("repo", "")) for p in profile.get("projects", [])),
            ]
        )
    )

    name = (profile.get("n") or settings.get("candidate_name") or _pick_first_line(resume_text)).strip()
    parts = name.split()
    first_name = parts[0] if parts else ""
    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

    return {
        **lead,
        "profile": profile,
        "name": name,
        "candidate_name": name,
        "first_name": settings.get("first_name") or first_name,
        "last_name": settings.get("last_name") or last_name,
        "email": settings.get("candidate_email") or settings.get("email") or contact["email"],
        "phone": settings.get("candidate_phone") or settings.get("phone") or contact["phone"],
        "linkedin_url": settings.get("linkedin_url") or settings.get("candidate_linkedin") or contact["linkedin_url"],
        "website": settings.get("website") or settings.get("portfolio_url") or contact["website"],
        "github": settings.get("github") or settings.get("github_url") or contact["github"],
        "cover_letter": cover_text.strip(),
    }, path


class AutomationService:
    def __init__(self, repo: Repository | None = None):
        self.repo = repo or create_repository()

    async def get_lead_for_fire(self, job_id: str) -> tuple[dict, str]:
        return await asyncio.to_thread(get_lead_for_fire_sync, job_id, self.repo)

    async def submit_application(self, lead: dict, asset: str) -> bool:
        from automation.actuator import run as actuate

        return await asyncio.to_thread(actuate, lead, asset)

    async def preview_application(self, lead: dict, asset: str):
        from automation.actuator import run as actuate

        return await asyncio.to_thread(actuate, lead, asset, True)

    async def read_form(self, url: str, identity: dict, cover_letter: str = "") -> dict:
        from automation.actuator import read_form

        return await read_form(url, identity, cover_letter=cover_letter)

    async def refresh_selectors(self) -> dict:
        from automation.selectors import get_selectors

        self.repo.settings.save_settings({"selectors_fetched_at": "0"})
        return await asyncio.to_thread(get_selectors)

    async def mark_applied(self, job_id: str) -> None:
        await asyncio.to_thread(self.repo.leads.mark_applied, job_id)


def create_automation_service(repo: Repository | None = None) -> AutomationService:
    return AutomationService(repo=repo)
