"""Keyless ATS source adapters: parsing + dispatch (network mocked).

Covers the direct public-API adapters (greenhouse/lever/ashby/workable and the
newly added smartrecruiters/recruitee/personio). Network is mocked at the
``json_get`` / ``xml_get`` boundary, so these assert the normalization + routing
logic that ships, without hitting live boards. Proves a keyless source returns
non-empty, normalized, field-agnostic leads.
"""

from __future__ import annotations

import asyncio
import html
import json

import httpx
import pytest

from discovery.sources import ats
from opportunities.canonicalize import source_record_from_lead
from opportunities.models import SourceKind


def _run(coro):
    return asyncio.run(coro)


def _patch_json(monkeypatch, payload):
    async def fake_json_get(url, params=None):
        return payload

    monkeypatch.setattr(ats, "json_get", fake_json_get)


def test_zoho_recruit_parses_public_embedded_jobs_and_excludes_unpublished(monkeypatch):
    rows = [
        {
            "id": "802052000002830025",
            "Posting_Title": "DevOps Intern",
            "Job_Description": "<p>Build CI/CD systems with AWS.</p>",
            "City": "Hyderabad",
            "State": "Telangana",
            "Country": "India",
            "Remote_Job": False,
            "Job_Type": "Intern",
            "Industry": "Software Product",
            "Salary": "INR 20,000 monthly",
            "Work_Experience": "Fresher",
            "Date_Opened": "2026-06-16",
            "Is_Locked": False,
            "Keep_on_Career_Site": False,
            "Publish": True,
        },
        {"id": "closed", "Posting_Title": "Old Intern", "Publish": False},
    ]
    page = (
        "<html><head><title>Careers | mavQ</title></head><body>"
        f'<input type="hidden" value="{html.escape(json.dumps(rows), quote=True)}">'
        "</body></html>"
    )
    detail_payload = json.dumps([rows[0]], ensure_ascii=True)
    detail_encoded = detail_payload.replace("\\", "\\\\").replace('"', r"\x22")
    detail_page = (
        "<html><body><h1>DevOps Intern</h1><a>Apply Now</a>"
        f"<script>var jobs = JSON.parse('{detail_encoded}');</script>"
        "</body></html>"
    )

    async def fake_text_get(url, params=None, *, request_headers=None):
        assert url.startswith("https://mavq.zohorecruit.com/jobs/Careers")
        return page if url.endswith("/Careers") else detail_page

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    leads = _run(ats.scrape_zoho_recruit("mavq"))

    assert len(leads) == 1
    lead = leads[0]
    assert lead["title"] == "DevOps Intern"
    assert lead["company"] == "mavQ"
    assert lead["url"] == "https://mavq.zohorecruit.com/jobs/Careers/802052000002830025"
    assert lead["platform"] == "zohorecruit"
    assert lead["description"] == (
        "Build CI/CD systems with AWS.\n"
        "Employment type: Intern\n"
        "Experience: Fresher\n"
        "Salary: INR 20,000 monthly\n"
        "Workplace: onsite"
    )
    assert lead["posted_date"] == "2026-06-16"
    assert lead["location"] == "Hyderabad, Telangana, India"
    assert lead["workplace"] == "onsite"
    assert lead["active_hint"] == "active"
    assert lead["kind"] == "job"
    expected_meta = {
        "ats": "zohorecruit",
        "slug": "mavq",
        "tld": "com",
        "job_id": "802052000002830025",
        "job_type": "Intern",
        "industry": "Software Product",
        "salary": "INR 20,000 monthly",
        "work_experience": "Fresher",
        "city": "Hyderabad",
        "state": "Telangana",
        "country": "India",
        "remote_job": False,
        "workplace_type": "onsite",
        "date_opened": "2026-06-16",
        "publish": True,
        "is_locked": False,
        "keep_on_career_site": False,
        "board_url": "https://mavq.zohorecruit.com/jobs/Careers",
        "public_detail_verified": True,
    }
    assert expected_meta.items() <= lead["source_meta"].items()


def test_zoho_recruit_rejects_collection_ghost_without_live_detail_handoff(monkeypatch):
    row = {
        "id": "stale-123",
        "Posting_Title": "Software Engineer Intern",
        "Job_Description": "Build production APIs.",
        "Country": "India",
        "Publish": True,
    }
    board = (
        "<html><head><title>Careers | Example</title></head><body>"
        f'<input type="hidden" value="{html.escape(json.dumps([row]), quote=True)}">'
        "</body></html>"
    )

    async def fake_text_get(url, params=None, *, request_headers=None):
        if url.endswith("/Careers"):
            return board
        return "<html><body><h1>Current opportunities</h1></body></html>"

    monkeypatch.setattr(ats, "text_get", fake_text_get)

    assert _run(ats.scrape_zoho_recruit("example")) == []


def test_lever_preserves_full_salary_description_workplace_and_apply_fields(monkeypatch):
    _patch_json(monkeypatch, [{
        "id": "job-123",
        "text": "Software Engineer Intern",
        "createdAt": 1_767_225_600_000,
        "descriptionBodyPlain": "This role is for one of our clients.",
        "salaryDescriptionPlain": (
            "Responsibilities: Build Python APIs. Stipend: INR 30,000 per month."
        ),
        "lists": [{"content": "<li>Ship production software</li>"}],
        "categories": {
            "commitment": "Full-time",
            "department": "Engineering",
            "location": "Bengaluru",
            "allLocations": ["Bengaluru"],
        },
        "country": "IN",
        "workplaceType": "remote",
        "salaryRange": {
            "min": 300000,
            "max": 600000,
            "currency": "INR",
            "interval": "per-year-salary",
        },
        "hostedUrl": "https://jobs.lever.co/acme/job-123",
        "applyUrl": "https://jobs.lever.co/acme/job-123/apply",
    }])

    lead = _run(ats.scrape_lever("acme"))[0]

    assert "Build Python APIs" in lead["description"]
    assert "Ship production software" in lead["description"]
    assert "Salary: INR 300000 - 600000 per year" in lead["description"]
    assert lead["location"] == "Bengaluru"
    assert lead["workplace"] == "remote"
    expected_meta = {
        "ats": "lever",
        "slug": "acme",
        "job_id": "job-123",
        "country": "IN",
        "location": "Bengaluru",
        "workplace_type": "remote",
        "commitment": "Full-time",
        "department": "Engineering",
        "all_locations": ["Bengaluru"],
        "apply_url": "https://jobs.lever.co/acme/job-123/apply",
        "hosted_url": "https://jobs.lever.co/acme/job-123",
        "salary_minimum": 300000,
        "salary_maximum": 600000,
        "salary_currency": "INR",
        "salary_interval": "per-year-salary",
    }
    for key, value in expected_meta.items():
        assert lead["source_meta"][key] == value


def test_zoho_recruit_dispatch_and_direct_url(monkeypatch):
    calls = []

    async def fake(slug, tld="com"):
        calls.append((slug, tld))
        return []

    monkeypatch.setattr(ats, "scrape_zoho_recruit", fake)
    _run(ats.scrape_target("ats:zohorecruit:fireblazeaischool:in"))
    _run(ats.scrape_direct_ats_url(
        "https://synoriq.zohorecruit.com/jobs/Careers/123"
    ))

    assert calls == [("fireblazeaischool", "in"), ("synoriq", "com")]
    assert ats.is_ats_target("https://mavq.zohorecruit.com/jobs/Careers")


def test_zoho_recruit_detail_payload_recovers_full_public_fields():
    payload = json.dumps([{
        "id": "123",
        "Posting_Title": "Flutter Developer Intern",
        "Job_Description": '<div>Build mobile apps and REST APIs.</div>',
        "Salary": "10 - 15 K",
        "Work_Experience": "Fresher",
    }], ensure_ascii=True)
    # Zoho JavaScript hex-escapes JSON quotes before handing it to JSON.parse.
    encoded = payload.replace("\\", "\\\\").replace('"', r"\x22")
    detail = ats._zoho_detail_job(
        f"<script>var jobs = JSON.parse('{encoded}');</script>",
        "123",
    )

    assert detail["Salary"] == "10 - 15 K"
    assert detail["Work_Experience"] == "Fresher"
    assert "REST APIs" in detail["Job_Description"]


def test_freshteam_parses_current_board_and_public_jobposting_jsonld(monkeypatch):
    board = """
    <html><body>
      <a href="/jobs/J_kVTqYfSfUi/software-engineer-intern-remote"
         class="heading" data-portal-title="softwareengineerintern(remote)"
         data-portal-location="Indore, India" data-portal-job-type="3"
         data-portal-remote-location=true>
        <div class="row"><div class="job-list-info">
          <div class="job-title">Software Engineer Intern (Remote)</div>
          <div class="job-desc text">Build production software...</div>
        </div><div class="job-location"><div class="location-info">
          Remote<br/>Internship
        </div></div></div>
      </a>
    </body></html>
    """
    posting = {
        "@context": "http://schema.org/",
        "@type": "JobPosting",
        "url": "https://indianpix-people.freshteam.com/jobs/J_kVTqYfSfUi/Software%20Engineer%20Intern",
        "title": "Software Engineer Intern (Remote)",
        "description": (
            "&lt;p&gt;Build TypeScript applications &amp;amp; APIs.&lt;/p&gt;"
            "&lt;p&gt;Good stipend based on one month's performance.&lt;/p&gt;"
        ),
        "datePosted": "2026-02-28 16:24:41 UTC",
        "employmentType": "INTERN",
        "remote": "true",
        "validThrough": "2026-09-30T23:59:59+00:00",
        "jobLocationType": "TELECOMMUTE",
        "applicantLocationRequirements": [{"@type": "Country", "name": "India"}],
        "baseSalary": {
            "@type": "MonetaryAmount",
            "currency": "INR",
            "value": {"@type": "QuantitativeValue", "value": 25000, "unitText": "MONTH"},
        },
        "directApply": True,
        "skills": "TypeScript, Node.js, React",
        "hiringOrganization": {"@type": "Organization", "name": "IndianPix"},
        "jobLocation": {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressRegion": "Indore",
                "addressLocality": "Madhya Pradesh",
                "postalCode": "452001",
                "addressCountry": "India",
            },
        },
    }
    detail = '<script type="application/ld+json">' + json.dumps(posting) + "</script>"
    calls = []

    async def fake_text_get(url, params=None, *, request_headers=None):
        calls.append(url)
        return board if url.endswith("/jobs") else detail

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    leads = _run(ats.scrape_freshteam("indianpix-people"))

    assert len(leads) == 1
    lead = leads[0]
    assert calls == [
        "https://indianpix-people.freshteam.com/jobs",
        "https://indianpix-people.freshteam.com/jobs/J_kVTqYfSfUi/software-engineer-intern-remote",
    ]
    assert lead["title"] == "Software Engineer Intern (Remote)"
    assert lead["company"] == "IndianPix"
    assert lead["platform"] == "freshteam"
    assert lead["description"] == (
        "Build TypeScript applications & APIs.\n"
        "Good stipend based on one month's performance."
    )
    assert lead["posted_date"] == "2026-02-28T16:24:41+00:00"
    assert lead["deadline"] == "2026-09-30T23:59:59+00:00"
    assert lead["location"] == "Indore, India"
    assert lead["workplace"] == "remote"
    assert lead["active_hint"] == "active"
    assert {
        "ats": "freshteam",
        "slug": "indianpix-people",
        "job_id": "J_kVTqYfSfUi",
        "job_type_id": "3",
        "employment_type": "INTERN",
        "remote_job": True,
        "workplace_type": "remote",
        "board_location": "Indore, India",
        "structured_location": "Madhya Pradesh, Indore, India",
        "date_posted": "2026-02-28T16:24:41+00:00",
        "date_posted_raw": "2026-02-28 16:24:41 UTC",
        "valid_through": "2026-09-30T23:59:59+00:00",
        "job_location_type": "TELECOMMUTE",
        "applicant_location_requirements": [{"@type": "Country", "name": "India"}],
        "base_salary": {
            "@type": "MonetaryAmount",
            "currency": "INR",
            "value": {"@type": "QuantitativeValue", "value": 25000, "unitText": "MONTH"},
        },
        "direct_apply": True,
        "skills": "TypeScript, Node.js, React",
        "address_locality": "Madhya Pradesh",
        "address_region": "Indore",
        "postal_code": "452001",
        "address_country": "India",
        "board_url": "https://indianpix-people.freshteam.com/jobs",
        "jsonld_url": "https://indianpix-people.freshteam.com/jobs/J_kVTqYfSfUi/Software%20Engineer%20Intern",
    }.items() <= lead["source_meta"].items()


