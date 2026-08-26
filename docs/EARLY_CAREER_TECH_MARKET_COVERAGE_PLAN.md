# Early-Career Tech Market Coverage — Master Product and Delivery Plan

**Status:** Proposed master plan
**Supersedes:** The internship-only product scope in `REMOTE_TECH_INTERNSHIPS_PLAN.md`
**Pilot audience:** Final-year B.Tech CSE students in India
**Coverage target:** Internships and early-career full-time technical roles from startups through large global employers
**Workplace policy:** India onsite/hybrid; India-eligible or worldwide remote

## 1. Product commitment

Build JustHireMe into an early-career technical opportunity intelligence system with the widest practical, lawful, measurable coverage of the current market.

The product must not claim to contain literally every job on the internet. No system can verify that claim because many roles are private, login-gated, shared only through campuses/referrals, unavailable through public APIs, or removed before discovery. The defensible promise is:

> Continuously search the broadest supported mix of employer career sites, ATS boards, job APIs, aggregators, startup sources, and community signals; measure what each source uniquely contributes; and surface every current opportunity that satisfies the candidate's location and early-career constraints.

Candidate data and personalized ranking remain local by default. A shared public-opportunity index may be added because continuously scanning the entire market separately on every student's laptop is inefficient, expensive, and incomplete.

## 2. Locked scope

### 2.1 Candidate

Initial candidate assumptions:

- based in India;
- final-year B.Tech CSE or adjacent computing degree;
- zero to two years of professional experience;
- may have internships, freelance work, open-source work, projects, hackathons, research, and coursework;
- willing to work onsite/hybrid in India;
- willing to work remotely for an employer anywhere only when India-based hiring is allowed;
- interested in internships and early-career full-time roles.

These facts are configurable per friend and must never be guessed from name, college, or location alone.

### 2.2 Accepted opportunity types

- paid technical internships;
- co-ops only when remote/India eligible and compatible with the candidate's academic schedule;
- graduate engineer and new-graduate programs;
- campus-independent fresher roles;
- entry-level full-time technical roles;
- `0–1`, `0–2`, and selectively `1–3 years` roles when demonstrated projects plausibly satisfy the work;
- Software Engineer I / SDE I / Associate Engineer / Junior Engineer equivalents;
- research-engineering internships or full-time roles suitable for undergraduate candidates.

Do not mix freelance gigs, unpaid volunteering, generic apprenticeships, sales internships, or unrelated operations roles into this feed.

### 2.3 Workplace and geography

Accept:

- onsite or hybrid roles located in India;
- remote roles explicitly open to India;
- remote roles explicitly open worldwide;
- remote roles open to a region that includes India;
- remote roles with no stated geography only in `Needs review`, never as confirmed eligible.

Reject or hide by default:

- onsite/hybrid roles outside India;
- “remote” roles restricted to the US, Canada, UK, EU, or another region that excludes India;
- roles requiring unsupported citizenship, security clearance, export-control status, or work authorization;
- roles whose required working hours cannot overlap the candidate's timezone/preferences.

### 2.4 Technical role taxonomy

Primary tracks:

- software engineering;
- backend, frontend, full-stack, web platform;
- Android, iOS, React Native, Flutter, and mobile infrastructure;
- AI engineering, machine learning, applied AI, LLM systems, NLP, computer vision, speech, recommender systems, and MLOps;
- data engineering, analytics engineering, data science, and ML/data platforms;
- DevOps, cloud, platform, infrastructure, SRE, observability, and developer experience;
- cybersecurity, application/product/cloud security, SOC engineering, and security research;
- QA automation, SDET, testing infrastructure, and performance engineering;
- embedded software, firmware, robotics software, IoT software, and systems programming;
- compilers, databases, distributed systems, networking, operating systems, graphics, and research engineering.

Secondary tracks may be enabled explicitly:

- technical product engineering roles with substantial coding;
- solutions engineering with substantial implementation work;
- quantitative developer/research roles accessible to undergraduates;
- developer advocacy only when software creation is a material responsibility.

Exclude recruiting, HR, sales, marketing, customer success, finance, legal, content, manual QA, generic operations, BPO, and data-entry roles from the default technical feed.

## 3. Product flow

