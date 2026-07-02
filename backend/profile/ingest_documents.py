"""Document text extraction for profile ingestion.

Reads raw text out of uploaded resume files (PDF via pypdf, DOCX via the docx
XML, plain .txt/.md) and provides the markdown-strip / PDF-spacing-repair
cleaners used on extracted text. No dependency on the rest of the ingestor.
"""

import re
import zipfile
from pathlib import Path

import defusedxml.ElementTree as ET

from core.logging import get_logger

_log = get_logger(__name__)

# Ceiling for a single decompressed DOCX member: guards against zip bombs where
# a tiny archive expands to gigabytes. A real resume's document.xml is well
# under this.
_MAX_DOCX_MEMBER_BYTES = 64 * 1024 * 1024

# Bounds on PDF extraction: a résumé is a handful of pages. These stop a
# decompression-bomb / thousands-of-pages PDF from hanging pypdf or exhausting
# memory and stalling the sidecar.
_MAX_PDF_PAGES = 300
_MAX_PDF_TEXT_CHARS = 200_000


def _read_zip_member(archive: zipfile.ZipFile, name: str) -> bytes:
    info = archive.getinfo(name)
    if info.file_size > _MAX_DOCX_MEMBER_BYTES:
        raise ValueError(f"DOCX member {name!r} too large: {info.file_size} bytes")
    return archive.read(name)


def _docx(path: str) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = _read_zip_member(archive, "word/document.xml")
        root = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []
        for paragraph in root.findall(".//w:p", ns):
            text = "".join(node.text or "" for node in paragraph.findall(".//w:t", ns))
            if text.strip():
                paragraphs.append(text)
        return "\n".join(paragraphs)
    except Exception as exc:
        _log.error("DOCX read error for %s: %s", path, exc)
        return ""


def _text_file(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        _log.error("text resume read error for %s: %s", path, exc)
        return ""


def _document(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return _pdf(path)
    if suffix == ".docx":
        return _docx(path)
    if suffix in {".txt", ".md"}:
        return _text_file(path)
    if suffix == ".doc":
        _log.error("Legacy .doc resume uploads are not supported; export the resume as PDF or DOCX")
        return ""
    return _text_file(path)


def _pdf(path: str) -> str:
    try:
        from pypdf import PdfReader
        # strict=False: tolerate the malformed-but-readable PDFs real users upload
        # instead of raising on the first spec violation.
        reader = PdfReader(path, strict=False)
        parts: list[str] = []
        total = 0
        truncated = False
        for index, page in enumerate(reader.pages):
            if index >= _MAX_PDF_PAGES:
                _log.warning("PDF exceeds %d pages; reading only the first %d: %s", _MAX_PDF_PAGES, _MAX_PDF_PAGES, path)
                truncated = True
                break
            try:
                chunk = page.extract_text() or ""
            except Exception as exc:
                # One bad page must not abort extraction of the rest.
                _log.warning("PDF page %d extract error (%s): %s", index, path, exc)
                continue
            parts.append(chunk)
            total += len(chunk)
            if total >= _MAX_PDF_TEXT_CHARS:
                _log.warning("PDF text exceeded %d chars; truncating: %s", _MAX_PDF_TEXT_CHARS, path)
                truncated = True
                break
        text = "\n".join(parts)
        if not text.strip() and not truncated:
            _log.warning("PDF has no extractable text (may be scanned/image-only): %s", path)
        return text
    except Exception as exc:
        _log.error("PDF read error for %s: %s", path, exc)
        return ""


def _strip_md(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text or "")
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("→", "->").replace("·", "-")
    text = re.sub(r"^\s*(?:[-*]|•|â€¢)\s*", "", text)
    text = _repair_pdf_spacing(text)
    return re.sub(r"\s+", " ", text).strip()


def _repair_pdf_spacing(text: str) -> str:
    text = re.sub(r"\b([A-Z]\.[A-Z])\s+([a-z]{2,})\b", r"\1\2", text or "")
    text = re.sub(r"\b([A-Z])\.\s+([A-Za-z]{2,})\b", r"\1.\2", text or "")
    return re.sub(r"\b([BFV])\s+([a-z]{2,})\b", r"\1\2", text)
