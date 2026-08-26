from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import HTTPException, UploadFile


MAX_UPLOAD_SIZE = 10 * 1024 * 1024


async def read_capped(file: UploadFile, max_bytes: int = MAX_UPLOAD_SIZE) -> bytes:
    """Read actual multipart bytes in chunks; never trust client-declared size."""
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


@asynccontextmanager
async def temp_upload(file: UploadFile | None):
    if not file or not file.filename:
        yield None
        return
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".doc", ".docx", ".txt", ".md"}:
        suffix = ".txt"
    tmp_name = ""
    try:
        content = await read_capped(file)

        def write_temp() -> str:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                return tmp.name

        tmp_name = await asyncio.to_thread(write_temp)
        yield tmp_name
    finally:
        if tmp_name:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