```text
Company universe + query matrix
  -> Direct ATS / career-site collectors
  -> Licensed job-data APIs
  -> Public aggregators and remote feeds
  -> Community/startup discovery signals
  -> Raw source records with provenance
  -> Canonicalization and cross-source deduplication
  -> Opportunity type + technical taxonomy
  -> Workplace/location/India-eligibility gates
  -> Freshness, active-link, compensation, and safety checks
  -> Candidate hard eligibility
  -> Fit, compensation, career-growth, and urgency intelligence
  -> Apply now / Strong stretch / Needs review / Skip
  -> Local tailoring, outreach, preparation, and tracking
```

Sources discover records. Deterministic rules establish hard facts. Optional models resolve messy text and explain evidence. The existing graph/vector layer personalizes surviving opportunities.

## 4. Coverage architecture decision

### 4.1 Why the desktop alone is insufficient

The current local-first scanner is appropriate for personal discovery, but maximum market coverage introduces constraints:

- hundreds or thousands of company boards must be revisited when the user's laptop is off;
- each friend's installation would repeat the same public network requests;
- paid API keys cannot safely be distributed in a desktop application;
- source rate limits and query budgets need central coordination;
- closed-role detection requires historical state and scheduled rechecks;
- cross-source deduplication works better over a shared public corpus;
- new listings lose value if discovered days late.

### 4.2 Recommended hybrid design

Add an optional shared **Opportunity Index** that stores only public employer/job data:

```text
Central ingestion plane
  collectors -> raw records -> canonical opportunities -> public delta feed/API

Local JustHireMe desktop
  public opportunity deltas + local candidate profile
    -> eligibility + private fit ranking + generation + CRM
```

Privacy boundary:

- central service stores public job/company/source data only;
- resumes, candidate graphs, feedback, generated documents, and application history stay local;
- the desktop may send a generic query such as role/location only when the user enables live server search;
- no candidate profile is required to download the public feed;
- API provider keys live in a server-side secret manager or remain in a user's local settings for personal connectors.

### 4.3 Low-cost deployment progression

1. **Pilot:** run collectors locally or in scheduled CI and publish a versioned compressed catalog artifact.
2. **Shared beta:** scheduled workers plus a small managed Postgres database/object store and read-only delta API.
3. **Scale:** job queue, provider-specific workers, cache, dead-link validation, observability, and regional mirrors only when usage demands it.

The public index must be optional so the current local-only mode remains viable.

## 5. Source portfolio

No single source provides adequate coverage. Use independent layers so one provider outage, policy change, or blind spot does not collapse discovery.

### 5.1 Layer A — direct public ATS and company career sites

Highest-trust source because the employer controls the posting and the application URL is canonical.

Existing JustHireMe adapters to retain and strengthen:

- Greenhouse;
- Lever;
- Ashby;
- Workable;
- SmartRecruiters;
- Recruitee;
- Personio;
- Teamtailor;
- Breezy HR;
- Pinpoint;
- BambooHR;
- Rippling;
- supported RSS/JSON career feeds.

Priority new enterprise adapters:

- Workday tenant career sites;
- iCIMS;
- Jobvite;
- Eightfold;
- Oracle Recruiting / Taleo;
- SAP SuccessFactors;
- Freshteam;
- Zoho Recruit;
- Darwinbox public career pages;
- Comeet;
- Avature and other platforms observed in the target-company registry.

Rules:

- use a documented/public endpoint or the public career page intended for applicants;
- do not bypass authentication, CAPTCHA, access controls, or anti-bot challenges;
- preserve the employer's canonical apply URL;
- capture provider, tenant/slug, requisition ID, published/updated dates, active status, and last verification;
- keep adapter fixtures because provider schemas change;
- treat an individual board failure as isolated and observable.

### 5.2 Layer B — broad licensed job-data APIs

These APIs are the practical way to cover sources that are unavailable through open APIs and to increase recall quickly.

Benchmark candidates:

- **TheirStack:** broad job search with country, title, technology, company, date, and remote filters; supports incremental discovery patterns.
- **Coresignal Jobs Data API:** large global structured job corpus with multi-source records and active-status refresh.
- other vendors only after they pass the same benchmark and licensing review.

Do not subscribe blindly. Run a controlled bake-off using the same query matrix and measure:

- unique eligible opportunities after canonical deduplication;
- India onsite/hybrid coverage;
- India-eligible remote coverage;
- internships and zero-to-two-year role coverage;
- direct/canonical URL availability;
- description completeness;
- posting and closure latency;
- duplicate and stale rates;
- cost per unique eligible active opportunity;
- contractual right to show records in JustHireMe.

Select at most one primary broad vendor initially. Add a second only when its incremental unique yield justifies its cost.

### 5.3 Layer C — search and aggregator APIs

Recommended sources:

- **SerpApi Google Jobs:** targeted India city, India remote, and worldwide remote query coverage; useful for discovering postings from boards without an adapter.
- **Adzuna India API:** India keyword/location/salary/full-time searches.
- **Jooble India API:** broad web job search by keyword and location.
- **Himalayas:** remote jobs with structured country, timezone, employment type, and worldwide filters.
- **Remotive:** supplemental remote technical roles with required attribution and conservative polling.
- existing RemoteOK, Jobicy, We Work Remotely, RSS, HN, GitHub, and Reddit sources when their terms and signal quality are acceptable.

Aggregator records are leads, not authority. Re-resolve to the employer/ATS URL when possible and apply every normal quality/eligibility rule.

### 5.4 Layer D — Indian early-career and startup discovery

Target coverage includes postings seen on:

- Naukri;
- Foundit;
- Internshala;
- Unstop;
- Cutshort;
- Instahyre;
- Wellfound;
- LinkedIn Jobs;
- Indeed;
- startup communities, incubators, accelerators, hackathon communities, and college-facing hiring programs.

Many of these do not expose unrestricted public job-search APIs. Use one of the following compliant paths:

1. licensed broad-data/search provider coverage;
2. approved official partner/API access;
3. public search discovery followed by canonical employer-page validation;
4. user-pasted posting;
5. employer/community-submitted feed;
6. public RSS/JSON endpoint with acceptable terms.

Do not create brittle scrapers that evade login, rate controls, robots policy, or access restrictions. LinkedIn talent/job APIs require approval for relevant restricted capabilities; direct uncontrolled API access should not be assumed.

### 5.5 Layer E — startup and company-universe discovery

Maintain a company registry rather than waiting for generic queries to find every employer.

Company cohorts:

- India seed and early-stage startups;
- India growth-stage startups, unicorns, and public technology companies;
- global remote-first startups that hire in India;
- accelerator/incubator portfolios;
- product companies with engineering teams in India;
- global technology giants;
- GCCs and multinational engineering centers in India;
- developer-tool, AI, security, data, and infrastructure companies;
- research labs and deep-tech companies.

Each registry record should include:

```yaml
company_id: stable-id
name: Example
domain: example.com
company_cohort: india_growth_startup
careers_url: https://example.com/careers
ats_provider: greenhouse
ats_tenant: example
india_presence: true
known_remote_scope: india_or_worldwide
technical_focus: [ai_ml, backend, data]
last_board_check_at: 2026-08-24T00:00:00Z
last_success_at: 2026-08-24T00:00:00Z
enabled: true
```

Registry sources must have usable licensing/terms. Company discovery can use job-provider company catalogs, public accelerator portfolios, employer submissions, and community contributions. Company metadata is a crawl target, not evidence that an employer currently has an opening.

## 6. Query matrix

Generic “software jobs” queries will miss most entry-level terminology. Maintain a versioned, testable matrix.

### 6.1 Opportunity terms

- intern, internship, software intern, engineering intern;
- graduate engineer trainee when the work is technical and paid;
- new graduate, new grad, graduate software engineer;
- fresher, entry level, entry-level, junior;
- SDE I, SDE 1, Software Engineer I, Engineer I;
- Associate Software Engineer, Associate Developer;
- 0–1 years, 0–2 years, one year experience;
- campus-independent/off-campus hiring.

### 6.2 Technical tracks

Run role-specific queries for every taxonomy track rather than a single combined query. Include title and description synonyms such as `AI engineer`, `ML engineer`, `applied scientist intern`, `data engineer`, `platform engineer`, `cloud engineer`, `security engineer`, `SDET`, and `firmware engineer`.

### 6.3 Indian locations

At minimum:

- India;
- Bengaluru/Bangalore;
- Hyderabad;
- Pune;
- Gurugram/Gurgaon;
- Noida;
- Delhi NCR;
- Chennai;
- Mumbai/Navi Mumbai;
- Ahmedabad;
- Kochi;
- Kolkata;
- Chandigarh/Mohali;
- Jaipur;
- Coimbatore;
- remote India and work from home India.

Location aliases must normalize into stable city/state/country IDs.

### 6.4 Remote reach

Search separately for:

- worldwide/anywhere remote;
- India remote;
- APAC/Asia remote;
- remote roles with UTC+05:30-compatible hours;
- employer-of-record or contractor arrangements that explicitly permit India, displayed separately when not standard employment.

Never infer candidate eligibility solely from a remote keyword.

## 7. Canonical opportunity model

The current canonical-URL deduplication is not enough because the same requisition appears through an ATS, Google Jobs, LinkedIn, Adzuna, Jooble, and other aggregators.

Create two entities:

### 7.1 Source record

One raw observation from one provider:

```json
{
  "source_record_id": "provider:external-id",
  "provider": "adzuna",
  "source_url": "...",
  "canonical_apply_url": "...",
  "raw_title": "...",
  "raw_company": "...",
  "raw_description": "...",
  "observed_at": "...",
  "provider_published_at": "...",
  "provider_updated_at": "...",
  "raw_payload_hash": "...",
  "attribution": "..."
}
```

### 7.2 Canonical opportunity

The deduplicated job shown to users:

```json
{
  "opportunity_id": "stable-id",
  "requisition_id": "...",
  "company_id": "...",
  "title": "Machine Learning Engineer Intern",
  "opportunity_type": "internship",
  "technical_track": "ai_ml",
  "seniority": "intern",
  "experience_min_years": 0,
  "experience_max_years": 1,
  "employment_type": "internship",
  "workplace_type": "remote",
  "location_country": null,
  "location_city": null,
  "allowed_countries": ["IN"],
  "allowed_regions": ["APAC"],
  "timezone_constraints": ["UTC+03:00", "UTC+08:00"],
  "compensation": {},
  "education_requirements": {},
  "authorization_requirements": {},
  "published_at": "...",
  "updated_at": "...",
  "deadline": "...",
  "first_seen_at": "...",
  "last_seen_active_at": "...",
  "active_status": "active",
  "canonical_apply_url": "...",
  "source_record_ids": ["..."]
}
```

Deduplication sequence:

1. canonical employer/ATS URL and requisition ID;
2. provider mappings and redirect resolution;
3. normalized company domain + normalized title + normalized location;
4. description fingerprint and date proximity;
5. cautious fuzzy matching with explainable confidence;
6. never merge uncertain records automatically when applications may be distinct.

## 8. Freshness and active-state model

Keep these facts separate:

- source-published date;
- source-updated date;
- first observed date;
- application deadline;
- last successfully observed active date;
- closed/expired observation date.

Rules:

- a currently published direct ATS record is active even when older than seven days;
- age affects priority, not truth, when the application remains open;
- future deadline is strong evidence of availability but still requires a live URL;
- explicit closed/expired status is decisive;
- aggregator disappearance alone is not enough to close a role if the direct employer page remains active;
- never relabel `updated_at` as original publication time;
- recheck high-priority links more frequently than low-priority records;
- mark closed records instead of deleting them, preserving pipeline history.

## 9. Eligibility gates

Run hard gates before fit ranking.

### 9.1 Opportunity gate

Accepted opportunity type and technical taxonomy.

### 9.2 Workplace gate

- onsite/hybrid -> India location required;
- remote -> India/worldwide/containing-region eligibility required for Apply;
- unclear remote geography -> Needs review.

### 9.3 Candidate stage gate

Evaluate:

- graduation year/window;
- current enrollment;
- degree/branch requirements;
- start date and duration;
- weekly availability;
- required experience;
- work authorization/citizenship;
- security clearance/export restrictions;
- timezone overlap.

Return `eligible`, `likely_eligible`, `needs_review`, or `ineligible`, with evidence for every blocker and uncertainty.

### 9.4 Safety gate

Reject or prominently quarantine:

- unpaid/exposure/equity-only work unless explicitly enabled;
- application/training/equipment/security fees;
- payment requested to receive work;
- coercive bonds and exit penalties;
- original-document surrender;
- suspicious identity/contact mismatches;
- free-work trials or excessive unpaid assignments;
- commission-only technical “jobs.”