def test_freshteam_falls_back_to_card_when_detail_fetch_fails(monkeypatch):
    board = """
      <a href="/jobs/abc/product-engineering-intern" class="heading"
         data-portal-location="New Delhi, India" data-portal-job-type="3"
         data-portal-remote-location=false>
        <div class="job-title">Product Engineering Intern</div>
        <div class="job-desc text">Build Flutter products for small businesses.</div>
        <div class="location-info">New Delhi<br/>Internship</div>
      </a>
    """

    async def fake_text_get(url, params=None, *, request_headers=None):
        if url.endswith("/jobs"):
            return board
        raise RuntimeError("temporary detail failure")

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    lead = _run(ats.scrape_freshteam("restat"))[0]

    assert lead["title"] == "Product Engineering Intern"
    assert lead["company"] == "restat"
    assert lead["description"] == "Build Flutter products for small businesses."
    assert lead["location"] == "New Delhi, India"
    assert lead["active_hint"] == "active"


def test_freshteam_merges_alternate_theme_anchors(monkeypatch):
    board = """
      <li class="heading"><div class="row"><div class="job-list-info">
        <a href="/jobs/abc/full-stack-ai-engineer-remote" class="job-title">
          Full-Stack AI Engineer (Remote)
        </a>
        <a href="/jobs/abc/full-stack-ai-engineer-remote" class="job-desc text">
          Build production AI systems.
        </a>
      </div><div class="job-location">
        <a href="/jobs/abc/full-stack-ai-engineer-remote" class="location-info">
          Remote<br/>Full Time
        </a>
        <a href="/jobs/abc/full-stack-ai-engineer-remote" class="location-icon">→</a>
      </div></div></li>
    """

    async def fake_text_get(url, params=None, *, request_headers=None):
        if url.endswith("/jobs"):
            return board
        return "<html></html>"

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    leads = _run(ats.scrape_freshteam("cesltd"))

    assert len(leads) == 1
    assert leads[0]["title"] == "Full-Stack AI Engineer (Remote)"
    assert leads[0]["description"] == "Build production AI systems."
    assert leads[0]["location"] == "Remote"
    assert leads[0]["source_meta"]["employment_type"] == "Full Time"
    assert leads[0]["source_meta"]["remote_job"] is True


def test_freshteam_dispatch_and_direct_url(monkeypatch):
    calls = []

    async def fake(slug):
        calls.append(slug)
        return []

    monkeypatch.setattr(ats, "scrape_freshteam", fake)
    _run(ats.scrape_target("ats:freshteam:creditsaisonin-talent"))
    _run(ats.scrape_direct_ats_url(
        "https://codvo-team.freshteam.com/jobs/abc/system-engineer-intern"
    ))

    assert calls == ["creditsaisonin-talent", "codvo-team"]
    assert ats.is_ats_target("https://restat.freshteam.com/jobs")


def test_keka_parses_current_rich_public_job_feed(monkeypatch):
    tenant_id = "1f7a7e3f-2b83-448c-a9f3-368f72583618"

    async def fake_text_get(url, params=None, *, request_headers=None):
        assert url == "https://comprinno.keka.com/careers"
        return (
            "<script>fetch('/ats/documents/"
            f"{tenant_id}/careerportal/public.html')</script>"
        )

    async def fake_json_get(url, params=None):
        if url.endswith("/api/organization/default/careerportalinfo"):
            return {
                "name": "Comprinno Technologies Pvt.Ltd",
                "companyWebsite": "https://www.comprinno.net/",
            }
        assert url.endswith(f"/api/embedjobs/default/active/{tenant_id}")
        return [
            {
                "id": 134653,
                "title": "Data Science Intern",
                "description": "<p>Build production GenAI and ML systems.</p>",
                "excerpt": "ignored fallback",
                "departmentIdentifier": "data-ai",
                "departmentName": "Data & Artificial Intelligence",
                "jobLocations": [
                    {
                        "id": 39851,
                        "name": "SBC Office",
                        "city": "Pune",
                        "state": "MH",
                        "countryCode": "IN",
                        "countryName": "India",
                    }
                ],
                "jobType": 2,
                "experience": "0 - 1 year",
                "salaryRange": {
                    "minimum": 14999.0,
                    "maximum": 15000.0,
                    "currency": "INR",
                    "salaryPeriod": 3,
                    "cultureInfo": "en-IN",
                },
                "salaryRangeFormat": "INR 14,999.00 - 15,000.00",
                "publishedOn": "2026-05-08T13:14:30.773Z",
                "publishedSinceDays": 109,
                "skillNames": ["Python", "Machine Learning"],
                # Even if the upstream payload later grows candidate fields,
                # the adapter keeps an allow-list of public job facts.
                "candidateEmail": "must-not-be-retained@example.com",
            },
            {"id": "", "title": "Malformed"},
        ]

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    monkeypatch.setattr(ats, "json_get", fake_json_get)
    leads = _run(ats.scrape_keka("comprinno"))

    assert len(leads) == 1
    lead = leads[0]
    assert lead["title"] == "Data Science Intern"
    assert lead["company"] == "Comprinno Technologies Pvt.Ltd"
    assert lead["url"] == "https://comprinno.keka.com/careers/jobdetails/134653"
    assert lead["apply_url"] == lead["url"]
    assert lead["platform"] == "keka"
    assert lead["posted_date"] == "2026-05-08T13:14:30.773Z"
    assert lead["location"] == "Pune, MH, India"
    assert lead["workplace"] == "onsite"
    assert lead["active_hint"] == "active"
    assert "Salary: INR 14,999.00 - 15,000.00" in lead["description"]
    assert "Skills: Python, Machine Learning" in lead["description"]
    meta = lead["source_meta"]
    assert meta["ats"] == "keka"
    assert meta["tenant_identifier"] == tenant_id
    assert meta["job_id"] == "134653"
    assert meta["employment_type"] == "Full Time"
    assert meta["experience"] == "0 - 1 year"
    assert meta["salary_minimum"] == 14999.0
    assert meta["salary_period_id"] == 3
    assert meta["employer_domain"] == "comprinno.net"
    assert meta["job_locations"] == [{
        "id": 39851,
        "name": "SBC Office",
        "city": "Pune",
        "state": "MH",
        "country_code": "IN",
        "country": "India",
    }]
    assert "candidateEmail" not in meta
    assert "candidate_email" not in meta


def test_keka_mixed_remote_location_and_dispatch(monkeypatch):
    location, structured, workplace = ats._keka_location_facts([
        {
            "id": 1,
            "name": "Remote",
            "city": "Remote",
            "state": "Oregon",
            "countryCode": "US",
            "countryName": "United States",
        },
        {
            "id": 2,
            "name": "Head Office",
            "city": "Bengaluru",
            "state": "KA",
            "countryCode": "IN",
            "countryName": "India",
        },
    ])
    assert location == "Remote, Oregon, United States; Bengaluru, KA, India"
    assert len(structured) == 2
    assert workplace == "remote or onsite"

    calls = []

    async def fake(slug):
        calls.append(slug)
        return []

    monkeypatch.setattr(ats, "scrape_keka", fake)
    _run(ats.scrape_target("ats:keka:comprinno"))
    _run(ats.scrape_direct_ats_url(
        "https://vajrorap.keka.com/careers/jobdetails/138169"
    ))

    assert calls == ["comprinno", "vajrorap"]
    assert ats.is_ats_target("https://solytics.keka.com/careers")


def test_keka_native_2026_portal_without_tenant_identifier(monkeypatch):
    async def fake_text_get(url, params=None, *, request_headers=None):
        assert url == "https://popclub.keka.com/careers"
        return (
            '<base href="/careers/">'
            '<meta name="portalName">'
            '<script src="https://cdn.keka.com/careers/v/2026/scripts/app/app.min.js"></script>'
        )

    async def fake_json_get(url, params=None):
        if url.endswith("/api/organization/default/careerportalinfo"):
            return {"name": "Poptech Growth Private Limited"}
        assert url == "https://popclub.keka.com/careers/api/jobs/default/active"
        return [{
            "id": 62366,
            "title": "Quality Assurance (QA) Intern – Software Testing",
            "description": "<p>Test web and API software using Java and Python.</p>",
            "departmentName": "Engineering",
            "jobLocations": [{
                "id": 1,
                "name": "Head Office",
                "city": "Bengaluru",
                "state": "KA",
                "countryCode": "IN",
                "countryName": "India",
            }],
            "jobType": 2,
            "experience": "0-1 Years",
            "publishedOn": "2026-03-13T10:33:06.153Z",
            "publishedSinceDays": 165,
            "salaryRange": {"currency": "INR", "salaryPeriod": 0},
        }]

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    monkeypatch.setattr(ats, "json_get", fake_json_get)
    lead = _run(ats.scrape_keka("popclub"))[0]

    assert lead["company"] == "Poptech Growth Private Limited"
    assert lead["url"] == "https://popclub.keka.com/careers/jobdetails/62366"
    assert lead["source_meta"]["portal_generation"] == "native_2026"
    assert "tenant_identifier" not in lead["source_meta"]


def test_keka_uses_bounded_prose_location_when_structured_location_is_absent(monkeypatch):
    async def fake_text_get(url, params=None, *, request_headers=None):
        return '<script src="https://cdn.keka.com/careers/v/2026/scripts/app/app.min.js"></script>'

    async def fake_json_get(url, params=None):
        if url.endswith("/api/organization/default/careerportalinfo"):
            return {"name": "POP"}
        return [{
            "id": 63846,
            "title": "Data Analyst / DA-1",
            "description": (
                "Job Title: Data Analyst. Experience: 0-2 years. "
                "Location: Bengaluru Type: Full-Time About POP: Build dashboards."
            ),
            "jobLocations": [],
            "jobType": 2,
            "experience": "0-2 years",
            "publishedOn": "2026-04-21T06:42:31.337Z",
        }]

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    monkeypatch.setattr(ats, "json_get", fake_json_get)
    lead = _run(ats.scrape_keka("popclub"))[0]

    assert lead["location"] == "Bengaluru"
    assert lead["workplace"] == "onsite"
    assert lead["source_meta"]["description_location"] == "Bengaluru"


def test_keka_description_location_stops_before_department(monkeypatch):
    async def fake_text_get(url, params=None, *, request_headers=None):
        return '<script src="https://cdn.keka.com/careers/v/2026/scripts/app/app.min.js"></script>'

    async def fake_json_get(url, params=None):
        if url.endswith("/api/organization/default/careerportalinfo"):
            return {"name": "Adit"}
        return [{
            "id": 133505,
            "title": "AI Engineer - Remote",
            "description": (
                "Job Title: AI Engineer Location: 100% Remote "
                "Department: Product Team Employment Type: Full-time"
            ),
            "jobLocations": [],
            "jobType": 2,
            "experience": "3",
            "publishedOn": "2026-08-07T10:35:47.26Z",
        }]

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    monkeypatch.setattr(ats, "json_get", fake_json_get)
    lead = _run(ats.scrape_keka("adit"))[0]

    assert lead["location"] == "100% Remote"
    assert lead["workplace"] == "remote"
    assert lead["source_meta"]["description_location"] == "100% Remote"


# --- Greenhouse -------------------------------------------------------------

def test_greenhouse_prefers_posting_location_over_corporate_office_name(monkeypatch):
    _patch_json(monkeypatch, {"jobs": [{
        "title": "Software Engineer Intern",
        "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1",
        "location": {"name": "Bangalore"},
        "offices": [{"name": "Acme Technologies Private Limited", "location": "Karnataka, India"}],
        "content": "Build Python services.",
    }]})

    lead = _run(ats.scrape_greenhouse("acme"))[0]

    assert lead["location"] == "Bangalore; Karnataka, India"
    assert "Acme Technologies Private Limited" not in lead["location"]


def test_greenhouse_uses_office_names_for_generic_multiple_location_posting(monkeypatch):
    _patch_json(monkeypatch, {"jobs": [{
        "title": "Graduate Software Engineer",
        "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/2",
        "location": {"name": "Multiple Locations"},
        "offices": [{"name": "Bengaluru"}, {"name": "Hyderabad"}],
        "content": "Build reliable systems.",
    }]})

    lead = _run(ats.scrape_greenhouse("acme"))[0]

    assert lead["location"] == "Multiple Locations; Bengaluru; Hyderabad"


# --- Workday ----------------------------------------------------------------

