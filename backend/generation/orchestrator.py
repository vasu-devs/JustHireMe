"""Generation orchestration — the full "make a package for this lead" use case.

Moved out of the API layer so the router holds no storage access and no
transactional rules. Progress reaches the UI through the ``notify`` callback the
API layer supplies; this module knows nothing about WebSockets or HTTP.
"""

from __future__ import annotations

import asyncio
import logging

from core.errors import GenerationError, NotFoundError, UnprocessableError
from core.generation_readiness import lead_generation_blocker
from data.repository import Repository
from gateway.lead_adapters import annotate_job_lead, manual_lead_from_text

_log = logging.getLogger(__name__)

#: How long to ask the client to wait before retrying a transient failure.
GENERATION_RETRY_AFTER_SECONDS = 30


class TransientGenerationError(GenerationError):
    """Worth retrying: network/timeout/rate-limit. The lead stays in `tailoring`."""

    retry_after = GENERATION_RETRY_AFTER_SECONDS


def is_transient_generation_error(exc: Exception) -> bool:
    """Classify a generation failure as transient (worth retrying) vs permanent.

    Transient: network/timeout issues and retryable LLM errors (rate limit,
    connection, 5xx) that survived the client's own retries. Permanent: bad
    template, invalid lead, parsing errors — retrying won't help.
    """
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    try:
        from llm.client import is_transient_llm_error
    except ImportError:
        return False
    return is_transient_llm_error(exc)


