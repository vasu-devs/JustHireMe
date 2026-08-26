"""Resume-template service — business layer behind the templates router."""

from __future__ import annotations

import asyncio
import logging
import zipfile
from pathlib import Path

from core.errors import NotFoundError, UnprocessableError
from data.repository import Repository

_log = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024
ALLOWED_SUFFIXES = frozenset({".pdf", ".docx", ".txt", ".md"})
_MAX_DOCX_XML_BYTES = 64 * 1024 * 1024


def extract_text(path: str) -> str:
    """Extract plain text from an uploaded PDF/DOCX/TXT/MD resume.

    ponytail: near-duplicate of profile/ingest_documents.py's extraction. Kept
    separate because that path applies CV-specific cleanup this one must not;
    merge behind one interface if a third caller appears.
    """
    suffix = Path(path).suffix.lower()
    try:
        if suffix == ".pdf":
            from pypdf import PdfReader

            return " ".join(page.extract_text() or "" for page in PdfReader(path).pages)
        if suffix == ".docx":
            import defusedxml.ElementTree as ET

            with zipfile.ZipFile(path) as archive:
                info = archive.getinfo("word/document.xml")
                if info.file_size > _MAX_DOCX_XML_BYTES:
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
        _log.warning("template text extraction failed for %s: %s", path, exc)
        return ""


class TemplateService:
    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    async def list_templates(self) -> dict:
        return {"templates": await asyncio.to_thread(self._repo.resume_templates.list_templates)}

    async def get_template(self, template_id: str) -> dict:
        template = await asyncio.to_thread(self._repo.resume_templates.get_template, template_id)
        if not template:
            raise NotFoundError("Template not found")
        return template

    async def create_from_file(self, *, path: str, display_name: str, filename: str, make_default: bool) -> dict:
        text = (await asyncio.to_thread(extract_text, path) or "").strip()
        if not text:
            raise UnprocessableError(
                "Could not extract text from the file (scanned/image PDFs are not supported)"
            )
        template = await self.create_from_text(
            name=display_name or Path(filename or "Resume template").stem,
            content=text,
            source_filename=filename,
            make_default=make_default,
        )
        _log.info("resume template created: %s (%s chars)", template["id"], template["char_count"])
        return template

    async def create_from_text(self, *, name: str, content: str, source_filename: str = "", make_default: bool = False) -> dict:
        try:
            return await asyncio.to_thread(
                self._repo.resume_templates.create_template,
                name,
                content,
                source_filename,
                make_default=make_default or None,
            )
        except ValueError as exc:
            raise UnprocessableError(str(exc)) from exc

    async def set_default(self, template_id: str) -> None:
        if not await asyncio.to_thread(self._repo.resume_templates.set_default_template, template_id):
            raise NotFoundError("Template not found")

    async def delete(self, template_id: str) -> None:
        if not await asyncio.to_thread(self._repo.resume_templates.delete_template, template_id):
            raise NotFoundError("Template not found")


def create_template_service(repo: Repository) -> TemplateService:
    return TemplateService(repo)


__all__ = [
    "ALLOWED_SUFFIXES",
    "MAX_UPLOAD_SIZE",
    "TemplateService",
    "create_template_service",
    "extract_text",
]
