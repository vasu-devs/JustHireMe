from __future__ import annotations

import asyncio
import json
import os
import tempfile
import contextlib
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import Field

from api.rate_limit import RateLimiter, require_rate_limit
from api.dependencies import get_profile_service
from core.types import StrictBody

MAX_UPLOAD_SIZE = 10 * 1024 * 1024
# Serialized-JSON ceiling for the profile-import body: generous for any real
# profile (a rich profile is a few hundred KB) while refusing an abusive blob
# before it is parsed/normalized. Kept separate from MAX_UPLOAD_SIZE (files).
MAX_PROFILE_JSON_BYTES = 5 * 1024 * 1024
# Hard cap on pasted résumé text, so a giant paste can't buffer unbounded in the
# form parser. The parser itself truncates further (profile.ingestor MAX_INGEST_CHARS).
MAX_RAW_RESUME_CHARS = 2_000_000

_EMPTY_IMPORT_STATS = {
    "skills": 0, "experience": 0, "projects": 0,
    "education": 0, "certifications": 0, "achievements": 0,
    "vector_sync": "skipped",
}


class GithubIngestBody(StrictBody):
    username: str = Field(max_length=100)
    token: str = Field(default="", max_length=200)
    max_repos: int = Field(default=100, ge=1, le=500)


class PortfolioIngestBody(StrictBody):
    url: str = Field(max_length=2000)
    auto_import: bool = Field(
        default=False,
        description="if true, immediately write extracted data to the graph",
    )


# NOTE: POST /ingest/profile intentionally does NOT bind a strict Pydantic body.
# Profile JSON shapes vary too much (grouped-dict skills, list stacks, alt keys),
# and a strict model 422'd valid data before the tolerant normalizer could run.
# The endpoint takes the raw JSON object; profile.normalization.normalize_profile_payload
# coerces + bounds every field. Field caps that used to live on the removed
# Profile* models are enforced there by truncation.


def _read_profile_template(path: Path, logger) -> dict:
    """Load the profile-import template, falling back to a built-in default if
    the file is missing or corrupt (C3 — packaged builds must not 500 here)."""
    try:
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("profile template unavailable (%s); serving default", exc)
        return _default_profile_template()


def _default_profile_template() -> dict:
    """Minimal valid profile-import template, used when the bundled JSON file
    is missing (e.g. a packaged build that didn't ship it). Mirrors the shape
    of data/profile_schema_example.json so the import UI keeps working."""
    return {
        "candidate": {"name": "Your Full Name", "summary": "2-4 sentence professional summary."},
        "identity": {
            "email": "you@example.com",
            "phone": "",
            "linkedin_url": "",
            "github_url": "",
            "website_url": "",
            "city": "",
        },
        "skills": [{"name": "Python", "category": "language"}],
        "experience": [{"role": "", "company": "", "period": "", "description": ""}],
        "projects": [{"title": "", "stack": "", "repo": "", "impact": ""}],
        "education": [{"title": ""}],
        "certifications": [{"title": ""}],
        "achievements": [{"title": ""}],
    }


async def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload in chunks, rejecting at the real byte ceiling.

    file.size is client-declared multipart metadata (absent or spoofable), so the
    cap is enforced on actual bytes read — not by trusting the declared size.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="Upload too large")
        chunks.append(chunk)
    return b"".join(chunks)


@contextlib.asynccontextmanager
async def _temp_upload(file: UploadFile | None):
    if not file or not file.filename:
        yield None
        return
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".doc", ".docx", ".txt", ".md"}:
        suffix = ".txt"
    tmp_name = ""
    try:
        # L1: read the upload asynchronously and write the temp file off the
        # event loop so a large upload can't block other coroutines.
        content = await _read_capped(file, MAX_UPLOAD_SIZE)

        def _write() -> str:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                return tmp.name

        tmp_name = await asyncio.to_thread(_write)
        yield tmp_name
    finally:
        if tmp_name:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)


