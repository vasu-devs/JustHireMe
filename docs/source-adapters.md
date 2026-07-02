# Source Adapter Contract

Source adapters turn external job sources into normalized lead dictionaries. A good adapter is boring, deterministic, and easy to test.

## Normalized Lead Fields

Required:

- `title`: role title
- `company`: company or source owner
- `url`: canonical apply/source URL
- `platform`: stable source id, such as `greenhouse`, `lever`, `hn_hiring`
- `description`: useful job text for ranking/customization

Recommended:

- `posted_date`: visible source date when available
- `location`: remote/location text
- `tech_stack`: list of detected technologies
- `signal_score`: source-level quality score
- `signal_reason`: short explanation of source signal
- `signal_tags`: source tags
- `source_meta`: source-specific metadata

## Quality Gate

Before saving, leads should pass `discovery.quality_gate.evaluate_lead_quality`.

The gate rejects or down-ranks:

- missing URLs
- thin scraped rows
- stale jobs
- senior-only jobs in beginner-focused feeds
- spam, unpaid, or low-trust postings
- missing company/context signals

Saved leads should keep `source_meta.lead_quality_score` and `source_meta.lead_quality_reason` so users and contributors can understand why the lead was shown.

## New Source Checklist

- [ ] Adapter returns normalized fields.
- [ ] URLs are canonical and dedupable.
- [ ] Dates are parsed or passed through.
- [ ] No credentials are required for basic tests.
- [ ] At least one good fixture passes.
- [ ] At least one noisy fixture is filtered.
- [ ] README or settings docs explain how to enable the source.

Prefer direct ATS/company APIs over broad search result scraping. Use broad search only as a fallback.
