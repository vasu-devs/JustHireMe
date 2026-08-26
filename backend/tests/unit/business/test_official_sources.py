from __future__ import annotations

import asyncio
import base64
import json
from urllib.parse import parse_qs, urlsplit

from discovery.sources import official
from opportunities.canonicalize import source_record_from_lead
from opportunities.models import SourceKind


def test_official_technical_title_signal_covers_data_science_noun_phrase() -> None:
    assert official._OFFICIAL_TECH_TITLE.search("Senior Advisor, Data Science")


def test_deliveroo_india_projects_only_public_job_facts(monkeypatch) -> None:
    async def fake_json_get(url, params=None):
        assert url == official.DELIVEROO_ROLES_API
        assert params["locations_slug"] == "india"
        return [{
            "id": 123,
            "status": "publish",
            "link": "https://careers.deliveroo.co.uk/role/software-intern-abc/",
            "date_gmt": "2026-08-20T10:00:00",
            "modified_gmt": "2026-08-24T10:00:00",
            "title": {"rendered": "Software Engineering Intern"},
            "content": {"rendered": "<p>Build production Python services.</p>"},
            "meta": {
                "ats_location": "Hyderabad - Main Office",
                "ats_remote": False,
                "ashby_req_id": "R123",
                "ashby_questions": "must never be retained",
                "ashby_surveys": "must never be retained",
            },
        }]

    monkeypatch.setattr(official, "json_get", fake_json_get)

    lead = asyncio.run(official.scrape_deliveroo_india())[0]
    record = source_record_from_lead(lead)

    assert lead["company"] == "Deliveroo"
    assert lead["location"] == "Hyderabad - Main Office"
    assert lead["apply_url"].endswith("/apply/")
    assert "production Python" in lead["description"]
    assert "ashby_questions" not in str(lead)
    assert "ashby_surveys" not in str(lead)
    assert record.provider_requisition_id == "R123"
    assert record.source_kind == SourceKind.DIRECT_EMPLOYER
    assert record.employer_domain == "deliveroo.co.uk"


def test_deliveroo_ignores_non_public_and_malformed_rows(monkeypatch) -> None:
    async def fake_json_get(url, params=None):
        return [
            {"status": "draft", "title": {"rendered": "Hidden"}, "link": "https://example.com"},
            {"status": "publish", "title": {"rendered": "Missing URL"}},
            "not a row",
        ]

    monkeypatch.setattr(official, "json_get", fake_json_get)
    assert asyncio.run(official.scrape_deliveroo_india()) == []


def test_zeqo_reads_all_live_paid_role_cards_and_ignores_hydration_duplicates(monkeypatch) -> None:
    card_class = "bg-white border border-border-theme rounded-3xl p-8"
    raw_html = f"""
      <main>
        <div class="{card_class}">
          <h2>Founding Full Stack Engineer (Intern to FTE)</h2>
          <div><span>Remote / Dehradun</span><span>₹25,000/mo min base</span></div>
          <a href="mailto:hello@example.invalid">Apply Now →</a>
          <h3>The Role</h3><p>Build offline-first mobile and AI systems.</p>
          <h3>Perks &amp; Conversion Path</h3><p>Successful internships convert to FTE.</p>
        </div>
        <div class="{card_class}">
          <h2>Cloud Infrastructure Engineer (LLM Routing)</h2>
          <div><span>Remote / Jaipur</span><span>₹20,000 - ₹35,000/mo</span></div>
          <a href="mailto:hello@example.invalid">Apply Now →</a>
          <p>Open to freshers with 0–2 years. Build a multi-provider LLM router.</p>
        </div>
        <div class="{card_class}">
          <h2>Closed Role</h2><span>Remote</span><p>No apply control.</p>
        </div>
      </main>
      <script>Founding Full Stack Engineer (Intern to FTE)</script>
    """

    async def fake_text_get(url, params=None, *, request_headers=None):
        assert url == official.ZEQO_CAREERS
        return raw_html

    monkeypatch.setattr(official, "text_get", fake_text_get)
    leads = asyncio.run(official.scrape_zeqo_early_career())
    records = [source_record_from_lead(lead) for lead in leads]

    assert [lead["title"] for lead in leads] == [
        "Founding Full Stack Engineer (Intern to FTE)",
        "Cloud Infrastructure Engineer (LLM Routing)",
    ]
    assert leads[0]["location"] == "Remote; Dehradun, India"
    assert leads[0]["workplace"] == "remote"
    assert leads[0]["source_meta"]["base_salary"] == {
        "currency": "INR", "interval": "month", "min": 25000, "max": None,
    }
    assert leads[1]["source_meta"]["base_salary"]["max"] == 35000
    assert "Conversion Path" in leads[0]["description"]
    assert records[0].source_kind == SourceKind.DIRECT_EMPLOYER
    assert records[0].provider_requisition_id.startswith("founding-full-stack")
    assert records[0].canonical_source_url != records[1].canonical_source_url
    assert all(record.employer_domain == "zeqo.in" for record in records)


