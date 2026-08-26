# Opportunity Events and Metrics Dictionary

Events are immutable facts. Metrics are derived from them. Every decision event records rule/model version and evidence references.

## Public opportunity events

| Event | Required fields | Meaning |
| --- | --- | --- |
| `source_fetch_started` | provider, target, run_id, ts | A bounded provider fetch began |
| `source_fetch_completed` | provider, target, counts, cost, ts | Fetch completed with candidate records |
| `source_fetch_failed` | provider, target, error_class, retryable, ts | Fetch failed; not equivalent to zero jobs |
| `source_record_observed` | source_record_id, provider, hash, ts | One provider observation was recorded |
| `opportunity_canonicalized` | opportunity_id, source_record_id, confidence, rule_version | Observation linked to canonical requisition |
| `duplicate_linked` | opportunity_id, source_record_ids, method, confidence | Cross-source duplicate relationship created |
| `opportunity_verified_active` | opportunity_id, method, evidence_ref, ts | Canonical application was verified active |
| `opportunity_marked_closed` | opportunity_id, method, evidence_ref, ts | Opportunity closure/expiry was observed |
| `opportunity_reopened` | opportunity_id, evidence_ref, ts | Previously closed opportunity became active again |

## Local candidate events

| Event | Required fields | Meaning |
| --- | --- | --- |
| `eligibility_decided` | candidate_id, opportunity_id, verdict, blockers, unknowns, rule_version | Hard eligibility evaluated |
| `decision_corrected` | candidate_id, opportunity_id, before, after, corrected_fact | Human correction changed the decision |
| `opportunity_surfaced` | candidate_id, opportunity_id, bucket, rank, ts | Candidate saw the opportunity |
| `candidate_opened` | candidate_id, opportunity_id, ts | Candidate inspected details |
| `candidate_accepted_recommendation` | candidate_id, opportunity_id, ts | Candidate intends to apply |
| `candidate_skipped` | candidate_id, opportunity_id, reason_code, note | Candidate rejected the recommendation |
| `package_generated` | candidate_id, opportunity_id, asset_version, ts | Application materials prepared |
| `application_started` | candidate_id, opportunity_id, ts | Candidate began the application |
| `application_abandoned` | candidate_id, opportunity_id, reason_code, ts | Application was not completed |
| `application_submitted` | candidate_id, opportunity_id, ts | Candidate confirms submission |
| `outreach_sent` | candidate_id, opportunity_id, channel, ts | Candidate confirms outreach |
| `recruiter_replied` | candidate_id, opportunity_id, reply_type, ts | Meaningful recruiter response received |
| `assessment_received` | candidate_id, opportunity_id, assessment_type, ts | Screening/technical assessment received |
| `interviewing` | candidate_id, opportunity_id, stage, ts | Candidate entered interview process |
| `offer_received` | candidate_id, opportunity_id, ts | Candidate received an offer |
| `accepted` | candidate_id, opportunity_id, ts | Candidate accepted offer |
| `rejected` | candidate_id, opportunity_id, stage, ts | Employer rejected candidate |
| `withdrawn` | candidate_id, opportunity_id, reason_code, ts | Candidate withdrew |

## Metric definitions

### North star

```text
interviews_per_20_applications =
  20 × distinct opportunities reaching interviewing
  / distinct completed applications
```

Use a fixed reporting window and show numerator/denominator. Never report the ratio without sample size.

### Quality

- `apply_now_live_precision`: audited Apply-now opportunities confirmed active / audited Apply-now opportunities.
- `apply_now_applicability_precision`: audited Apply-now opportunities confirmed hard-eligible / audited Apply-now opportunities.
- `dead_link_rate`: Apply-now opportunities whose canonical application is closed/unusable / audited Apply-now opportunities.
- `duplicate_application_rate`: duplicate submitted applications caused by failed canonicalization / submitted applications.
- `unsafe_leakage`: unsafe Apply-now recommendations / audited Apply-now opportunities.

### Funnel

- recommendation acceptance = accepted recommendation / surfaced Apply-now;
- application completion = submitted / accepted recommendation;
- reply rate = recruiter replies / submitted;
- interview rate = interview processes / submitted;
- offer rate = offers / interviews and offers / submitted;
- median discovery-to-application time;
- median accepted-recommendation-to-application time.

### Coverage and economics

- known-opening capture = captured benchmark openings / known active benchmark openings;
- source unique yield = canonical eligible opportunities first contributed by source;
- source incremental yield = opportunities absent from the union without that source;
- cost per unique eligible opportunity;
- cost per completed application;
- source-to-reply/interview conversion with sample size;
- publication-to-discovery latency by provider.

## Privacy

Public source events may enter a shared index. Candidate events remain local by default. Anonymous outcome sharing requires explicit candidate consent and must not include resume text, contact details, application answers, or employer correspondence.
