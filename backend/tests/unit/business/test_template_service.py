"""Unit tests for templates/service.py — stored resume templates."""

from __future__ import annotations

import types
import zipfile

import pytest

from core.errors import NotFoundError, UnprocessableError
from templates.service import TemplateService, extract_text


def _repo(templates=None, create=None, set_default=True, delete=True):
    rows = list(templates or [])

    class Store:
        def list_templates(self):
            return rows

        def get_template(self, template_id):
            return next((t for t in rows if t["id"] == template_id), None)

        def create_template(self, name, content, filename, make_default=None):
            if create == "reject":
                raise ValueError("template too short")
            return {"id": "t1", "name": name, "content": content,
                    "source": filename, "char_count": len(content), "is_default": bool(make_default)}

        def set_default_template(self, template_id):
            return set_default

        def delete_template(self, template_id):
            return delete

    return types.SimpleNamespace(resume_templates=Store())


# ------------------------------------------------------------------ extraction


def test_extract_text_reads_plain_text(tmp_path):
    path = tmp_path / "cv.md"
    path.write_text("# Ada Lovelace\nEngineer", encoding="utf-8")
    assert "Ada Lovelace" in extract_text(str(path))


def test_extract_text_reads_a_docx(tmp_path):
    path = tmp_path / "cv.docx"
    xml = (
        '<?xml version="1.0"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Grace Hopper</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Rear Admiral</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    assert extract_text(str(path)) == "Grace Hopper\nRear Admiral"


def test_extract_text_returns_empty_instead_of_raising_on_a_corrupt_file(tmp_path):
    path = tmp_path / "cv.docx"
    path.write_bytes(b"not a zip")
    assert extract_text(str(path)) == ""


def test_extract_text_returns_empty_for_a_missing_file():
    assert extract_text("/definitely/not/here.txt") == ""


# --------------------------------------------------------------------- service


@pytest.mark.asyncio
async def test_list_templates_wraps_rows():
    result = await TemplateService(_repo([{"id": "t1"}])).list_templates()
    assert result == {"templates": [{"id": "t1"}]}


@pytest.mark.asyncio
async def test_get_template_raises_not_found():
    with pytest.raises(NotFoundError):
        await TemplateService(_repo()).get_template("nope")


@pytest.mark.asyncio
async def test_create_from_file_extracts_and_stores(tmp_path):
    path = tmp_path / "resume.md"
    path.write_text("Ada Lovelace — Engineer", encoding="utf-8")
    template = await TemplateService(_repo()).create_from_file(
        path=str(path), display_name="", filename="resume.md", make_default=True
    )
    assert template["name"] == "resume"          # falls back to the file stem
    assert "Ada Lovelace" in template["content"]
    assert template["is_default"] is True


@pytest.mark.asyncio
async def test_create_from_file_rejects_a_file_with_no_extractable_text(tmp_path):
    """Scanned/image PDFs yield nothing — that must be a clear 422, not an empty template."""
    path = tmp_path / "scan.md"
    path.write_text("   \n  ", encoding="utf-8")
    with pytest.raises(UnprocessableError, match="scanned/image"):
        await TemplateService(_repo()).create_from_file(
            path=str(path), display_name="", filename="scan.md", make_default=False
        )


@pytest.mark.asyncio
async def test_create_from_text_maps_a_storage_rejection_to_422():
    with pytest.raises(UnprocessableError, match="too short"):
        await TemplateService(_repo(create="reject")).create_from_text(name="n", content="x")


@pytest.mark.asyncio
async def test_set_default_and_delete_raise_not_found_when_the_row_is_gone():
    service = TemplateService(_repo(set_default=False, delete=False))
    with pytest.raises(NotFoundError):
        await service.set_default("t1")
    with pytest.raises(NotFoundError):
        await service.delete("t1")


@pytest.mark.asyncio
async def test_set_default_and_delete_succeed_quietly():
    service = TemplateService(_repo())
    assert await service.set_default("t1") is None
    assert await service.delete("t1") is None
