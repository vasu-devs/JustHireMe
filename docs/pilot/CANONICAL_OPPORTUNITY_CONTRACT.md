# Canonical Opportunity Contract — Phase 0

This contract separates one employer requisition from the many sources that may observe it. It is a design contract for Phase 1 implementation and a review checklist for the Phase 0 gold corpus.

## Source record

One immutable observation from one provider.

Required identity and provenance:

- `source_record_id`: provider-stable identifier;
- `provider`: Greenhouse, Lever, Ashby, Adzuna, and so on;
- `provider_requisition_id`: provider requisition/record identifier when available;
- `source_url`: the URL returned by the provider;
- `canonical_apply_url`: resolved employer/ATS application URL when available;
- `observed_at`;
- `raw_payload_hash`;
- `parser_version`;
- attribution and retention requirements.

Source facts must retain their semantics:

- `provider_published_at`;
- `provider_updated_at`;
- `provider_deadline`;
- `provider_active_status`;
- raw title, company, description, location, compensation, and employment type.

Provider-specific public facts that do not belong in the common schema may be
retained in bounded `public_metadata`. This includes structured salary,
employment type, applicant-location restrictions, timezones, categories,
department, and company logo/domain where the provider exposes them. Before
persistence, keys associated with candidate identity, contact details, resumes,
credentials, cookies, demographics, or application forms/questions are removed
recursively. Candidate-specific inputs always belong in local candidate state,
never in a shared source record.

Never relabel an updated date as publication time. Preserve the full raw description or permitted snapshot; create truncated text only as a derived model/ranking input.

## Canonical opportunity

One deduplicated employer requisition.

```json
{
  "schema_version": 1,
  "opportunity_id": "stable-id",
  "requisition_id": "employer-or-ats-id",
  "company": {
    "company_id": "stable-company-id",
    "name": "Example",
    "domain": "example.com",
    "cohort": "india_startup"
  },
  "title": "Machine Learning Engineer Intern",
  "opportunity_type": "internship",
  "technical_track": "ai_ml",
  "seniority": "intern",
  "experience": {"minimum_years": 0, "maximum_years": 1},
  "employment_type": "internship",
  "workplace": {
    "type": "remote",
    "scope": "worldwide_remote",
    "country": null,
    "city": null,
    "allowed_countries": ["IN"],
    "allowed_regions": ["APAC"],
    "timezone_constraints": ["UTC+03:00", "UTC+08:00"]
  },
  "candidate_stage_requirements": {
    "graduation_years": [2026, 2027],
    "currently_enrolled": true,
    "degree": ["Computer Science", "Related technical degree"],
    "work_authorization": [],
    "citizenship": [],
    "start_date": null,
    "duration_weeks": 12,
    "hours_per_week": 30
  },
  "compensation": {
    "status": "paid",
    "minimum": 600,
    "maximum": 900,
    "currency": "USD",
    "period": "month",
    "provenance": "posting_text"
  },
  "lifecycle": {
    "published_at": null,
    "updated_at": null,
    "deadline": null,
    "first_seen_at": "2026-08-24T00:00:00Z",
    "last_verified_active_at": "2026-08-24T00:00:00Z",
    "closed_at": null,
    "active_status": "active"
  },
  "safety": {"blockers": [], "warnings": []},
  "canonical_apply_url": "https://example.com/careers/req-123",
  "source_record_ids": ["greenhouse:123", "adzuna:987"],
  "evidence": {},
  "unknowns": []
}
```

## Candidate decision

Candidate-specific facts do not belong inside the public canonical opportunity.

```json
{
  "opportunity_id": "stable-id",
  "candidate_id": "local-id",
  "rule_version": "1",
  "eligibility": "eligible",
  "decision": "apply_now",
  "hard_blockers": [],
  "unknowns": [],
  "fit": {},
  "career_growth": {},
  "compensation_value": {},
  "hiring_confidence": {},
  "urgency": {},
  "evidence_refs": []
}
```

This separation permits a shared public opportunity index while resumes and personalized decisions remain local.

## Deduplication order

1. Employer/ATS requisition ID.
2. Canonical employer/ATS application URL.
3. Known provider mappings and resolved redirects.
4. Normalized company domain, title, workplace/location, and time window.
5. Description fingerprint.
6. Cautious fuzzy candidate with human-review status.

Uncertain merges remain separate until resolved. A false merge can hide a real application, so deduplication precision outranks aggressive compression.