def test_workday_india_cse_discovers_country_facet_filters_and_deduplicates(monkeypatch):
    posts = []
    detail_calls = []

    async def fake_json_post(url, payload):
        posts.append(payload)
        if not payload["searchText"]:
            return {"facets": [{
                "facetParameter": "locationMainGroup",
                "values": [{
                    "facetParameter": "locationHierarchy1",
                    "descriptor": "Locations",
                    "values": [
                        {"descriptor": "India", "id": "india-id", "count": 4},
                        {"descriptor": "United States", "id": "us-id", "count": 30},
                    ],
                }],
            }]}
        return {
            "total": 3,
            "jobPostings": [
                {
                    "title": "Software Engineer Intern",
                    "externalPath": "/job/india/intern-1",
                    "locationsText": "India, Bengaluru",
                    "postedOn": "Posted Today",
                },
                {
                    "title": "Senior Software Engineer",
                    "externalPath": "/job/india/senior-1",
                    "locationsText": "India, Pune",
                },
                {
                    "title": "Software Engineer Intern",
                    "externalPath": "/job/india/intern-1",
                    "locationsText": "India, Bengaluru",
                },
            ],
        }

    async def fake_json_get(url, params=None):
        detail_calls.append(url)
        return {"jobPostingInfo": {
            "id": "internal-posting-id",
            "title": "Software Engineer Intern",
            "jobDescription": "<p>Build Python services.</p>",
            "location": "India, Bengaluru",
            "additionalLocations": ["India, Hyderabad"],
            "postedOn": "Posted Today",
            "startDate": "2026-08-26",
            "timeType": "Full time",
            "jobReqId": "R4042696",
            "jobPostingId": "Software-Engineer-Intern_R4042696",
            "jobPostingSiteId": "External",
            "country": {"descriptor": "India"},
            "jobRequisitionLocation": {
                "country": {"descriptor": "India", "alpha2Code": "IN"},
            },
            "canApply": True,
            "posted": True,
            "externalUrl": "https://acme.wd5.myworkdayjobs.com/External/job/intern_R4042696",
        }}

    monkeypatch.setattr(ats, "json_post", fake_json_post)
    monkeypatch.setattr(ats, "json_get", fake_json_get)

    leads = _run(ats.scrape_workday("acme", "wd5", "External", "india-cse"))

    assert len(leads) == 1
    assert leads[0]["title"] == "Software Engineer Intern"
    assert leads[0]["location"] == "India, Bengaluru; India, Hyderabad"
    assert leads[0]["url"].endswith("/intern_R4042696")
    assert leads[0]["active_hint"] == "active"
    assert leads[0]["source_meta"]["query"] == "india-cse"
    expected_metadata = {
        "ats": "workday",
        "slug": "acme",
        "site": "External",
        "query": "india-cse",
        "id": "R4042696",
        "internal_posting_id": "internal-posting-id",
        "job_posting_id": "Software-Engineer-Intern_R4042696",
        "job_posting_site_id": "External",
        "time_type": "Full time",
        "posted_relative": "Posted Today",
        "start_date": "2026-08-26",
        "additional_locations": ["India, Hyderabad"],
        "country": "India",
        "country_code": "IN",
        "can_apply": True,
        "posted": True,
    }
    assert expected_metadata.items() <= leads[0]["source_meta"].items()
    assert len(detail_calls) == 1
    assert posts[0]["appliedFacets"] == {}
    assert all(
        payload["appliedFacets"] == {"locationHierarchy1": ["india-id"]}
        for payload in posts[1:]
    )


def test_workday_india_cse_returns_empty_when_tenant_has_no_india_facet(monkeypatch):
    async def fake_json_post(url, payload):
        return {"facets": [{
            "facetParameter": "locationHierarchy1",
            "values": [{"descriptor": "Canada", "id": "canada-id", "count": 3}],
        }]}

    monkeypatch.setattr(ats, "json_post", fake_json_post)

    assert _run(ats.scrape_workday("acme", "wd5", "External", "india-cse")) == []


def test_workday_india_cse_enriches_generic_campus_title_before_technical_filter(monkeypatch):
    async def fake_json_post(url, payload):
        if not payload["searchText"]:
            return {
                "facets": [
                    {
                        "facetParameter": "locationCountry",
                        "values": [{"descriptor": "India", "id": "india-id"}],
                    }
                ]
            }
        if payload["searchText"] == "campus":
            return {
                "total": 1,
                "jobPostings": [
                    {
                        "title": "India Campus Program",
                        "externalPath": "/job/india/campus-program",
                        "locationsText": "India, Bengaluru",
                    }
                ],
            }
        return {"total": 0, "jobPostings": []}

    async def fake_json_get(url, params=None):
        return {
            "jobPostingInfo": {
                "jobDescription": "<p>AI/ML, cybersecurity, and database internships.</p>",
                "location": "India, Bengaluru",
            }
        }

    monkeypatch.setattr(ats, "json_post", fake_json_post)
    monkeypatch.setattr(ats, "json_get", fake_json_get)

    leads = _run(ats.scrape_workday("acme", "wd5", "External", "india-cse"))

    assert len(leads) == 1
    assert leads[0]["title"] == "India Campus Program"
    assert "AI/ML" in leads[0]["description"]


def test_workday_india_facet_combines_city_values_when_country_facet_is_absent():
    facets = [{
        "facetParameter": "locationMainGroup",
        "values": [{
            "facetParameter": "locations",
            "values": [
                {"descriptor": "Bangalore, Karnataka, India", "id": "blr"},
                {"descriptor": "Chennai, Tamil Nadu, India", "id": "maa"},
                {"descriptor": "Austin, Texas, United States", "id": "aus"},
            ],
        }],
    }]

    assert ats._workday_india_facet(facets) == ("locations", ["blr", "maa"])


def test_workday_india_facet_accepts_opaque_parameter_with_country_descriptor():
    facets = [
        {
            "facetParameter": "a",
            "descriptor": "Country",
            "values": [
                {"descriptor": "India", "id": "in"},
                {"descriptor": "United States of America", "id": "us"},
            ],
        }
    ]

    assert ats._workday_india_facet(facets) == ("a", ["in"])


def test_workday_early_career_facets_prefer_worker_subtype_and_group_ids():
    facets = [
        {
            "facetParameter": "workerSubType",
            "values": [
                {"descriptor": "Regular Employee", "id": "regular"},
                {"descriptor": "Intern (Fixed Term)", "id": "intern"},
                {"descriptor": "New College Graduate", "id": "graduate"},
            ],
        },
        {
            "facetParameter": "jobFamilyGroup",
            "values": [{"descriptor": "University", "id": "university"}],
        },
        {
            "facetParameter": "jobFamily",
            "values": [{"descriptor": "Intern", "id": "intern-role"}],
        },
    ]

    assert ats._workday_early_career_facets(facets) == [
        ("workerSubType", ["intern", "graduate"]),
        ("jobFamilyGroup", ["university"]),
        ("jobFamily", ["intern-role"]),
    ]


# --- Ashby ------------------------------------------------------------------

def test_ashby_preserves_current_location_workplace_and_apply_fields(monkeypatch):
    _patch_json(monkeypatch, {"jobs": [{
        "id": "job-1",
        "title": "Software Engineer Intern",
        "department": "Engineering",
        "team": "Platform",
        "employmentType": "Intern",
        "location": "Canada",
        "secondaryLocations": [{
            "location": "United States",
            "address": {"postalAddress": {
                "addressLocality": "San Francisco",
                "addressRegion": "California",
                "addressCountry": "United States",
            }},
        }],
        "address": {"postalAddress": {"addressCountry": "Canada"}},
        "isListed": True,
        "isRemote": True,
        "workplaceType": "Remote",
        "publishedAt": "2026-08-14T08:29:03Z",
        "jobUrl": "https://jobs.ashbyhq.com/acme/job-1",
        "applyUrl": "https://jobs.ashbyhq.com/acme/job-1/application",
        "descriptionPlain": "Build production services.",
    }]})

    lead = _run(ats.scrape_ashby("acme"))[0]

    assert lead["location"] == "Canada; San Francisco, California, United States"
    assert lead["workplace"] == "remote"
    assert lead["apply_url"].endswith("/application")
    assert lead["posted_date"] == "2026-08-14T08:29:03Z"
    assert lead["active_hint"] == "active"
    assert lead["source_meta"] | {
        "ats": "ashby",
        "slug": "acme",
        "id": "job-1",
        "is_listed": True,
        "job_url": "https://jobs.ashbyhq.com/acme/job-1",
        "apply_url": "https://jobs.ashbyhq.com/acme/job-1/application",
        "department": "Engineering",
        "team": "Platform",
        "employment_type": "Intern",
    } == lead["source_meta"]
    assert "Workplace: remote" in lead["description"]


def test_ashby_uses_structured_onsite_address_and_skips_unlisted_rows(monkeypatch):
    _patch_json(monkeypatch, {"jobs": [
        {
            "id": "live",
            "title": "Fullstack Engineering Internship",
            "location": "sf",
            "isListed": True,
            "isRemote": False,
            "workplaceType": "OnSite",
            "address": {"postalAddress": {
                "addressLocality": "San Francisco",
                "addressRegion": "California",
                "addressCountry": "USA",
            }},
            "jobUrl": "https://jobs.ashbyhq.com/acme/live",
        },
        {
            "id": "hidden",
            "title": "Hidden role",
            "isListed": False,
            "jobUrl": "https://jobs.ashbyhq.com/acme/hidden",
        },
        {
            "id": "malformed",
            "title": "  ",
            "isListed": True,
            "jobUrl": "https://jobs.ashbyhq.com/acme/malformed",
        },
    ]})

    leads = _run(ats.scrape_ashby("acme"))

    assert len(leads) == 1
    assert leads[0]["location"] == "San Francisco, California, USA"
    assert leads[0]["workplace"] == "onsite"


# --- Workable ---------------------------------------------------------------

def test_workable_collapses_location_variants_and_preserves_requisition(monkeypatch):
    _patch_json(monkeypatch, {
        "name": "Acme Labs",
        "jobs": [
            {
                "title": "Software Engineer Intern",
                "shortcode": "ABC123",
                "application_url": "https://apply.workable.com/acme/j/ABC123/apply",
                "published_on": "2026-08-20",
                "locations": [{"city": "Bengaluru", "country": "India"}],
                "description": "Build production Python services.",
                "telecommuting": False,
            },
            {
                "title": "Software Engineer Intern",
                "shortcode": "ABC123",
                "application_url": "https://apply.workable.com/acme/j/ABC123/apply",
                "published_on": "2026-08-20",
                "locations": {"city": "Hyderabad", "country": "India"},
                "description": "Build production Python services.",
                "telecommuting": False,
            },
        ],
    })

    leads = _run(ats.scrape_workable("acme"))

    assert len(leads) == 1
    assert leads[0]["company"] == "Acme Labs"
    assert leads[0]["location"] == "Bengaluru, India; Hyderabad, India"
    assert leads[0]["source_meta"]["id"] == "ABC123"
    assert leads[0]["apply_url"].endswith("/apply")


def test_workable_marks_telecommuting_requisition_remote(monkeypatch):
    _patch_json(monkeypatch, {
        "jobs": [{
            "title": "Machine Learning Intern",
            "shortcode": "REMOTE1",
            "url": "https://apply.workable.com/j/REMOTE1",
            "country": "India",
            "description": "Paid internship.",
            "telecommuting": True,
        }],
    })

    lead = _run(ats.scrape_workable("acme"))[0]

    assert lead["location"] == "India"
    assert lead["workplace"] == "remote"


# --- SmartRecruiters ---------------------------------------------------------

def test_smartrecruiters_parses_nursing_posting(monkeypatch):
    _patch_json(monkeypatch, {"content": [
        {
            "id": "abc123",
            "name": "ICU Registered Nurse",
            "company": {"name": "Mercy Health"},
            "location": {"city": "Berlin", "country": "Germany"},
            "releasedDate": "",  # empty => not freshness-filtered
        }
    ]})
    leads = _run(ats.scrape_smartrecruiters("mercy"))
    assert len(leads) == 1
    lead = leads[0]
    assert lead["title"] == "ICU Registered Nurse"
    assert lead["company"] == "Mercy Health"
    assert lead["platform"] == "smartrecruiters"
    assert "mercy/abc123" in lead["url"]
    assert lead["source_meta"]["ats"] == "smartrecruiters"
    # Field-agnostic: a non-tech posting still normalizes with a real signal.
    assert lead["signal_score"] > 0


def test_smartrecruiters_active_board_does_not_drop_old_posting_date(monkeypatch):
    _patch_json(monkeypatch, {"content": [
        {"id": "1", "name": "Welder", "releasedDate": "2020-01-01T00:00:00Z"}
    ]})
    assert len(_run(ats.scrape_smartrecruiters("acme"))) == 1


