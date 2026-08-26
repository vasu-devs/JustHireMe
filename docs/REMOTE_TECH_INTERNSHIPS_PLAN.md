# Remote Tech Internships — Focused Product and Delivery Plan

**Status:** Superseded by `EARLY_CAREER_TECH_MARKET_COVERAGE_PLAN.md`; retained as the internship-only domain design
**Initial audience:** Fourth-year B.Tech CSE students, beginning with the maintainer's friends
**Initial candidate location:** Configurable, with India / Asia-Kolkata as the pilot default
**Product scope:** Paid, remote, CSE-related internships that the candidate can legally and practically apply to

## 1. Product decision

Build this as a strict `Internships` mode inside JustHireMe, reusing the existing source adapters, local profile, lead store, ranking, generation, and pipeline.

Do not build a broad internship marketplace and do not make the existing field-agnostic discovery pipeline responsible for internship precision. Add an internship-specific classification and decision layer between normalization and persistence:

```text
Public source / company ATS
  -> existing source normalization
  -> strict internship classifier
  -> CSE/tech classifier
  -> remote-scope and candidate-country eligibility
  -> freshness, authenticity, pay, fee, bond, and safety gates
  -> fit + career-growth prioritization
  -> existing local lead store and pipeline
  -> internship-specific tailoring and interview preparation
```

The central product promise is:

> Show a student recent, real, remote tech internships they appear eligible for, explain every uncertainty, and help them decide what to apply to next.

## 2. Goals and non-goals

### Goals for the first release

1. Find actual internships rather than generic entry-level jobs.
2. Restrict the feed to CSE-related technical work.
3. Confirm remote scope separately from geographic eligibility.
4. Prefer direct employer or recognized ATS application URLs.
5. Reject stale, closed, unpaid, fee-charging, bond-heavy, and obviously misleading opportunities.
6. Explain why the candidate is eligible, why the role fits, and what evidence is missing.
7. Prioritize career growth, not only keyword overlap.
8. Tailor applications around projects, coursework, open source, hackathons, and demonstrated skills without inventing experience.
9. Remain useful with no API key and preserve JustHireMe's local-first behavior.

### Explicit non-goals

- Full-time, new-grad, freelance, apprenticeship, volunteer, campus-only, or non-technical roles.
- Supporting every profession or every kind of internship.
- Scraping login-gated sites or trying to bypass anti-bot controls.
- Automatic application submission.
- Claiming a company is fraudulent based only on model output.
- A shared employer reputation network in the first release.
- Employer accounts, candidate accounts, social features, or a hosted marketplace.

## 3. Definition of an accepted opportunity

A lead enters the default internship feed only when every hard gate passes.

### 3.1 Internship gate

Accept when at least one strong signal exists:

- the title contains `intern`, `internship`, or `co-op`; or
- a trusted structured source marks employment type as `Intern` and the full description is consistent with an internship.

Reject by default:

- new-grad and graduate roles without an explicit internship designation;
- apprenticeships, traineeships, fellowships, working-student roles, and volunteer roles;
- generic job pages or talent communities;
- roles asking for normal full-time professional experience under an internship label;
- ambiguous description-only mentions such as “mentor interns.”

The excluded categories may be added later as separately named feeds. They must not weaken internship precision now.

### 3.2 Technical CSE gate

Initial accepted tracks:

- software engineering;
- frontend, backend, and full-stack development;
- Android, iOS, and cross-platform mobile development;
- AI, ML, applied AI, NLP, computer vision, and MLOps;
- data engineering, data science, and analytics engineering;
- cloud, DevOps, platform engineering, infrastructure, and SRE;
- cybersecurity, application security, and security engineering;
- QA automation, SDET, developer tooling, and test infrastructure;
- embedded software, firmware, robotics software, and systems programming;
- database, distributed systems, compilers, graphics, and research engineering where the work is software-related.

Reject non-technical tracks even when the employer is a technology company: recruiting, HR, sales, marketing, content, customer success, finance, legal, generic operations, and manual data entry.

### 3.3 Remote gate

