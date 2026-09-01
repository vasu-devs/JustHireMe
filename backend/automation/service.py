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
    source_meta = lead.get("source_meta") if isinstance(lead.get("source_meta"), dict) else {}
    candidate_id = str(source_meta.get("candidate_id") or "").strip()
    if not candidate_id and not hasattr(active_repo, "profile"):
        return lead, path

    cover_path = lead.get("cover_letter_path") or ""
    if candidate_id:
        try:
            profile = active_repo.opportunities.get_candidate_application_profile(candidate_id)
        except Exception as log_exc:
            logging.getLogger(__name__).warning(
                "candidate application profile unavailable for %s: %s", candidate_id, log_exc
            )
            profile = {}
    else:
        try:
            profile = active_repo.profile.get_profile()
        except Exception as log_exc:
            logging.getLogger(__name__).warning('suppressed exception in backend/automation/service.py:get_lead_for_fire_sync: %s', log_exc)
            profile = {}
    resume_text = _read_pdf_text(path)
    cover_text = _read_pdf_text(cover_path)
    try:
        settings = active_repo.settings.get_settings() if not candidate_id else {}
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

    candidate_identity = (
        profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
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
        "email": candidate_identity.get("email") or settings.get("candidate_email") or settings.get("email") or contact["email"],
        "phone": candidate_identity.get("phone") or settings.get("candidate_phone") or settings.get("phone") or contact["phone"],
        "linkedin_url": candidate_identity.get("linkedin_url") or settings.get("linkedin_url") or settings.get("candidate_linkedin") or contact["linkedin_url"],
        # website_url is the canonical settings key update_identity writes (and that
        # read_lead_form / GET /identity read); the legacy "website"/"portfolio_url"
        # keys are never populated, so without website_url first the fire/preview
        # auto-fill dropped a user-configured website. Keep the aliases as fallbacks.
        "website": candidate_identity.get("website_url") or settings.get("website_url") or settings.get("website") or settings.get("portfolio_url") or contact["website"],
        "github": candidate_identity.get("github_url") or settings.get("github") or settings.get("github_url") or contact["github"],
        "city": candidate_identity.get("city") or settings.get("city") or "",
        "cover_letter": cover_text.strip(),
    }, path



def asset_ready(path: str) -> bool:
    return bool(path) and os.path.isfile(path)


def fire_blocker(lead: dict, asset: str) -> tuple[int, str]:
    """(status, detail) explaining why this lead cannot be submitted; (0, "") if it can."""
    if not lead:
        return 404, "Lead not found"
    if lead.get("status") == "applied":
        return 409, "Lead is already marked applied"
    if not lead.get("url"):
        return 409, "Lead has no application URL"
    if not asset_ready(asset):
        return 409, "Generate a resume before firing this application"
    cover = lead.get("cover_letter_asset") or lead.get("cover_letter_path") or ""
    if not asset_ready(cover):
        return 409, "Generate a cover letter before firing this application"
    return 0, ""


def _raise_if_blocked(lead: dict, asset: str) -> None:
    from core.errors import ConflictError, NotFoundError

    status, detail = fire_blocker(lead, asset)
    if not detail:
        return
    raise NotFoundError(detail) if status == 404 else ConflictError(detail)


def resolve_cover_letter_text(asset_path: str, logger) -> str:
    """Resolve cover letter *text* from a stored asset path (H3).

    The asset path may point at a ``.pdf`` or ``.md`` artifact. Form-fill needs
    the text, so we prefer the ``.md`` sibling and only read text-like files —
    never the raw PDF bytes, and never the path string itself. Returns "" (with
    a warning) when no readable text file exists.
    """
    from pathlib import Path

    if not asset_path:
        return ""
    asset = Path(asset_path)
    md_path = asset.with_suffix(".md")
    for candidate in (md_path, asset):
        try:
            if candidate.suffix.lower() in {".md", ".txt"} and candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("could not read cover letter %s: %s", candidate, exc)
            return ""
    logger.warning(
        "no readable cover letter text for asset %s (.pdf exists=%s)",
        asset_path,
        asset.is_file() and asset.suffix.lower() == ".pdf",
    )
    return ""