def test_smartrecruiters_pages_full_board_and_enriches_public_job_facts(monkeypatch):
    calls: list[tuple[str, dict | None]] = []
    first_page = [
        {"id": str(index), "name": f"Role {index}", "ref": f"https://api/jobs/{index}"}
        for index in range(100)
    ]
    second_page = [{
        "id": "100",
        "name": "Software Engineering Intern",
        "ref": "https://api/jobs/100",
    }]

    async def fake_json_get(url, params=None):
        calls.append((url, params))
        if params == {"limit": "100", "offset": "0"}:
            return {"totalFound": 101, "content": first_page}
        if params == {"limit": "100", "offset": "100"}:
            return {"totalFound": 101, "content": second_page}
        job_id = url.rsplit("/", 1)[-1]
        return {
            "id": job_id,
            "name": "Software Engineering Intern" if job_id == "100" else f"Role {job_id}",
            "company": {"name": "Acme"},
            "postingUrl": f"https://jobs.smartrecruiters.com/acme/{job_id}",
            "applyUrl": f"https://jobs.smartrecruiters.com/acme/{job_id}?oga=true",
            "releasedDate": "2026-08-25T00:00:00Z",
            "location": {
                "fullLocation": "Bengaluru, India",
                "country": "in",
                "hybrid": True,
            },
            "jobAd": {"sections": {
                "jobDescription": {
                    "title": "Job Description",
                    "text": "<p>Build production Python services.</p>",
                },
                "qualifications": {
                    "title": "Qualifications",
                    "text": "Currently pursuing a Computer Science degree.",
                },
            }},
            "typeOfEmployment": {"label": "Intern"},
            "experienceLevel": {"label": "Entry Level"},
            "function": {"label": "Engineering"},
            "refNumber": f"REF-{job_id}",
            "active": False,
            "applicationQuestions": "must never be retained",
        }

    monkeypatch.setattr(ats, "json_get", fake_json_get)
    leads = _run(ats.scrape_smartrecruiters("acme"))

    assert len(leads) == 101
    assert [params for _url, params in calls[:2]] == [
        {"limit": "100", "offset": "0"},
        {"limit": "100", "offset": "100"},
    ]
    lead = leads[-1]
    assert lead["title"] == "Software Engineering Intern"
    assert lead["workplace"] == "hybrid"
    assert lead["apply_url"].endswith("100?oga=true")
    assert "Build production Python services" in lead["description"]
    assert "Currently pursuing" in lead["description"]
    assert "Experience level: Entry Level" in lead["description"]
    assert lead["source_meta"]["id"] == "100"
    assert lead["source_meta"]["reference_number"] == "REF-100"
    assert lead["source_meta"]["active"] is False
    assert lead["source_meta"]["api_ref"] == "https://api/jobs/100"
    assert lead["source_meta"]["posting_url"].endswith("/100")
    assert lead["source_meta"]["apply_url"].endswith("100?oga=true")
    assert "applicationQuestions" not in str(lead)


def test_smartrecruiters_india_cse_mode_filters_before_detail_requests(monkeypatch):
    calls: list[tuple[str, dict | None]] = []

    async def fake_json_get(url, params=None):
        calls.append((url, params))
        if params is not None:
            assert params == {"limit": "100", "offset": "0", "country": "in"}
            return {"totalFound": 4, "content": [
                {
                    "id": "india-tech",
                    "name": "Software Engineer Full Stack",
                    "location": {"country": "in", "fullLocation": "Bengaluru, India"},
                    "ref": "https://api/jobs/india-tech",
                },
                {
                    "id": "india-senior",
                    "name": "Senior Software Engineer",
                    "location": {"country": "in", "fullLocation": "Bengaluru, India"},
                },
                {
                    "id": "india-sales",
                    "name": "Sales Manager",
                    "location": {"country": "in", "fullLocation": "Mumbai, India"},
                },
                {
                    "id": "us-tech",
                    "name": "Software Engineer",
                    "location": {"country": "us", "fullLocation": "Austin, US"},
                },
            ]}
        assert url == "https://api/jobs/india-tech"
        return {
            "id": "india-tech",
            "name": "Software Engineer Full Stack",
            "company": {"name": "Bosch Group"},
            "postingUrl": "https://jobs.smartrecruiters.com/BoschGroup/india-tech",
            "location": {"country": "in", "fullLocation": "Bengaluru, India"},
            "jobAd": {"sections": {"jobDescription": {
                "title": "Job Description",
                "text": "Build Java and React applications.",
            }}},
            "active": False,
        }

    monkeypatch.setattr(ats, "json_get", fake_json_get)
    leads = _run(ats.scrape_target("ats:smartrecruiters:BoschGroup:india-cse"))

    assert [lead["title"] for lead in leads] == ["Software Engineer Full Stack"]
    assert len([call for call in calls if call[1] is None]) == 1
    assert leads[0]["location"] == "Bengaluru, India"
    assert leads[0]["active_hint"] == "closed"


# --- Recruitee ---------------------------------------------------------------

def test_recruitee_parses_trade_posting(monkeypatch):
    _patch_json(monkeypatch, {"offers": [
        {
            "title": "Structural Welder",
            "careers_url": "https://acme.recruitee.com/o/welder",
            "city": "Houston",
            "country": "USA",
            "description": "MIG and TIG welding from blueprints",
            "created_at": "",
        }
    ]})
    leads = _run(ats.scrape_recruitee("acme"))
    assert len(leads) == 1
    lead = leads[0]
    assert lead["platform"] == "recruitee"
    assert lead["title"] == "Structural Welder"
    assert "Houston" in lead["location"]
    assert lead["url"] == "https://acme.recruitee.com/o/welder"


# --- Personio (XML feed) -----------------------------------------------------

def test_personio_parses_xml_feed(monkeypatch):
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><positions>'
        "<position><id>42</id><name>Staff Accountant</name><office>Munich</office>"
        "<jobDescriptions><jobDescription><name>Role</name>"
        "<value>Bookkeeping and financial reporting</value></jobDescription></jobDescriptions>"
        "<createdAt></createdAt></position>"
        "</positions>"
    )

    async def fake_xml_get(url, params=None):
        return xml

    monkeypatch.setattr(ats, "xml_get", fake_xml_get)
    leads = _run(ats.scrape_personio("acme"))
    assert len(leads) == 1
    lead = leads[0]
    assert lead["platform"] == "personio"
    assert lead["title"] == "Staff Accountant"
    assert "42" in lead["url"]
    assert "Munich" in lead["location"]


def test_personio_bad_xml_is_reported_as_a_source_failure(monkeypatch):
    async def fake_xml_get(url, params=None):
        return "not xml at all <<<"

    monkeypatch.setattr(ats, "xml_get", fake_xml_get)
    with pytest.raises(ValueError, match="invalid Personio XML"):
        _run(ats.scrape_personio("acme"))


def test_personio_falls_back_to_de_when_com_board_is_missing(monkeypatch):
    seen = []

    async def fake_at(slug, tld):
        seen.append((slug, tld))
        if tld == "com":
            raise RuntimeError("missing .com tenant")
        return [{"title": "Software Intern"}]

    monkeypatch.setattr(ats, "_scrape_personio_at", fake_at)
    assert _run(ats.scrape_personio("acme")) == [{"title": "Software Intern"}]
    assert seen == [("acme", "com"), ("acme", "de")]


# --- Dispatch / detection ----------------------------------------------------

def test_is_ats_target_recognizes_new_hosts():
    assert ats.is_ats_target("ats:smartrecruiters:acme")
    assert ats.is_ats_target("ats:recruitee:acme")
    assert ats.is_ats_target("ats:personio:acme")
    assert ats.is_ats_target("https://jobs.smartrecruiters.com/Acme/12345")
    assert ats.is_ats_target("https://acme.recruitee.com/careers")
    assert ats.is_ats_target("https://acme.jobs.personio.com/")
    assert not ats.is_ats_target("https://example.com/jobs")


def test_scrape_target_dispatches_ats_prefix(monkeypatch):
    seen = {}

    async def fake(slug):
        seen["slug"] = slug
        return [{"title": "x"}]

    monkeypatch.setattr(ats, "scrape_smartrecruiters", fake)
    _run(ats.scrape_target("ats:smartrecruiters:acme"))
    assert seen["slug"] == "acme"


def test_scrape_direct_ats_url_detects_subdomain_slug(monkeypatch):
    seen = {}

    async def fake_recruitee(slug):
        seen["recruitee"] = slug
        return []

    async def fake_personio(slug, tld="com"):
        seen["personio"] = slug
        return []

    monkeypatch.setattr(ats, "scrape_recruitee", fake_recruitee)
    monkeypatch.setattr(ats, "scrape_personio", fake_personio)
    _run(ats.scrape_direct_ats_url("https://acme.recruitee.com/o/welder"))
    _run(ats.scrape_direct_ats_url("https://beta.jobs.personio.com/job/9"))
    assert seen["recruitee"] == "acme"
    assert seen["personio"] == "beta"


# --- Himalayas (India-eligible filtered search segments) --------------------

def test_himalayas_pages_filtered_segment_and_preserves_all_fields(monkeypatch):
    import time
    fresh_epoch = int(time.time())
    pages = {
        "1": {"limit": 20, "totalCount": 21, "jobs": [{
            "title": "Applied AI Engineer", "companyName": "Acme AI",
            "description": "Build RAG pipelines", "pubDate": fresh_epoch,
            "expiryDate": fresh_epoch + 86400,
            "companySlug": "acme-ai", "employmentType": "Intern",
            "seniority": ["Entry-level"], "locationRestrictions": [],
            "timezoneRestrictions": [5.5], "categories": ["AI-Engineering"],
            "minSalary": 30000, "maxSalary": 50000,
            "salaryPeriod": "monthly", "currency": "INR",
            "applicationLink": "https://himalayas.app/companies/acme/jobs/1",
        }]},
        "2": {"limit": 20, "totalCount": 21, "jobs": []},
    }

    async def fake_json_get(url, params=None):
        assert url.endswith("/jobs/api/search")
        assert params["country"] == "IN"
        assert params["employment_type"] == "Intern"
        assert params["exclude_worldwide"] == "false"
        return pages[params["page"]]

    monkeypatch.setattr(ats, "json_get", fake_json_get)
    leads = _run(ats.scrape_himalayas("intern-india-eligible"))
    assert len(leads) == 1
    lead = leads[0]
    assert lead["platform"] == "himalayas"
    assert lead["company"] == "Acme AI"
    assert lead["location"] == "Worldwide"
    assert lead["workplace"] == "remote"
    assert lead["active_hint"] == "active"
    assert lead["deadline"]
    assert "Compensation: INR 30000-50000 monthly" in lead["description"]
    assert lead["source_meta"]["slug"] == "acme-ai"
    assert lead["source_meta"]["seniority"] == ["Entry-level"]
    assert lead["source_meta"]["timezone_restrictions"] == ["5.5"]


def test_himalayas_compacts_oversized_country_display_without_losing_metadata():
    restrictions = [f"Country {index}" for index in range(150)] + ["India"]
    job = {
        "title": "Software Engineering Intern",
        "companyName": "Acme AI",
        "description": "Build production services",
        "locationRestrictions": restrictions,
        "applicationLink": "https://himalayas.app/companies/acme/jobs/large-region",
    }

    lead = ats._himalayas_lead(job)

    assert len(lead["location"]) <= 1000
    assert "India eligible" in lead["location"]
    assert "151 listed countries" in lead["location"]
    assert lead["source_meta"]["location_restrictions"] == restrictions


# --- Teamtailor (JSON Feed 1.1, content_html is the full description) -------

def test_teamtailor_uses_content_html_no_second_fetch(monkeypatch):
    _patch_json(monkeypatch, {"items": [{
        "title": "MLOps Engineer",
        "url": "https://acme.teamtailor.com/jobs/1-mlops",
        "date_published": "",  # empty => not freshness-filtered
        "content_html": "<p>Own our model serving stack.</p>",
        "_jobposting": {"hiringOrganization": {"name": "Acme"},
                         "jobLocation": [{"address": {"addressLocality": "Berlin", "addressCountry": "DE"}}]},
    }]})
    leads = _run(ats.scrape_teamtailor("acme"))
    assert len(leads) == 1
    lead = leads[0]
    assert lead["platform"] == "teamtailor"
    assert lead["company"] == "Acme"
    assert "Berlin" in lead["location"]
    assert "model serving" in lead["description"]


# --- Rippling (list + per-job detail, no usable recency signal) ------------

def test_rippling_fetches_detail_and_skips_recency_gate(monkeypatch):
    async def fake_json_get(url, params=None):
        if url.endswith("/jobs"):
            return [{"uuid": "u1", "name": "AI Platform Engineer",
                      "url": "https://ats.rippling.com/acme/jobs/u1",
                      "workLocation": {"label": "Remote"}}]
        return {
            "companyName": "Acme",
            "createdOn": "2019-01-01T00:00:00-07:00",  # old, but must NOT be filtered
            "description": {"role": "Ship LLM evals", "company": "About Acme"},
            "workLocations": ["Remote (US)"],
        }

    monkeypatch.setattr(ats, "json_get", fake_json_get)
    leads = _run(ats.scrape_rippling("acme"))
    assert len(leads) == 1
    lead = leads[0]
    assert lead["platform"] == "rippling"
    assert lead["company"] == "Acme"
    assert "LLM evals" in lead["description"]


# --- Breezy (list has no description; detail page is JSON-LD or HTML block) -

def test_breezy_parses_ldjson_detail_page(monkeypatch):
    _patch_json(monkeypatch, [{
        "name": "RAG Engineer",
        "url": "https://acme.breezy.hr/p/1",
        "published_date": "",
        "location": {"name": "Remote"},
        "company": {"name": "Acme"},
    }])

    async def fake_xml_get(url, params=None):
        return (
            '<script type="application/ld+json">'
            '{"@type": "JobPosting", "description": "Build retrieval pipelines"}'
            "</script>"
        )

    monkeypatch.setattr(ats, "xml_get", fake_xml_get)
    leads = _run(ats.scrape_breezy("acme"))
    assert len(leads) == 1
    assert "retrieval pipelines" in leads[0]["description"]


