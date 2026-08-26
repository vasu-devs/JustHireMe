"""Unit tests for generation/contact_lookup.py.

This module reaches two paid third-party APIs (Hunter.io, Proxycurl) and was
entirely untested. Every test here stubs ``_json_get``, so the suite never makes
a network call and never needs a key.
"""

import pytest

from generation import contact_lookup as cl


# --------------------------------------------------------------------------- domain


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://careers.acme.com/jobs/17", "acme.com"),
        ("https://www.acme.co.uk/careers", "co.uk"),  # documented limitation: no PSL
        ("acme.com", "acme.com"),                      # scheme-less input
        ("https://user@acme.com:8443/x", "acme.com"),  # userinfo + port stripped
        ("https://boards.greenhouse.io/acme/jobs/1", ""),   # ATS host -> no domain
        ("https://www.linkedin.com/jobs/view/1", ""),       # www stripped, then matched
        ("", ""),
        ("not a url", ""),
    ],
)
def test_domain_from_url(url, expected):
    assert cl._domain_from_url(url) == expected


def test_infer_company_domain_prefers_explicit_override():
    lead = {"url": "https://careers.acme.com/1", "source_meta": {"website": "meta.com"}}
    assert cl._infer_company_domain(lead, {"contact_lookup_domain": "override.com"}) == "override.com"


def test_infer_company_domain_falls_back_meta_then_url():
    lead = {"url": "https://careers.acme.com/1", "source_meta": {"company_domain": "meta.com"}}
    assert cl._infer_company_domain(lead, {}) == "meta.com"
    assert cl._infer_company_domain({"url": "https://careers.acme.com/1"}, {}) == "acme.com"


def test_infer_company_domain_ignores_non_dict_source_meta():
    assert cl._infer_company_domain({"url": "https://acme.com/1", "source_meta": "junk"}, {}) == "acme.com"


# --------------------------------------------------------------------------- contacts


def test_clean_contact_maps_hunter_field_names():
    contact = cl._clean_contact({
        "first_name": "Ada", "last_name": "Lovelace",
        "position": "CTO", "value": "ada@acme.com", "confidence": 91,
    })
    assert contact["name"] == "Ada Lovelace"
    assert contact["first_name"] == "Ada"
    assert contact["title"] == "CTO"
    assert contact["email"] == "ada@acme.com"
    assert contact["confidence"] == 91
    assert contact["source"] == "hunter"


def test_clean_contact_derives_first_name_from_a_whole_name():
    contact = cl._clean_contact({"name": "Grace Hopper", "email": "g@acme.com"})
    assert contact["name"] == "Grace Hopper"
    assert contact["first_name"] == "Grace"


def test_clean_contact_survives_an_entirely_empty_record():
    contact = cl._clean_contact({})
    assert contact["name"] == ""
    assert contact["first_name"] == ""


def test_contact_score_ranks_by_seniority_then_confidence():
    founder = cl._contact_score({"title": "Founder", "confidence": 10})
    recruiter = cl._contact_score({"title": "Recruiter", "confidence": 99})
    nobody = cl._contact_score({"title": "Sales Rep", "confidence": 99})
    assert founder > recruiter > nobody


def test_hunter_contacts_sorts_seniority_first_and_caps_at_five(monkeypatch):
    payload = {"data": {"emails": [
        {"first_name": "Sal", "last_name": "Rep", "position": "Sales", "value": "s@a.com", "confidence": 99},
        {"first_name": "Ada", "last_name": "L", "position": "Founder", "value": "a@a.com", "confidence": 50},
        {"first_name": "Rec", "last_name": "R", "position": "Recruiter", "value": "r@a.com", "confidence": 60},
        {"position": "Nobody"},  # no email -> dropped
    ] + [{"first_name": f"X{i}", "position": "Intern", "value": f"x{i}@a.com"} for i in range(6)]}}
    monkeypatch.setattr(cl, "_json_get", lambda *a, **k: payload)

    contacts = cl._hunter_contacts("acme.com", "key")

    assert len(contacts) == 5
    assert contacts[0]["title"] == "Founder"
    assert contacts[1]["title"] == "Recruiter"
    assert all(contact["email"] for contact in contacts)


def test_hunter_contacts_handles_an_empty_payload(monkeypatch):
    monkeypatch.setattr(cl, "_json_get", lambda *a, **k: {})
    assert cl._hunter_contacts("acme.com", "key") == []


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Hiring Manager: Ada Lovelace", "Ada Lovelace"),
        ("Recruiter - Grace Hopper", "Grace Hopper"),
        ("recruiter: Grace Hopper", "Grace Hopper"),
        ("Contact: Alan Turing", "Alan Turing"),
        # The captured name stays case-sensitive so prose is not mistaken for a name.
        ("hiring manager: the whole team", ""),
        ("You will report to Alan Turing on this team", "Alan Turing"),
        ("no names here", ""),
        ("", ""),
    ],
)
def test_extract_manager_name(text, expected):
    assert cl._extract_manager_name(text) == expected


def test_proxycurl_returns_existing_linkedin_without_calling_out(monkeypatch):
    def explode(*a, **k):
        raise AssertionError("must not call Proxycurl when the contact already has a URL")

    monkeypatch.setattr(cl, "_json_get", explode)
    url = cl._proxycurl_linkedin("acme.com", "key", {"linkedin_url": "https://li/in/ada"}, {})
    assert url == "https://li/in/ada"


def test_proxycurl_needs_a_full_name(monkeypatch):
    monkeypatch.setattr(cl, "_json_get", lambda *a, **k: {"url": "nope"})
    assert cl._proxycurl_linkedin("acme.com", "key", {"name": "Ada"}, {}) == ""