def test_zeqo_returns_no_roles_when_visible_apply_cards_are_absent(monkeypatch) -> None:
    async def fake_text_get(url, params=None, *, request_headers=None):
        return '<main><div><h2>General careers interest</h2></div></main>'

    monkeypatch.setattr(official, "text_get", fake_text_get)
    assert asyncio.run(official.scrape_zeqo_early_career()) == []


def test_aicte_projects_paid_technical_public_facts_without_application_fields(
    monkeypatch,
) -> None:
    requisition_id = "INTERNSHIP_123"
    uid = base64.b64encode(requisition_id.encode()).decode()
    detail_path = f"internship-details.php?uid={uid}"
    listing_html = f"""
      <main>
        <div class="internships-list"><div class="card internship-item">
          <h3 class="job-title">AI / ML Engineering Intern</h3>
          <li class="stipend"><h6>Stipend</h6><span>₹10,000 to ₹15,000 /month</span></li>
          <a href="{detail_path}">View Details</a>
        </div></div>
        <div class="internships-list"><div class="card internship-item">
          <h3 class="job-title">Software Engineering Intern</h3>
          <li class="stipend"><h6>Stipend</h6><span>Unpaid</span></li>
          <a href="internship-details.php?uid=unsafe">View Details</a>
        </div></div>
        <div class="internships-list"><div class="card internship-item">
          <h3 class="job-title">Sales Intern</h3>
          <li class="stipend"><h6>Stipend</h6><span>₹20,000 /month</span></li>
          <a href="internship-details.php?uid=nontech">View Details</a>
        </div></div>
      </main>
    """
    detail_html = """
      <h3 class="job-title">AI / ML Engineering Intern</h3>
      <h5 class="company-name">Example AI Private Limited</h5>
      <li class="wfh"><span>Virtual Internship</span></li>
      <li class="posted-on"><span>22-Aug-2026</span></li>
      <li class="location"><span>Pan India, </span></li>
      <h6>Start date</h6><span>Immediately</span>
      <h6>Duration</h6><span>6 Months</span>
      <h6>Stipend</h6><span>₹10,000 to ₹15,000 /month</span>
      <h6>No of Credits</h6><span>4</span>
      <h6>Apply by</h6><span>30-Sep-2026</span>
      <section><h4>About the program</h4><p>Build Python ML services.</p></section>
      <section><h4>Who can apply?</h4><ol><li>Final-year CSE students</li></ol></section>
      <section><h4>Terms of Engagement</h4><p>Stipend paid monthly.</p></section>
      <section><h4>Number of openings</h4><p>5</p></section>
      <form><input name="csrf_token" value="private-token">
        <input name="candidate_email" value="private@example.com">
        <label>Custom application question must never persist</label>
        <button disabled id="applyBtn" name="apply_login_private">Apply Now</button>
      </form>
    """
    requested: list[str] = []

    async def fake_text_get(url, params=None, *, request_headers=None):
        requested.append(url)
        return listing_html if url == official.AICTE_CSE_SEARCH else detail_html

    monkeypatch.setattr(official, "text_get", fake_text_get)
    leads = asyncio.run(official.scrape_aicte_cse_internships())

    assert requested == [
        official.AICTE_CSE_SEARCH,
        f"{official.AICTE_DETAILS_BASE}{detail_path}",
    ]
    assert len(leads) == 1
    lead = leads[0]
    record = source_record_from_lead(lead)
    assert lead["company"] == "Example AI Private Limited"
    assert lead["location"] == "Pan India"
    assert lead["workplace"] == "remote"
    assert lead["deadline"] == "30-Sep-2026"
    assert "Build Python ML services" in lead["description"]
    assert lead["source_meta"]["base_salary"] == {
        "currency": "INR", "interval": "month", "min": 10000, "max": 15000,
    }
    assert lead["source_meta"]["number_of_openings"] == "5"
    assert record.provider_requisition_id == requisition_id
    assert record.source_kind == SourceKind.AGGREGATOR
    serialized = json.dumps(lead)
    assert "private-token" not in serialized
    assert "private@example.com" not in serialized
    assert "Custom application question" not in serialized


