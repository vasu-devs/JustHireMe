"""Resume visual style presets (#90): preset resolution + rendered output.

The presets change accent color, base font, and name alignment in the resume
PDF. We pin: every declared preset is complete, resolution falls back to
classic on unknown/legacy values, and each preset renders a real PDF.
"""

from __future__ import annotations

import os

import pytest

from generation import pdf_renderer as pr


REQUIRED_KEYS = {"label", "accent", "font", "name_align"}


def test_presets_are_complete_and_distinct():
    assert set(pr.STYLE_PRESETS) == {"classic", "harvard", "modern"}
    for name, preset in pr.STYLE_PRESETS.items():
        assert set(preset) >= REQUIRED_KEYS, name
        assert preset["font"] in {"Helvetica", "Times", "Courier"}  # fpdf core faces
        assert preset["name_align"] in {"L", "C", "R"}
    accents = {p["accent"] for p in pr.STYLE_PRESETS.values()}
    assert len(accents) == 3  # visually distinct, not aliases


@pytest.mark.parametrize("chosen,expected_font", [
    ("classic", "Helvetica"),
    ("harvard", "Times"),
    ("modern", "Helvetica"),
    ("no-such-preset", "Helvetica"),  # unknown → classic fallback
])
def test_resolve_reads_setting_with_fallback(monkeypatch, chosen, expected_font):
    import data.sqlite.settings as settings_mod
    monkeypatch.setattr(settings_mod, "get_setting", lambda key, default="": chosen)
    preset = pr._resolve_style_preset()
    assert preset["font"] == expected_font


@pytest.mark.parametrize("chosen", ["classic", "harvard", "modern"])
def test_each_preset_renders_a_pdf(monkeypatch, tmp_path, chosen):
    import data.sqlite.settings as settings_mod
    monkeypatch.setattr(settings_mod, "get_setting", lambda key, default="": chosen)
    md = (
        "# Jordan Ellis\n"
        "jordan@example.com | Rotterdam, NL\n\n"
        "## Experience\n"
        "**Senior Nurse** - Halcyon Health (May 2020 - Aug 2022)\n"
        "- Led a 12-bed ICU night team\n\n"
        "## Skills\n"
        "- Critical care, triage, mentoring\n"
    )
    out = pr._render_resume_template(md, str(tmp_path / f"resume-{chosen}.pdf"))
    assert os.path.exists(out)
    assert os.path.getsize(out) > 500  # a real PDF, not an empty stub
