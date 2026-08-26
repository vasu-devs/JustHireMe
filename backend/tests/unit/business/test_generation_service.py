import asyncio
from types import SimpleNamespace
from unittest import mock

import pytest

from core.errors import UnprocessableError
from generation.service import GenerationService


def _fake_repo(candidate_profile=None):
    return SimpleNamespace(
        settings=SimpleNamespace(get_settings=lambda: {"contact_lookup_enabled": "true"}),
        profile=SimpleNamespace(get_profile=lambda: {"n": "Candidate"}),
        opportunities=SimpleNamespace(get_candidate_application_profile=lambda _candidate_id: candidate_profile or {}),
    )


def test_generation_service_generates_package():
    service = GenerationService(repo=_fake_repo())
    expected = {"resume": "resume.pdf", "cover_letter": "cover.pdf"}

    with mock.patch("generation.service.run_package", return_value=expected) as run_package:
        result = asyncio.run(service.generate_package({"title": "Role"}, "template"))

    assert result == expected
    run_package.assert_called_once_with({"title": "Role"}, "template", service.repo, {"n": "Candidate"})


def test_generation_service_looks_up_contacts():
    service = GenerationService(repo=_fake_repo())
    expected = {"contacts": [{"email": "a@example.com"}]}

    with mock.patch("generation.service.lookup_contacts", return_value=expected) as lookup:
        result = asyncio.run(service.lookup_contact({"company": "Acme"}))

    assert result == expected
    lookup.assert_called_once_with({"company": "Acme"}, {"contact_lookup_enabled": "true"}, {"n": "Candidate"})


def test_generation_service_can_generate_with_contacts_disabled():
    service = GenerationService()
    package = {"resume": "resume.pdf"}

    with mock.patch.object(service, "generate_package", return_value=package) as generate, \
         mock.patch.object(service, "lookup_contact") as lookup:
        result = asyncio.run(service.generate_with_contacts({"title": "Role"}, include_contacts=False))

    assert result.package == package
    assert result.contact_lookup is None
    generate.assert_called_once()
    lookup.assert_not_called()


def test_generation_service_keeps_package_when_contact_lookup_fails():
    service = GenerationService()
    package = {"resume": "resume.pdf", "cover_letter": "cover.pdf"}

    with mock.patch.object(service, "generate_package", return_value=package), \
         mock.patch.object(service, "lookup_contact", side_effect=RuntimeError("hunter unavailable")):
        result = asyncio.run(service.generate_with_contacts({"job_id": "job-1", "title": "Role"}))

    assert result.package == package
    assert result.contact_lookup == {"contacts": [], "error": "hunter unavailable"}


def test_candidate_scoped_generation_requires_an_explicit_profile_snapshot():
    service = GenerationService(repo=_fake_repo())
    lead = {"source_meta": {"candidate_id": "friend-1"}}
    with pytest.raises(UnprocessableError, match="friend-1"):
        asyncio.run(service.generate_package(lead))


def test_candidate_scoped_generation_uses_the_candidate_snapshot_not_global_profile():
    snapshot = {"n": "Friend One", "s": "Backend engineer", "skills": [{"n": "Python"}]}
    service = GenerationService(repo=_fake_repo(snapshot))
    lead = {"title": "Role", "source_meta": {"candidate_id": "friend-1"}}
    expected = {"resume": "friend-1.pdf"}
    with mock.patch("generation.service.run_package", return_value=expected) as run_package:
        result = asyncio.run(service.generate_package(lead))
    assert result == expected
    run_package.assert_called_once_with(lead, "", service.repo, snapshot)
