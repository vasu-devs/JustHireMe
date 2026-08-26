# Phase 0 Baseline Report

**Status:** In progress — measured intake, human review pending
**Measurement window:** 2026-08-24 UTC bounded live scan
**Prepared by:** Project maintainer
**Reviewed by:** TBD

## 1. Executive result

- Gold corpus: `14 / 300` synthetic schema seeds; `0 / 200` public snapshots; `0 / 300` double reviewed.
- Company inventory: `120` generated candidates; all require human verification.
- Pilot candidates onboarded: `0 / 5`.
- Baseline discovery run: `120` boards attempted, `107` succeeded, `13` failed, `8,618` raw rows observed.
- Review intake: `51` unique-URL, unreviewed candidates across `40` companies and three represented providers.
- Proposed-only intake mix: `1` India-eligible worldwide-remote graduate role, `5` location/eligibility ambiguous early-career roles, `15` non-technical early-career traps, and `30` seniority traps.
- Phase 0 exit: **NO-GO** until all evidence gates are complete.

The `51` review records are not gold cases. Automated labels are triage proposals, and `reviewed_records` remains zero.

Canonical pipeline diagnostic (automated labels, not human gold):

- `8,617` raw direct-source rows in the first complete run;
- `8,448` accepted source observations and `8,232` canonical opportunities;
- generic India final-year profile decisions: `4` Apply now, `2` Strong stretch, `17` Needs review, `8,209` Skip;
- first-run Workday date defect: `169` relative date strings rejected; fixed by preserving provider text and normalizing `Posted Today` / `Posted N Days Ago` against observation time;
- corrected Workday control: `170` raw rows, `169` observations, `164` canonical opportunities, `0` conversion errors;
- early-career Workday matrix: `39` searches across `13` tenants returned `412` accepted observations and `371` canonical opportunities, including `57` internships, `8` new-grad roles, and `5` entry-level roles;
- Workday matrix decisions: `29` Needs review and `342` Skip; no role was promoted through missing workplace evidence.

Production vertical-slice controls after runtime integration:

- default runtime matrix: `160` searches across `18` provider families;
- India startup control: six boards, `83` canonical opportunities, `4` Apply now, `5` Needs review, `74` Skip, zero source failures;
- India Workday control: nine early-career searches, `79` canonical opportunities, `1` Needs review, `78` Skip, zero source failures;
- keyless market-feed control: seven searches, `227` canonical opportunities, `4` Needs review, `223` Skip, zero source failures;
- direct ATS active-board correction restored Nirmata and epiFi postings that an inappropriate 30-day creation-date cutoff had suppressed;
- a Product Ops false positive caused by AI wording in the description was reproduced, fixed with title-first non-technical exclusion, and regression tested.
- pilot profiles now support distinct technical-track, role-type, workplace-mode, pay, duration, unpaid-work, and bond policies;
- private immutable outcome events and per-candidate funnel metrics are implemented, including source-attributed submissions, meaningful contacts, interviews, offers, and interviews per 20 applications.

These are automated operational controls, not reviewed precision measurements.

## 2. Pilot cohort

| Candidate ID | Track | Profile confirmed | Constraints confirmed | Existing applications imported |
| --- | --- | --- | --- | --- |
| TBD | Backend/full-stack | No | No | No |
| TBD | AI/ML/data | No | No | No |
| TBD | Frontend/mobile | No | No | No |
| TBD | Cloud/DevOps/security | No | No | No |
| TBD | General software | No | No | No |

Do not add real names, email addresses, phone numbers, or resume text to this report.

## 3. Corpus readiness

Paste the output of:

```bash
cd backend
python -m evals.opportunity_harness
```

Record:

- counts by category;
- public versus synthetic;
- double-review completion;
- invariant count;
- unresolved disputes.

Current harness result:

- total schema-valid cases: `14 / 300`;
- public snapshots: `0 / 200`;
- double reviewed: `0 / 300`;
- invariants: `12 / 10`;
- every target category remains below its distribution gate.

## 4. Company benchmark readiness

```bash
cd backend
python -m evals.company_benchmark
```

Record:

- entries by cohort/provider;
- reviewed versus needs-review;
- valid/invalid career URLs;
- India presence confirmed;
- remote reach confirmed;
- expected zero-result versus parser-failure behavior.

Current generated inventory:

- company candidates: `120`;
- providers represented: Greenhouse `54`, Ashby `40`, Workday `13`, Lever `9`, SmartRecruiters `2`, Workable `1`, Personio `1`;
- human-reviewed companies: `0 / 100` required;
- all `120` remain `needs_review` and must not be represented as verified coverage.

## 5. Current-system baseline

| Metric | Result | Sample | Notes |
| --- | ---: | ---: | --- |
| Known-opening capture | Not measurable | 120-company candidate inventory | Known openings require manual benchmark verification |
| Duplicate observation rate | TBD | TBD | |
| Canonical duplicate rate | TBD | TBD | |
| Live/closed precision | TBD | TBD | |
| Dead links in current shortlist | Not audited | 51 unreviewed candidates | Human liveness review pending |
| Early-career technical precision | Not audited | 51 unreviewed candidates | Proposed mix shows only 6 potentially technical early-career records |
| India/workplace eligibility precision | Not audited | 51 unreviewed candidates | Source-level location propagation was fixed before the final run |
| Unsafe leakage | TBD | TBD | |
| Direct application URL rate | 100% ATS-hosted in intake | 51 | Route usability still requires human verification |
| Median publication-to-discovery latency | TBD | TBD | |
| Candidate review time per useful opportunity | TBD | TBD | |

## 6. Source baseline

For every enabled source record:

| Source | Requests | Raw rows | Canonical opportunities | Eligible | Unique | Dead/stale | Failures | Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Ashby | bounded public board calls | 3,346 | Not canonicalized | Not reviewed | Not measured | Not audited | Included in 13 board failures | ₹0 |
| Greenhouse | bounded public board calls | 5,083 | Not canonicalized | Not reviewed | Not measured | Not audited | Included in 13 board failures | ₹0 |
| Lever | bounded public board calls | 19 | Not canonicalized | Not reviewed | Not measured | Not audited | Included in 13 board failures | ₹0 |
| Workday | bounded public search calls | 170 | Not canonicalized | Not reviewed | Not measured | Not audited | No raised failure in final run | ₹0 |
| Personio | bounded public feed call | 0 | 0 | 0 | 0 | 0 | Successful zero result | ₹0 |
| SmartRecruiters | bounded public API calls | 0 | 0 | 0 | 0 | 0 | Successful zero result | ₹0 |
| Workable | bounded public API call | 0 | 0 | 0 | 0 | 0 | One 404 board failure | ₹0 |

Final-run source-health summary: `107 / 120` board calls completed without a raised source error. The `13` failures are retained in `backend/evals/output/public_opportunity_review_report.json`; zero rows from a successful call are reported separately from an exception.

## 7. Failure inventory

Rank by candidate harm and frequency:

1. Closed/unusable application routes.
2. India-ineligible remote roles.
3. Senior/non-technical leakage.
4. Duplicate requisitions.
5. Missing/ambiguous compensation and remote reach.
6. Unsafe conditions.
7. Missed known openings.
8. Late discovery.

Observed implementation failures from the first two trial runs:

- sequential collection let two high-volume boards monopolize the queue;
- generic experienced technical vacancies were incorrectly admitted as useful review cases;
- negative seniority examples could fill the entire target count;
- Greenhouse, Lever, and Ashby calculated location but did not expose it as an authoritative top-level field, allowing description boilerplate to contaminate geography;
- `13 / 120` benchmark scan targets currently return hard source errors and need registry correction or retirement;
- the current 120-company mix supplies too few live India/India-eligible technical internships to satisfy the positive corpus targets.

Corrections already applied:

- scan every selected board with bounded concurrency before final sampling;
- cap per-board, per-company, and per-category contributions;
- exclude unclassified generic experienced roles from the early-career review queue;
- propagate authoritative ATS locations and classify India on-site/hybrid from that field;
- preserve errors, raw-row counts, review state, evidence excerpts, content hashes, and source provenance.
- preserve full ATS descriptions instead of truncating at 1,200 characters;
- separate provider tenant plus requisition identity from immutable observation identity;
- normalize relative provider dates without relabeling provider semantics;
- route direct-source rows through canonical lifecycle, deduplication, applicability, and safety gates;
- distinguish source success, successful zero results, conversion defects, and hard failures;
- expand Workday to a bounded `intern` / `graduate` / `entry level` query matrix.

For each failure record example IDs, root cause, affected source/module, frequency, and intended phase.

## 8. Phase 0 go/no-go

Phase 1 may begin only when:

- five pilot constraint profiles are confirmed locally;
- 300 cases meet distribution targets;
- at least 200 real public snapshots exist;
- all 300 are double reviewed;
- 100 benchmark employers are manually verified;
- current-system baseline metrics are recorded;
- unresolved cases remain explicitly unknown/Needs review;
- API experiment budget and go/no-go ownership are approved.

**Decision:** NO-GO
**Owner:** Project maintainer
**Decision date:** 2026-08-24 (interim)
**Evidence links:** `backend/evals/opportunity_cases/adversarial.jsonl`, `backend/evals/company_benchmark.jsonl`, `backend/evals/output/public_opportunity_review_queue.jsonl`, `backend/evals/output/public_opportunity_review_report.json`

## 9. Paid-source readiness checkpoint

SerpApi, Adzuna India, and Jooble regional adapters are now available as disabled experiments. No credential or paid-call budget has been supplied, so request count and spend remain zero. Enabling them does not change the Phase 0 decision: the system must still obtain the five real candidate profiles, complete the double-reviewed corpus, verify the employer benchmark, and measure the seven-day provider lift before any paid source can graduate into normal scanning.

The operational retention rule is: collect at least 10 successful requests, deduplicate against canonical truth, and retain only at >=10% net-new eligible yield unless a documented under-covered cohort or latency outcome justifies an exception.

## 10. Pilot-participant integrity checkpoint

As of 2026-08-25, a saved candidate ID no longer counts as an onboarded pilot participant. The product records a candidate-confirmed consent timestamp, prevents manual and scheduled scans before consent, prevents application tracking until a complete candidate-scoped application profile is linked, and reports saved-but-pending candidates separately. The five-person cohort numerator includes only candidates who have both confirmed consent and an application-ready profile.

This removes accidental or placeholder IDs from the interview funnel denominator. It does not satisfy the five-profile exit gate by itself: five real candidates must still review their constraints, consent locally, and link their own application evidence.

Candidate profile linking is also a two-step identity check. The product first displays the current Profile workspace's name and evidence counts, then accepts confirmation only for that exact content fingerprint. If the Profile changes between review and confirmation, the link fails and must be reviewed again. This prevents a stale tab or a switch between friends from silently attaching the wrong resume evidence to a candidate ID.

The five-person pilot no longer requires replacing the shared Profile workspace five times. A consented candidate can upload a PDF, DOCX, TXT, or Markdown resume directly into their own opportunity workspace, review the locally parsed identity/evidence, and confirm the exact fingerprint. Candidate-scoped resume parsing is deterministic and local-only even when the application has a cloud LLM configured; it does not write to the shared profile graph or global identity settings.
