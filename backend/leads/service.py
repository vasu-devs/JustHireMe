"""Lead lifecycle service — the business layer behind the leads/events routers.

Every method here runs blocking storage calls through ``asyncio.to_thread``. The
sidecar serves the UI from a single worker: a blocking SQLite call left on the
event loop stalls *every* coroutine, including ``/health``, and the UI then
reports the backend as unreachable.
"""

from __future__ import annotations

import asyncio
import csv
import io
import os
import re

from core.errors import NotFoundError, UnprocessableError, ValidationError
from core.paths import app_data_path
from data.repository import Repository
from gateway.lead_adapters import annotate_job_lead, classify_job_seniority, manual_lead_from_text


CSV_COLUMNS = (
    "job_id", "title", "company", "url", "platform", "status", "score",
    "signal_score", "seniority_level", "location", "reason", "created_at",
)

BEGINNER_LEVELS = {"fresher", "junior"}
SENIORITY_LEVELS = {"fresher", "junior", "mid", "senior", "unknown"}

# GET /api/v1/leads ships every job lead in one response (the desktop client
# has no pagination UI -- see useLeads.ts); at ~1.2KB average, full
# descriptions alone are ~13MB of the ~50MB payload. The list view only ever
# shows a 3-line-clamped preview (JobCard.tsx); the full text is still
# available from GET /api/v1/leads/{job_id}, which ApprovalDrawer now fetches
# when a lead is opened (see its loadFullLead effect).
_LIST_DESCRIPTION_PREVIEW_CHARS = 600


def _preview_lead(lead: dict) -> dict:
    description = lead.get("description") or ""
    if len(description) <= _LIST_DESCRIPTION_PREVIEW_CHARS:
        return lead
    return {**lead, "description": description[:_LIST_DESCRIPTION_PREVIEW_CHARS].rstrip() + "…"}


_JOB_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")
_MAX_PAGE_SIZE = 1000
_MANUAL_FEEDBACK_TIMEOUT_SECONDS = 8


def safe_job_id(job_id: str) -> str:
    """Reject anything that isn't a plain id before it reaches storage or a path."""
    if not _JOB_ID_RE.match(job_id or ""):
        raise ValidationError("Invalid job ID format")
    return job_id


def default_assets_dir() -> str:
    return str(app_data_path("assets"))


def versioned_assets(job_id: str, base_dir: str) -> list[dict]:
    """Every generated resume/cover-letter version on disk, newest first."""
    versions: dict[int, dict] = {}
    patterns = [
        ("resume", re.compile(rf"^{re.escape(job_id)}_v(\d+)\.pdf$")),
        ("cover_letter", re.compile(rf"^{re.escape(job_id)}_cl_v(\d+)\.pdf$")),
    ]
    try:
        names = os.listdir(base_dir)
    except OSError:
        return []
    for name in names:
        if not os.path.isfile(os.path.join(base_dir, name)):
            continue
        for key, pattern in patterns:
            match = pattern.match(name)
            if match:
                version = int(match.group(1))
                versions.setdefault(version, {"version": version})[key] = os.path.join(base_dir, name)
    return [versions[version] for version in sorted(versions, reverse=True)]