`remote` and `globally eligible` are different facts. Every opportunity receives one remote-scope classification:

- `worldwide`: source explicitly says worldwide, anywhere, work from anywhere, or provides a trusted structured worldwide flag;
- `candidate_country_allowed`: remote and explicitly allows the candidate's country or a containing region such as APAC when appropriate;
- `region_restricted`: remote, but restricted to countries or regions that exclude the candidate;
- `remote_unknown`: remote is stated, but hiring geography is not clear;
- `hybrid_or_onsite`: not a remote internship.

Only `worldwide` and `candidate_country_allowed` appear in the default Apply feed. `remote_unknown` appears in a separate Review feed. Restricted, hybrid, and onsite roles are hidden by default.

Important rules:

- Never infer worldwide eligibility merely because a description says `remote`.
- An empty restriction list means worldwide only for sources whose contract explicitly defines it that way.
- Timezone overlap is a separate constraint from country eligibility.
- “Remote in the US” is not globally remote.
- Work authorization, citizenship, export-control, and university-enrollment requirements are hard eligibility facts when stated.

### 3.4 Authenticity and quality gate

Require:

- a canonical, reachable source or apply URL;
- a named company;
- a useful job description;
- a confirmed recent date, recent source window, or currently published/active status from a structured API;
- a title and description consistent with the same opportunity;
- no indication that the application is closed or the requisition has expired.

Prefer direct employer and recognized ATS URLs. Aggregator records must preserve attribution and link to the source-supplied application URL.

Internship freshness must not reuse the generic seven-day job rule unchanged. Internship applications often remain open for several weeks:

- a direct ATS record that is currently published or has a future deadline remains eligible even when it is older than seven days;
- age lowers freshness/urgency priority but does not by itself prove closure;
- an explicit closed/expired status or past deadline rejects the record;
- aggregator/community records require a recent source date plus a successful canonical-link recheck;
- keep `published_at`, `updated_at`, `deadline`, `first_seen_at`, and `last_verified_active_at` as different facts;
- never present an ATS `updated_at` value as the original publication date.

### 3.5 Safety and compensation gate

Reject by default when the posting states:

- unpaid work, exposure-only compensation, commission-only compensation, or equity-only compensation;
- an application fee, training fee, security deposit, equipment purchase from the employer, or payment to receive work;
- a mandatory employment bond or exit penalty beyond a user-configurable tolerance;
- a free-work trial or substantial unpaid assignment;
- surrender of original documents or other coercive conditions.

Classify compensation as `paid`, `unpaid`, `unknown`, or `suspicious`. Unknown pay should enter Review unless the user explicitly allows undisclosed compensation.

The UI must show the exact posting evidence behind every warning and must avoid unverified legal or fraud claims.

## 4. Candidate profile for the pilot

Add internship preferences to settings/profile without requiring a separate account system:

```json
{
  "opportunity_mode": "remote_tech_internships",
  "home_country": "IN",
  "timezone": "Asia/Kolkata",
  "graduation_date": "2027-06",
  "currently_enrolled": true,
  "available_from": "2026-09-01",
  "available_hours_per_week": 30,
  "preferred_duration_weeks": [8, 26],
  "preferred_tracks": ["backend", "fullstack", "ai_ml"],
  "minimum_monthly_stipend": null,
  "stipend_currency": "INR",
  "allow_undisclosed_pay": false,
  "allow_unpaid": false,
  "allow_bond": false,
  "work_authorizations": ["IN"],
  "remote_scope_preference": "worldwide_or_india_eligible"
}
```

Each friend imports a resume and confirms these facts. The system must never infer work authorization, graduation date, or willingness to accept unpaid work.

## 5. Normalized internship facts

Reuse the existing `Lead` and `source_meta` boundary for the first vertical slice. Add an `internship_facts` object with evidence and confidence:

```json
{
  "opportunity_type": "internship",
  "technical_track": "backend",
  "technical_confidence": 0.97,
  "remote_scope": "candidate_country_allowed",
  "allowed_countries": ["IN"],
  "allowed_regions": ["APAC"],
  "timezone_constraints": ["UTC+03:00", "UTC+08:00"],
  "paid_status": "paid",
  "stipend_min": 600,
  "stipend_max": 900,
  "stipend_currency": "USD",
  "stipend_period": "month",
  "duration_weeks": 12,
  "hours_per_week": 30,
  "start_date": null,
  "application_deadline": null,
  "graduation_years": [2026, 2027],
  "enrollment_required": true,
  "experience_years_required": 0,
  "bond": false,
  "fees": false,
  "work_authorization": [],
  "evidence": {
    "remote_scope": "This internship is open to candidates worldwide...",
    "paid_status": "Monthly stipend: USD 600–900..."
  },
  "unknowns": ["application_deadline"]
}
```

For long-term querying, add indexed columns in a later migration for:

- `opportunity_type`;
- `technical_track`;
- `remote_scope`;
- `paid_status`;
- `eligibility_verdict`;
- `decision_bucket`;
- `internship_priority_score`.

Keep the full extracted structure and evidence in JSON so new facts do not require a migration every time.

## 6. Source strategy

### Tier A — direct ATS company boards

This is the primary source layer because it provides current, canonical employer postings with stable structured endpoints.

Use the adapters already present for Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee, Personio, Teamtailor, and other supported ATS providers. Maintain a versioned source registry:

```yaml
- company: Example
  provider: ashby
  slug: example
  careers_url: https://jobs.ashbyhq.com/example
  remote_history: worldwide
  tracks: [backend, ai_ml]
  enabled: true
  last_verified_at: 2026-08-24
```

Registry requirements:

- start with companies known to hire remote technical interns;
- validate every provider and slug automatically;
- retain boards that currently have zero internships because new openings may appear later;
- record scan health, last successful fetch, result counts, and parser failures;
- scan direct ATS boards at a respectful configurable interval with jitter and conditional caching where supported;
- add companies only from public career pages, trusted community contributions, or previously validated postings.

### Tier B — remote-job APIs and feeds

1. **Himalayas**: update the existing adapter to use the current search endpoint with `employment_type=Intern`, `worldwide=true` or candidate-country filters, technical keywords, and recent sorting. Preserve location and timezone restrictions. Use cursor/page pagination according to the current API contract and attribute Himalayas in the UI.
2. **Remotive**: use the public search/category filters as a supplemental feed, honor its polling limit, preserve Remotive attribution, and always send users through the Remotive-supplied URL.
3. **RSS/API sources already supported**: enable only feeds with clear redistribution/use rules and adequate internship coverage.

Aggregator data is a discovery signal, not proof. Run the same internship, technical, remote-eligibility, freshness, and safety gates over every item.

### Tier C — curated open-source lists

Community-maintained internship repositories can discover leads and company boards, but should not be copied blindly into the database. For each candidate row:

1. parse the row;
2. follow the canonical application link;
3. validate that the requisition is still open;
4. re-extract facts from the employer/ATS posting;
5. preserve the community source as discovery provenance;
6. ingest only if its license and reuse terms permit the intended use.

### Deferred sources

Do not depend on LinkedIn, Indeed, Internshala, Wellfound, or other login-gated/anti-bot sites for the MVP. Search-result scraping from these sites is fragile, frequently incomplete, and may violate platform rules. A user can still paste a posting manually.

## 7. Classification and extraction

Use a two-stage system.

### Stage 1 — deterministic extraction

Fast, free, and testable rules extract:

- internship title terms and exclusion terms;
- technical track;
- remote, country, region, and timezone phrases;
- dates and deadlines;
- stipend/pay ranges and periods;
- duration and weekly hours;
- graduation-year and enrollment requirements;
- experience requirements;
- fee, unpaid, bond, trial-work, citizenship, and work-authorization signals.

Structured source fields override free-text guesses when the source contract is explicit.

### Stage 2 — optional model extraction

Use the configured local or remote model only when facts remain ambiguous. Require schema-constrained JSON containing:

