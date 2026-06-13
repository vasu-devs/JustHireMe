from __future__ import annotations

import hashlib
import os
import re

from data.repository import Repository, create_repository
from core.logging import get_logger
from core.generation_readiness import lead_generation_blocker

from generation.generators.base import _DocPackage  # noqa: F401
from generation.generators.cover_letter import (
    _normalize_package,
)
from generation.generators.drafting import _draft_package
from generation.generators.keywords import (
    _keyword_coverage,
)
from generation.generators.resume import (
    _build_proof,
    _fallback_package,
)
import generation.pdf_renderer as _pdf

_log = get_logger(__name__)
_assets = _pdf._assets


def _is_transient_llm_error(exc: Exception) -> bool:
    try:
        from llm.client import is_transient_llm_error
    except ImportError:
        return False
    return is_transient_llm_error(exc)


def _safe_job_id(value: object) -> str:
    raw = str(value or "manual").strip()
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)
    safe = safe.strip("._-") or "manual"
    # If sanitizing was lossy, two distinct ids (e.g. "a/b" and "a:b") collapse to
    # the same stem and would overwrite each other's PDFs. Append a short digest
    # of the raw id to keep them distinct. Clean ids are left untouched so the
    # leads router can still reconstruct versioned filenames from the raw id.
    if safe != raw:
        digest = hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:8]
        safe = f"{safe}_{digest}"
    return safe


def get_profile(repo: Repository | None = None) -> dict:
    active_repo = repo or create_repository()
    return active_repo.profile.get_profile()


def _clean(text: str) -> str:
    return _pdf.clean(text)


def _strip_inline(text: str) -> str:
    return _pdf.strip_inline(text)


def _render_resume_template(md_text: str, filename: str) -> str:
    _pdf._assets = _assets
    os.makedirs(_assets, exist_ok=True)
    return _pdf.render_resume_template(md_text, filename)


def _render(md_text: str, filename: str, kind: str = "resume") -> str:
    _pdf._assets = _assets
    os.makedirs(_assets, exist_ok=True)
    return _pdf.render(md_text, filename, kind=kind)


def run_package(lead: dict, template: str = "", repo: Repository | None = None) -> dict:
    blocked_reason = lead_generation_blocker(lead)
    if blocked_reason:
        raise ValueError(blocked_reason)
    # Fail loudly if a key-based provider is selected without a key, instead of
    # silently drafting with an empty LLM result and shipping a generic resume
    # marked "approved". Keyless providers (ollama / CLIs) pass through.
    from llm.client import assert_llm_configured

    assert_llm_configured("generator")
    repo = repo or create_repository()
    profile = get_profile(repo)
    proof = _build_proof(profile)
    lead_with_ctx = {**lead, "candidate_name": profile.get("n", "")}

    try:
        package = _draft_package(profile, proof, lead_with_ctx, template=template)
        package = _normalize_package(package, profile, lead_with_ctx, template=template)
    except Exception as exc:
        if _is_transient_llm_error(exc):
            # Rate limits / timeouts / 5xx: surface to the router's retry path
            # (503 + Retry-After, lead stays in "tailoring") instead of silently
            # shipping an untailored fallback resume marked "approved".
            raise
        _log.warning(
            "LLM draft failed for %s; using local fallback package: %s",
            lead.get("job_id", "?"),
            exc,
        )
        package = _fallback_package(profile, lead_with_ctx, template=template)
    keyword_coverage = _keyword_coverage(profile, lead_with_ctx, package.resume_markdown)

    job_id = _safe_job_id(lead.get("job_id") or lead.get("id"))
    try:
        current_version = repo.leads.get_resume_version(job_id)
        new_version = current_version + 1
        resume_path = _render(package.resume_markdown, f"{job_id}_v{new_version}.pdf", kind="resume")
        cover_letter_path = _render(package.cover_letter_markdown, f"{job_id}_cl_v{new_version}.pdf", kind="cover")
        try:
            repo.leads.save_generated_asset_version(job_id, resume_path, cover_letter_path, new_version)
        except Exception as exc:
            _log.warning("asset version persistence skipped for %s: %s", job_id, exc)
    except Exception as exc:
        _log.warning("PDF render failed for %s; retrying with local fallback package: %s", job_id, exc)
        try:
            package = _fallback_package(profile, lead_with_ctx, template=template)
            keyword_coverage = _keyword_coverage(profile, lead_with_ctx, package.resume_markdown)
            current_version = repo.leads.get_resume_version(job_id)
            new_version = current_version + 1
            resume_path = _render(package.resume_markdown, f"{job_id}_v{new_version}.pdf", kind="resume")
            cover_letter_path = _render(package.cover_letter_markdown, f"{job_id}_cl_v{new_version}.pdf", kind="cover")
            try:
                repo.leads.save_generated_asset_version(job_id, resume_path, cover_letter_path, new_version)
            except Exception as persist_exc:
                _log.warning("asset version persistence skipped for %s: %s", job_id, persist_exc)
        except Exception as fallback_exc:
            _log.error("Fallback PDF render failed for %s: %s", job_id, fallback_exc)
            raise RuntimeError(f"PDF render failed: {fallback_exc}") from fallback_exc

    return {
        "resume": resume_path,
        "cover_letter": cover_letter_path,
        "selected_projects": package.selected_projects,
        "founder_message": (package.founder_message or "").strip(),
        "linkedin_note": (package.linkedin_note or "").strip(),
        "cold_email": (package.cold_email or "").strip(),
        "keyword_coverage": keyword_coverage,
    }


def run(lead: dict, template: str = "") -> str:
    return run_package(lead, template=template)["resume"]