Describe observed conditions. Do not make unsupported fraud or legal claims.

## 10. Compensation intelligence

“High paying” must be evidence-based rather than inferred from company reputation.

Store:

- minimum and maximum;
- currency;
- hourly/monthly/annual/one-time period;
- base versus stipend, bonus, equity, benefits;
- source/evidence;
- disclosed, estimated-by-source, model-extracted, or unknown provenance.

Normalize only for comparison:

- convert using a timestamped exchange-rate source;
- annualize or monthly-normalize only when hours/period are known;
- compare internships against internship cohorts, not senior salaries;
- compare India onsite roles against India/location/track cohorts;
- compare global remote roles against other India-eligible remote roles;
- show the original amount alongside normalized values;
- never label undisclosed pay as high-paying.

Present separate signals:

- disclosed compensation;
- market percentile/confidence;
- benefits/equity;
- compensation clarity;
- user minimum satisfied/unknown/failed.

## 11. Opportunity intelligence and ranking

Do not use one opaque score. Show four independent views:

1. **Eligibility:** can this candidate apply?
2. **Fit:** does existing evidence satisfy the requirements?
3. **Career growth:** will the role build useful technical depth and portfolio evidence?
4. **Opportunity value:** compensation, credibility, freshness, work mode, and application effort.

### 11.1 Priority score after hard gates

Suggested initial composition:

| Component | Weight |
| --- | ---: |
| Candidate/project fit | 25 |
| Career-growth value | 20 |
| Compensation value and clarity | 15 |
| Freshness/deadline urgency | 15 |
| Engineering substance/mentorship | 10 |
| Company/posting credibility | 10 |
| Application effort/friction | 5 |

Keep the components visible. Unknown information receives no invented credit.

### 11.2 Decision buckets

- **Apply now:** hard-eligible, active, safe, strong priority.
- **Strong stretch:** hard-eligible; misses some preferred skills but has adjacent evidence and high growth value.
- **Needs review:** important geography, pay, stage, or authorization fact is unclear.
- **Skip:** evidenced incompatibility, unsafe condition, closed role, non-technical role, or user minimum failure.

Feedback may adjust ranking among eligible opportunities. It must never override geography, authorization, safety, or active-status gates.

## 12. AI boundary

### Deterministic first

Use rules/structured fields for:

- opportunity type and common title exclusions;
- experience ranges and seniority;
- workplace type and location normalization;
- country/region/timezone restrictions;
- dates, deadline, and active status;
- compensation ranges/periods;
- graduation/enrollment/authorization requirements;
- unpaid, fee, bond, deposit, and suspicious-contact flags.

### Model-assisted second

Use a configured local or remote model for:

- messy or conflicting descriptions;
- technical-track classification when rules are ambiguous;
- requirement/evidence extraction into strict JSON;
- connecting profile projects to responsibilities;
- career-growth explanation;
- application tailoring and interview preparation.

Every extracted conclusion must contain value, confidence, and evidence span. Missing facts remain unknown. Low-confidence material facts route to Needs review.

## 13. Backend design

Reuse current source adapters and add focused domains:

```text
backend/opportunities/
  models.py
  canonicalize.py
  deduplicate.py
  taxonomy.py
  extraction.py
  eligibility.py
  safety.py
  compensation.py
  scoring.py
  pipeline.py

backend/catalog/
  company_registry.py
  query_matrix.py
  source_registry.py
  sync.py
  export.py

backend/discovery/sources/
  existing adapters
  workday.py
  enterprise_ats.py
  adzuna.py
  jooble.py
  serpapi_jobs.py
  broad_jobs_provider.py
```

Business logic stays out of routers, UI components, and provider-specific adapters. Adapters return source records; the opportunity pipeline determines user-visible meaning.

Repository changes:

- retain `leads` for local CRM/application state;
- add source-record and canonical-opportunity persistence;
- link one lead/application to one canonical opportunity;
- store extraction/evidence version so decisions can be recomputed;
- use migrations after contracts stabilize in fixtures;
- support delta import/export for the shared public catalog;
- preserve all source attribution and terms metadata.

## 14. Scheduler and source operations

For each provider configure:

- enabled status;
- polling interval and jitter;
- request and credit budget;
- concurrency limit;
- retry/backoff policy;
- cache/ETag/Last-Modified behavior;
- attribution requirements;
- health status;
- last successful fetch;
- parser version;
- result and error counts.

Operational rules:

- direct high-value ATS boards: frequent respectful checks based on observed update rate;
- daily-refreshed APIs: do not poll more frequently than their data changes;
- paid search APIs: incremental queries and cached pages only;
- circuit-break failing sources;
- use exponential backoff on 429/5xx responses;
- never let one provider abort a scan;
- revalidate canonical links and deadlines asynchronously;
- store raw payload hashes to avoid reprocessing unchanged records;
- generate source health and unique-yield dashboards.

## 15. Cost controls

API willingness does not justify waste.

- use provider preview/count endpoints before consuming record credits;
- query incrementally by discovered/published time;
- cache identical search pages;
- deduplicate before paid enrichment when licensing permits;
- cap credits per provider per day and per scan;
- alert at 50%, 80%, and 100% of budget;
- report cost per fetched record and cost per unique eligible record;
- terminate sources whose incremental yield stays below the agreed threshold;
- keep free direct ATS data as the durable backbone;
- never ship paid API secrets inside the desktop binary.

## 16. Frontend

Add an `Opportunities` workspace focused on early career:

Tabs:

- Apply now;
- Strong stretch;
- Needs review;
- Applied;
- Skipped/closed.

Filters:

- internship/full-time/new-grad;
- technical track;
- remote/onsite/hybrid;
- worldwide/India-eligible/India city;
- stipend/salary disclosed and minimum;
- experience requirement;
- posted/verified date;
- company cohort: startup, growth, giant, GCC;
- source and direct-employer status;
- deadline;
- eligibility confidence.

Every card should show:

- opportunity type and technical track;
- employer and company cohort;
- workplace/location and India-eligibility status;
- compensation with provenance;
- experience/graduation requirements;
- posted/updated/last-verified/deadline facts;
- Apply/Stretch/Review decision and concise reasons;
- direct application link.

The drawer should show the full eligibility checklist, source provenance, duplicate/source observations, compensation comparison, project evidence, gaps, career-growth breakdown, and questions the candidate needs to verify.

## 17. Delivery sequence

### Phase 0 — scope contracts and evaluation corpus

Deliver:

- `Opportunity`, `SourceRecord`, `EligibilityDecision`, `Compensation`, and evidence contracts;
- role/opportunity/location taxonomies;
- query matrix;
- positive/negative fixtures across internship, new-grad, entry-level, remote restrictions, India locations, seniority traps, safety issues, and stale/closed records;
- manually reviewed target-company and known-opening benchmark.

Exit:

- every hard rule has fixtures;
- no hard fact requires an LLM;
- expected decisions are manually audited.

### Phase 1 — expanded local vertical slice

Deliver:

- internships plus early-career full-time classification;
- India onsite/hybrid and India-eligible/worldwide remote policies;
- updated Himalayas filtered search;
- current direct ATS adapters flowing through the new opportunity pipeline;
- Apply/Stretch/Review/Skip data in the existing pipeline UI.

Exit:

- no senior/non-technical leakage in audited Apply records;
- remote-US-only does not appear as India eligible;
- every record has active/freshness and canonical URL evidence.

### Phase 2 — India/search API expansion

Deliver:

- Adzuna India connector;
- Jooble India connector;
- SerpApi Google Jobs connector with bounded query matrix;
- cross-source source-record storage and canonical deduplication;
- source attribution and API-budget counters.

Exit:

- providers survive partial failures and rate limits;
- duplicate applications consolidate without losing source provenance;
- cost and unique yield are visible per source.

### Phase 3 — broad-data vendor bake-off

Deliver:

- provider-neutral licensed job-data connector;
- same query benchmark against TheirStack, Coresignal, or selected alternatives;
- coverage/cost report;
- one selected primary vendor if it materially improves eligible unique coverage.

Exit:

- contractual display/use rights confirmed;
- unique eligible yield and stale/dead rates measured;
- selected provider has a hard daily/monthly budget.

### Phase 4 — company registry and enterprise ATS coverage

Deliver:

- startup/giant/GCC company registry;
- Workday and prioritized enterprise ATS adapters;
- tenant/board discovery and health validation;
- source contribution workflow with fixtures.