def test_breezy_falls_back_to_og_description(monkeypatch):
    _patch_json(monkeypatch, [{
        "name": "Support Engineer", "url": "https://acme.breezy.hr/p/2",
        "published_date": "", "location": {}, "company": {},
    }])

    async def fake_xml_get(url, params=None):
        return '<meta property="og:description" content="Help our customers ship"/>'

    monkeypatch.setattr(ats, "xml_get", fake_xml_get)
    leads = _run(ats.scrape_breezy("acme"))
    assert leads[0]["description"] == "Help our customers ship"


# --- Pinpoint (full HTML description in one call, no date field) -----------

def test_pinpoint_parses_full_posting_in_one_call(monkeypatch):
    _patch_json(monkeypatch, {"data": [{
        "title": "LLM Evaluation Engineer",
        "url": "https://acme.pinpointhq.com/en/postings/1",
        "location": {"name": "London"},
        "description": "<p>Design our eval harness.</p>",
    }]})
    leads = _run(ats.scrape_pinpoint("acme"))
    assert len(leads) == 1
    lead = leads[0]
    assert lead["platform"] == "pinpoint"
    assert "eval harness" in lead["description"]
    assert "London" in lead["location"]


# --- BambooHR (HTML fragment list, not JSON) --------------------------------

def test_bamboohr_parses_html_fragment_and_detail(monkeypatch):
    fragment = (
        '<div class="BambooHR-ATS-board"><ul class="BambooHR-ATS-Jobs-List">'
        '<li id="bhrPositionID_7" class="BambooHR-ATS-Jobs-Item"><a\n'
        '\t\thref="//acme.bamboohr.com/careers/7">Applied AI Engineer</a><span\n'
        '\t\tclass="BambooHR-ATS-Location">Remote</span></li>'
        "</ul></div>"
    )

    async def fake_xml_get(url, params=None):
        if "careers/7" in url:
            return '<meta property="og:description" content="Build agent tooling"/>'
        return fragment

    monkeypatch.setattr(ats, "xml_get", fake_xml_get)
    leads = _run(ats.scrape_bamboohr("acme"))
    assert len(leads) == 1
    lead = leads[0]
    assert lead["platform"] == "bamboohr"
    assert lead["title"] == "Applied AI Engineer"
    assert "Remote" in lead["location"]
    assert lead["description"] == "Build agent tooling\nLocation: Remote"


# --- Dispatch / host detection for the new platforms ------------------------

def test_is_ats_target_recognizes_new_platform_hosts():
    assert ats.is_ats_target("ats:himalayas")
    assert ats.is_ats_target("ats:teamtailor:acme")
    assert ats.is_ats_target("ats:rippling:acme")
    assert ats.is_ats_target("ats:breezy:acme")
    assert ats.is_ats_target("ats:pinpoint:acme")
    assert ats.is_ats_target("ats:bamboohr:acme")
    assert ats.is_ats_target("ats:freshteam:acme")
    assert ats.is_ats_target("https://himalayas.app/jobs/api")
    assert ats.is_ats_target("https://acme.teamtailor.com/jobs")
    assert ats.is_ats_target("https://acme.breezy.hr/p/1")
    assert ats.is_ats_target("https://acme.pinpointhq.com/postings.json")
    assert ats.is_ats_target("https://acme.bamboohr.com/careers/7")
    assert ats.is_ats_target("https://acme.freshteam.com/jobs")
    assert ats.is_ats_target(
        "https://emit.fa.ca3.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_2001"
    )
    assert ats.is_ats_target(
        "https://app.eightfold.ai/careers/job/43751444?domain=micron.com"
    )
    assert ats.is_ats_target(
        "https://internationalcareers-waters.icims.com/jobs/26860/trainee-intern/job"
    )


def _eightfold_schema(title="Intern"):
    return json.dumps({
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": title,
        "description": (
            "<p>Build semiconductor software, data science, and AI systems.</p>"
        ),
        "datePosted": "2026-08-24T00:00:00",
        "validThrough": "2027-02-20T00:00:00",
        "employmentType": "FULL_TIME",
        "hiringOrganization": {"name": "Micron Technology"},
        "applicationQuestions": "must never be retained",
    })


def test_eightfold_pcsx_discovers_india_roles_and_enriches_jobposting(monkeypatch):
    search_calls: list[dict] = []
    details: list[str] = []
    rows = [
        {
            "id": 43751444,
            "displayJobId": "JR108596",
            "atsJobId": "JR108596",
            "name": "Intern",
            "locations": [
                "Hyderabad, Telangana, India", "Bengaluru, Karnataka, India",
            ],
            "standardizedLocations": ["Hyderabad, TS, IN", "Bengaluru, KA, IN"],
            "postedTs": 1787529600,
            "creationTs": 1786320000,
            "workLocationOption": "onsite",
            "positionUrl": "/careers/job/43751444",
            "isHot": 1,
        },
        {
            "id": 2,
            "displayJobId": "JR2",
            "name": "Software Engineer",
            "locations": ["Hyderabad, Telangana, India"],
            "standardizedLocations": ["Hyderabad, TS, IN"],
            "positionUrl": "/careers/job/2",
        },
        {
            "id": 3,
            "name": "Senior Software Engineer",
            "locations": ["Bengaluru, Karnataka, India"],
            "standardizedLocations": ["Bengaluru, KA, IN"],
        },
        {
            "id": 4,
            "name": "Software Intern",
            "locations": ["Austin, Texas, United States"],
            "standardizedLocations": ["Austin, TX, US"],
        },
    ]

    async def fake_text_get(url, params=None, request_headers=None):
        if url.endswith("/api/pcsx/search"):
            search_calls.append(params)
            assert request_headers["Accept"] == "application/json, */*"
            return json.dumps({
                "data": {"positions": rows, "count": len(rows)},
            })
        assert "/careers/job/" in url
        details.append(url)
        title = "Intern" if "/43751444?" in url else "Software Engineer"
        return (
            '<script type="application/ld+json">'
            + _eightfold_schema(title)
            + "</script>"
        )

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    leads = _run(ats.scrape_eightfold(
        "micron", "app.eightfold.ai", "micron.com"
    ))

    assert len(search_calls) == len(ats._EIGHTFOLD_SEARCHES)
    assert all(call["location"] == "India" for call in search_calls)
    assert len(details) == 2
    assert {lead["title"] for lead in leads} == {"Intern", "Software Engineer"}
    intern = next(lead for lead in leads if lead["title"] == "Intern")
    assert intern["company"] == "Micron Technology"
    assert intern["location"] == (
        "Hyderabad, Telangana, India; Bengaluru, Karnataka, India"
    )
    assert intern["workplace"] == "onsite"
    assert intern["posted_date"] == "2026-08-24T00:00:00"
    assert intern["deadline"] == "2027-02-20T00:00:00"
    assert intern["source_meta"]["id"] == "JR108596"
    assert intern["source_meta"]["position_id"] == "43751444"
    assert intern["source_meta"]["generation"] == "pcsx"
    assert intern["source_meta"]["creation_epoch_seconds"] == 1786320000
    assert intern["source_meta"]["is_hot"] == 1
    assert "semiconductor software" in intern["description"]
    assert "applicationQuestions" not in str(intern)
    record = source_record_from_lead(intern)
    assert record.source_kind == SourceKind.ATS
    assert record.provider_requisition_id == "JR108596"
    assert record.employer_domain == "micron.com"


def test_eightfold_falls_back_to_classic_generation(monkeypatch):
    calls: list[tuple[str, dict | None]] = []

    async def fake_text_get(url, params=None, request_headers=None):
        calls.append((url, params))
        if url.endswith("/api/pcsx/search"):
            request = httpx.Request("GET", url)
            response = httpx.Response(
                403, request=request, text='{"message":"PCSX is not enabled for this user."}'
            )
            raise httpx.HTTPStatusError("forbidden", request=request, response=response)
        if url.endswith("/api/apply/v2/jobs"):
            return json.dumps({
                "count": 1,
                "positions": [{
                    "id": "classic-1",
                    "name": "Data Science Intern",
                    "location": "Bengaluru, India",
                    "locations": ["Bengaluru, India"],
                    "t_create": 1787529600,
                }],
            })
        return (
            '<script type="application/ld+json">'
            + _eightfold_schema("Data Science Intern")
            + "</script>"
        )

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    leads = _run(ats.scrape_eightfold(
        "acme", "acme.eightfold.ai", "acme.example"
    ))
    assert len(leads) == 1
    assert leads[0]["source_meta"]["generation"] == "classic"
    assert any(url.endswith("/api/apply/v2/jobs") for url, _params in calls)
    assert leads[0]["posted_date"].startswith("2026-")


def test_eightfold_rejects_untrusted_host_without_network(monkeypatch):
    called = False

    async def fake_text_get(url, params=None, request_headers=None):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    assert _run(ats.scrape_eightfold(
        "micron", "example.com", "micron.com"
    )) == []
    assert called is False


def _icims_card(job_id, title, location, summary="Build Python software and AI systems."):
    return f"""
    <li class="iCIMS_JobCardItem">
      <div class="title"><a class="iCIMS_Anchor"
        href="/jobs/{job_id}/{title.lower().replace(' ', '-')}/job?in_iframe=1">
        <h3 class="themed">{title}</h3></a></div>
      <div class="description">{summary}</div>
      <div class="iCIMS_JobHeaderTag">
        <dt class="iCIMS_JobHeaderField">Req. #</dt>
        <dd class="iCIMS_JobHeaderData"><span>{job_id}</span></dd>
      </div>
      <div class="header left">
        <span class="sr-only themed field-label">Job Locations</span>
        <span>{location}</span>
      </div>
      <div class="iCIMS_JobHeaderTag">
        <dt class="iCIMS_JobHeaderField">Job Family</dt>
        <dd class="iCIMS_JobHeaderData"><span>DA - Data Analytics</span></dd>
      </div>
    </li>
    """


def test_icims_discovers_india_tech_roles_and_rechecks_jobposting(monkeypatch):
    calls: list[tuple[str, dict | None]] = []

    async def fake_text_get(url, params=None, request_headers=None):
        calls.append((url, params))
        assert request_headers["Accept-Encoding"] == "identity"
        if url.endswith("/jobs/search"):
            return (
                _icims_card("26860", "Trainee-Intern (GCC)", "IN-Bangalore")
                + _icims_card("999", "Software Intern", "US-New York")
            )
        assert url.endswith("/jobs/26860/trainee-intern-(gcc)/job")
        return '<script nonce="abc" type="application/ld+json">' + json.dumps({
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Trainee-Intern (GCC)",
            "description": "<p>Build Databricks pipelines and GenAI models.</p>",
            "datePosted": "2026-08-24T04:00:00Z",
            "validThrough": "2027-02-24T04:00:00Z",
            "employmentType": "INTERN",
            "directApply": True,
            "hiringOrganization": {
                "name": "Waters Corporation", "sameAs": "www.waters.com",
            },
            "jobLocation": [{
                "@type": "Place",
                "address": {
                    "@type": "PostalAddress",
                    "addressLocality": "Bangalore",
                    "addressCountry": "IN",
                },
            }],
            "applicationQuestions": "must never be retained",
        }) + "</script>"

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    leads = _run(ats.scrape_icims(
        "waters", "internationalcareers-waters.icims.com", "waters.com"
    ))

    assert len(leads) == 1
    lead = leads[0]
    assert lead["title"] == "Trainee-Intern (GCC)"
    assert lead["company"] == "Waters Corporation"
    assert lead["location"] == "IN-Bangalore"
    assert lead["workplace"] == "onsite"
    assert lead["posted_date"] == "2026-08-24T04:00:00Z"
    assert lead["deadline"] == "2027-02-24T04:00:00Z"
    assert lead["source_meta"]["id"] == "26860"
    assert lead["source_meta"]["direct_apply"] is True
    assert lead["source_meta"]["additional_fields"]["Job Family"] == "DA - Data Analytics"
    assert lead["source_meta"]["structured_locations"][0]["address_country"] == "IN"
    assert "Databricks pipelines" in lead["description"]
    assert "applicationQuestions" not in str(lead)
    assert sum(url.endswith("/jobs/search") for url, _ in calls) == 1
    record = source_record_from_lead(lead)
    assert record.source_kind == SourceKind.ATS
    assert record.provider_requisition_id == "26860"
    assert record.employer_domain == "waters.com"


def test_icims_rejects_untrusted_host_without_network(monkeypatch):
    called = False

    async def fake_text_get(url, params=None, request_headers=None):
        nonlocal called
        called = True
        return ""

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    assert _run(ats.scrape_icims("waters", "example.com", "waters.com")) == []
    assert called is False


def _avature_card(
    job_id="16601",
    title="Software Engineer I",
    *,
    portal="careers",
    country="",
):
    location = (
        f'<p><span class="text--bold">City:</span> Bengaluru</p>'
        f'<p><span class="text--bold">State/Province:</span> Karnataka</p>'
        f'<p><span class="text--bold">Country:</span> {country}</p>'
        if country else ""
    )
    return f"""
    <article class="article article--result result">
      <div class="article__header__text">
        <h3 class="article__header__text__title title--04">
          <a href="https://synopsys.avature.net/{portal}/JobDetail/software-engineer/{job_id}">
            {title}
          </a>
        </h3>
        <div class="article__header__text__subtitle">
          <span class="list-item-jobId">Job ID {job_id}</span>
          <span class="list-item-hireType">Employee</span>
          <span class="list-item-posted">Posted 24-Aug-2026</span>
          {location}
        </div>
      </div>
      <a href="https://synopsys.avature.net/{portal}/Login?jobId={job_id}">Apply</a>
    </article>
    """


