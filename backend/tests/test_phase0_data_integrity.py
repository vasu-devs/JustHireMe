"""Phase 0 (CGFE prerequisite) source-integrity fixes.

These guard the data-hygiene fixes that must land before the field-agnostic scoring
engine, because a perfect formula on corrupted inputs is still wrong:

- M1: C / C++ / C# must survive normalization as three distinct skills.
- M2: legitimate single-word non-tech skills must not be dropped as "not in the tech
      taxonomy"; generic filler still is.
- M3: a skill the candidate explicitly moved OFF ("migrated away from Angular") must not
      be credited as usage evidence.
"""

from __future__ import annotations

from profile.normalization import (
    normalize_skills,
    scan_skills_in_text,
    _skill_dedupe_key,
    _valid_skill,
)


def _names(items) -> list[str]:
    return [s["name"] for s in items]


class TestM1CPlusPlusCSharp:
    def test_c_variants_stay_distinct(self):
        out = _names(normalize_skills(["C", "C++", "C#"]))
        assert "C" in out and "C++" in out and "C#" in out
        assert len(out) == 3

    def test_dedupe_key_separates_c_family(self):
        keys = {_skill_dedupe_key(x) for x in ("C", "C++", "C#")}
        assert len(keys) == 3

    def test_nodejs_variants_still_dedupe(self):
        # Dots are still stripped, so the two spellings collapse to one skill.
        assert _skill_dedupe_key("node.js") == _skill_dedupe_key("nodejs")

    def test_real_duplicate_skill_still_deduped(self):
        out = _names(normalize_skills(["Python", "python", "PYTHON"]))
        assert out.count("Python") + out.count("python") + out.count("PYTHON") == 1


class TestM2NonTechSkills:
    def test_lowercase_non_tech_skills_survive(self):
        for skill in ("phlebotomy", "welding", "figma", "conveyancing", "carpentry"):
            assert _valid_skill(skill), f"{skill!r} should be a valid skill"

    def test_non_tech_skills_normalize_through(self):
        out = {n.lower() for n in _names(normalize_skills(["phlebotomy", "IV therapy", "welding", "figma"]))}
        # figma canonicalizes to "Figma"; the non-tech words pass through as-is.
        assert {"phlebotomy", "welding", "figma"} <= out

    def test_generic_filler_still_rejected(self):
        for junk in ("and", "the", "with", "experience", "responsibilities", "years"):
            assert not _valid_skill(junk), f"{junk!r} should be rejected as filler"

    def test_too_short_lowercase_rejected(self):
        assert not _valid_skill("an")


class TestM3MentionNotUsage:
    def test_migrated_away_from_is_not_credited(self):
        # Both React and Django are SKILL_CANONICAL aliases; React follows the
        # negation cue and must be suppressed, Django is a genuine usage.
        found = scan_skills_in_text("We migrated away from React and rebuilt everything using Django")
        assert "Django" in found
        assert "React" not in found

    def test_deprecated_skill_suppressed(self):
        found = scan_skills_in_text("Deprecated Flask in favour of FastAPI for the new services")
        assert "FastAPI" in found
        assert "Flask" not in found

    def test_plain_usage_still_credited(self):
        found = scan_skills_in_text("Built the backend in Python with FastAPI and Redis for caching")
        assert {"Python", "FastAPI", "Redis"} <= found

    def test_skill_used_and_negated_elsewhere_is_kept(self):
        # One clean usage is enough even if another mention is negated.
        text = "Moved away from Redis for caching, then reintroduced Redis for the job queue"
        assert "Redis" in scan_skills_in_text(text)
