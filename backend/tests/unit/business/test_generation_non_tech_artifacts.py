"""All FIVE generation artifacts must work for NON-tech candidates.

JustHireMe tailors application packages for any field, not just software. These
tests lock that promise for the generation layer: an ICU nurse (and a welder/chef
variant) must get a real resume PDF, a real cover-letter PDF, and three usable
outreach messages (founder_message, linkedin_note, cold_email) — both when the
LLM is unavailable (deterministic fallback) and when it returns a structured
package.

Key seams exercised:
- ``generation.generator.run_package(lead, template="")`` -> dict with keys
  resume / cover_letter / founder_message / linkedin_note / cold_email plus
  selected_projects / keyword_coverage.
- The LLM draft seam is ``_draft_package``. Forcing it to raise RuntimeError
  drives the deterministic ``_fallback_package`` + ``_fallback_outreach`` path
  (the package never silently ships empty docs).

These tests must not hit the real DB or a real LLM: we pass a stub repo via the
``repo=`` parameter, mock ``get_profile`` / ``assert_llm_configured``, and
redirect the PDF asset dir to a tmp folder.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock

import pytest

import generation.generator as generator

pytestmark = pytest.mark.integration


@pytest.fixture
def assets_dir():
    """A self-managed system-temp dir for rendered PDFs.

    Deliberately NOT pytest's ``tmp_path``: this suite redirects pytest's
    basetemp to a shared ``.pytest-basetemp`` under the repo, which is known to
    race/clean unpredictably across the full run and produced intermittent
    'PDF FileNotFound' flakes. A dedicated mkdtemp under the OS temp root is
    isolated from that redirect and cleaned up here.
    """
    path = tempfile.mkdtemp(prefix="jhm-gen-nontech-")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# A non-tech profile: an ICU nurse with an accented name (unicode must render
# without crashing the PDF layer). NOTE the skills carry NO software terms.
_NURSE_PROFILE = {
    "n": "Zoë Achieng",  # accented + non-ASCII char on purpose
    "s": "Registered Nurse with 7 years in acute and intensive care.",
    "skills": [
        {"n": "IV Therapy", "cat": "clinical"},
        {"n": "ACLS", "cat": "clinical"},
        {"n": "Patient Assessment", "cat": "clinical"},
        {"n": "Wound Care", "cat": "clinical"},
        {"n": "Medication Administration", "cat": "clinical"},
    ],
    "projects": [
        {
            "title": "ICU Rapid-Response Protocol",
            "stack": ["ACLS", "Patient Assessment"],
            "impact": "Cut code-blue response time through structured triage and IV therapy readiness.",
        }
    ],
    "exp": [
        {
            "role": "Registered Nurse",
            "co": "Kenyatta National Hospital",
            "period": "Jan 2019 - Present",
            "d": "Delivered ICU patient care, IV therapy, wound care, and medication administration.",
        }
    ],
    "certifications": [{"title": "ACLS Certification - AHA Jan 2022"}],
    "education": [],
    "achievements": [],
}

# A non-US lead (Nairobi) for a non-tech role.
_NURSE_LEAD = {
    "job_id": "nontech-nurse-001",
    "title": "ICU Registered Nurse",
    "company": "Nairobi General Hospital",
    "url": "https://example.test/jobs/icu-nurse",
    "description": (
        "Nairobi General Hospital seeks an experienced ICU Registered Nurse for "
        "patient assessment, IV therapy, wound care, and medication administration. "
        "ACLS certification required. 4+ years of acute care experience preferred."
    ),
    "match_points": ["ICU patient assessment match", "IV Therapy and ACLS match"],
}

# A second non-tech variant (welder) — proves the field-agnostic behavior is not
# nurse-specific.
_WELDER_PROFILE = {
    "n": "Mateo Álvarez",
    "s": "Certified structural welder with offshore fabrication experience.",
    "skills": [
        {"n": "MIG Welding", "cat": "trade"},
        {"n": "TIG Welding", "cat": "trade"},
        {"n": "Blueprint Reading", "cat": "trade"},
        {"n": "Structural Fabrication", "cat": "trade"},
    ],
    "projects": [
        {
            "title": "Offshore Rig Weld Repair",
            "stack": ["MIG Welding", "TIG Welding"],
            "impact": "Completed pressure-vessel weld repairs passing radiographic inspection.",
        }
    ],
    "exp": [
        {
            "role": "Structural Welder",
            "co": "Doha Fabrication Yard",
            "period": "Mar 2017 - Present",
            "d": "MIG and TIG welding of structural assemblies from blueprints.",
        }
    ],
    "certifications": [],
    "education": [],
    "achievements": [],
}
_WELDER_LEAD = {
    "job_id": "nontech-welder-001",
    "title": "Structural Welder",
    "company": "Doha Steelworks",
    "url": "https://example.test/jobs/welder",
    "description": (
        "Doha Steelworks is hiring a Structural Welder for MIG and TIG welding of "
        "structural assemblies. Must read blueprints and pass radiographic weld "
        "inspection. Full-time, on-site position."
    ),
    "match_points": ["MIG/TIG welding match", "Blueprint reading match"],
}

# Software-stack tokens that must NOT leak into a non-tech candidate's outreach.
_TECH_LEAK_TERMS = ("Python", "React", "FastAPI", "LangGraph", "Docker", "PostgreSQL")


class _StubLeadsRepo:
    """Minimal repo.leads stub so run_package never touches a real DB."""

    def get_resume_version(self, _job_id: str) -> int:
        return 0

    def save_generated_asset_version(self, *_args, **_kwargs) -> None:
        return None


class _StubRepo:
    def __init__(self) -> None:
        self.leads = _StubLeadsRepo()


def _assert_pdf(path: str, suffix: str) -> None:
    assert path.endswith(suffix), f"expected path ending {suffix!r}, got {path!r}"
    p = Path(path)
    assert p.exists(), f"PDF not written to disk: {path}"
    assert p.stat().st_size > 0, f"PDF is empty: {path}"
    # A real PDF starts with the %PDF magic header.
    assert p.read_bytes()[:4] == b"%PDF", f"not a PDF file: {path}"


def _assert_outreach_trio(package: dict) -> None:
    for key in ("founder_message", "linkedin_note", "cold_email"):
        value = package[key]
        assert isinstance(value, str), f"{key} is not a str: {value!r}"
        assert value.strip(), f"{key} is empty"
    # The founder message is meant to be punchy (<= ~300 chars).
    assert len(package["founder_message"]) <= 300, (
        f"founder_message too long ({len(package['founder_message'])} chars)"
    )


def _run_no_llm(lead: dict, profile: dict, assets_dir: str) -> dict:
    """Run run_package forcing the deterministic (no-LLM) fallback path."""
    previous_assets = generator._assets
    generator._assets = assets_dir
    try:
        with (
            mock.patch.object(generator, "get_profile", return_value=profile),
            # assert_llm_configured is imported lazily inside run_package, so patch
            # it at its source module rather than on the generator module.
            mock.patch("llm.client.assert_llm_configured", return_value=None),
            mock.patch.object(
                generator,
                "_draft_package",
                side_effect=RuntimeError("offline"),
            ),
        ):
            return generator.run_package(lead, repo=_StubRepo())
    finally:
        generator._assets = previous_assets


def test_nurse_all_five_artifacts_without_llm(assets_dir):
    package = _run_no_llm(_NURSE_LEAD, _NURSE_PROFILE, assets_dir)

    # Two real, non-empty PDFs on disk.
    _assert_pdf(package["resume"], "_v1.pdf")
    _assert_pdf(package["cover_letter"], "_cl_v1.pdf")

    # All three outreach messages present and the founder note is short.
    _assert_outreach_trio(package)

    # No tech-default leakage: the candidate has none of these skills, so the
    # outreach must not name a software stack.
    outreach_blob = " ".join(
        [package["founder_message"], package["linkedin_note"], package["cold_email"]]
    )
    for term in _TECH_LEAK_TERMS:
        assert term not in outreach_blob, f"tech term {term!r} leaked into non-tech outreach"

    # Field-appropriateness (CONSERVATIVE): at least one nursing signal — a real
    # skill or the role word — must surface across the outreach. The deterministic
    # outreach front-loads the candidate's own top skills, so this is robust.
    lower_blob = outreach_blob.lower()
    assert any(
        signal in lower_blob
        for signal in ("iv therapy", "acls", "patient assessment", "nurse")
    ), f"no nursing signal found in outreach: {outreach_blob!r}"


def test_welder_all_five_artifacts_without_llm(assets_dir):
    package = _run_no_llm(_WELDER_LEAD, _WELDER_PROFILE, assets_dir)

    _assert_pdf(package["resume"], "_v1.pdf")
    _assert_pdf(package["cover_letter"], "_cl_v1.pdf")
    _assert_outreach_trio(package)

    outreach_blob = " ".join(
        [package["founder_message"], package["linkedin_note"], package["cold_email"]]
    )
    for term in _TECH_LEAK_TERMS:
        assert term not in outreach_blob, f"tech term {term!r} leaked into welder outreach"

    lower_blob = outreach_blob.lower()
    assert any(
        signal in lower_blob
        for signal in ("welding", "welder", "mig", "tig", "blueprint", "fabrication")
    ), f"no welding signal found in outreach: {outreach_blob!r}"


def test_nurse_outreach_is_deterministic_and_field_specific():
    """The no-LLM outreach trio itself (independent of PDF rendering) must be
    non-empty, short where required, and built from the candidate's real skills.
    Exercising _fallback_outreach directly keeps this assertion tight and fast."""
    from generation.generators.outreach_email import _fallback_outreach

    out = _fallback_outreach(_NURSE_PROFILE, _NURSE_LEAD)

    assert out["founder_message"].strip()
    assert out["linkedin_note"].strip()
    assert out["cold_email"].strip()
    assert len(out["founder_message"]) <= 280  # generator's documented cap

    blob = " ".join(out.values())
    # Real nursing skills are surfaced; the generic "software engineering" default
    # (used only when a profile has zero skills) must NOT appear here.
    assert "IV Therapy" in blob or "ACLS" in blob
    assert "software engineering" not in blob
    for term in _TECH_LEAK_TERMS:
        assert term not in blob


def test_nurse_all_five_artifacts_with_llm(assets_dir):
    """WITH-LLM variant: mock the structured _DocPackage the LLM would return and
    assert all five artifacts populate from it (the LLM resume/cover survive
    normalization and render to PDFs; the LLM outreach trio passes through).

    The structured-output schema (_DocPackage) is straightforward here, so this
    is NOT skipped. If the schema ever becomes fiddly, prefer skipping over a
    brittle test rather than asserting on exact LLM wording.
    """
    from generation.generators.base import _DocPackage

    # A valid, recruiter-ready structured package an LLM could return for the
    # nurse. resume_markdown / cover_letter_markdown must be substantial enough to
    # survive the _is_trivial_doc gate (resume >= 160 alpha-ish chars, cover >=
    # 120) so the fallback does not replace them.
    llm_package = _DocPackage(
        selected_projects=["ICU Rapid-Response Protocol"],
        resume_markdown=(
            "# Zoë Achieng\n\n"
            "## SUMMARY\n"
            "ICU Registered Nurse with 7 years of acute and intensive care experience "
            "delivering patient assessment, IV therapy, and ACLS-driven rapid response.\n\n"
            "## SKILLS\n"
            "**Clinical:** IV Therapy, ACLS, Patient Assessment, Wound Care, Medication Administration\n\n"
            "## EXPERIENCE\n"
            "### Registered Nurse - Kenyatta National Hospital Jan 2019 - Present\n"
            "- Delivered ICU patient care including IV therapy and wound care.\n"
            "- Performed structured patient assessment and medication administration.\n\n"
            "## CERTIFICATES\n"
            "- ACLS Certification - AHA Jan 2022\n"
        ),
        cover_letter_markdown=(
            "Dear Nairobi General Hospital team,\n\n"
            "I am applying for the ICU Registered Nurse position. My seven years of "
            "intensive-care experience in patient assessment, IV therapy, wound care, "
            "and ACLS-driven rapid response map directly to your unit's needs.\n\n"
            "I would welcome the chance to discuss how my bedside experience fits your team.\n\n"
            "Sincerely,\nZoë Achieng\n"
        ),
        founder_message=(
            "Your ICU Registered Nurse opening caught my eye.\n"
            "7 years of acute care: IV therapy, ACLS, patient assessment.\n"
            "Happy to share specifics or jump on a quick call."
        ),
        linkedin_note=(
            "Hi! Saw the ICU Registered Nurse opening at Nairobi General Hospital. "
            "My ICU background in IV Therapy and ACLS maps well — would love to connect."
        ),
        cold_email=(
            "Subject: ICU Registered Nurse - acute care background\n\n"
            "Hi Nairobi General Hospital team,\n\n"
            "I came across the ICU Registered Nurse role and it aligns with my seven "
            "years of intensive-care experience in patient assessment and IV therapy. "
            "I would welcome the chance to share specifics.\n\n"
            "Best regards,\nZoë Achieng"
        ),
    )

    previous_assets = generator._assets
    generator._assets = assets_dir
    try:
        with (
            mock.patch.object(generator, "get_profile", return_value=_NURSE_PROFILE),
            mock.patch("llm.client.assert_llm_configured", return_value=None),
            mock.patch.object(generator, "_draft_package", return_value=llm_package),
        ):
            package = generator.run_package(_NURSE_LEAD, repo=_StubRepo())
    finally:
        generator._assets = previous_assets

    _assert_pdf(package["resume"], "_v1.pdf")
    _assert_pdf(package["cover_letter"], "_cl_v1.pdf")
    _assert_outreach_trio(package)

    # The LLM-supplied outreach text survives (founder hook references nursing,
    # not a tech stack).
    blob = " ".join(
        [package["founder_message"], package["linkedin_note"], package["cold_email"]]
    )
    assert "ICU" in blob or "ACLS" in blob or "IV therapy" in blob.lower()
    for term in _TECH_LEAK_TERMS:
        assert term not in blob


def test_unicode_and_long_token_render_without_crash(assets_dir):
    """Rendering must survive an accented name and a very long unbroken token
    (e.g. a pasted URL-like string) without raising."""
    profile = {
        **_NURSE_PROFILE,
        "n": "Zoë-Achieng " + "A" * 120,  # accented + long unbroken token
    }
    # Should not raise; produces real PDFs.
    package = _run_no_llm(_NURSE_LEAD, profile, assets_dir)
    _assert_pdf(package["resume"], "_v1.pdf")
    _assert_pdf(package["cover_letter"], "_cl_v1.pdf")
    # Sanity: the asset dir actually received files.
    assert any(f.endswith(".pdf") for f in os.listdir(assets_dir))
