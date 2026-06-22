from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data.repository import Repository, create_repository
from generation.generators.keywords import _keyword_coverage
from generation.generators.resume import _fallback_package


class PacketCommandError(RuntimeError):
    """User-facing CLI packet generation failure."""


def _safe_job_id(value: object) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "manual").strip())
    return safe.strip("._-") or "manual"


def default_packet_root() -> Path:
    root = os.environ.get("JHM_APP_DATA_DIR") or os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    return Path(root) / "JustHireMe" / "application_packets"


def _artifact_ref(path: Path | str, kind: str, *, reused: bool = False) -> dict[str, Any]:
    raw = Path(path).expanduser()
    resolved = raw if raw.is_absolute() else raw.resolve()
    ref = {"kind": kind, "path": str(resolved), "reused": reused}
    try:
        ref["file_url"] = resolved.as_uri()
    except ValueError:
        ref["file_url"] = ""
    return ref


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _lead_score(lead: dict[str, Any]) -> int:
    for key in ("score", "signal_score", "lead_quality_score"):
        try:
            value = int(lead.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0


def _packet_generation_blocker(lead: dict[str, Any]) -> str:
    title = str(lead.get("title") or "").strip()
    description = str(lead.get("description") or "").strip()
    reason = str(lead.get("reason") or "").strip()
    match_points = " ".join(str(item or "") for item in lead.get("match_points", []) or [])
    context = re.sub(r"\s+", " ", "\n".join([title, description, reason, match_points])).strip()
    if not title:
        return "Lead needs a title before packet generation."
    if not description and not reason and not match_points:
        return "Paste the job description before generating. The current lead has no role requirements to tailor against."
    if len(context) < 25:
        return "Paste a fuller job description before generating so the packet can be tailored without guessing."
    return ""


def _resolve_lead(
    selector: str | None,
    *,
    repo: Repository,
    job_url: str | None = None,
    high_score: bool = False,
    min_score: int = 0,
) -> dict[str, Any]:
    if selector:
        lead = repo.leads.get_lead_by_id(selector)
        if lead:
            return lead
        if selector.startswith(("http://", "https://")):
            job_url = selector
        else:
            raise PacketCommandError(f"Lead {selector!r} not found")

    leads = [lead for lead in repo.leads.get_all_leads() if (lead.get("kind") or "job") == "job"]
    if job_url:
        normalized = job_url.strip().rstrip("/")
        for lead in leads:
            if str(lead.get("url") or "").strip().rstrip("/") == normalized:
                return lead
        raise PacketCommandError(f"Lead URL {job_url!r} not found; add/import the lead before packet generation")

    if high_score:
        eligible = [lead for lead in leads if _lead_score(lead) >= min_score]
        if not eligible:
            raise PacketCommandError(f"No job leads found at or above score {min_score}")
        return sorted(eligible, key=_lead_score, reverse=True)[0]

    raise PacketCommandError("Provide a job id, --job-url, or --high-score")


def _application_answers(profile: dict[str, Any], lead: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    if not isinstance(identity, dict):
        identity = {}
    return {
        "job_id": lead.get("job_id") or lead.get("id") or "",
        "job_url": lead.get("url") or "",
        "candidate_name": profile.get("n") or profile.get("name") or "Candidate",
        "email": identity.get("email") or "",
        "phone": identity.get("phone") or "",
        "linkedin_url": identity.get("linkedin_url") or "",
        "resume_path": artifacts["resume"]["path"],
        "cover_note_path": artifacts["cover_note"]["path"],
        "handoff_fields": {
            "work_authorization": "review manually before submitting",
            "sponsorship": "review manually before submitting",
            "salary_expectation": "review manually before submitting",
            "availability": "review manually before submitting",
            "current_location": identity.get("location") or "review manually before submitting",
        },
        "submission_instruction": "Manual handoff only. Do not submit without operator review/approval.",
    }


def render_packet_summary(packet: dict[str, Any]) -> str:
    lead = packet.get("lead", {})
    artifacts = packet.get("artifacts", {})
    lines = [
        f"# Application packet: {lead.get('title') or 'Unknown role'} @ {lead.get('company') or 'Unknown company'}",
        "",
        f"- Job ID: {packet.get('job_id', '')}",
        f"- Job URL: {lead.get('url') or ''}",
        f"- Score: {lead.get('score') or lead.get('signal_score') or 0}",
        f"- Dry run: {'yes' if packet.get('dry_run') else 'no'}",
        f"- Submitted: {'yes' if packet.get('submitted') else 'no'}",
        f"- Reused existing assets: {'yes' if packet.get('reused_existing_assets') else 'no'}",
        "",
        "## Artifacts",
    ]
    for name in ("resume", "cover_note", "application_answers", "audit_record"):
        artifact = artifacts.get(name, {})
        lines.append(f"- {name}: {artifact.get('path', '')}")
    warnings = packet.get("warnings") or []
    if warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in warnings)
    lines.extend(["", "No external application was submitted.", ""])
    return "\n".join(lines)


def generate_application_packet(
    selector: str | None,
    *,
    repo: Repository | None = None,
    job_url: str | None = None,
    output_root: str | Path | None = None,
    dry_run: bool = True,
    submit: bool = False,
    high_score: bool = False,
    min_score: int = 0,
    force: bool = False,
) -> dict[str, Any]:
    if submit:
        raise PacketCommandError("external submission is not supported in the packet CLI")
    if not dry_run:
        raise PacketCommandError("safe mode requires --dry-run; lead/application mutation is intentionally not implemented")

    repo = repo or create_repository()
    lead = _resolve_lead(selector, repo=repo, job_url=job_url, high_score=high_score, min_score=min_score)
    blocker = _packet_generation_blocker(lead)
    if blocker:
        raise PacketCommandError(blocker)

    profile = repo.profile.get_profile()
    job_id = _safe_job_id(lead.get("job_id") or lead.get("id") or selector or lead.get("url"))
    packet_dir = Path(output_root) / job_id if output_root is not None else default_packet_root() / job_id
    packet_dir.mkdir(parents=True, exist_ok=True)

    existing_resume = str(lead.get("resume_asset") or lead.get("asset") or "").strip()
    existing_cover = str(lead.get("cover_letter_asset") or lead.get("cover_letter_path") or "").strip()
    existing_paths = [Path(existing_resume).expanduser(), Path(existing_cover).expanduser()]
    stale_existing_assets = bool(existing_resume or existing_cover) and not all(path.is_file() for path in existing_paths)
    reused = bool(existing_resume and existing_cover and not force and not stale_existing_assets)

    artifacts: dict[str, Any] = {}
    selected_projects: list[str] = []
    keyword_coverage: dict[str, Any] = {}
    warnings: list[str] = []

    if reused:
        artifacts["resume"] = _artifact_ref(existing_resume, "resume", reused=True)
        artifacts["cover_note"] = _artifact_ref(existing_cover, "cover_note", reused=True)
        selected_projects = list(lead.get("selected_projects") or [])
        keyword_coverage = dict(lead.get("keyword_coverage") or {})
    else:
        if stale_existing_assets:
            warnings.append("Existing resume/cover asset paths were stale; regenerated Markdown handoff artifacts.")
        package = _fallback_package(profile, lead, template="")
        selected_projects = package.selected_projects
        keyword_coverage = _keyword_coverage(profile, lead, package.resume_markdown)
        resume_path = packet_dir / "resume.md"
        cover_path = packet_dir / "cover_note.md"
        _write_text(resume_path, package.resume_markdown.rstrip() + "\n")
        _write_text(cover_path, package.cover_letter_markdown.rstrip() + "\n")
        artifacts["resume"] = _artifact_ref(resume_path, "resume")
        artifacts["cover_note"] = _artifact_ref(cover_path, "cover_note")
        warnings.append("Generated Markdown handoff artifacts only; no ATS/browser filling was attempted.")

    answers_path = packet_dir / "application_answers.json"
    answers = _application_answers(profile, lead, artifacts)
    _write_json(answers_path, answers)
    artifacts["application_answers"] = _artifact_ref(answers_path, "application_answers")

    audit_path = packet_dir / "audit_record.json"
    audit_record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "job_id": job_id,
        "job_url": lead.get("url") or "",
        "dry_run": dry_run,
        "submitted": False,
        "submit_attempted": False,
        "mutation_policy": "dry-run: no lead/application mutation; artifacts only",
        "reused_existing_assets": reused,
        "selected_projects": selected_projects,
        "keyword_coverage": keyword_coverage,
        "artifacts": artifacts,
    }
    _write_json(audit_path, audit_record)
    artifacts["audit_record"] = _artifact_ref(audit_path, "audit_record")

    packet = {
        "status": "ready",
        "job_id": job_id,
        "dry_run": dry_run,
        "submitted": False,
        "reused_existing_assets": reused,
        "lead": {
            "job_id": lead.get("job_id") or job_id,
            "title": lead.get("title") or "",
            "company": lead.get("company") or "",
            "url": lead.get("url") or "",
            "score": lead.get("score") or lead.get("signal_score") or 0,
            "status": lead.get("status") or "",
        },
        "artifacts": artifacts,
        "selected_projects": selected_projects,
        "keyword_coverage": keyword_coverage,
        "warnings": warnings,
        "recoverable_by_job_id": True,
    }
    summary_path = packet_dir / "summary.md"
    _write_text(summary_path, render_packet_summary(packet))
    packet["summary_markdown_path"] = str(summary_path.resolve())

    index_path = packet_dir / "packet_index.json"
    _write_json(index_path, packet)
    packet["packet_index_path"] = str(index_path.resolve())
    _write_json(index_path, packet)
    return packet