def create_router(manager, logger) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["ingestion"])
    ingest_limiter = RateLimiter(5, 60)

    @router.post("/ingest")
    async def ingest(
        raw: str = Form(""),
        file: UploadFile | None = File(None),
    ):
        require_rate_limit(ingest_limiter)
        if file and file.filename and file.size and file.size > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_SIZE // 1024 // 1024} MB)")
        # Bound pasted text so an oversized paste can't pin the parser; the parser
        # truncates further for LLM cost. Truncate rather than 413 — a best-effort
        # parse of the first ~2M chars beats rejecting the whole paste.
        if raw and len(raw) > MAX_RAW_RESUME_CHARS:
            raw = raw[:MAX_RAW_RESUME_CHARS]
        try:
            async with _temp_upload(file) as pdf_path:
                profile = await get_profile_service().ingest_resume(raw, pdf_path)
                if isinstance(profile, dict):
                    profile_payload = profile
                    skill_count = len(profile.get("skills", []))
                    profile_name = profile.get("n", "")
                else:
                    profile_payload = profile.model_dump()
                    skill_count = len(profile.skills)
                    profile_name = profile.n
                await manager.broadcast({
                    "type": "agent",
                    "event": "ingested",
                    "msg": f"Profile ingested: {profile_name} - {skill_count} skills",
                })
                return profile_payload
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/ingest/linkedin")
    async def ingest_linkedin(file: UploadFile = File(...)):
        require_rate_limit(ingest_limiter)
        if not (file.filename or "").endswith(".zip"):
            raise HTTPException(400, "expected a .zip file from LinkedIn data export")
        raw = await _read_capped(file, 50 * 1024 * 1024)
        try:
            return await get_profile_service().ingest_linkedin(raw)
        except Exception as exc:
            logger.error("linkedin parse failed: %s", exc)
            raise HTTPException(422, "Could not parse the LinkedIn export.") from exc

    @router.post("/ingest/github")
    async def ingest_github_endpoint(body: GithubIngestBody):
        require_rate_limit(ingest_limiter)
        try:
            result = await get_profile_service().ingest_github(
                body.username,
                token=body.token or None,
                max_repos=body.max_repos,
            )
        except Exception as exc:
            logger.error("github ingest failed: %s", exc)
            raise HTTPException(502, "Could not ingest the GitHub profile.") from exc
        if "error" in result:
            status_code = int(result.get("status_code") or (404 if result.get("error_kind") == "not_found" else 502))
            raise HTTPException(status_code, result["error"])
        return result

    @router.post("/ingest/profile")
    async def import_profile_json(request: Request):
        # Accept the raw JSON object rather than a rigid Pydantic model: real
        # profile exports vary in shape (skills as a grouped {category:[...]}
        # dict, a flat string list, or [{name,category}]; stack as a list or a
        # string; alternate keys). The service + normalizer already coerce all
        # of these — validating against a strict schema here 422'd valid data
        # BEFORE the tolerant path (and the fallback below) could ever run.
        require_rate_limit(ingest_limiter)
        raw_body = await request.body()
        if len(raw_body) > MAX_PROFILE_JSON_BYTES:
            raise HTTPException(413, f"Profile JSON too large (max {MAX_PROFILE_JSON_BYTES // 1024 // 1024} MB)")
        try:
            data = json.loads(raw_body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(400, f"Body is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise HTTPException(400, "Profile JSON must be a JSON object (e.g. {\"skills\": ...})")
        try:
            return await get_profile_service().import_profile_data(data)
        except Exception as exc:
            logger.error("profile import failed: %s", exc)
            return {"status": "partial", "stats": dict(_EMPTY_IMPORT_STATS), "errors": [str(exc)]}

    @router.get("/ingest/profile/template")
    async def get_profile_template():
        template_path = Path(__file__).resolve().parents[2] / "data" / "profile_schema_example.json"
        return _read_profile_template(template_path, logger)

    @router.post("/ingest/portfolio")
    async def ingest_portfolio_endpoint(body: PortfolioIngestBody):
        require_rate_limit(ingest_limiter)
        if not body.url.startswith(("http://", "https://")):
            raise HTTPException(400, "url must start with http:// or https://")
        try:
            result = await get_profile_service().ingest_portfolio(body.url, auto_import=body.auto_import)
        except Exception as exc:
            logger.error("portfolio ingest failed: %s", exc)
            raise HTTPException(502, f"could not ingest portfolio: {exc}") from exc
        if result.get("error") and not result.get("screenshot_b64"):
            raise HTTPException(int(result.get("status_code") or 422), result["error"])
        if result.get("imported"):
            result["import_stats"] = result["imported"]["stats"]
            result["import_errors"] = result["imported"]["errors"]
        return result

    return router