def test_proxycurl_resolves_a_name_found_in_the_job_description(monkeypatch):
    monkeypatch.setattr(cl, "_json_get", lambda *a, **k: {"profile_url": "https://li/in/turing"})
    url = cl._proxycurl_linkedin("acme.com", "key", {}, {"description": "You report to Alan Turing."})
    assert url == "https://li/in/turing"


# --------------------------------------------------------------------------- email


def test_skills_line_prefers_the_structured_stack():
    assert cl._skills_line({"tech_stack": ["Python", "FastAPI"]}) == "Python, FastAPI"


def test_skills_line_dedupes_case_insensitively_and_caps_at_four():
    line = cl._skills_line({"tech_stack": ["Python", "python", "AWS", "Docker", "Kafka", "React"]})
    assert line == "Python, AWS, Docker, Kafka"


def test_skills_line_falls_back_to_scanning_the_description():
    line = cl._skills_line({"description": "We use Python and Kubernetes with ci/cd."})
    assert "Python" in line and "Kubernetes" in line
    assert "CI/CD" in line  # normalised to upper case


def test_skills_line_has_a_neutral_fallback_for_non_tech_roles():
    assert cl._skills_line({"description": "Caring for patients on the ward."}) == "the stack and product needs in the role"


def test_personalized_email_uses_contact_company_and_candidate():
    email = cl._personalized_email(
        {"title": "Staff Engineer", "company": "Acme", "tech_stack": ["Python"]},
        {"first_name": "Ada"},
        {},
        {"n": "Grace Hopper"},
    )
    assert "Subject: Quick note on Staff Engineer" in email
    assert "Hi Ada," in email
    assert "Acme is hiring for Staff Engineer" in email
    assert email.rstrip().endswith("Grace Hopper")


def test_personalized_email_degrades_gracefully_with_nothing_known():
    email = cl._personalized_email({}, {}, {}, {})
    assert "Hi there," in email
    assert "your team" in email
    assert "Candidate" in email


# --------------------------------------------------------------------------- run()


BASE_LEAD = {"url": "https://careers.acme.com/jobs/1", "title": "Engineer", "company": "Acme"}


def test_run_is_a_no_op_when_disabled():
    assert cl.run(BASE_LEAD, {"contact_lookup_enabled": "false"})["status"] == "disabled"


def test_run_reports_when_no_domain_can_be_inferred():
    result = cl.run({"url": "https://boards.greenhouse.io/acme/jobs/1"}, {})
    assert result["status"] == "no_domain"
    assert result["contacts"] == []


def test_run_reports_a_missing_hunter_key(monkeypatch):
    monkeypatch.delenv("HUNTER_API_KEY", raising=False)
    result = cl.run(BASE_LEAD, {})
    assert result["status"] == "missing_hunter_key"
    assert result["domain"] == "acme.com"


def test_run_surfaces_a_hunter_failure_instead_of_raising(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("429 rate limited")

    monkeypatch.setattr(cl, "_hunter_contacts", boom)
    result = cl.run(BASE_LEAD, {"hunter_api_key": "k"})
    assert result["status"] == "error"
    assert "429 rate limited" in result["message"]


def test_run_reports_when_hunter_returns_nothing(monkeypatch):
    monkeypatch.setattr(cl, "_hunter_contacts", lambda *a, **k: [])
    assert cl.run(BASE_LEAD, {"hunter_api_key": "k"})["status"] == "not_found"


def test_run_returns_the_primary_contact_with_a_drafted_email(monkeypatch):
    monkeypatch.setattr(cl, "_hunter_contacts", lambda *a, **k: [
        {"name": "Ada Lovelace", "first_name": "Ada", "title": "CTO", "email": "ada@acme.com"},
        {"name": "Bob", "first_name": "Bob", "title": "Recruiter", "email": "bob@acme.com"},
    ])
    result = cl.run(BASE_LEAD, {"hunter_api_key": "k"}, {"n": "Grace Hopper"})

    assert result["status"] == "found"
    assert result["domain"] == "acme.com"
    assert result["primary_contact"]["email"] == "ada@acme.com"
    assert "Hi Ada," in result["primary_contact"]["personalized_email"]
    assert len(result["contacts"]) == 2


def test_run_enriches_the_primary_contact_with_linkedin(monkeypatch):
    monkeypatch.setattr(cl, "_hunter_contacts", lambda *a, **k: [{"name": "Ada L", "first_name": "Ada", "email": "a@acme.com"}])
    monkeypatch.setattr(cl, "_proxycurl_linkedin", lambda *a, **k: "https://li/in/ada")
    result = cl.run(BASE_LEAD, {"hunter_api_key": "k", "proxycurl_api_key": "p"})
    assert result["primary_contact"]["linkedin_url"] == "https://li/in/ada"


def test_run_records_a_proxycurl_failure_without_losing_the_contact(monkeypatch):
    """A dead enrichment API must not throw away a good Hunter result."""
    monkeypatch.setattr(cl, "_hunter_contacts", lambda *a, **k: [{"name": "Ada L", "first_name": "Ada", "email": "a@acme.com"}])

    def boom(*a, **k):
        raise RuntimeError("proxycurl down")

    monkeypatch.setattr(cl, "_proxycurl_linkedin", boom)
    result = cl.run(BASE_LEAD, {"hunter_api_key": "k", "proxycurl_api_key": "p"})

    assert result["status"] == "found"
    assert result["primary_contact"]["email"] == "a@acme.com"
    assert "proxycurl down" in result["primary_contact"]["linkedin_error"]
