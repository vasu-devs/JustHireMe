"""Resume-templates API — transport only.

Multipart handling and the byte cap live here (transport concerns); extraction
and storage live in ``templates.service``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import Field

from api.dependencies import get_template_service
from api.rate_limit import RateLimiter, require_rate_limit
from core.types import StrictBody
from templates.service import ALLOWED_SUFFIXES, MAX_UPLOAD_SIZE


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
    if suffix not in ALLOWED_SUFFIXES:
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


def create_router(logger: logging.Logger | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["templates"])
    upload_limiter = RateLimiter(10, 60)

    @router.get("/templates")
    async def list_templates(service=Depends(get_template_service)):
        return await service.list_templates()

    @router.get("/templates/{template_id}")
    async def get_template(template_id: str, service=Depends(get_template_service)):
        return await service.get_template(template_id)

    @router.post("/templates/upload")
    async def upload_template(
        name: str = Form(""),
        make_default: bool = Form(False),
        file: UploadFile = File(...),
        service=Depends(get_template_service),
    ):
        require_rate_limit(upload_limiter)
        if file.size and file.size > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_SIZE // 1024 // 1024} MB)")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix and suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(status_code=415, detail="Upload a PDF, DOCX, TXT, or MD resume")
        async with _temp_upload(file) as path:
            return await service.create_from_file(
                path=path,
                display_name=name.strip(),
                filename=file.filename or "",
                make_default=make_default,
            )

    @router.post("/templates/text")
    async def create_template_from_text(body: TemplateTextBody, service=Depends(get_template_service)):
        require_rate_limit(upload_limiter)
        return await service.create_from_text(
            name=body.name, content=body.content, make_default=body.make_default
        )

    @router.post("/templates/{template_id}/default")
    async def set_default(template_id: str, service=Depends(get_template_service)):
        await service.set_default(template_id)
        return {"ok": True}

    @router.delete("/templates/{template_id}")
    async def delete_template(template_id: str, service=Depends(get_template_service)):
        await service.delete(template_id)
        return {"ok": True}

    return router