class GenerationOrchestrator:
    def __init__(self, repo: Repository, service, job_store) -> None:
        self._repo = repo
        self._service = service
        self._jobs = job_store

    async def _resolve_template(self, template_id: str) -> str:
        try:
            return await asyncio.to_thread(self._repo.resume_templates.resolve_template_content, template_id)
        except Exception as exc:
            _log.warning("template resolve failed for %r: %s", template_id, exc)
            if template_id:
                # The user explicitly picked this template; silently generating
                # with a different layout would misrepresent the output.
                raise UnprocessableError(f"Resume template {template_id!r} could not be loaded") from None
            return await asyncio.to_thread(self._repo.settings.get_setting, "resume_template", "")

    async def generate(self, job_id: str, notify, *, template_id: str = "") -> dict:
        """Generate, persist and return the enriched lead. Raises on failure."""
        job = await asyncio.to_thread(self._jobs.create, "generate_package", {"job_id": job_id})
        lead = await asyncio.to_thread(self._repo.leads.get_lead_by_id, job_id)
        if not lead:
            await notify({"type": "agent", "event": "gen_error", "msg": f"Lead {job_id} not found"})
            raise NotFoundError("Lead not found")

        blocked_reason = lead_generation_blocker(lead)
        if blocked_reason:
            await self._safe_job_update(job.job_id, status="failed", error=blocked_reason)
            await notify({"type": "agent", "event": "gen_error", "msg": blocked_reason})
            raise UnprocessableError(blocked_reason)

        template = await self._resolve_template(template_id)
        await notify({
            "type": "agent",
            "event": "gen_start",
            "msg": f"Generating for {lead.get('title','?')} @ {lead.get('company','?')}",
        })

        try:
            return await self._generate_and_persist(job, lead, job_id, template, notify)
        except Exception as exc:
            await self._handle_failure(job, lead, job_id, exc, notify)
            raise

    async def _generate_and_persist(self, job, lead: dict, job_id: str, template: str, notify) -> dict:
        await self._safe_job_update(job.job_id, status="running", progress=10)
        try:
            await asyncio.to_thread(self._repo.leads.update_lead_status, job_id, "tailoring")
            await notify({"type": "LEAD_UPDATED", "data": {**lead, "status": "tailoring"}})
        except Exception as exc:
            _log.warning("could not mark %s tailoring: %s", job_id, exc)

        generation = await self._service.generate_with_contacts(lead, template=template)
        package = generation.package
        persistence_errors: list[str] = []

        try:
            await asyncio.to_thread(
                self._repo.leads.save_asset_package,
                job_id,
                package["resume"],
                package["cover_letter"],
                package.get("selected_projects", []),
                package.get("keyword_coverage", {}),
            )
        except Exception as exc:
            # save_asset_package is the only write that flips the lead to
            # "approved" and records asset_path. If it fails, the UI would show
            # success while the DB still says "tailoring" with no resume —
            # treat the whole generation as failed instead.
            raise RuntimeError(f"generated assets could not be saved: {exc}") from exc

        outreach_fields = {
            key: package[source]
            for key, source in (
                ("outreach_reply", "founder_message"),
                ("outreach_dm", "linkedin_note"),
                ("outreach_email", "cold_email"),
            )
            if package.get(source)
        }
        if outreach_fields:
            try:
                await asyncio.to_thread(self._repo.leads.update_outreach_fields, job_id, outreach_fields)
            except Exception as exc:
                _log.warning("outreach field persist failed for %s: %s", job_id, exc)
                persistence_errors.append(f"outreach fields: {exc}")

        contact_lookup = generation.contact_lookup or {}
        try:
            await asyncio.to_thread(self._repo.leads.save_contact_lookup, job_id, contact_lookup)
        except Exception as exc:
            _log.warning("contact lookup persist failed for %s: %s", job_id, exc)
            persistence_errors.append(f"contact lookup: {exc}")

        enriched_lead = {
            **lead,
            "asset": package["resume"],
            "resume_asset": package["resume"],
            "cover_letter_asset": package["cover_letter"],
            "selected_projects": package.get("selected_projects", []),
            "keyword_coverage": package.get("keyword_coverage", {}),
            "outreach_reply": package.get("founder_message", lead.get("outreach_reply", "")),
            "outreach_dm": package.get("linkedin_note", lead.get("outreach_dm", "")),
            "outreach_email": package.get("cold_email", lead.get("outreach_email", "")),
            "status": "approved",
            "contact_lookup": contact_lookup,
        }
        enriched_meta = dict(enriched_lead.get("source_meta") or {})
        enriched_meta["contact_lookup"] = contact_lookup
        if persistence_errors:
            enriched_meta["generation_persistence_errors"] = persistence_errors
        enriched_lead["source_meta"] = enriched_meta

        await notify({"type": "LEAD_UPDATED", "data": enriched_lead})
        await notify({
            "type": "agent",
            "event": "gen_done",
            "msg": f"Resume and cover letter ready: {lead.get('title','?')}",
        })
        await self._safe_job_update(job.job_id, status="succeeded", progress=100, result={"lead": enriched_lead})
        enriched_lead["generation_job_id"] = job.job_id
        return enriched_lead

    async def _handle_failure(self, job, lead: dict, job_id: str, exc: Exception, notify) -> None:
        await self._safe_job_update(job.job_id, status="failed", error=str(exc))
        # Keep transient failures (network/rate-limit) in "tailoring" so the user
        # can simply retry. Only permanent failures fall back to "discovered".
        transient = is_transient_generation_error(exc)
        revert_status = "tailoring" if transient else "discovered"
        try:
            await asyncio.to_thread(self._repo.leads.update_lead_status, job_id, revert_status)
            failed_lead = {**lead, "status": revert_status}
            failed_meta = dict(failed_lead.get("source_meta") or {})
            failed_meta["generation_error"] = str(exc)
            if transient:
                failed_meta["retry_after"] = GENERATION_RETRY_AFTER_SECONDS
            failed_lead["source_meta"] = failed_meta
            await notify({"type": "LEAD_UPDATED", "data": failed_lead})
        except Exception as revert_exc:
            _log.warning("could not revert %s after failure: %s", job_id, revert_exc)
        await notify({
            "type": "agent",
            "event": "gen_error",
            "msg": f"Generation failed for {lead.get('title','?')}: {exc}",
        })

    async def start(self, job_id: str, notify, *, template_id: str = "") -> dict:
        """Kick generation off in the background and return the queued lead."""
        lead = await asyncio.to_thread(self._repo.leads.get_lead_by_id, job_id)
        if not lead:
            raise NotFoundError("Lead not found")
        tailoring_lead = {**lead, "status": "tailoring"}
        try:
            await asyncio.to_thread(self._repo.leads.update_lead_status, job_id, "tailoring")
            await notify({"type": "LEAD_UPDATED", "data": tailoring_lead})
        except Exception as exc:
            _log.warning("could not mark %s tailoring: %s", job_id, exc)
        return tailoring_lead

    async def generate_quietly(self, job_id: str, notify, *, template_id: str = "") -> None:
        """Background variant: failures are already broadcast, so swallow them."""
        try:
            await self.generate(job_id, notify, template_id=template_id)
        except Exception as exc:
            _log.warning("background generation failed for %s: %s", job_id, exc)

    async def create_manual_and_generate(self, text: str, url: str, notify) -> dict:
        """Save a pasted lead, then generate for it in the background."""
        from core.errors import ValidationError

        if not (text or "").strip() and not (url or "").strip():
            raise ValidationError("Paste lead text or a URL")
        raw_lead = manual_lead_from_text(text, url, "job")
        if raw_lead.get("kind") != "job":
            raise UnprocessableError("Only job leads are accepted right now")
        lead = annotate_job_lead(raw_lead)

        blocked_reason = lead_generation_blocker(lead)
        if blocked_reason:
            await asyncio.to_thread(self._repo.leads.save_lead, lead)
            saved = await asyncio.to_thread(self._repo.leads.get_lead_by_id, lead["job_id"]) or lead
            await notify({"type": "LEAD_UPDATED", "data": saved})
            raise UnprocessableError(blocked_reason)

        queued_lead = {**lead, "status": "tailoring"}

        async def _run() -> None:
            try:
                await asyncio.to_thread(self._repo.leads.save_lead, lead)
                try:
                    await asyncio.to_thread(self._repo.leads.update_lead_status, lead["job_id"], "tailoring")
                except Exception as exc:
                    _log.warning("could not mark manual lead tailoring: %s", exc)
                saved = await asyncio.to_thread(self._repo.leads.get_lead_by_id, lead["job_id"])
                await notify({"type": "LEAD_UPDATED", "data": saved or queued_lead})
                await self.generate(lead["job_id"], notify)
            except Exception as exc:
                _log.warning("manual lead generation failed: %s", exc)
                failed = {**queued_lead, "status": "discovered"}
                meta = dict(failed.get("source_meta") or {})
                meta["generation_error"] = str(exc)
                failed["source_meta"] = meta
                await notify({"type": "LEAD_UPDATED", "data": failed})
                await notify({
                    "type": "agent",
                    "event": "gen_error",
                    "msg": f"Generation failed for {lead.get('title','?')}: {exc}",
                })

        return {"lead": queued_lead, "run": _run}

    async def run_pipeline(self, job_id: str, notify) -> dict:
        """Start the evaluation graph for one lead; returns the tracking job id."""
        lead = await asyncio.to_thread(self._repo.leads.get_lead_by_id, job_id)
        if not lead:
            raise NotFoundError("lead not found")
        job = self._jobs.create("pipeline_run", {"job_id": job_id})

        async def _run() -> None:
            from graph import PipelineState, eval_graph

            self._jobs.update(job.job_id, status="running", progress=10)
            profile, cfg = {}, {}
            try:
                profile = await asyncio.wait_for(self._service.resolve_profile_for_lead(lead), timeout=20)
            except Exception as exc:
                _log.warning("pipeline profile read failed: %s", exc)
            try:
                cfg = await asyncio.wait_for(asyncio.to_thread(self._repo.settings.get_settings), timeout=10)
            except Exception as exc:
                _log.warning("pipeline settings read failed: %s", exc)
            state: PipelineState = {
                "job_id": job_id, "lead": lead, "profile": profile, "cfg": cfg,
                "score": 0, "reason": "", "match_points": [], "gaps": [],
                "asset_path": "", "cover_letter_path": "", "error": None,
            }
            try:
                result = await asyncio.to_thread(eval_graph.invoke, state)
                final_status = "failed" if result["error"] else "succeeded"
                self._jobs.update(
                    job.job_id, status=final_status, progress=100,
                    result={"score": result["score"], "error": result["error"]},
                    error=str(result["error"] or ""),
                )
                message = f"Pipeline done for {job_id}: score={result['score']}, error={result['error']}"
            except Exception as exc:
                _log.warning("pipeline failed for %s: %s", job_id, exc)
                self._jobs.update(job.job_id, status="failed", error=str(exc))
                message = f"Pipeline failed for {job_id}: {exc}"
            await notify({
                "type": "agent", "kind": "agent", "src": "pipeline",
                "event": "pipeline_done", "msg": message,
            })

        return {"pipeline_job_id": job.job_id, "run": _run}

    async def _safe_job_update(self, job_id: str, **fields) -> None:
        try:
            await asyncio.to_thread(self._jobs.update, job_id, **fields)
        except Exception as exc:
            _log.warning("job store update failed for %s: %s", job_id, exc)


def create_generation_orchestrator(repo: Repository, service, job_store) -> GenerationOrchestrator:
    return GenerationOrchestrator(repo, service, job_store)


__all__ = [
    "GENERATION_RETRY_AFTER_SECONDS",
    "GenerationOrchestrator",
    "create_generation_orchestrator",
    "is_transient_generation_error",
]