class AutomationService:
    def __init__(self, repo: Repository | None = None):
        self.repo = repo or create_repository()

    async def get_lead_for_fire(self, job_id: str) -> tuple[dict, str]:
        return await asyncio.to_thread(get_lead_for_fire_sync, job_id, self.repo)

    async def _require_candidate_submission_ready(
        self,
        lead: dict,
        *,
        require_auto_apply: bool = False,
    ) -> None:
        from core.errors import ConflictError

        source_meta = lead.get("source_meta") if isinstance(lead.get("source_meta"), dict) else {}
        candidate_id = str(source_meta.get("candidate_id") or "").strip()
        if not candidate_id:
            if require_auto_apply:
                enabled = await asyncio.to_thread(
                    self.repo.settings.get_setting, "auto_apply", "false"
                )
                if str(enabled).lower() != "true":
                    raise ConflictError("Auto-apply is disabled")
            return
        payload = await asyncio.to_thread(
            self.repo.opportunities.get_candidate_profile, candidate_id
        )
        if not isinstance(payload, dict):
            raise ConflictError("Candidate profile is missing or invalid")
        if not str(payload.get("consent_confirmed_at") or "").strip():
            raise ConflictError("Candidate consent is required before preview or submission")
        if require_auto_apply:
            if not payload.get("auto_apply_enabled"):
                raise ConflictError("Auto-apply is disabled for this candidate")
            if not str(payload.get("auto_apply_confirmed_at") or "").strip():
                raise ConflictError("Candidate auto-apply confirmation is required")
        status = await asyncio.to_thread(
            self.repo.opportunities.candidate_application_profile_status, candidate_id
        )
        if not status.get("ready"):
            raise ConflictError(
                "Candidate-specific application profile with email and phone is required"
            )

    async def submit_application(self, lead: dict, asset: str) -> bool:
        result = await self.submit_application_result(lead, asset)
        return bool(isinstance(result, dict) and result.get("status") == "submitted")

    async def submit_application_result(self, lead: dict, asset: str) -> dict:
        from automation.actuator import run as actuate

        _raise_if_blocked(lead, asset)
        await self._require_candidate_submission_ready(lead, require_auto_apply=True)
        result = await asyncio.to_thread(actuate, lead, asset, False, True)
        if isinstance(result, dict):
            return result
        return {"status": "submitted" if result else "failed", "ready_to_submit": bool(result)}

    async def preview_application(self, lead: dict, asset: str):
        from automation.actuator import run as actuate

        await self._require_candidate_submission_ready(lead)
        result = await asyncio.to_thread(actuate, lead, asset, True, False)
        return result if isinstance(result, dict) else {"status": "dry_run", "ready_to_submit": bool(result)}

    async def read_form(self, url: str, identity: dict, cover_letter: str = "") -> dict:
        from automation.actuator import read_form

        return await read_form(url, identity, cover_letter=cover_letter)

    async def refresh_selectors(self) -> dict:
        from automation.selectors import get_selectors

        self.repo.settings.save_settings({"selectors_fetched_at": "0"})
        return await asyncio.to_thread(get_selectors)

    async def mark_applied(self, job_id: str) -> None:
        await asyncio.to_thread(self.repo.leads.mark_applied, job_id)


    # ---------------------------------------------------------------- flows
    # Whole use-cases, so the router stays transport-only. `notify` is an async
    # callback the API layer supplies to fan progress out over the WebSocket —
    # the domain never imports the connection manager.

    async def candidate_identity(self) -> dict:
        """The contact block used to fill application forms.

        The profile is FLAT: the candidate name is profile["n"], not a
        "candidate" sub-dict (there is none), and no "full_name" setting is ever
        written by the app. Read it the way get_lead_for_fire_sync does, else a
        fully-configured candidate gets a blank name on every form.
        """
        profile = await asyncio.to_thread(self.repo.profile.get_profile)
        cfg = await asyncio.to_thread(self.repo.settings.get_settings)
        candidate_name = str(profile.get("n") or "").strip() if isinstance(profile, dict) else ""
        return {
            "name": cfg.get("full_name", "") or candidate_name,
            "email": cfg.get("email", ""),
            "phone": cfg.get("phone", ""),
            "linkedin_url": cfg.get("linkedin_url", ""),
            "github": cfg.get("github_url", ""),
            "website": cfg.get("website_url", ""),
            "city": cfg.get("city", ""),
            "current_company": cfg.get("current_company", ""),
        }

    async def read_lead_form(self, job_id: str, url_override: str = "") -> dict:
        from core.errors import NotFoundError, ValidationError

        lead = await asyncio.to_thread(self.repo.leads.get_lead_by_id, job_id)
        if not lead:
            raise NotFoundError("lead not found")
        url = (url_override or lead.get("url") or "").strip()
        if not url:
            raise ValidationError("no url available for this lead")
        identity = await self.candidate_identity()
        cover_letter = await asyncio.to_thread(
            resolve_cover_letter_text, lead.get("cover_letter_asset", ""), logging.getLogger(__name__)
        )
        return await self.read_form(url, identity, cover_letter=cover_letter)

    async def preview_apply(self, job_id: str) -> dict:
        """Enrich with candidate identity like the fire path, else the preview
        renders every name/email/phone field blank."""
        lead, asset = await self.get_lead_for_fire(job_id)
        _raise_if_blocked(lead, asset)
        return await self.preview_application(lead, asset)

    async def check_can_fire(self, job_id: str) -> None:
        """Raise the domain error that blocks submission, or return cleanly."""
        lead = await asyncio.to_thread(self.repo.leads.get_lead_by_id, job_id)
        asset = (lead or {}).get("resume_asset") or (lead or {}).get("asset") or ""
        _raise_if_blocked(lead, asset)
        await self._require_candidate_submission_ready(lead, require_auto_apply=True)

    async def actuate(self, job_id: str, notify, job_store=None) -> None:
        """Run a full application submission, reporting progress through `notify`."""
        from gateway.jobs import get_job_store

        job_store = job_store or get_job_store()
        job = job_store.create("automation_fire", {"job_id": job_id})
        try:
            job_store.update(job.job_id, status="running", progress=10)
            # Enrich with candidate identity (name/email/phone/links/cover_letter)
            # the same way the Ghost auto-apply path does — the bare
            # get_lead_by_id row has only job metadata, so the actuator would
            # fill every identity field blank.
            lead, asset = await self.get_lead_for_fire(job_id)
            _status, detail = fire_blocker(lead, asset)
            if detail:
                await notify({"type": "agent", "event": "failed", "job_id": job_id,
                              "msg": f"Submission blocked for {job_id}: {detail}"})
                job_store.update(job.job_id, status="failed", error=detail)
                return

            await notify({
                "type": "agent", "event": "actuating", "job_id": job_id,
                "msg": f"Opening browser for {lead.get('title','')} @ {lead.get('company','')}",
            })
            ok = await self.submit_application(lead, asset)
        except Exception as exc:
            logging.getLogger(__name__).warning("automation actuate failed for %s: %s", job_id, exc)
            await notify({"type": "agent", "event": "failed", "job_id": job_id,
                          "msg": f"Submission failed for {job_id}: {exc}"})
            job_store.update(job.job_id, status="failed", error=str(exc))
            return

        if ok:
            await asyncio.to_thread(self.repo.leads.mark_applied, job_id)
            job_store.update(job.job_id, status="succeeded", progress=100)
            await notify({"type": "agent", "event": "applied", "job_id": job_id,
                          "msg": f"Application submitted for {job_id}"})
        else:
            job_store.update(job.job_id, status="failed", error="submit_application returned false")
            await notify({"type": "agent", "event": "failed", "job_id": job_id,
                          "msg": f"Submission failed for {job_id}"})


def create_automation_service(repo: Repository | None = None) -> AutomationService:
    return AutomationService(repo=repo)