def _avature_detail(title="Software Engineer I", job_id="16601", country=""):
    country_field = (
        '<div class="article__content__view__field__label">Country</div>'
        f'<div class="article__content__view__field__value">{country}</div>'
        if country else ""
    )
    return f"""
    <html><head><meta property="og:title" content="{title}"></head><body>
      <article class="article article--details">
        <div class="article__content__view__field__label">Job Title</div>
        <div class="article__content__view__field__value">{title}</div>
        <div class="article__content__view__field__label">Job ID</div>
        <div class="article__content__view__field__value">{job_id}</div>
        <div class="article__content__view__field__label">City</div>
        <div class="article__content__view__field__value">Bengaluru</div>
        <div class="article__content__view__field__label">State/Province</div>
        <div class="article__content__view__field__value">Karnataka</div>
        {country_field}
        <div class="article__content__view__field__label">Date Posted</div>
        <div class="article__content__view__field__value">24-Aug-2026</div>
        <div class="article__content__view__field__label">Hire Type</div>
        <div class="article__content__view__field__value">Employee</div>
        <div class="article__content__view__field__label">Remote Eligible</div>
        <div class="article__content__view__field__value">No</div>
      </article>
      <article class="article article--details description">
        Description and Requirements: Build Python services, machine-learning
        pipelines, APIs, automated tests, and cloud infrastructure with a product
        engineering team. Candidate profile or application questions are not here.
      </article>
    </body></html>
    """


def test_avature_uses_india_facet_and_rechecks_rich_same_host_detail(monkeypatch):
    calls: list[tuple[str, dict | None]] = []
    search_html = (
        '<select name="2001"><option value="21372">India</option></select>'
        '<div>1-1 of 1 results</div>'
        + _avature_card()
    )

    async def fake_text_get(url, params=None, request_headers=None):
        calls.append((url, params))
        assert request_headers["Accept-Encoding"] == "identity"
        if url.endswith("/SearchJobs"):
            return search_html
        assert url == (
            "https://synopsys.avature.net/careers/JobDetail/software-engineer/16601"
        )
        return _avature_detail()

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    leads = _run(ats.scrape_avature(
        "synopsys", "synopsys.avature.net", "careers", "synopsys.com",
    ))

    assert len(leads) == 1
    lead = leads[0]
    assert lead["title"] == "Software Engineer I"
    assert lead["company"] == "Synopsys"
    assert lead["location"] == "Bengaluru, Karnataka, India"
    assert lead["workplace"] == "onsite"
    assert lead["posted_date"] == "2026-08-24"
    assert lead["apply_url"].endswith("/careers/Login?jobId=16601")
    assert lead["source_meta"]["id"] == "16601"
    assert lead["source_meta"]["india_scope"] == {
        "facet": "2001", "value": "21372",
    }
    assert lead["source_meta"]["additional_fields"]["Hire Type"] == "Employee"
    assert "machine-learning pipelines" in lead["description"]
    assert "applicationQuestions" not in str(lead)
    assert any(params == {"2001": "21372", "jobOffset": 0} for _, params in calls)
    record = source_record_from_lead(lead)
    assert record.source_kind == SourceKind.ATS
    assert record.provider_requisition_id == "16601"
    assert record.employer_domain == "synopsys.com"


def test_avature_fallback_search_requires_exact_india_card(monkeypatch):
    search_html = (
        '<div>1-2 of 2 results</div>'
        + _avature_card("1", "Software Engineer I", country="India")
        + _avature_card("2", "Data Engineer I", country="United States")
    )
    detail_calls: list[str] = []

    async def fake_text_get(url, params=None, request_headers=None):
        if url.endswith("/SearchJobs"):
            return search_html
        detail_calls.append(url)
        return _avature_detail("Software Engineer I", "1", "India")

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    leads = _run(ats.scrape_avature(
        "synopsys", "synopsys.avature.net", "careers", max_pages=1,
    ))
    assert [lead["source_meta"]["id"] for lead in leads] == ["1"]
    assert len(detail_calls) == 1
    assert leads[0]["source_meta"]["india_scope"] == {"search": "India"}


def test_avature_normalizes_both_observed_publication_date_themes():
    assert ats._avature_date("24-Aug-2026") == "2026-08-24"
    assert ats._avature_date("Tuesday, January 20, 2026") == "2026-01-20"


def test_avature_auto_heals_branded_offset_pagination(monkeypatch):
    calls: list[dict | None] = []

    async def fake_text_get(url, params=None, request_headers=None):
        calls.append(params)
        if url.endswith("/SearchJobs"):
            if params == {"search": "India", "offset": 1}:
                return '<div>2-2 of 2 results</div>' + _avature_card(
                    "2", "Data Engineer I", country="India",
                )
            return '<div>1-1 of 2 results</div>' + _avature_card(
                "1", "Software Engineer I", country="India",
            )
        job_id = url.rsplit("/", 1)[-1]
        title = "Software Engineer I" if job_id == "1" else "Data Engineer I"
        return _avature_detail(title, job_id, "India")

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    leads = _run(ats.scrape_avature(
        "synopsys", "synopsys.avature.net", "careers",
    ))
    assert {lead["source_meta"]["id"] for lead in leads} == {"1", "2"}
    assert {"search": "India", "jobOffset": 1} in calls
    assert {"search": "India", "offset": 1} in calls
    assert {lead["source_meta"]["pagination_key"] for lead in leads} == {"offset"}


def test_avature_rejects_host_portal_and_detail_title_mismatch(monkeypatch):
    called = False

    async def fake_text_get(url, params=None, request_headers=None):
        nonlocal called
        called = True
        return ""

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    assert _run(ats.scrape_avature(
        "bad", "avature.net", "careers",
    )) == []
    assert _run(ats.scrape_avature(
        "bad", "bad.avature.net.evil.example", "careers",
    )) == []
    assert _run(ats.scrape_avature(
        "bad", "bad.avature.net", "../../candidate",
    )) == []
    assert called is False


def test_avature_dispatches_production_target(monkeypatch):
    seen = {}

    async def fake_avature(slug, host, portal="careers", employer_domain=""):
        seen.update({
            "slug": slug, "host": host, "portal": portal, "domain": employer_domain,
        })
        return [{"title": "Software Engineer I"}]

    monkeypatch.setattr(ats, "scrape_avature", fake_avature)
    leads = _run(ats.scrape_target(
        "ats:avature:xerox:xerox.avature.net:en_US/careers:xerox.com"
    ))
    assert leads == [{"title": "Software Engineer I"}]
    assert seen == {
        "slug": "xerox", "host": "xerox.avature.net",
        "portal": "en_US/careers", "domain": "xerox.com",
    }


def _jobvite_row(job_id, title, location):
    return f"""
      <tr>
        <td class="jv-job-list-name"><a href="/acme/job/{job_id}">{title}</a></td>
        <td class="jv-job-list-location">{location}</td>
      </tr>
    """


def _jobvite_detail(
    job_id="abc123",
    title="Software Engineer I",
    country="India",
    *,
    closed=False,
):
    if closed:
        return "<h1>The job listing no longer exists</h1>"
    schema = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": title,
        "identifier": job_id,
        "datePosted": "2026-08-24",
        "validThrough": "2026-09-30",
        "description": (
            "<p>Build Python services and machine learning systems with automated "
            "tests, peer review, observability, and reliable production delivery.</p>"
        ),
        "hiringOrganization": {"name": "Acme AI", "sameAs": "https://acme.example"},
        "jobLocation": [{"address": {
            "addressLocality": "Bengaluru",
            "addressRegion": "Karnataka",
            "addressCountry": country,
            "postalCode": "560001",
        }}],
        "jobLocationType": "HYBRID",
        "employmentType": ["FULL_TIME"],
        "industry": "Engineering",
        "baseSalary": {"currency": "INR", "value": {"minValue": 500000}},
        "experienceRequirements": "0-2 years",
        "educationRequirements": "B.Tech CSE or equivalent",
        "skills": "Python, SQL, machine learning",
        "responsibilities": "Ship and test production systems",
        "qualifications": "Strong computer science fundamentals",
        "directApply": True,
    }
    return (
        '<script type="application/ld+json">'
        + json.dumps(schema)
        + '</script><a href="/acme/job/' + job_id + '/apply?nl=1">Apply</a>'
    )


def test_jobvite_rechecks_live_india_rows_and_retains_rich_public_facts(monkeypatch):
    board = "".join([
        _jobvite_row("abc123", "Software Engineer I", "Bangalore, Karnataka"),
        _jobvite_row("outside", "Data Engineer I", "New York, NY"),
        _jobvite_row("senior", "Senior Software Engineer", "Bangalore, Karnataka"),
        _jobvite_row("nontech", "Finance Intern", "Bangalore, Karnataka"),
    ])
    calls = []

    async def fake_text_get(url, params=None, request_headers=None):
        calls.append(url)
        if url == "https://jobs.jobvite.com/acme":
            return board
        assert url == "https://jobs.jobvite.com/acme/job/abc123"
        return _jobvite_detail()

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    leads = _run(ats.scrape_jobvite("acme", "acme.example"))

    assert calls == [
        "https://jobs.jobvite.com/acme",
        "https://jobs.jobvite.com/acme/job/abc123",
    ]
    assert len(leads) == 1
    lead = leads[0]
    assert lead["title"] == "Software Engineer I"
    assert lead["company"] == "Acme AI"
    assert lead["location"] == "Bengaluru, Karnataka, India"
    assert lead["workplace"] == "hybrid"
    assert lead["apply_url"] == (
        "https://jobs.jobvite.com/acme/job/abc123/apply?nl=1"
    )
    assert lead["posted_date"] == "2026-08-24"
    assert lead["deadline"] == "2026-09-30"
    assert lead["active_hint"] == "active"
    assert lead["source_meta"]["skills"] == "Python, SQL, machine learning"
    assert lead["source_meta"]["base_salary"]["currency"] == "INR"
    assert "applicationQuestions" not in str(lead)
    record = source_record_from_lead(lead)
    assert record.source_kind == SourceKind.ATS
    assert record.provider_requisition_id == "abc123"
    assert record.employer_domain == "acme.example"


def test_jobvite_structured_country_overrides_ambiguous_india_city_card(monkeypatch):
    async def fake_text_get(url, params=None, request_headers=None):
        if url == "https://jobs.jobvite.com/acme":
            return _jobvite_row("us-role", "Software Engineer I", "Bangalore")
        return _jobvite_detail("us-role", country="United States")

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    assert _run(ats.scrape_jobvite("acme")) == []


def test_jobvite_rejects_closed_and_identity_mismatched_details(monkeypatch):
    board = (
        _jobvite_row("closed", "Software Engineer I", "India")
        + _jobvite_row("mismatch", "Data Engineer I", "India")
    )

    async def fake_text_get(url, params=None, request_headers=None):
        if url == "https://jobs.jobvite.com/acme":
            return board
        if url.endswith("/closed"):
            return _jobvite_detail(closed=True)
        return _jobvite_detail("another-id", "Data Engineer I")

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    assert _run(ats.scrape_jobvite("acme")) == []


def test_jobvite_rejects_hostile_slug_and_domain_without_network(monkeypatch):
    called = False

    async def fake_text_get(url, params=None, request_headers=None):
        nonlocal called
        called = True
        return ""

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    assert _run(ats.scrape_jobvite("../../candidate")) == []
    assert _run(ats.scrape_jobvite("acme", "bad_domain")) == []
    assert called is False


def test_jobvite_dispatches_target_and_direct_board_alias(monkeypatch):
    seen = []

    async def fake_jobvite(slug, employer_domain=""):
        seen.append((slug, employer_domain))
        return []

    monkeypatch.setattr(ats, "scrape_jobvite", fake_jobvite)
    _run(ats.scrape_target("ats:jobvite:acme:acme.example"))
    _run(ats.scrape_direct_ats_url(
        "https://jobs.jobvite.com/careers/acme/jobs"
    ))
    assert seen == [("acme", "acme.example"), ("acme", "")]


def _successfactors_field(label, value, itemprop=""):
    itemprop_attr = f' itemprop="{itemprop}"' if itemprop else ""
    return f"""
      <div class="joblayouttoken displayDTM"><div><div><div>
        <span class="joblayouttoken-label">{label}:&nbsp;</span>
        <span{itemprop_attr} class="rtltextaligneligible">{value}</span>
      </div></div></div></div>
    """