Exit:

- benchmark company cohorts have measurable scan coverage;
- zero openings is distinguishable from a broken collector;
- adapters have regression fixtures and failure telemetry.

### Phase 5 — shared Opportunity Index

Deliver:

- scheduled ingestion deployment;
- public-data database and raw-payload/object retention policy;
- signed/versioned compressed delta feed or read-only API;
- desktop delta synchronization;
- secrets, budget, and health management.

Exit:

- candidate profile never enters central storage;
- desktop works without the index in degraded local mode;
- index recovers safely from provider outages and replays.

### Phase 6 — intelligence, generation, and pilot

Deliver:

- four-part eligibility/fit/growth/value explanation;
- disclosed compensation comparison;
- project-first resume and outreach;
- interview preparation;
- friend-pilot feedback and outcome tracking.

Exit:

- generated claims are profile-grounded;
- model outage preserves eligibility and basic ranking;
- pilot metrics meet the thresholds below before public expansion.

## 18. Coverage and quality evaluation

“Absolute coverage” becomes a measured engineering objective.

### 18.1 Benchmark universe

Build a manually reviewed set across:

- Indian early-stage startups;
- Indian scaleups/unicorns;
- remote-first global startups;
- global technology giants;
- India GCC/MNC engineering employers;
- major AI/ML, data, developer-tools, security, and cloud companies.

Record their career sites, ATS provider, known relevant openings, and expected scan behavior.

### 18.2 Coverage metrics

- company-board coverage by cohort;
- known-opening capture rate;
- source recall relative to the observed union of all sources;
- unique eligible opportunities per source;
- unique eligible opportunities per rupee/API credit;
- publication-to-discovery latency;
- India onsite/hybrid yield;
- India-eligible remote yield;
- internship versus full-time early-career yield;
- employer-direct URL rate.

### 18.3 Quality thresholds

Initial pilot targets:

- technical precision in Apply: >=95%;
- early-career precision in Apply: >=95%;
- workplace/location eligibility precision: >=95%;
- dead/closed links in Apply: <5%, then <2%;
- canonical deduplication precision: >=98%;
- 100% of hard decisions include source evidence;
- no paid provider retained without measurable unique yield;
- no source allowed to silently fail.

### 18.4 Outcome metrics

- qualified opportunities per friend per week;
- applications started and completed;
- callbacks/interviews per 20 applications;
- offers and recruiter conversations;
- time from discovery to application;
- reasons candidates skip high-ranked records;
- eligibility/extraction corrections per 100 reviewed opportunities.

Raw fetched-record count is not a success metric.

## 19. Immediate implementation slice

Do this before adding dozens of source-specific files:

1. introduce canonical `Opportunity` and `SourceRecord` contracts;
2. add internship/new-grad/entry-level opportunity classification;
3. add the CSE/AI technical taxonomy;
4. implement the workplace rule: onsite/hybrid India, remote India-eligible/worldwide;
5. implement candidate-stage and safety hard gates;
6. update Himalayas to the current filtered API;
7. route existing direct ATS adapters through the opportunity pipeline;
8. store canonical/source provenance without discarding the existing local lead CRM;
9. build the adversarial fixture corpus;
10. expose Apply/Stretch/Review/Skip in the current UI;
11. run the first audited query set and establish baseline yield;
12. only then add Adzuna, Jooble, SerpApi, and the paid-provider bake-off.

This sequence prevents a flood of low-quality duplicates from overwhelming a data model that cannot yet represent eligibility or provenance.

## 20. Fixed principles

- Maximize lawful, measured coverage; never promise unknowable totality.
- Internships and early-career full-time roles share one opportunity engine but retain distinct labels and rules.
- Onsite/hybrid means India only for the pilot.
- Remote means India eligible, worldwide, or visibly unresolved—not merely a remote keyword.
- Hard eligibility and safety gates precede ranking.
- Direct employer data outranks aggregator interpretations.
- Preserve all source provenance through deduplication.
- Pay for unique coverage, freshness, and canonical data—not raw duplicate volume.
- AI extracts and explains; it does not invent eligibility, pay, or certainty.
- Public opportunity aggregation may be shared; candidate data remains local.
- Success is measured through credible opportunities, applications, interviews, and offers.