- the normalized value;
- confidence;
- a short exact evidence span from the posting;
- `unknown` when the posting does not say.

The model may classify and explain text. It may not invent missing eligibility or compensation facts. A low-confidence model result goes to Review rather than Apply.

## 8. Decision engine

Do not collapse everything into one opaque score. Evaluate gates first, then rank the opportunities that survive.

### 8.1 Eligibility verdict

Return one of:

- `eligible`: all stated hard requirements appear satisfied;
- `likely_eligible`: no blocker is present, but one or more non-critical facts are unknown;
- `needs_review`: an important requirement is ambiguous;
- `ineligible`: at least one evidenced hard blocker exists.

Hard blockers include candidate-country exclusion, incompatible graduation window, citizenship/work-authorization requirement, incompatible start date or hours, onsite requirement, and explicit experience above the allowed threshold.

Every blocker and uncertainty must retain a posting evidence span.

### 8.2 Career-growth score

Score only surviving opportunities from 0–100 using explainable components:

| Component | Weight | Evidence |
| --- | ---: | --- |
| Candidate/project fit | 30 | existing graph/vector match and required skills |
| Learning trajectory | 20 | useful stretch skills adjacent to existing ability |
| Engineering substance | 15 | real product/code/research ownership rather than clerical work |
| Mentorship environment | 10 | named mentor, code review, pairing, feedback, team integration |
| Portfolio value | 10 | shippable output, open source, measurable scope, production exposure |
| Compensation clarity | 5 | stated stipend/pay structure |
| Company/posting credibility | 5 | direct source, complete JD, identifiable team/company |
| Freshness and urgency | 5 | recency and approaching deadline |

Unknown evidence receives a neutral or small penalty, never fabricated credit.

### 8.3 Decision buckets

- **Apply now:** eligible/likely eligible, no safety blocker, priority score above the configured threshold.
- **Review:** ambiguous geography, pay, graduation rules, or other material uncertainty.
- **Skip:** ineligible, unsafe, stale, closed, non-technical, non-internship, or below the user's minimum standards.

The application list should sort by decision bucket, deadline, freshness, then priority—not by model enthusiasm.

## 9. Backend implementation boundaries

Add a focused domain package without duplicating source fetching:

```text
backend/internships/
  models.py          # normalized facts, evidence, verdicts
  taxonomy.py        # accepted technical tracks and title rules
  extractor.py       # deterministic + optional structured model extraction
  eligibility.py     # profile versus posting hard requirements
  safety.py          # pay/fee/bond/unpaid/trial rules
  scoring.py         # career-growth and priority rubric
  pipeline.py        # orchestrates the stages and emits decisions
```

Integrate it after existing source normalization and before `save_lead` in the discovery orchestrator/free-scout path. Avoid embedding internship business logic in routers, React components, or individual source adapters.

Recommended changes:

- set accepted records to `kind="internship"`;
- pass `target_level="fresher"` to the existing quality gate, but add an internship-aware active/deadline policy instead of blindly applying its seven-day rejection rule;
- store the structured decision under `source_meta.internship` for the first vertical slice;
- introduce repository query filters for decision bucket, technical track, eligibility, pay status, and remote scope;
- add a migration only after the JSON contract stabilizes;
- add source attribution and source-contract metadata to each lead;
- update the Himalayas adapter rather than adding a second competing adapter.

## 10. Frontend experience

Add an `Internships` entry with three tabs:

1. **Apply now** — clean, eligible, high-priority opportunities.
2. **Needs review** — promising opportunities with a visible unanswered question.
3. **Skipped** — transparent rejection reason, hidden by default.

Each card should answer six questions without opening the description:

- Is it actually an internship?
- Is it technical and which track?
- Can someone in my country apply?
- Is it paid?
- When was it posted and when does it close?
- Why should I apply or skip it?

The detail view should show:

- eligibility verdict and hard-requirement checklist;
- remote/country/timezone evidence;
- stipend, duration, hours, start date, and deadline;
- safety warnings;
- matching projects and skills;
- growth-score breakdown;
- missing evidence and questions to verify with the recruiter;
- direct Apply, Tailor resume, Prepare interview, and Mark incorrect actions.