def test_aicte_rejects_detail_without_live_apply_control(monkeypatch) -> None:
    uid = base64.b64encode(b"INTERNSHIP_456").decode()
    listing_html = f"""
      <main><div class="internships-list">
        <h3 class="job-title">Cloud Engineering Intern</h3>
        <h6>Stipend</h6><span>₹12,000 /month</span>
        <a href="internship-details.php?uid={uid}">View Details</a>
      </div></main>
    """

    async def fake_text_get(url, params=None, *, request_headers=None):
        if url == official.AICTE_CSE_SEARCH:
            return listing_html
        return """
          <h3 class="job-title">Cloud Engineering Intern</h3>
          <h5 class="company-name">Closed Example</h5>
          <h6>Stipend</h6><span>₹12,000 /month</span>
          <p>This listing no longer has an application control.</p>
        """

    monkeypatch.setattr(official, "text_get", fake_text_get)
    assert asyncio.run(official.scrape_aicte_cse_internships()) == []


def test_ibm_india_early_career_uses_official_filters_and_full_public_facts(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_json_post(url, body):
        assert url == official.IBM_SEARCH_API
        calls.append(body)
        level = body["post_filter"]["bool"]["must"][0]["term"]["field_keyword_18"]
        if level == "Entry Level":
            return {"hits": {"total": {"value": 0}, "hits": []}}
        return {
            "hits": {
                "total": {"value": 1},
                "hits": [{
                    "_id": "hash-114791",
                    "_source": {
                        "title": "Technical Support Representative Intern",
                        "url": "https://careers.ibm.com/careers/JobDetail?jobId=114791",
                        "description": "Short public summary",
                        "body": (
                            "Build and monitor production applications. Only open for candidates "
                            "who have applied under the Prime Minister's Internship Scheme through "
                            "their portal. India Infrastructure & Technology Hybrid Internship "
                            "Multiple Cities (0063) IBM India Private Limited"
                        ),
                        "country": ["in"],
                        "language": "en",
                        "dcdate": "2026-08-12",
                        "effectivedate": "2026-05-11",
                        "expiredate": "2030-05-11T00:00:00Z",
                        "processedtime": "2026-08-25T05:16:58Z",
                        "field_keyword_08": "Infrastructure & Technology",
                        "field_keyword_18": "Internship",
                        "field_keyword_19": "Multiple Cities",
                    },
                }],
            }
        }

    monkeypatch.setattr(official, "json_post", fake_json_post)

    lead = asyncio.run(official.scrape_ibm_india_early_career())[0]
    record = source_record_from_lead(lead)

    assert len(calls) == 2
    assert all(call["post_filter"]["bool"]["must"][1] == {"term": {"country": "in"}} for call in calls)
    assert set(call["post_filter"]["bool"]["must"][0]["term"]["field_keyword_18"] for call in calls) == {
        "Internship", "Entry Level",
    }
    assert lead["company"] == "IBM"
    assert lead["location"] == "Multiple Cities, India"
    assert lead["workplace"] == "hybrid"
    assert "Career area: Infrastructure & Technology" in lead["description"]
    assert lead["source_meta"]["index_expire_date"].startswith("2030-")
    assert "deadline" not in lead
    assert record.provider_requisition_id == "114791"
    assert record.source_kind == SourceKind.DIRECT_EMPLOYER
    assert record.employer_domain == "ibm.com"
    assert record.provider_published_text == "2026-08-12"
    assert record.provider_updated_text == "2026-08-25T05:16:58Z"


def test_ibm_skips_malformed_results_and_deduplicates_requisitions(monkeypatch) -> None:
    async def fake_json_post(url, body):
        if body["post_filter"]["bool"]["must"][0]["term"]["field_keyword_18"] == "Entry Level":
            return {"hits": {"total": {"value": 0}, "hits": []}}
        source = {
            "title": "Software Intern",
            "url": "https://careers.ibm.com/careers/JobDetail?jobId=42",
            "body": "Build Python services. India Software Engineering Internship Bengaluru, IN",
            "country": ["in"],
            "field_keyword_18": "Internship",
            "field_keyword_19": "Bengaluru, IN",
        }
        return {"hits": {"total": {"value": 4}, "hits": [
            {"_id": "one", "_source": source},
            {"_id": "duplicate", "_source": source},
            {"_id": "missing-url", "_source": {"title": "Broken"}},
            "not a hit",
        ]}}

    monkeypatch.setattr(official, "json_post", fake_json_post)
    leads = asyncio.run(official.scrape_ibm_india_early_career())
    assert [lead["source_meta"]["id"] for lead in leads] == ["42"]


def test_amazon_india_cse_uses_country_filter_full_facts_and_strict_location(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_text_get(url, params=None, *, request_headers=None):
        assert url == official.AMAZON_SEARCH_API
        assert params["country"] == "IND"
        assert request_headers["Accept-Encoding"] == "identity"
        calls.append(params)
        rows = []
        if params["base_query"] == "software development engineer":
            rows = [
                {
                    "id": "uuid-1",
                    "title": "Software Development Engineer I",
                    "location": "IN, KA, Bengaluru",
                    "job_path": "/en/jobs/123/software-development-engineer-i",
                    "posted_date": "August 25, 2026",
                    "description": "<p>Build distributed systems.</p>",
                    "basic_qualifications": "1-2 years with Java and Python",
                    "preferred_qualifications": "AWS experience",
                    "job_category": "Software Development",
                    "business_category": "amazon-development-centre-india",
                },
                {
                    "id": "uuid-us",
                    "title": "Software Development Engineer I",
                    "location": "US, WA, Seattle",
                    "job_path": "/en/jobs/999/us-role",
                },
            ]
        return json.dumps({"hits": len(rows), "jobs": rows})

    monkeypatch.setattr(official, "text_get", fake_text_get)

    lead = asyncio.run(official.scrape_amazon_india_cse())[0]
    record = source_record_from_lead(lead)

    assert len(calls) == len(official.AMAZON_CSE_SEARCHES)
    assert lead["company"] == "Amazon"
    assert lead["location"] == "Bengaluru, KA, India"
    assert "Basic qualifications" in lead["description"]
    assert lead["source_meta"]["id"] == "123"
    assert record.provider_requisition_id == "123"
    assert record.source_kind == SourceKind.DIRECT_EMPLOYER
    assert record.employer_domain == "amazon.jobs"


def test_microsoft_india_cse_pages_search_and_parses_public_json_ld(monkeypatch) -> None:
    search_calls: list[dict] = []

    async def fake_json_get(url, params=None):
        assert url == official.MICROSOFT_SEARCH_API
        search_calls.append(params)
        positions = []
        if params["query"] == "intern":
            positions = [{
                "id": 1970,
                "displayJobId": "200041085",
                "name": "Software Engineering INTERN",
                "locations": ["India, Multiple Locations, Multiple Locations"],
                "standardizedLocations": ["IN"],
                "department": "Software Engineering",
                "workLocationOption": "onsite",
                "positionUrl": "/careers/job/1970",
            }]
        return {"data": {"count": len(positions), "positions": positions}}

    async def fake_text_get(url, params=None, *, request_headers=None):
        assert url == f"{official.MICROSOFT_CAREERS_BASE}/careers/job/1970"
        payload = {
            "@context": "http://schema.org",
            "@type": "JobPosting",
            "title": "Software Engineering INTERN",
            "description": (
                "Build software. Currently pursuing a CS degree with one semester remaining."
            ),
            "datePosted": "2026-07-01T05:07:55",
            "validThrough": "2026-12-28T05:07:55",
            "employmentType": "FULL_TIME",
        }
        return f'<script type="application/ld+json">{json.dumps(payload)}</script>'

    monkeypatch.setattr(official, "json_get", fake_json_get)
    monkeypatch.setattr(official, "text_get", fake_text_get)

    lead = asyncio.run(official.scrape_microsoft_india_cse())[0]
    record = source_record_from_lead(lead)

    assert len(search_calls) == len(official.MICROSOFT_CSE_SEARCHES)
    assert lead["company"] == "Microsoft"
    assert lead["title"] == "Software Engineering INTERN"
    assert lead["deadline"] == "2026-12-28T05:07:55"
    assert lead["source_meta"]["id"] == "200041085"
    assert record.provider_requisition_id == "200041085"
    assert record.source_kind == SourceKind.DIRECT_EMPLOYER
    assert record.employer_domain == "microsoft.com"


def test_qualcomm_india_early_career_reads_internship_jobposting_facts(monkeypatch) -> None:
    search_calls: list[dict] = []

    async def fake_json_get(url, params=None):
        assert url == official.QUALCOMM_SEARCH_API
        assert params["domain"] == "qualcomm.com"
        search_calls.append(params)
        positions = []
        if params["query"] == "intern":
            positions = [{
                "id": 446720384411,
                "displayJobId": "3095138",
                "name": "Interim Engineering Intern_Systems- 2027",
                "locations": ["Bangalore, India", "Hyderabad, Telangana, India"],
                "standardizedLocations": ["Bengaluru, KA, IN", "Hyderabad, TS, IN"],
                "department": "Interim Engineering Intern - HW",
                "workLocationOption": "onsite",
                "positionUrl": "/careers/job/446720384411",
            }]
        return {"data": {"count": len(positions), "positions": positions}}

    async def fake_text_get(url, params=None, *, request_headers=None):
        assert url == f"{official.QUALCOMM_CAREERS_BASE}/careers/job/446720384411"
        payload = {
            "@context": "http://schema.org",
            "@type": "JobPosting",
            "title": "Interim Engineering Intern_Systems- 2027",
            "description": "Design wireless systems with Python and machine learning.",
            "datePosted": "2026-08-12T00:00:00",
            "validThrough": "2027-02-08T00:00:00",
            "employmentType": "FULL_TIME",
        }
        return f'<script type="application/ld+json">{json.dumps(payload)}</script>'

    monkeypatch.setattr(official, "json_get", fake_json_get)
    monkeypatch.setattr(official, "text_get", fake_text_get)

    lead = asyncio.run(official.scrape_qualcomm_india_early_career())[0]
    record = source_record_from_lead(lead)

    assert len(search_calls) == len(official.QUALCOMM_EARLY_SEARCHES)
    assert lead["company"] == "Qualcomm"
    assert lead["location"] == "Bangalore, India; Hyderabad, Telangana, India"
    assert lead["deadline"] == "2027-02-08T00:00:00"
    assert record.provider_requisition_id == "3095138"
    assert record.source_kind == SourceKind.DIRECT_EMPLOYER
    assert record.employer_domain == "qualcomm.com"


def test_google_india_early_career_pages_and_projects_only_technical_india_rows(monkeypatch) -> None:
    calls: list[dict] = []

    def row(job_id: str, title: str, *, country: str = "IN") -> list:
        value: list = [None] * 21
        value[0] = job_id
        value[1] = title
        value[2] = f"https://www.google.com/about/careers/applications/signin?jobId={job_id}"
        value[3] = [None, "<ul><li>Build and test production systems.</li></ul>"]
        value[4] = [None, "<p>Currently pursuing a Bachelor's degree in Computer Science.</p>"]
        value[7] = "Google"
        location = "Bengaluru, Karnataka, India" if country == "IN" else "London, UK"
        value[9] = [[location, [], "Bengaluru", "", "KA", country]]
        value[10] = [None, "Use Python, C++, data structures, and machine learning."]
        value[11] = [2]
        value[12] = [1786492800, 0]
        return value

    async def fake_text_get(url, params=None, *, request_headers=None):
        assert url == official.GOOGLE_CAREERS_SEARCH
        assert params["location"] == "India"
        assert params["target_level"] == ["EARLY", "INTERN_AND_APPRENTICE"]
        calls.append(params)
        rows = (
            [
                row("101", "Software Engineering Intern, 2027"),
                row("102", "Senior Software Engineer"),
                row("103", "Software Engineer", country="GB"),
            ]
            if params["page"] == 1
            else [row("104", "Design Verification Engineer, University Graduate")]
        )
        payload = [rows, None, 4, 3]
        return (
            "<script>AF_initDataCallback({key: 'ds:1', hash: '2', data:"
            f"{json.dumps(payload)}, sideChannel: {{}}}});</script>"
        )

    monkeypatch.setattr(official, "text_get", fake_text_get)

    leads = asyncio.run(official.scrape_google_india_early_career())
    records = [source_record_from_lead(lead) for lead in leads]

    assert [call["page"] for call in calls] == [1, 2]
    assert [lead["title"] for lead in leads] == [
        "Software Engineering Intern, 2027",
        "Design Verification Engineer, University Graduate",
    ]
    assert leads[0]["location"] == "Bengaluru, Karnataka, India"
    assert "Qualifications:" in leads[0]["description"]
    assert records[0].provider_requisition_id == "101"
    assert records[0].provider_published_text == "2026-08-12T00:00:00Z"
    assert all(record.source_kind == SourceKind.DIRECT_EMPLOYER for record in records)
    assert all(record.employer_domain == "google.com" for record in records)


def test_atlassian_india_cse_deduplicates_and_projects_only_public_tech_facts(
    monkeypatch,
) -> None:
    job = {
        "id": "25480",
        "portalId": "atlassian",
        "title": "Machine Learning Engineer, Senior",
        "type": "Engineering",
        "locations": ["Bengaluru, India", "Remote - India - Remote"],
        "category": "Engineering",
        "overview": "<p>Build production ML systems.</p>",
        "responsibilities": "<ul><li>Own model serving.</li></ul>",
        "qualifications": "Python and distributed systems.",
        "compensation": "Public compensation details where applicable.",
        "applyUrl": "https://jobs.atlassian.com/apply/25480",
        "portalJobPost": {
            "portalId": "atlassian",
            "id": "25480",
            "updatedDate": "2026-08-24T12:30:00Z",
            "portalUrl": "https://jobs.atlassian.com/25480",
        },
        "applicationQuestions": "must never be retained",
    }

    async def fake_json_get(url, params=None):
        assert url == official.ATLASSIAN_LISTINGS_API
        assert params is None
        return [
            job,
            {**job, "overview": "duplicate must not win"},
            {**job, "id": "us-1", "locations": ["Austin, United States"]},
            {
                **job,
                "id": "india-non-tech",
                "title": "Senior Finance Manager",
                "locations": ["Bengaluru, India"],
            },
            "not a row",
        ]

    monkeypatch.setattr(official, "json_get", fake_json_get)

    leads = asyncio.run(official.scrape_atlassian_india_cse())
    assert len(leads) == 1
    lead = leads[0]
    record = source_record_from_lead(lead)

    assert lead["company"] == "Atlassian"
    assert lead["workplace"] == "remote"
    assert lead["location"] == "Bengaluru, India; Remote - India - Remote"
    assert lead["apply_url"] == "https://jobs.atlassian.com/apply/25480"
    assert "Build production ML systems" in lead["description"]
    assert "Own model serving" in lead["description"]
    assert "applicationQuestions" not in str(lead)
    assert record.provider_requisition_id == "25480"
    assert record.provider_updated_text == "2026-08-24T12:30:00Z"
    assert record.source_kind == SourceKind.DIRECT_EMPLOYER
    assert record.employer_domain == "atlassian.com"


def test_oracle_india_early_cse_uses_exact_facets_and_full_public_detail(monkeypatch) -> None:
    search_calls: list[dict] = []
    job = {
        "Id": "335327",
        "Title": "Service Delivery Management Consultant 1- Support",
        "PostedDate": "2026-08-13",
        "PostingEndDate": "2026-09-30",
        "PrimaryLocationCountry": "IN",
        "PrimaryLocation": "BENGALURU, KARNATAKA, India",
        "ShortDescriptionStr": "Troubleshoot technical integration systems.",
        "WorkplaceType": "",
        "secondaryLocations": [],
    }

    async def fake_json_get(url, params=None):
        if url == official.ORACLE_RECRUITING_API + "/recruitingCEJobRequisitions":
            search_calls.append(params)
            facet = params["finder"].split("selectedFlexFieldsFacets=", 1)[1]
            rows = [
                job,
                {
                    **job,
                    "Id": "non-tech",
                    "Title": "Customer Service Coordinator",
                    "ShortDescriptionStr": "Coordinate customer requests.",
                },
                {
                    **job,
                    "Id": "outside-india",
                    "PrimaryLocationCountry": "US",
                    "PrimaryLocation": "Austin, United States",
                },
            ] if facet.startswith("AttributeChar6|") else [job]
            return {"items": [{"TotalJobsCount": len(rows), "requisitionList": rows}]}
        assert url == official.ORACLE_RECRUITING_API + "/recruitingCEJobRequisitionDetails"
        assert params["finder"] == 'ById;Id="335327",siteNumber=CX_45001'
        return {"items": [{
            **job,
            "RequisitionId": "302965956267672",
            "ExternalDescriptionStr": "<p>Advance healthcare technology.</p>",
            "ExternalResponsibilitiesStr": "<p>Build and support integrations.</p>",
            "ExternalQualificationsStr": (
                "<p>At least 2 years combined education and experience. "
                "Bachelor's degree in Computer Science preferred.</p>"
            ),
            "JobFunction": "SUPP-PREMSERV",
            "WorkerType": "Regular",
            "JobSchedule": "Full time",
            "applicationQuestions": "must never be retained",
        }]}

    monkeypatch.setattr(official, "json_get", fake_json_get)
    leads = asyncio.run(official.scrape_oracle_india_early_cse())

    assert len(search_calls) == 2
    assert all("location=India" in call["finder"] for call in search_calls)
    assert {
        call["finder"].split("selectedFlexFieldsFacets=", 1)[1]
        for call in search_calls
    } == {facet for facet, _fact in official.ORACLE_EARLY_FACETS}
    assert len(leads) == 1
    lead = leads[0]
    record = source_record_from_lead(lead)
    assert lead["company"] == "Oracle"
    assert lead["workplace"] == "onsite"
    assert "0 to 2+ years" in lead["description"]
    assert "Student / Intern" in lead["description"]
    assert "Bachelor's degree in Computer Science" in lead["description"]
    assert "applicationQuestions" not in str(lead)
    assert record.provider_requisition_id == "335327"
    assert record.provider_deadline_text == "2026-09-30"
    assert record.source_kind == SourceKind.DIRECT_EMPLOYER
    assert record.employer_domain == "oracle.com"


def test_swiggy_india_cse_projects_technical_jobs_and_stable_official_url(monkeypatch) -> None:
    async def fake_json_post(url, body):
        assert url == official.SWIGGY_CAREERS_API
        assert body == {"source": "careers", "code": "", "filterByBuId": -1}
        return {"reqDetailsBOList": [
            {
                "reqId": 30001,
                "reqTitle": "Software Development Engineer I",
                "designation": "Software Development Engineer I",
                "expMin": 0,
                "expMax": 2,
                "location": "Bangalore",
                "locationAddress": "Bangalore",
                "jdDisplay": "Build production Python services and distributed systems.",
                "approvedOn": "2026-08-25T10:00:00+05:30",
                "employmentType": "full_time",
                "buName": "Engineering",
                "careerStream": "Engineering",
                "totalPositions": 2,
                "fresher": True,
                "questionList": "must never be retained",
                "formFieldDetails": "must never be retained",
            },
            {
                "reqId": 30002,
                "reqTitle": "Sales Manager I",
                "location": "Mumbai",
                "jdDisplay": "Company description mentions AI and ML technology.",
            },
        ]}

    monkeypatch.setattr(official, "json_post", fake_json_post)
    leads = asyncio.run(official.scrape_swiggy_india_cse())

    assert len(leads) == 1
    lead = leads[0]
    record = source_record_from_lead(lead)
    assert lead["location"] == "Bangalore, India"
    assert lead["workplace"] == "onsite"
    assert "Experience range: 0 to 2 years" in lead["description"]
    query = parse_qs(urlsplit(lead["url"]).query)
    context = json.loads(base64.b64decode(query["p"][0]).decode("utf-8"))
    assert context["reqId"] == 30001
    assert context["pageType"] == "jd"
    assert "questionList" not in str(lead)
    assert "formFieldDetails" not in str(lead)
    assert record.provider_requisition_id == "30001"
    assert record.source_kind == SourceKind.DIRECT_EMPLOYER
    assert record.employer_domain == "swiggy.com"


def test_dell_india_cse_recovers_current_orc_board_and_expires_text_deadline(
    monkeypatch,
) -> None:
    row = {
        "Id": "R286029",
        "Title": "Systems Development Engineer 2",
        "PostedDate": "2026-08-18",
        "PostingEndDate": "",
        "PrimaryLocationCountry": "IN",
        "PrimaryLocation": "Bengaluru, Karnataka, India",
        "WorkplaceType": "On-site",
        "secondaryLocations": [],
    }

    async def fake_json_get(url, params=None):
        if url == official.DELL_RECRUITING_API + "/recruitingCEJobRequisitions":
            assert "siteNumber=CX_1001" in params["finder"]
            assert "location=India" in params["finder"]
            return {"items": [{"TotalJobsCount": 3, "requisitionList": [
                row,
                {
                    **row,
                    "Id": "sales",
                    "Title": "Direct Sales Account Executive",
                },
                {
                    **row,
                    "Id": "outside",
                    "PrimaryLocationCountry": "US",
                    "PrimaryLocation": "Austin, United States",
                },
            ]}]}
        assert url == official.DELL_RECRUITING_API + "/recruitingCEJobRequisitionDetails"
        assert params["finder"] == 'ById;Id="R286029",siteNumber=CX_1001'
        return {"items": [{
            **row,
            "ExternalDescriptionStr": (
                "<p>Build hardware and software systems with Python automation. "
                "Essential: 2-5 years of experience.</p>"
                "<p>Application closing date: 10th August 2026</p>"
            ),
            "ExternalResponsibilitiesStr": "<p>Design validation systems.</p>",
            "ExternalQualificationsStr": "<p>Bachelor's in CS preferred.</p>",
            "JobFunction": "Engineering Research & Development",
            "JobSchedule": "Full time",
            "candidateForm": "must never be retained",
        }]}

    monkeypatch.setattr(official, "json_get", fake_json_get)
    leads = asyncio.run(official.scrape_dell_india_cse())

    assert len(leads) == 1
    lead = leads[0]
    record = source_record_from_lead(lead)
    assert lead["company"] == "Dell Technologies"
    assert lead["deadline"] == "2026-08-10"
    assert lead["active_hint"] == "closed"
    assert lead["workplace"] == "onsite"
    assert "2-5 years" in lead["description"]
    assert "candidateForm" not in str(lead)
    assert record.provider_requisition_id == "R286029"
    assert record.provider_deadline_text == "2026-08-10"
    assert record.source_kind == SourceKind.DIRECT_EMPLOYER
    assert record.employer_domain == "dell.com"


def test_ycombinator_startups_preserves_structured_remote_restrictions(monkeypatch) -> None:
    listing = (
        '<a href="/companies/india-ai/jobs/abc123-software-engineer-intern">Intern</a>'
        '<a href="/companies/contradiction/jobs/def456-forward-deployed-engineer-india">Role</a>'
        '<a href="/companies/india-ai/jobs/abc123-software-engineer-intern">Duplicate</a>'
    )
    schemas = {
        "abc123": {
            "@context": "https://schema.org/",
            "@type": "JobPosting",
            "title": "Software Engineer Intern",
            "description": "<p>Build Python and React products with the founders.</p>",
            "datePosted": "2026-08-25T10:00:00Z",
            "validThrough": "2026-09-25T10:00:00Z",
            "employmentType": "INTERN",
            "hiringOrganization": {
                "@type": "Organization",
                "name": "India AI",
                "sameAs": "https://india-ai.example/",
                "logo": "https://india-ai.example/logo.png",
            },
            "jobLocation": {
                "@type": "Place",
                "address": {
                    "addressLocality": "Bengaluru",
                    "addressRegion": "Karnataka",
                    "addressCountry": "IN",
                },
            },
            "baseSalary": {
                "@type": "MonetaryAmount",
                "currency": "INR",
                "value": {
                    "@type": "QuantitativeValue",
                    "unitText": "MONTH",
                    "minValue": 40000,
                    "maxValue": 60000,
                },
            },
        },
        "def456": {
            "@context": "https://schema.org/",
            "@type": "JobPosting",
            "title": "Forward Deployed Engineer - India",
            "description": "<p>Support a developer platform.</p>",
            "datePosted": "2026-08-24T10:00:00Z",
            "employmentType": ["FULL_TIME"],
            "hiringOrganization": {
                "@type": "Organization",
                "name": "Contradiction",
                "sameAs": "https://contradiction.example/",
            },
            "jobLocationType": "TELECOMMUTE",
            "applicantLocationRequirements": {"@type": "Country", "name": "US"},
        },
    }

    async def fake_text_get(url, params=None, **kwargs):
        if url == official.YCOMBINATOR_STARTUP_LISTINGS["india"]:
            return listing
        key = "abc123" if "abc123" in url else "def456"
        return (
            '<script type="application/ld+json">'
            + json.dumps(schemas[key])
            + "</script>"
        )

    monkeypatch.setattr(official, "text_get", fake_text_get)
    leads = asyncio.run(official.scrape_ycombinator_startups("india"))

    assert len(leads) == 2
    intern = next(lead for lead in leads if lead["company"] == "India AI")
    restricted = next(lead for lead in leads if lead["company"] == "Contradiction")
    assert intern["location"] == "Bengaluru, Karnataka, India"
    assert intern["workplace"] == "onsite"
    assert "Compensation: INR 40000 - 60000 per MONTH" in intern["description"]
    assert intern["active_hint"] == "active"
    assert restricted["location"] == "Remote - United States"
    assert restricted["workplace"] == "remote"
    assert restricted["source_meta"]["applicant_location_requirements"] == ["United States"]
    record = source_record_from_lead(restricted)
    assert record.provider == "ycombinator"
    assert record.provider_tenant == "contradiction"
    assert record.provider_requisition_id == "def456"
    assert record.source_kind == SourceKind.AGGREGATOR
    assert record.public_metadata["listing_scope"] == "india"
    assert record.public_metadata["applicant_location_requirements"] == ["United States"]