class LeadService:
    def __init__(self, repo: Repository, ranking_service=None) -> None:
        self._repo = repo
        self._ranking = ranking_service

    # ---------------------------------------------------------------- reads

    async def list_leads(
        self,
        *,
        page: int | None = None,
        limit: int = 200,
        beginner_only: bool = False,
        seniority: str | None = None,
        status: str | None = None,
        min_score: int | None = None,
    ) -> list[dict] | dict:
        # One-time (per lead) cache fill: classify_job_seniority is a pure
        # title/description keyword scan, but running it for every lead with
        # no cached seniority_level on EVERY request (~6,516 of ~10,489 leads
        # predating this column) took 40s+ and blew past the client's 30s
        # timeout -- this endpoint always failed. Persisting it means only
        # leads added since the last request ever pay the classify cost.
        await asyncio.to_thread(self._repo.leads.classify_pending_seniority, classify_job_seniority)
        all_leads = await asyncio.to_thread(self._repo.leads.get_all_leads)
        jobs = [_preview_lead(annotate_job_lead(lead)) for lead in all_leads if (lead.get("kind") or "job") == "job"]

        requested = str(seniority or "").strip().lower()
        if beginner_only or requested == "beginner":
            jobs = [lead for lead in jobs if lead.get("seniority_level") in BEGINNER_LEVELS]
        elif requested in SENIORITY_LEVELS:
            jobs = [lead for lead in jobs if lead.get("seniority_level") == requested]
        if status:
            jobs = [lead for lead in jobs if str(lead.get("status") or "") == status]
        if min_score is not None:
            jobs = [lead for lead in jobs if int(lead.get("score") or 0) >= min_score]

        if page is None:
            return jobs
        page = max(1, page)
        limit = max(1, min(limit, _MAX_PAGE_SIZE))
        total = len(jobs)
        start = (page - 1) * limit
        return {
            "items": jobs[start:start + limit],
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit,
        }

    async def get_lead(self, job_id: str) -> dict:
        job_id = safe_job_id(job_id)
        lead = await asyncio.to_thread(self._repo.leads.get_lead_by_id, job_id)
        if not lead:
            raise NotFoundError("Lead not found")
        return annotate_job_lead(lead) if (lead.get("kind") or "job") == "job" else lead

    async def export_csv(self) -> str:
        rows = await asyncio.to_thread(self._repo.leads.get_all_leads)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(CSV_COLUMNS), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()

    async def list_versions(self, job_id: str) -> list[dict]:
        lead = await self.get_lead(job_id)
        return await asyncio.to_thread(versioned_assets, job_id, self._asset_dir(lead))

    async def resolve_pdf(self, job_id: str, kind: str, version: int | None) -> tuple[str, str]:
        """Resolve (path, filename) for a generated PDF, or raise NotFoundError."""
        lead = await self.get_lead(job_id)
        is_cover = kind in {"cover", "cover_letter", "cover-letter"}
        if version is not None:
            base_dir = self._asset_dir(lead)
            filename = f"{job_id}_cl_v{version}.pdf" if is_cover else f"{job_id}_v{version}.pdf"
            path = os.path.join(base_dir, filename)
            missing = "Cover letter not generated yet" if is_cover else "Resume not generated yet"
        elif is_cover:
            path = lead.get("cover_letter_asset") or ""
            filename = f"{job_id}_cover_letter.pdf"
            missing = "Cover letter not generated yet"
        else:
            path = lead.get("resume_asset") or lead.get("asset") or ""
            filename = f"{job_id}_resume.pdf"
            missing = "Resume not generated yet"
        if not path or not os.path.exists(path):
            raise NotFoundError(missing)
        return path, filename

    async def due_followups(self, limit: int = 25) -> list[dict]:
        from datetime import datetime, timezone

        return await asyncio.to_thread(
            self._repo.leads.get_due_followups, limit, datetime.now(timezone.utc).isoformat()
        )

    async def list_activity(self, *, limit: int = 100, job_id: str | None = None) -> list[dict]:
        # Clamp: an unbounded/negative limit reaches SQLite as LIMIT -1
        # (= unlimited) and would dump the whole events table.
        limit = max(1, min(limit, _MAX_PAGE_SIZE))
        return await asyncio.to_thread(self._repo.events.get_events, limit=limit, job_id=job_id)

    # --------------------------------------------------------------- writes

    async def delete_lead(self, job_id: str) -> None:
        job_id = safe_job_id(job_id)
        try:
            await asyncio.to_thread(self._repo.leads.delete_lead, job_id)
        except LookupError as exc:
            raise NotFoundError("lead not found") from exc

    async def update_status(self, job_id: str, status: str) -> dict:
        job_id = safe_job_id(job_id)
        try:
            await asyncio.to_thread(self._repo.leads.update_lead_status, job_id, status)
        except LookupError as exc:
            raise NotFoundError("lead not found") from exc
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return {"job_id": job_id, "status": status}

    async def save_feedback(self, job_id: str, feedback: str, note: str = "") -> dict:
        job_id = safe_job_id(job_id)
        try:
            lead = await asyncio.to_thread(self._repo.leads.save_lead_feedback, job_id, feedback, note)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        if not lead:
            raise NotFoundError("Lead not found")
        return lead

    async def schedule_followup(self, job_id: str, days: int) -> dict:
        job_id = safe_job_id(job_id)
        from datetime import datetime, timedelta, timezone

        days = max(1, min(int(days or 5), 60))
        now = datetime.now(timezone.utc)
        lead = await asyncio.to_thread(
            self._repo.leads.update_lead_followup,
            job_id,
            now.isoformat(),
            (now + timedelta(days=days)).isoformat(),
        )
        if not lead:
            raise NotFoundError("Lead not found")
        return lead

    async def create_manual_lead(self, text: str, url: str) -> dict:
        """Turn pasted text/URL into a saved, feedback-ranked lead."""
        raw_lead = self.parse_manual_lead(text, url)
        lead = raw_lead
        if self._ranking is not None:
            examples = await asyncio.to_thread(self._repo.feedback.get_feedback_training_examples)
            try:
                lead = await asyncio.wait_for(
                    self._ranking.apply_feedback(raw_lead, examples),
                    timeout=_MANUAL_FEEDBACK_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                # Feedback ranking is an enhancement; a slow/failed rank must not
                # lose the lead the user just pasted. Record why and keep going.
                meta = dict(raw_lead.get("source_meta") or {})
                meta["feedback_learning_error"] = str(exc) or "timed out"
                lead = {**raw_lead, "source_meta": meta}
        if lead.get("kind") != "job":
            raise UnprocessableError("Only job leads are accepted right now")
        lead = annotate_job_lead(lead)
        await asyncio.to_thread(self._repo.leads.save_lead, lead)
        return await asyncio.to_thread(self._repo.leads.get_lead_by_id, lead["job_id"]) or lead

    def parse_manual_lead(self, text: str, url: str) -> dict:
        """Structure pasted text without persisting it."""
        if not (text or "").strip() and not (url or "").strip():
            raise ValidationError("Paste lead text or a URL")
        raw_lead = manual_lead_from_text(text, url, "job")
        if raw_lead.get("kind") != "job":
            raise UnprocessableError("Only job leads are accepted right now")
        return annotate_job_lead(raw_lead)

    async def cleanup(self, *, limit: int, dry_run: bool, notify) -> dict:
        """Discard obvious non-jobs, reporting progress through `notify`."""
        await notify({
            "type": "agent", "event": "cleanup_start",
            "msg": f"Scanning up to {limit} leads for bad data...",
        })
        result = await asyncio.to_thread(self._repo.leads.cleanup_bad_leads, limit, dry_run)
        if not dry_run:
            for item in result.get("items", [])[:100]:
                lead = await asyncio.to_thread(self._repo.leads.get_lead_by_id, item["job_id"])
                if lead:
                    await notify({"type": "LEAD_UPDATED", "data": lead})
        action = "would discard" if dry_run else "discarded"
        await notify({
            "type": "agent", "event": "cleanup_done",
            "msg": f"Cleanup scanned {result['scanned']} leads and {action} {result['candidates']} bad rows.",
        })
        return result

    async def mark_applied(self, job_id: str) -> None:
        await asyncio.to_thread(self._repo.leads.mark_applied, job_id)

    async def recompute_feedback_signals(self) -> list[dict]:
        if self._ranking is None:
            return []
        return await self._ranking.recompute_feedback_signals()

    # -------------------------------------------------------------- helpers

    def _asset_dir(self, lead: dict) -> str:
        paths = [lead.get("resume_asset") or lead.get("asset") or "", lead.get("cover_letter_asset") or ""]
        return next((os.path.dirname(path) for path in paths if path), None) or default_assets_dir()


def create_lead_service(repo: Repository, ranking_service=None) -> LeadService:
    return LeadService(repo, ranking_service)


__all__ = [
    "CSV_COLUMNS",
    "LeadService",
    "create_lead_service",
    "default_assets_dir",
    "safe_job_id",
    "versioned_assets",
]