Never display `Global remote` unless the evidence supports worldwide eligibility. Use `Remote — geography unclear` when it does not.

## 11. Internship-specific application assistance

Reuse the existing generation service with internship prompts and deterministic safeguards:

- lead with relevant projects, outcomes, coursework, hackathons, open source, and independent builds;
- map each required skill to concrete profile evidence;
- make missing requirements visible rather than fabricating experience;
- generate a concise internship resume variant;
- draft a short recruiter/founder message grounded in one relevant project;
- draft answers for “Why this internship?”, availability, and learning goals;
- generate an interview preparation sheet from the job's stated stack and responsibilities;
- propose one small portfolio improvement only when it can be completed before the deadline.

## 12. Delivery sequence

### Phase 0 — contract and evaluation set

Deliverables:

- normalized `InternshipFacts`, evidence, eligibility, and decision contracts;
- technical taxonomy and explicit exclusions;
- pilot profile-preference contract;
- a checked-in fixture set containing positive internships and hard negatives: full-time roles mentioning interns, remote-but-US-only internships, onsite internships, non-tech internships, unpaid roles, expired roles, and ambiguous pay/geography;
- precision-oriented tests before production source work.

Exit criteria:

- all hard rules have named fixtures;
- expected decisions have been manually reviewed;
- no field relies solely on an LLM.

### Phase 1 — first end-to-end vertical slice

Deliverables:

- update Himalayas to its current filtered search API;
- fetch `Intern` opportunities using technical queries;
- extract remote restrictions, timezone restrictions, pay, and dates;
- run the strict gates and store `kind=internship`;
- expose Apply/Review/Skip in a minimal UI or existing pipeline filters.

Exit criteria:

- a scan produces only internship candidates;
- non-technical and region-ineligible records do not enter Apply;
- every visible record has a canonical apply URL, freshness status, remote verdict, and rejection/acceptance explanation;
- attribution requirements are visible.

### Phase 2 — direct ATS registry

Deliverables:

- versioned remote-tech company board registry;
- scheduled Greenhouse, Lever, Ashby, and other existing ATS scans;
- provider/slug health validation;
- direct-link verification and closed-role cleanup;
- source-health report: fetched, accepted, rejected, duplicate, failed, and last successful scan.

Exit criteria:

- one broken board cannot fail the scan;
- stale/closed postings disappear or move to Skipped;
- source and parsing failures are distinguishable from “zero internships available”;
- scan frequency respects provider constraints.

### Phase 3 — candidate eligibility and decision UI

Deliverables:

- internship preference onboarding;
- eligibility engine with country, timezone, graduation, enrollment, availability, and work-authorization checks;
- Apply/Review/Skip views and evidence drawer;
- filters for technical track, remote scope, paid status, date, and deadline.

Exit criteria:

- a US-only remote internship is not labeled globally eligible;
- every hard rejection names the incompatible requirement;
- users can correct an extracted fact and the decision recomputes deterministically.

### Phase 4 — growth and application assistance

Deliverables:

- career-growth score and component explanations;
- project-first fit evidence;
- internship resume/outreach generation;
- interview preparation sheet;
- feedback signals for relevant, ineligible, misleading, closed, and applied.

Exit criteria:

- generated claims are traceable to the profile;
- an unavailable model still produces deterministic eligibility and basic ranking;
- feedback never overrides a hard eligibility or safety gate.

### Phase 5 — friends pilot

Pilot loop:

1. onboard the initial friends and record only the preferences needed for matching;
2. manually audit the first 30–50 surfaced records per profile;
3. classify every wrong result by failure type;
4. adjust deterministic rules and source registry before tuning model prompts;
5. have users mark applied, replied, interview, rejected, closed, and offer outcomes;
6. review outcomes weekly and improve sources and decision logic.

Do not optimize for the raw number of scraped records. Optimize for qualified opportunities and callbacks.

## 13. Test and evaluation plan

