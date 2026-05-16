"""Unit tests for the Education Matcher module."""
from __future__ import annotations

from education.city_extractor import extract_city, get_city_search_terms
from education.domain_classifier import classify_domain
from education.matcher import EducationMatcher, MatchedProgram, _rank_programs


class TestCityExtractor:
    def test_paris_with_postal(self):
        assert extract_city("Paris (75)") == "PARIS"

    def test_lille_remote(self):
        assert extract_city("Lille · Remote") == "LILLE"

    def test_paris_postal(self):
        assert extract_city("75001 Paris") == "PARIS"

    def test_lyon(self):
        assert extract_city("Lyon, France") == "LYON"

    def test_rennes(self):
        assert extract_city("Rennes") == "RENNES"

    def test_lyon_alias(self):
        terms = get_city_search_terms("LYON")
        assert "VILLEURBANNE" in terms


class TestDomainClassifier:
    def test_dev(self):
        assert "SCIENCES" in (classify_domain("Développeur Fullstack") or "")

    def test_data(self):
        assert "SCIENCES" in (classify_domain("Data Scientist") or "")

    def test_design(self):
        assert "HUMAINES" in (classify_domain("UX Designer") or "")

    def test_no_match(self):
        assert classify_domain("Plumber") is None


class TestRankPrograms:
    def test_basic_ranking(self):
        programs = [
            {"for_intitule": "Informatique", "for_dom": "SCIENCES, TECHNOLOGIES, SANTÉ", "etab_nom": "Univ Test", "etab_ville": "PARIS", "etab_uai": "123", "for_modalite": ["Alternance"]},
            {"for_intitule": "Droit", "for_dom": "DROIT, ECONOMIE, GESTION", "etab_nom": "Univ Law", "etab_ville": "PARIS", "etab_uai": "456", "for_modalite": ["Alternance"]},
        ]
        result = _rank_programs(programs, "developpeur fullstack react node python", classified_domain="SCIENCES, TECHNOLOGIES, SANT")
        assert result is not None
        assert result.program_title == "Informatique"
        assert result.alternance_eligible is True

    def test_no_programs(self):
        assert _rank_programs([], "anything") is None


class TestEducationMatcher:
    def test_match_returns_program_or_none(self):
        matcher = EducationMatcher()
        # This test requires network; we only verify the method signature works
        lead = {
            "title": "Développeur",
            "location": "Paris",
            "description": "Fullstack developer needed",
            "score": 75,
        }
        result = matcher.match(lead, {})
        # Result may be None if API is down, or a MatchedProgram
        if result is not None:
            assert isinstance(result, MatchedProgram)
