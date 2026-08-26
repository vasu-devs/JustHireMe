"""The testable half of two I/O-heavy modules.

profile/ingest_documents.py — text extraction from a real file on disk.
automation/selectors.py      — which form fields to fill for a given URL.

Both are reachable without a browser or a network call, and both are where a
silent mistake costs the user a mangled CV or an unfilled application form.
"""

from __future__ import annotations

import zipfile

import pytest

from automation import selectors as sel
from profile import ingest_documents as docs


# ----------------------------------------------------------------- extraction


def test_a_text_file_is_read_verbatim(tmp_path):
    path = tmp_path / "cv.txt"
    path.write_text("Ada Lovelace\nEngineer", encoding="utf-8")
    assert "Ada Lovelace" in docs._document(str(path))


def test_a_docx_paragraphs_are_joined(tmp_path):
    path = tmp_path / "cv.docx"
    xml = (
        '<?xml version="1.0"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Grace Hopper</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Rear Admiral</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    text = docs._document(str(path))
    assert "Grace Hopper" in text and "Rear Admiral" in text


def test_a_corrupt_file_yields_empty_text_rather_than_raising(tmp_path):
    path = tmp_path / "cv.docx"
    path.write_bytes(b"not a zip at all")
    assert docs._document(str(path)) == ""


def test_a_missing_file_yields_empty_text(tmp_path):
    assert docs._document(str(tmp_path / "nope.pdf")) == ""


def test_an_unknown_extension_still_reads_as_text(tmp_path):
    path = tmp_path / "cv.rtfish"
    path.write_text("Plain content", encoding="utf-8")
    assert "Plain content" in docs._document(str(path))


# ------------------------------------------------------------- markdown clean


@pytest.mark.parametrize("raw, expected", [
    ("`code`", "code"),
    ("**bold**", "bold"),
    ("*italic*", "italic"),
    ("[label](https://x.com)", "label"),
    ("- bullet", "bullet"),
    ("• bullet", "bullet"),
])
def test_markdown_decoration_is_removed(raw, expected):
    assert docs._strip_md(raw) == expected


def test_arrows_and_middots_become_ascii():
    assert docs._strip_md("Built A → B") == "Built A -> B"
    assert docs._strip_md("A · B") == "A - B"


def test_whitespace_is_collapsed():
    assert docs._strip_md("too    many\n\nspaces") == "too many spaces"


# --------------------------------------------------- pdf extraction artefacts


def test_split_initials_are_rejoined():
    """PDF extraction inserts spaces inside initials ("B.Tech" -> "B. Tech")."""
    assert docs._repair_pdf_spacing("B. Tech in Computer Science") == "B.Tech in Computer Science"


def test_a_letter_separated_from_its_word_is_rejoined():
    assert docs._repair_pdf_spacing("B ackend Engineer") == "Backend Engineer"


def test_ordinary_prose_is_left_alone():
    text = "Led a team of five engineers across two products"
    assert docs._repair_pdf_spacing(text) == text


def test_repair_handles_empty_input():
    assert docs._repair_pdf_spacing("") == ""


# ------------------------------------------------------------------ selectors


@pytest.fixture()
def selector_config():
    return {
        "platforms": {
            "greenhouse": {
                "detect": ["boards.greenhouse.io"],
                "fields": [
                    {"selector": "#first_name", "type": "first_name"},
                    {"selector": "#email", "type": "email"},
                ],
            },
            "lever": {
                "detect": ["jobs.lever.co"],
                "fields": [{"selector": "input[name=name]", "type": "name"}],
            },
        },
        "generic": [
            {"selector": "input[type=email]", "type": "email"},
            {"selector": "input[name=phone]", "type": "phone"},
        ],
    }


def test_a_known_host_is_detected(selector_config):
    assert sel.detect_platform("https://boards.greenhouse.io/acme/jobs/1", selector_config) == "greenhouse"


def test_detection_is_case_insensitive(selector_config):
    assert sel.detect_platform("https://Boards.Greenhouse.IO/acme", selector_config) == "greenhouse"


def test_an_unknown_host_detects_nothing(selector_config):
    assert sel.detect_platform("https://careers.acme.com/apply", selector_config) is None


def test_platform_fields_come_first_and_generic_fills_the_gaps(selector_config):
    fields = sel.get_platform_fields("https://boards.greenhouse.io/acme", selector_config)
    types = [f["type"] for f in fields]
    assert types[:2] == ["first_name", "email"]      # platform-specific, in order
    assert "phone" in types                           # generic gap filled
    assert types.count("email") == 1, "a generic field must not duplicate a platform one"


def test_an_unknown_platform_falls_back_to_generic_only(selector_config):
    fields = sel.get_platform_fields("https://careers.acme.com/apply", selector_config)
    assert [f["type"] for f in fields] == ["email", "phone"]


def test_the_bundled_selector_pack_is_usable():
    """Ships with the app — a malformed pack breaks every auto-fill."""
    config = sel.get_selectors()
    assert isinstance(config.get("platforms"), dict) and config["platforms"]
    assert isinstance(config.get("generic"), list)
    for platform, cfg in config["platforms"].items():
        assert cfg.get("detect"), f"{platform} has no detect patterns"
        for field in cfg.get("fields", []):
            assert field.get("selector") and field.get("type"), f"{platform} has a malformed field"