def _successfactors_detail(
    job_id="700", title="Software Engineer I", *, apply_id="", closed=False,
):
    if closed:
        return "<h1>This job is no longer available</h1>"
    return "".join([
        (
            '<script>const fake = `<span class="joblayouttoken-label">Fake:'
            '</span>`;</script>'
        ),
        _successfactors_field("Req ID", job_id),
        _successfactors_field("Job Location", "Bangalore, IN"),
        _successfactors_field("Employment Type", "Full Time"),
        _successfactors_field("Business Unit", "Digital Engineering"),
        _successfactors_field("Job Category", "Information Technology"),
        _successfactors_field("Work Location Type", "Hybrid"),
        _successfactors_field("Job Title", title, "title"),
        (
            '<div class="joblayouttoken"><span itemprop="description" '
            'class="rtltextaligneligible"><div><p>Build Python cloud services, '
            'machine learning systems, automated tests, and production observability '
            'with an engineering team.</p><p><span>Applicants need a B.Tech in '
            'Computer Science and zero to two years of experience.</span></p></div>'
            '</span></div>'
        ),
        f'<a class="unify-apply-now" href="/talentcommunity/apply/{apply_id or job_id}/?locale=en_GB">Apply now</a>',
    ])


def test_successfactors_searches_india_and_rechecks_rich_same_host_detail(monkeypatch):
    rows = [
        {"response": {
            "id": "700",
            "unifiedStandardTitle": "Software Engineer I",
            "unifiedStandardStart": "24/08/2026",
            "unifiedStandardEnd": "30/09/2026",
            "jobLocationShort": ["Berlin, DEU", "Bangalore, IND    "],
            "jobLocationShortWithCoordinates": [
                {"value": "Bangalore, IND", "key": "12.9,77.5"}
            ],
            "supportedLocales": ["en_GB"],
            "currency": ["INR"],
            "filter2": ["Information Technology"],
            "filter3": ["Associate"],
        }},
        {"response": {
            "id": "outside", "unifiedStandardTitle": "Data Engineer I",
            "jobLocationShort": ["Berlin, DEU"],
        }},
        {"response": {
            "id": "senior", "unifiedStandardTitle": "Senior Software Engineer",
            "jobLocationShort": ["Pune, IND"],
        }},
        {"response": {
            "id": "nontech", "unifiedStandardTitle": "Finance Intern",
            "jobLocationShort": ["Pune, IND"],
        }},
    ]
    search_calls = []
    detail_calls = []

    async def fake_json_post(url, body):
        assert url == "https://jobs.acme.example/services/recruiting/v1/jobs"
        assert body["location"] == "India"
        assert body["locale"] == "en_GB"
        assert body["pageNumber"] == 0
        search_calls.append(body["keywords"])
        return {"jobSearchResult": rows, "totalJobs": len(rows)}

    async def fake_text_get(url, params=None, request_headers=None):
        detail_calls.append(url)
        assert url == (
            "https://jobs.acme.example/job/Software-Engineer-I/700-en_GB"
        )
        return _successfactors_detail()

    monkeypatch.setattr(ats, "json_post", fake_json_post)
    monkeypatch.setattr(ats, "text_get", fake_text_get)
    leads = _run(ats.scrape_successfactors(
        "acme", "jobs.acme.example", "en_GB", "acme.example",
    ))

    assert search_calls == list(ats._SUCCESSFACTORS_SEARCHES)
    assert detail_calls == [
        "https://jobs.acme.example/job/Software-Engineer-I/700-en_GB"
    ]
    assert len(leads) == 1
    lead = leads[0]
    assert lead["title"] == "Software Engineer I"
    assert lead["company"] == "Acme"
    assert lead["location"] == "Bangalore, India"
    assert lead["workplace"] == "hybrid"
    assert lead["posted_date"] == "2026-08-24"
    assert lead["deadline"] == "2026-09-30"
    assert lead["apply_url"] == (
        "https://jobs.acme.example/talentcommunity/apply/700/?locale=en_GB"
    )
    assert lead["source_meta"]["currency"] == ["INR"]
    assert lead["source_meta"]["location_coordinates"][0]["key"] == "12.9,77.5"
    assert lead["source_meta"]["employment_type"] == "Full Time"
    assert "zero to two years" in lead["description"]
    assert "candidate" not in str(lead).lower()
    record = source_record_from_lead(lead)
    assert record.source_kind == SourceKind.ATS
    assert record.provider_requisition_id == "700"
    assert record.employer_domain == "acme.example"


def test_successfactors_rejects_closed_or_identity_mismatched_detail(monkeypatch):
    async def fake_json_post(url, body):
        return {"jobSearchResult": [{"response": {
            "id": "700", "unifiedStandardTitle": "Software Engineer I",
            "jobLocationShort": ["Bangalore, IND"],
        }}], "totalJobs": 1}

    async def closed_text_get(url, params=None, request_headers=None):
        return _successfactors_detail(closed=True)

    monkeypatch.setattr(ats, "json_post", fake_json_post)
    monkeypatch.setattr(ats, "text_get", closed_text_get)
    assert _run(ats.scrape_successfactors("acme", "jobs.acme.example")) == []


def test_successfactors_falls_back_to_documented_public_xml_feed(monkeypatch):
    xml = """<?xml version="1.0"?>
      <Job-Listing><Job>
        <JobTitle>Developer Associate - Cloud ERP</JobTitle>
        <Job-Description><![CDATA[<p>Build cloud software.</p>]]></Job-Description>
        <ReqId>456251</ReqId><Posted-Date>08/24/2026</Posted-Date>
        <filter1><label>Work Area</label><value>Software-Design and Development</value></filter1>
        <filter2><label>Career Status</label><value>Graduate</value></filter2>
        <filter3><label>Employment Type</label><value>Regular Full Time</value></filter3>
        <filter4><label>Country</label><value>India</value></filter4>
        <filter5><label>Internal Posting Location</label><value>Bangalore</value></filter5>
      </Job></Job-Listing>
    """
    calls = []

    async def rejected_json_post(url, body):
        raise RuntimeError("JSON service disabled")

    async def fake_xml_get(url, params=None):
        assert url == "https://career5.successfactors.eu/career"
        assert params == {
            "company": "SAP",
            "career_ns": "job_listing_summary",
            "rcm_site_locale": "en_US",
            "resultType": "XML",
        }
        return xml

    async def fake_text_get(url, params=None, request_headers=None):
        calls.append(url)
        if url == "https://jobs.sap.example/search/":
            if params:
                assert params == {"q": "456251", "locationsearch": "India"}
                return (
                    '<a href="/job/Bangalore-Developer-Associate-Cloud-ERP/'
                    '1426371233/">Developer Associate - Cloud ERP</a>'
                )
            return "\"ssoUrl\" : 'https://career5.successfactors.eu'"
        assert url == (
            "https://jobs.sap.example/job/Bangalore-Developer-Associate-Cloud-ERP/"
            "1426371233/"
        )
        return _successfactors_detail(
            "456251", "Developer Associate - Cloud ERP", apply_id="1426371233",
        ).replace("Bangalore, IN", "Bangalore, India").replace(
            "locale=en_GB", "locale=en_US"
        )

    monkeypatch.setattr(ats, "json_post", rejected_json_post)
    monkeypatch.setattr(ats, "xml_get", fake_xml_get)
    monkeypatch.setattr(ats, "text_get", fake_text_get)
    leads = _run(ats.scrape_successfactors(
        "sap", "jobs.sap.example", "en_US", "sap.com",
    ))

    assert len(leads) == 1
    lead = leads[0]
    assert lead["company"] == "SAP"
    assert lead["posted_date"] == "2026-08-24"
    assert lead["location"] == "Bangalore, India"
    assert lead["source_meta"]["portal_generation"] == "xml"
    assert lead["source_meta"]["canonical_page_id"] == "1426371233"
    assert lead["source_meta"]["canonical_url_resolved_from_public_search"] is True
    assert lead["source_meta"]["experience_level"] == ["Graduate"]
    assert lead["source_meta"]["xml_fields"]["Country"] == "India"
    assert calls == [
        "https://jobs.sap.example/search/",
        "https://jobs.sap.example/search/",
        (
            "https://jobs.sap.example/job/Bangalore-Developer-Associate-Cloud-ERP/"
            "1426371233/"
        ),
    ]


def test_successfactors_xml_mapping_requires_exact_same_host_title(monkeypatch):
    assert ats._successfactors_search_detail_url(
        """
        <a href="https://evil.example/job/Data-Engineer/1/">Data Engineer I</a>
        <a href="/job/Data-Engineer/2/">Different title</a>
        """,
        "jobs.acme.example",
        "Data Engineer I",
    ) == ""


def test_successfactors_xml_fallback_rejects_untrusted_declared_host(monkeypatch):
    xml_called = False

    async def rejected_json_post(url, body):
        raise RuntimeError("disabled")

    async def fake_text_get(url, params=None, request_headers=None):
        return "\"ssoUrl\" : 'https://career5.successfactors.eu.evil.example'"

    async def fake_xml_get(url, params=None):
        nonlocal xml_called
        xml_called = True
        return ""

    monkeypatch.setattr(ats, "json_post", rejected_json_post)
    monkeypatch.setattr(ats, "text_get", fake_text_get)
    monkeypatch.setattr(ats, "xml_get", fake_xml_get)
    assert _run(ats.scrape_successfactors("sap", "jobs.sap.example", "en_US")) == []
    assert xml_called is False

    async def mismatch_text_get(url, params=None, request_headers=None):
        return _successfactors_detail("different", "Data Engineer I")

    monkeypatch.setattr(ats, "text_get", mismatch_text_get)
    assert _run(ats.scrape_successfactors("acme", "jobs.acme.example")) == []


def test_successfactors_rejects_hostile_target_without_network(monkeypatch):
    called = False

    async def fake_json_post(url, body):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(ats, "json_post", fake_json_post)
    assert _run(ats.scrape_successfactors("../../bad", "jobs.acme.example")) == []
    assert _run(ats.scrape_successfactors("acme", "127.0.0.1")) == []
    assert _run(ats.scrape_successfactors("acme", "jobs.acme.example", "bad")) == []
    assert _run(ats.scrape_successfactors(
        "acme", "jobs.acme.example", employer_domain="bad_domain",
    )) == []
    assert called is False


def test_successfactors_dispatches_production_target(monkeypatch):
    seen = {}

    async def fake_successfactors(company_id, site_host, locale="en_GB", employer_domain=""):
        seen.update({
            "company_id": company_id, "site_host": site_host,
            "locale": locale, "employer_domain": employer_domain,
        })
        return []

    monkeypatch.setattr(ats, "scrape_successfactors", fake_successfactors)
    _run(ats.scrape_target(
        "ats:successfactors:danfossas:jobs.danfoss.com:en_GB:danfoss.com"
    ))
    assert seen == {
        "company_id": "danfossas", "site_host": "jobs.danfoss.com",
        "locale": "en_GB", "employer_domain": "danfoss.com",
    }


def _jibe_job(*, searchable=True, applyable=True, title="Software Engineering Intern"):
    return {
        "slug": "89608",
        "language": "en-us",
        "languages": ["en-us"],
        "client_code": "amd",
        "req_id": "89608",
        "title": title,
        "description": (
            "<p>Build Python and C++ software, automated tests, developer tools, "
            "and machine learning infrastructure with the engineering team.</p>"
        ),
        "location_name": "AMD Hyderabad",
        "street_address": "HITEC City",
        "city": "Hyderabad",
        "state": "Telangana",
        "country": "India",
        "country_code": "IN",
        "postal_code": "500081",
        "location_type": "SUB_LOCALITY_1",
        "latitude": 17.438198,
        "longitude": 78.3821654,
        "additional_locations": [],
        "categories": ["Engineering", "Computer and IT"],
        "tags1": ["Student"],
        "department": "Software Engineering",
        "benefits": "<p>Competitive pay and mentoring.</p>",
        "employment_type": "INTERN",
        "qualifications": "<p>Final-year B.Tech Computer Science student.</p>",
        "responsibilities": "<p>Ship production code and automated tests.</p>",
        "hiring_organization": "Advanced Micro Devices, Inc.",
        "hiring_organization_logo": "https://careers.amd.example/logo.png",
        "posted_date": "2026-08-24T10:00:00+05:30",
        "apply_url": "https://global-external-amd.icims.com/jobs/89608/login",
        "internal": False,
        "external": False,
        "searchable": searchable,
        "applyable": applyable,
        "li_easy_applyable": False,
        "ats_code": "ICIMS",
        "hiring_flow_name": "External",
        "isFrontLineAIJob": False,
        "update_date": "2026-08-25T10:00:00+05:30",
        "create_date": "2026-08-24T10:00:00+05:30",
        "full_location": "Hyderabad, Telangana, India",
        "meta_data": {
            "last_mod": "2026-08-25T11:00:00+05:30",
            "icims": {
                "jps_is_public": True,
                "date_updated": "2026-08-25T05:30:00Z",
                "uuid": "job-uuid",
                "revision_int": 2,
                "primary_posted_site_object": {
                    "site": "global-external-amd", "tenantId": "12834",
                    "datePosted": "2026-08-24T10:00:00+05:30",
                },
            },
            "googlejobs": {
                "jobName": "projects/public/jobs/1",
                "jobHash": "hash",
                "derivedInfo": {
                    "jobCategories": ["COMPUTER_AND_IT"],
                    "locations": [{"postalAddress": {"regionCode": "IN"}}],
                },
            },
            "import_id": "import-1",
            "import_source": "ImporterService",
            "redirectOnApply": True,
            "gdpr": False,
        },
    }


