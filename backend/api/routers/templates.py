from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from api.dependencies import get_repository
from api.rate_limit import RateLimiter, require_rate_limit
from core.types import StrictBody
from data.repository import Repository
from pydantic import Field

MAX_UPLOAD_SIZE = 10 * 1024 * 1024
_ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


class TemplateTextBody(StrictBody):
    name: str = Field(default="", max_length=160)
    content: str = Field(max_length=60000)
    make_default: bool = Field(default=False)


async def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload in chunks, rejecting at the real byte ceiling.

    file.size is client-declared multipart metadata (absent or spoofable), so we
    enforce the cap on actual bytes read instead of trusting it.
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
async def _temp_upload(file: UploadFile):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        suffix = ".txt"
    content = await _read_capped(file, MAX_UPLOAD_SIZE)

    def _write() -> str:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            return tmp.name

    tmp_name = await asyncio.to_thread(_write)
    try:
        yield tmp_name
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)


def _extract_text(path: str) -> str:
    """Extract plain text from an uploaded PDF/DOCX/TXT/MD resume.

    Kept self-contained (stdlib + pypdf) so the api layer does not import the
    profile domain package (see tests/test_import_boundaries.py).
    """
    suffix = Path(path).suffix.lower()
    try:
        if suffix == ".pdf":
            from pypdf import PdfReader

            pages = PdfReader(path).pages
            return " ".join(page.extract_text() or "" for page in pages)
        if suffix == ".docx":
            import zipfile

            import defusedxml.ElementTree as ET

            with zipfile.ZipFile(path) as archive:
                info = archive.getinfo("word/document.xml")
                if info.file_size > 64 * 1024 * 1024:
                    raise ValueError("DOCX document.xml too large")
                root = ET.fromstring(archive.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paragraphs = [
                "".join(node.text or "" for node in para.findall(".//w:t", ns))
                for para in root.findall(".//w:p", ns)
            ]
            return "\n".join(line for line in paragraphs if line.strip())
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        logging.getLogger(__name__).warning("template text extraction failed for %s: %s", path, exc)
        return ""


def create_router(logger: logging.Logger | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["templates"])
    log = logger or logging.getLogger(__name__)
    upload_limiter = RateLimiter(10, 60)

    @router.get("/templates")
    async def list_templates(repo: Repository = Depends(get_repository)):
        return {"templates": await asyncio.to_thread(repo.resume_templates.list_templates)}

    @router.get("/templates/{template_id}")
    async def get_template(template_id: str, repo: Repository = Depends(get_repository)):
        template = await asyncio.to_thread(repo.resume_templates.get_template, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        return template

    @router.post("/templates/upload")
    async def upload_template(
        name: str = Form(""),
        make_default: bool = Form(False),
        file: UploadFile = File(...),
        repo: Repository = Depends(get_repository),
    ):
        require_rate_limit(upload_limiter)
        if file.size and file.size > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_SIZE // 1024 // 1024} MB)")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix and suffix not in _ALLOWED_SUFFIXES:
            raise HTTPException(status_code=415, detail="Upload a PDF, DOCX, TXT, or MD resume")
        async with _temp_upload(file) as path:
            text = await asyncio.to_thread(_extract_text, path)
        text = (text or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="Could not extract text from the file (scanned/image PDFs are not supported)")
        display_name = name.strip() or Path(file.filename or "Resume template").stem
        try:
            template = await asyncio.to_thread(
                repo.resume_templates.create_template,
                display_name,
                text,
                file.filename or "",
                make_default=make_default or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        log.info("resume template created: %s (%s chars)", template["id"], template["char_count"])
        return template

    @router.post("/templates/text")
    async def create_template_from_text(body: TemplateTextBody, repo: Repository = Depends(get_repository)):
        require_rate_limit(upload_limiter)
        try:
            template = await asyncio.to_thread(
                repo.resume_templates.create_template,
                body.name,
                body.content,
                "",
                make_default=body.make_default or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return template

    @router.post("/templates/{template_id}/default")
    async def set_default(template_id: str, repo: Repository = Depends(get_repository)):
        ok = await asyncio.to_thread(repo.resume_templates.set_default_template, template_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Template not found")
        return {"ok": True}

    @router.delete("/templates/{template_id}")
    async def delete_template(template_id: str, repo: Repository = Depends(get_repository)):
        ok = await asyncio.to_thread(repo.resume_templates.delete_template, template_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Template not found")
        return {"ok": True}

    return router
