from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from api.dependencies import get_automation_service, get_discovery_service, get_generation_service, get_job_runner, get_ranking_service, get_repository
from api.routers.automation import fire_blocker
from api.routers.discovery import run_free_source_scan, run_x_signal_scan
from gateway.discovery_config import free_sources_enabled, has_x_token, job_targets, profile_for_discovery
from api.startup_validation import log_startup_warnings
from data.sqlite.connection import init_sql


def create_scheduler() -> AsyncIOScheduler:
    return AsyncIOScheduler()


def ensure_ghost_job(scheduler: AsyncIOScheduler, ghost_tick) -> None:
    if not scheduler.get_job("ghost"):
        scheduler.add_job(ghost_tick, "interval", hours=6, id="ghost")


def create_ghost_tick(manager):
    async def ghost_tick():
        repo = get_repository()
        automation_service = get_automation_service()
        discovery_service = get_discovery_service()
        ranking_service = get_ranking_service()
        generation_service = get_generation_service()
        job_store = get_job_runner()

        cfg = repo.settings.get_settings()
        if repo.settings.get_setting("ghost_mode") != "true":
            return
        ghost_job = job_store.create("ghost_cycle", {})
        job_store.update(ghost_job.job_id, status="running", progress=5)

        profile = profile_for_discovery(await asyncio.to_thread(repo.profile.get_profile), cfg)
        boards = job_targets(cfg.get("job_boards", ""), cfg.get("job_market_focus", "global"))
        has_x = has_x_token(cfg)
        has_free = free_sources_enabled(cfg)
        if has_x:
            await run_x_signal_scan(manager, cfg, "job", profile)
        if has_free:
            await run_free_source_scan(manager, cfg, "job", profile)
        if not boards and not has_x and not has_free:
            await manager.broadcast({"type": "agent", "event": "ghost_warn", "msg": "Ghost Mode: no job boards configured - skipping"})
            job_store.update(ghost_job.job_id, status="cancelled", error="no job boards configured")
            return

        await manager.broadcast({"type": "agent", "event": "ghost_scout", "msg": "Ghost Mode: scout cycle starting"})
        try:
            boards = await discovery_service.plan_board_targets(profile, boards, cfg.get("job_market_focus", "global"))
            result = await discovery_service.scan_job_boards(boards, cfg)
            leads = result.leads
            await manager.broadcast({"type": "agent", "event": "ghost_scout", "msg": f"Ghost scout complete - {len(leads)} new leads found"})
        except Exception as exc:
            await manager.broadcast({"type": "agent", "event": "ghost_error", "msg": f"Scout failed: {exc}"})
            job_store.update(ghost_job.job_id, status="failed", error=str(exc))
            return

        profile = profile_for_discovery(await asyncio.to_thread(repo.profile.get_profile), cfg)
        discovered = await asyncio.to_thread(repo.leads.get_discovered_leads)
        await manager.broadcast({"type": "agent", "event": "ghost_eval", "msg": f"Ghost Mode: evaluating {len(discovered)} leads"})

        approved = []
        for lead in discovered:
            try:
                result = await ranking_service.evaluate_lead(lead, profile)
                await asyncio.to_thread(
                    repo.leads.update_lead_score,
                    lead["job_id"], result["score"], result["reason"],
                    result.get("match_points", []), result.get("gaps", []),
                )
                await manager.broadcast({"type": "LEAD_UPDATED", "data": {**lead, **result}})
                if result["score"] >= 85:
                    approved.append({**lead, **result})
                    await manager.broadcast({
                        "type": "agent",
                        "event": "ghost_approved",
                        "msg": f"Approved: {lead.get('title','')} @ {lead.get('company','')} [{result['score']}/100]",
                    })
            except Exception as exc:
                await manager.broadcast({"type": "agent", "event": "ghost_error", "msg": f"Eval failed for {lead.get('title','?')}: {exc}"})

        await manager.broadcast({"type": "agent", "event": "ghost_eval", "msg": f"Evaluation done - {len(approved)}/{len(discovered)} approved"})

        if not approved:
            await manager.broadcast({"type": "agent", "event": "ghost_done", "msg": "Ghost Mode: no approved leads this cycle"})
            job_store.update(ghost_job.job_id, status="succeeded", progress=100, result={"approved": 0})
            return

        await manager.broadcast({"type": "agent", "event": "ghost_gen", "msg": f"Ghost Mode: generating assets for {len(approved)} leads"})
        generated = []
        for lead in approved:
            try:
                package = await generation_service.generate_package(lead)
                await asyncio.to_thread(
                    repo.leads.save_asset_package,
                    lead["job_id"],
                    package["resume"],
                    package["cover_letter"],
                    package.get("selected_projects", []),
                    package.get("keyword_coverage", {}),
                )
                generated.append({
                    **lead,
                    "asset": package["resume"],
                    "resume_asset": package["resume"],
                    "cover_letter_asset": package["cover_letter"],
                    "selected_projects": package.get("selected_projects", []),
                    "keyword_coverage": package.get("keyword_coverage", {}),
                })
                await manager.broadcast({"type": "agent", "event": "ghost_gen", "msg": f"Generated resume and cover letter for {lead.get('title','?')}"})
            except Exception as exc:
                await manager.broadcast({"type": "agent", "event": "ghost_error", "msg": f"Generation failed for {lead.get('title','?')}: {exc}"})

        if repo.settings.get_setting("auto_apply", "false") != "true":
            await manager.broadcast({
                "type": "agent",
                "event": "ghost_done",
                "msg": f"Ghost cycle complete - {len(generated)} leads ready. Auto-apply is OFF - waiting for manual approval in Sniper view.",
            })
            job_store.update(ghost_job.job_id, status="succeeded", progress=100, result={"approved": len(approved), "generated": len(generated)})
            return

        await manager.broadcast({"type": "agent", "event": "ghost_apply", "msg": f"Ghost Mode: auto-applying to {len(generated)} leads"})
        for item in generated:
            try:
                lead, asset = await automation_service.get_lead_for_fire(item["job_id"])
                _status, detail = fire_blocker(lead, asset)
                if detail:
                    await manager.broadcast({"type": "agent", "event": "ghost_error", "msg": f"Submission blocked: {item.get('title','?')} - {detail}"})
                    continue

                ok = await automation_service.submit_application(lead, asset)
                if ok:
                    await automation_service.mark_applied(item["job_id"])
                    await manager.broadcast({"type": "agent", "event": "ghost_applied", "msg": f"Applied: {item.get('title','?')} @ {item.get('company','?')}"})
                else:
                    await manager.broadcast({"type": "agent", "event": "ghost_error", "msg": f"Submission failed: {item.get('title','?')}"})
            except Exception as exc:
                await manager.broadcast({"type": "agent", "event": "ghost_error", "msg": f"Actuator error for {item.get('title','?')}: {exc}"})

        await manager.broadcast({"type": "agent", "event": "ghost_done", "msg": "Ghost cycle complete."})
        job_store.update(ghost_job.job_id, status="succeeded", progress=100, result={"approved": len(approved), "generated": len(generated)})

    return ghost_tick


def create_lifespan(scheduler: AsyncIOScheduler, ghost_tick, logger, service_supervisor=None):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_sql()
        if service_supervisor is not None:
            registry = await service_supervisor.start()
            app.state.service_registry = registry
            app.state.service_supervisor = service_supervisor
        ensure_ghost_job(scheduler, ghost_tick)
        log_startup_warnings(get_repository(), logger)
        scheduler.start()
        logger.info("FastAPI live.")
        try:
            yield
        finally:
            scheduler.shutdown(wait=False)
            if service_supervisor is not None:
                await service_supervisor.stop()
        logger.info("FastAPI shutdown.")

    return lifespan