### Unit tests

- internship title positives and false positives;
- technical taxonomy positives and non-technical exclusions;
- country/region/timezone normalization;
- worldwide versus remote-unknown classification;
- stipend and pay-period normalization;
- graduation, enrollment, work-authorization, availability, and experience extraction;
- unpaid, fee, bond, deposit, and trial-work detection;
- deterministic eligibility and decision buckets;
- score bounds and component provenance.

### Adapter contract tests

- recorded fixtures for every enabled provider;
- canonical URL and attribution preservation;
- source dates and active/closed status;
- separation of published, updated, first-seen, deadline, and last-verified-active dates;
- malformed rows and partial provider failures;
- rate-limit and retry behavior;
- structured-field precedence over text inference.

### Regression tests

- “mentor interns” in a full-time JD is not an internship;
- “remote” plus “US only” is not worldwide;
- an empty country list from an unknown ATS is not automatically worldwide;
- `Intern` employment type plus a non-technical role is rejected;
- a paid internship mentioning an unpaid volunteer program in boilerplate is not rejected without contextual evidence;
- unknown pay stays unknown;
- feedback cannot promote an ineligible role into Apply;
- a source outage does not delete previously valid leads until expiry is independently confirmed.

### Pilot quality thresholds

- internship precision in Apply: at least 95%;
- technical-role precision in Apply: at least 95%;
- remote/country eligibility precision: at least 90% initially, then 95%;
- dead or closed apply links: below 5%;
- every Apply record posted/verified within the configured freshness window;
- 100% of hard rejections and warnings include evidence or a deterministic source fact.

## 14. Product metrics

Primary metrics:

- qualified Apply-now opportunities per candidate per week;
- median time from employer publication to discovery;
- percentage of surfaced opportunities the candidate actually applies to;
- callbacks and interviews per 20 applications;
- offers and useful recruiter conversations;
- incorrect eligibility decisions per 100 audited leads.

Diagnostic metrics:

- accepted/rejected/duplicate/error counts by source;
- rejection-reason distribution;
- unknown geography and unknown pay rates;
- dead-link rate;
- direct ATS versus aggregator yield;
- model extraction usage and correction rate;
- generation claims corrected by users.

Raw scrape volume is a diagnostic metric, not a success metric.

## 15. Operational and ethical constraints

- Respect each source's API terms, robots policy, attribution requirements, rate limits, and caching guidance.
- Do not bypass authentication, CAPTCHAs, or access controls.
- Store only public posting data and the candidate's local profile.
- Keep exact provenance for every extracted fact.
- Describe suspicious conditions, not unsupported accusations.
- Require human review before submitting any application.
- Do not infer protected traits or use them in ranking.
- Keep candidate country/work-authorization logic factual and separate from skill fit.

## 16. First implementation slice

The recommended first coding slice is deliberately small:

1. add `backend/internships/models.py`, `taxonomy.py`, and `pipeline.py`;
2. implement strict deterministic opportunity-type, technical-track, and remote-scope classification;
3. update the existing Himalayas source to query the current search API for technical internships;
4. store accepted records as `kind=internship` with structured evidence in `source_meta.internship`;
5. add unit fixtures for the highest-risk false positives;
6. add an Internships filter/view using the existing pipeline UI;
7. run the first friend-profile audit before adding more sources or model reasoning.

This slice proves the full value chain: source -> trustworthy classification -> candidate-relevant decision -> usable application link. Only after its precision is acceptable should the source registry and AI extraction be expanded.

## 17. Decisions that should remain fixed during the MVP

- Internship only means internship; adjacent early-career categories stay out.
- Technical only means CSE-related production, infrastructure, data, AI, security, systems, or research engineering work.
- Remote does not mean globally eligible.
- Paid is the default; unknown pay requires review.
- Direct, recent, canonical opportunities outrank scraped volume.
- Hard eligibility and safety rules run before fit ranking.
- AI explains ambiguity; it does not manufacture certainty.
- The pilot succeeds when friends find and progress through credible opportunities, not when the database becomes large.