def test_jibe_scans_india_and_rechecks_rich_public_detail(monkeypatch):
    calls = []

    async def fake_json_get(url, params=None):
        calls.append((url, params))
        if url == "https://careers.amd.example/api/jobs":
            assert params == {"location": "India", "page": 1}
            return {
                "jobs": [
                    {"data": _jibe_job()},
                    {"data": {**_jibe_job(title="Finance Intern"), "req_id": "2", "slug": "2"}},
                    {"data": {**_jibe_job(title="Senior Software Engineer"), "req_id": "3", "slug": "3"}},
                    {"data": {**_jibe_job(), "req_id": "4", "slug": "4", "country": "Canada"}},
                ],
                "totalCount": 4,
                "filter": {"displayLimit": 10},
            }
        assert url == "https://careers.amd.example/api/jobs/89608/en-us"
        assert params is None
        return _jibe_job()

    monkeypatch.setattr(ats, "json_get", fake_json_get)
    leads = _run(ats.scrape_jibe(
        "amd", "careers.amd.example", "careers-home", "en-us", "amd.com",
    ))

    assert len(leads) == 1
    lead = leads[0]
    assert lead["company"] == "Advanced Micro Devices, Inc."
    assert lead["location"] == "Hyderabad, Telangana, India"
    assert lead["apply_url"] == "https://global-external-amd.icims.com/jobs/89608/login"
    assert lead["url"] == "https://careers.amd.example/careers-home/jobs/89608?lang=en-us"
    assert lead["source_meta"]["postal_code"] == "500081"
    assert lead["source_meta"]["latitude"] == 17.438198
    assert lead["source_meta"]["icims_public"] is True
    assert lead["source_meta"]["google_derived_categories"] == ["COMPUTER_AND_IT"]
    assert "Competitive pay" in lead["description"]
    record = source_record_from_lead(lead)
    assert record.source_kind == SourceKind.ATS
    assert record.provider == "jibe"
    assert record.provider_requisition_id == "89608"
    assert record.employer_domain == "amd.com"
    assert calls[-1][0].endswith("/api/jobs/89608/en-us")


def test_jibe_rejects_closed_or_unsafe_apply(monkeypatch):
    async def fake_json_get(url, params=None):
        if url.endswith("/api/jobs"):
            return {"jobs": [{"data": _jibe_job()}], "totalCount": 1}
        return _jibe_job(searchable=False)

    monkeypatch.setattr(ats, "json_get", fake_json_get)
    assert _run(ats.scrape_jibe("amd", "careers.amd.example")) == []

    async def unsafe_apply_json_get(url, params=None):
        if url.endswith("/api/jobs"):
            return {"jobs": [{"data": _jibe_job()}], "totalCount": 1}
        return {**_jibe_job(), "apply_url": "https://evil.example/jobs/89608/login"}

    monkeypatch.setattr(ats, "json_get", unsafe_apply_json_get)
    assert _run(ats.scrape_jibe("amd", "careers.amd.example")) == []


def test_jibe_rejects_hostile_target_without_network(monkeypatch):
    called = False

    async def fake_json_get(url, params=None):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(ats, "json_get", fake_json_get)
    assert _run(ats.scrape_jibe("../bad", "careers.amd.example")) == []
    assert _run(ats.scrape_jibe("amd", "127.0.0.1")) == []
    assert _run(ats.scrape_jibe("amd", "careers.amd.example", "../bad")) == []
    assert _run(ats.scrape_jibe("amd", "careers.amd.example", locale="bad")) == []
    assert called is False


def test_jibe_dispatches_production_target(monkeypatch):
    seen = {}

    async def fake_jibe(client_code, site_host, context="careers-home", locale="en-us", employer_domain=""):
        seen.update({
            "client_code": client_code, "site_host": site_host, "context": context,
            "locale": locale, "employer_domain": employer_domain,
        })
        return []

    monkeypatch.setattr(ats, "scrape_jibe", fake_jibe)
    _run(ats.scrape_target(
        "ats:jibe:amd:careers.amd.com:careers-home:en-us:amd.com"
    ))
    assert seen == {
        "client_code": "amd", "site_host": "careers.amd.com",
        "context": "careers-home", "locale": "en-us", "employer_domain": "amd.com",
    }


def test_oraclehcm_discovers_india_cse_roles_and_rechecks_detail_liveness(monkeypatch):
    search_calls: list[dict] = []
    detail_calls: list[str] = []
    base_row = {
        "PrimaryLocation": "Bengaluru, Karnataka, India",
        "PrimaryLocationCountry": "IN",
        "PostedDate": "2026-08-24",
        "PostingEndDate": "2026-09-30",
        "secondaryLocations": [{"Name": "Hyderabad, Telangana, India"}],
    }
    rows = [
        {
            **base_row,
            "Id": "91137",
            "Title": "Intern, Building Technology Systems",
            "ShortDescriptionStr": "Support ICT systems and software tooling.",
            "JobFunction": "Building Technology Systems",
        },
        {
            **base_row,
            "Id": "20002",
            "Title": "Software Engineer",
            "ShortDescriptionStr": "Build Python cloud services.",
        },
        {
            **base_row,
            "Id": "closed",
            "Title": "Data Science Intern",
            "ShortDescriptionStr": "Train machine learning models.",
        },
        {
            **base_row,
            "Id": "senior",
            "Title": "Senior Software Engineer",
            "ShortDescriptionStr": "Build software.",
        },
        {
            **base_row,
            "Id": "nontech",
            "Title": "Finance Intern",
            "ShortDescriptionStr": "Prepare accounting reports.",
        },
        {
            **base_row,
            "Id": "outside-india",
            "Title": "Software Intern",
            "PrimaryLocation": "Toronto, Canada",
            "PrimaryLocationCountry": "CA",
        },
    ]

    async def fake_json_get(url, params=None):
        if url.endswith("/recruitingCEJobRequisitions"):
            search_calls.append(params)
            return {"items": [{"TotalJobsCount": len(rows), "requisitionList": rows}]}
        assert url.endswith("/recruitingCEJobRequisitionDetails")
        finder = params["finder"]
        detail_calls.append(finder)
        requisition_id = finder.split('Id="', 1)[1].split('"', 1)[0]
        if requisition_id == "closed":
            return {"items": []}
        row = next(item for item in rows if item["Id"] == requisition_id)
        return {"items": [{
            **row,
            "RequisitionId": f"internal-{requisition_id}",
            "ExternalDescriptionStr": "<p>Build production systems.</p>",
            "ExternalResponsibilitiesStr": "<p>Own testing and delivery.</p>",
            "ExternalQualificationsStr": "<p>B.Tech CSE or equivalent.</p>",
            "LegalEmployer": "WSP India",
            "LegalEmployerId": "legal-1",
            "BusinessUnit": "Digital",
            "BusinessUnitId": "bu-1",
            "Department": "Engineering",
            "Organization": "Technology",
            "OrganizationId": "org-1",
            "JobFunction": row.get("JobFunction") or "Software Engineering",
            "JobFamily": "Digital Technology",
            "JobType": "Intern" if "Intern" in row["Title"] else "Regular",
            "JobSchedule": "Full time",
            "WorkerType": "Employee",
            "ContractType": "Fixed term",
            "StudyLevel": "Bachelor's degree",
            "WorkplaceType": "Hybrid",
            "WorkplaceTypeCode": "ORA_HYBRID",
            "WorkDurationMonths": 6,
            "WorkHours": 40,
            "DomesticTravelRequired": "No",
            "applicationQuestions": "must never be retained",
        }]}

    monkeypatch.setattr(ats, "json_get", fake_json_get)
    leads = _run(ats.scrape_oraclehcm(
        "wsp",
        "emit.fa.ca3.oraclecloud.com",
        "CX_2001",
        "wsp.com",
    ))

    assert len(search_calls) == len(
        ats._ORACLEHCM_EARLY_SEARCHES + ats._ORACLEHCM_TECH_SEARCHES
    )
    assert all("location=India" in call["finder"] for call in search_calls)
    assert all("limit=25" in call["finder"] for call in search_calls)
    assert len(detail_calls) == 3
    assert {lead["title"] for lead in leads} == {
        "Intern, Building Technology Systems", "Software Engineer",
    }
    intern = next(lead for lead in leads if "Intern" in lead["title"])
    assert intern["company"] == "WSP"
    assert intern["workplace"] == "hybrid"
    assert intern["location"] == (
        "Bengaluru, Karnataka, India; Hyderabad, Telangana, India"
    )
    assert intern["posted_date"] == "2026-08-24"
    assert intern["deadline"] == "2026-09-30"
    assert intern["active_hint"] == "active"
    assert "B.Tech CSE or equivalent" in intern["description"]
    assert "Business unit: Digital" in intern["description"]
    assert intern["source_meta"]["work_duration_months"] == 6
    assert intern["source_meta"]["work_hours"] == 40
    assert intern["source_meta"]["employer_domain"] == "wsp.com"
    assert "applicationQuestions" not in str(intern)
    record = source_record_from_lead(intern)
    assert record.source_kind == SourceKind.ATS
    assert record.provider_requisition_id == "91137"
    assert record.employer_domain == "wsp.com"


def test_oraclehcm_rejects_untrusted_host_and_site_without_network(monkeypatch):
    called = False

    async def fake_json_get(url, params=None):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(ats, "json_get", fake_json_get)
    assert _run(ats.scrape_oraclehcm("bad", "example.com", "CX_1")) == []
    assert _run(ats.scrape_oraclehcm(
        "bad", "emit.fa.ca3.oraclecloud.com", "not-a-site"
    )) == []
    assert called is False


def test_scrape_target_dispatches_new_platform_prefixes(monkeypatch):
    seen = {}

    async def fake_teamtailor(slug):
        seen["teamtailor"] = slug
        return []

    monkeypatch.setattr(ats, "scrape_teamtailor", fake_teamtailor)
    _run(ats.scrape_target("ats:teamtailor:acme"))
    assert seen["teamtailor"] == "acme"


def test_scrape_target_dispatches_oraclehcm(monkeypatch):
    seen = {}

    async def fake_oraclehcm(slug, host, site_number, employer_domain=""):
        seen.update({
            "slug": slug,
            "host": host,
            "site_number": site_number,
            "employer_domain": employer_domain,
        })
        return []

    monkeypatch.setattr(ats, "scrape_oraclehcm", fake_oraclehcm)
    _run(ats.scrape_target(
        "ats:oraclehcm:wsp:emit.fa.ca3.oraclecloud.com:CX_2001:wsp.com"
    ))
    assert seen == {
        "slug": "wsp",
        "host": "emit.fa.ca3.oraclecloud.com",
        "site_number": "CX_2001",
        "employer_domain": "wsp.com",
    }


def test_scrape_target_dispatches_eightfold(monkeypatch):
    seen = {}

    async def fake_eightfold(slug, host, domain):
        seen.update({"slug": slug, "host": host, "domain": domain})
        return []

    monkeypatch.setattr(ats, "scrape_eightfold", fake_eightfold)
    _run(ats.scrape_target(
        "ats:eightfold:micron:app.eightfold.ai:micron.com"
    ))
    assert seen == {
        "slug": "micron", "host": "app.eightfold.ai", "domain": "micron.com",
    }


def test_scrape_target_dispatches_icims(monkeypatch):
    seen = {}

    async def fake_icims(slug, host, employer_domain=""):
        seen.update({
            "slug": slug, "host": host, "employer_domain": employer_domain,
        })
        return []

    monkeypatch.setattr(ats, "scrape_icims", fake_icims)
    _run(ats.scrape_target(
        "ats:icims:waters:internationalcareers-waters.icims.com:waters.com"
    ))
    assert seen == {
        "slug": "waters",
        "host": "internationalcareers-waters.icims.com",
        "employer_domain": "waters.com",
    }


def test_direct_oraclehcm_jobsearch_alias_resolves_public_site_number(monkeypatch):
    seen = {}

    async def fake_text_get(url):
        assert "/sites/jobsearch/job/91137" in url
        return '<body data-sitenumber="CX_2001"></body>'

    async def fake_oraclehcm(slug, host, site_number, employer_domain=""):
        seen.update({"slug": slug, "host": host, "site_number": site_number})
        return []

    monkeypatch.setattr(ats, "text_get", fake_text_get)
    monkeypatch.setattr(ats, "scrape_oraclehcm", fake_oraclehcm)
    _run(ats.scrape_direct_ats_url(
        "https://emit.fa.ca3.oraclecloud.com/hcmUI/CandidateExperience/"
        "en/sites/jobsearch/job/91137"
    ))
    assert seen == {
        "slug": "emit",
        "host": "emit.fa.ca3.oraclecloud.com",
        "site_number": "CX_2001",
    }
