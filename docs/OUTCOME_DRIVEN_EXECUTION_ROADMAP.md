# JustHireMe Early-Career Opportunity Engine — Outcome-Driven Execution Roadmap

**Status:** Active delivery roadmap — production vertical slice implemented; human evidence gates remain
**Companion documents:** `OPPORTUNITY_SYSTEM_FUNDAMENTALS.md`, `EARLY_CAREER_TECH_MARKET_COVERAGE_PLAN.md`
**Initial cohort:** Final-year B.Tech CSE candidates based in India
**Primary outcome:** Credible interviews and offers from verified, applicable opportunities

## 1. Executive objective

Build a system that repeatedly turns public market opportunities into completed, high-quality applications and measurable candidate outcomes:

```text
Observed posting
  -> canonical, verified-live opportunity
  -> candidate is demonstrably eligible
  -> opportunity is worth applying to
  -> truthful application is completed quickly
  -> recruiter reply
  -> interview
  -> offer / learning signal
```

The project is not validated by the number of sources, records, generated documents, or model calls. It is validated only when real candidates reliably reach interviews without being sent toward closed, ineligible, unsafe, or irrelevant roles.

### 1.1 Implementation checkpoint — 2026-08-24

Implemented and verified in the local product:

- immutable source observations, canonical opportunities, cautious exact dedupe, and lifecycle facts;
- authoritative direct-source disappearance reconciliation: only a successfully completed ATS target may close a missing requisition, failed/unscanned sources never do, and every saved candidate is immediately re-decided;
- candidate-specific India/workplace, early-career, technical, graduation, experience, pay, fee, unpaid, and bond decisions;
- per-candidate specialization, opportunity-type, onsite/hybrid, and India/worldwide-remote preferences;
- transparent candidate-fit evidence from locally supplied technical skills and project technologies, with exact matches shown and missing evidence kept neutral rather than invented;
- local candidate constraint profiles and candidate-scoped decision queues;
- asynchronous production scans with inspectable progress, per-source health, persisted run outcomes, and restart-interruption handling;
- a three-hour in-app refresh that scans the public market once and locally recomputes every saved candidate, preventing duplicate network sweeps for the five-person pilot;
- a default bounded production matrix of `160` searches spanning `18` ATS/feed provider families;
- India-priority startup and Workday/GCC targets plus remote and keyless public feeds;
- evidence-based career-growth, hiring-confidence, and priority signals;
- `Apply now`, `Strong stretch`, `Needs review`, and `Skip` UI queues;
- desktop and mobile opportunity workspaces, including a viewport-bound mobile queue verified to scroll through candidate constraints into actionable cards;
- promotion of a non-skipped opportunity into the existing application/resume/follow-up pipeline.
- immutable candidate/opportunity outcome events for application starts, submissions, outreach, replies, screens, assessments, interviews, rejections, and offers;
- a candidate funnel exposing completion, meaningful contacts, interviews, offers, source attribution, and the north-star `interviews per 20 applications` metric.
- a five-candidate cohort control showing progress toward `100` applications, `10` meaningful contacts, `5` interviews, and traction for at least `3 / 5` candidates.
- explicit local application-profile snapshots per candidate; candidate-scoped generation is blocked until a complete profile is linked, preventing one pilot participant's resume evidence from being used for another participant.

Live adapter controls on 2026-08-24 (diagnostic, not human gold):

- six India startup ATS boards: `83` canonical opportunities, `4` Apply now, `5` Needs review, `74` Skip, zero source failures;
- nine India-priority Workday searches: `79` canonical opportunities, `1` Needs review, `78` Skip, zero source failures;
- seven keyless aggregator/remote-feed searches: `227` canonical opportunities, `4` Needs review, `223` Skip, zero source failures.

These results prove the runtime path and conservative gates. They do not satisfy
the Phase 0 human-review exit criteria or promise interviews before the five-person pilot runs.

## 2. Product outcome contract

### 2.1 North-star metric

**Verified interviews per 20 completed applications.**

This measures the entire system: source quality, liveness, eligibility, ranking, application quality, timing, and follow-up.

It must be paired with application volume so the system cannot inflate its rate by recommending only one obvious company.

### 2.2 Primary outcome metrics

- qualified `Apply now` opportunities per active candidate per week;
- completed applications per active candidate per week;
- recruiter replies per 20 completed applications;
- interviews per 20 completed applications;
- offers per interview and per completed application;
- median time from source publication/discovery to candidate application;
- percentage of Apply-now recommendations confirmed live and applicable during audit.

### 2.3 Guardrail metrics

- dead/closed links in Apply now;
- hard-ineligible opportunities in Apply now;
- non-technical or non-early-career opportunities in Apply now;
- unsafe/fee/unpaid/bond-heavy opportunities in Apply now;
- unsupported “worldwide” or compensation claims;
- duplicate applications caused by failed canonicalization;
- paid-source spend per unique eligible opportunity and per completed application;
- candidate time spent reviewing false positives.

### 2.4 Anti-vanity metrics

These may be reported diagnostically but must never define success:

- raw jobs scraped;
- total database size;
- total companies observed;
- model-generated score average;
- resumes generated without an application;
- source requests made;
- duplicate aggregator records.

## 3. Pilot definition

Start with five real final-year CSE candidates, including the maintainer's friends.

Each candidate supplies or confirms:

- resume/profile;
- graduation date;
- current enrollment;
- home country and timezone;
- India cities acceptable for onsite/hybrid work;
- remote-work preferences;
- work authorizations/citizenships;
- earliest start date and weekly availability;
- internship/full-time preferences;
- technical tracks;
- minimum compensation policy;
- unpaid-work and bond policy;
- existing applications so the system does not recommend duplicates.

The pilot must include different skill shapes rather than five nearly identical profiles, for example:

- backend/full-stack;
- AI/ML/data;
- frontend/mobile;
- cloud/DevOps/security;
- general software engineer with strong projects but limited specialization.

Candidate information stays local. The shared evaluation dataset contains public postings and expected decisions, not private resumes.

## 4. Delivery philosophy

Phases are controlled by exit outcomes, not dates. Indicative durations assume one primary full-time builder; reduced availability extends dates but must not weaken exit criteria.

Do not expand source volume when the current system cannot correctly canonicalize, verify, or classify its existing records. More ingestion before truth and eligibility foundations increases noise and candidate workload.

## 5. Roadmap overview

| Phase | Indicative effort | Main outcome | Exit decision |
| --- | ---: | --- | --- |
| 0. Baseline and gold set | 3–5 days | We can measure current failure honestly | Gold corpus and baseline report exist |
| 1. Opportunity truth | 1.5–2 weeks | One real opening appears once and is verifiably live | Liveness and deduplication meet thresholds |
| 2. Applicability | 1.5–2 weeks | Apply now contains roles the candidate can actually pursue | Eligibility precision reaches target |
| 3. Coverage backbone | 2–3 weeks | Direct/free sources cover the priority company universe | Known-opening capture and latency meet target |
| 4. Paid market expansion | 1.5–2 weeks | Paid sources add measurable unique eligible coverage | Provider retained or rejected on evidence |
| 5. Opportunity intelligence | 1.5–2 weeks | Candidates understand priority, value, pay, and hiring confidence | Top recommendations survive human audit |
| 6. Interview-conversion workflow | 1.5–2 weeks | Apply-now records become completed applications quickly | Completion and time-to-apply targets hold |
| 7. Real-candidate pilot | 4 weeks | Applications produce replies and interviews | Outcome targets validate or reject the system |
| 8. Shared index and scale | After validation | Coverage continues while candidate devices are offline | Privacy, reliability, and public-beta gates hold |

## 6. Phase 0 — baseline, corpus, and measurement

### Goal

Establish what the current system gets right and wrong before changing its architecture or purchasing data.

### Work

1. Onboard the five pilot profiles and record only confirmed candidate constraints.
2. Build a manually reviewed gold corpus of at least 300 public postings:
   - 60 valid India technical internships;
   - 50 valid India early-career full-time roles;
   - 40 valid India-eligible/worldwide remote roles;
   - 35 remote roles that exclude India;
   - 30 senior/mid-level traps mentioning juniors or interns in prose;
   - 25 non-technical roles at technology companies;
   - 25 closed, expired, evergreen, or ambiguous postings;
   - 20 unsafe/unpaid/fee/bond cases;
   - 15 difficult duplicates observed through multiple sources.
3. Build a known-opening benchmark across at least 100 target employers:
   - Indian startups/product companies;
   - global remote-first startups;
   - giants and India GCC/MNC engineering teams;
   - AI, data, developer-tool, security, and cloud companies.
4. Run the current discovery system and record:
   - known-opening capture;
   - duplicate rate;
   - dead/closed rate;
   - India-eligibility errors;
   - early-career and technical classification errors;
   - discovery latency where publication time is available;
   - current source yield.
5. Define event names and a metrics dictionary before feature work.

### Candidate outcome

None promised yet. This phase prevents us from claiming improvement without a baseline.

### Exit criteria

- 300-posting gold corpus has two-pass human review for hard decisions;
- 100-employer benchmark has careers/ATS URLs and expected scan behavior;
- current precision, capture, duplicate, dead-link, and latency metrics are recorded;
- every later phase can run against the same dataset;
- disputed examples are labeled ambiguous rather than forced into false certainty.

### Stop condition

Do not begin paid-provider integration without this benchmark. Otherwise API spend cannot be evaluated.

## 7. Phase 1 — canonical opportunity truth

### Goal

Represent the actual employer requisition rather than a loose collection of URLs.

### Work

1. Introduce `SourceRecord` and `CanonicalOpportunity` contracts.
2. Preserve full source descriptions/raw payload hashes; create bounded derived text only for scoring/model calls.
3. Canonicalize redirects, tracking parameters, ATS requisition IDs, employer domains, titles, and locations.
4. Deduplicate through:
   - canonical employer/ATS URL;
   - requisition/provider IDs;
   - employer domain + normalized title + location;
   - description fingerprint/date proximity;
   - cautious fuzzy matching with confidence.
5. Persist distinct lifecycle facts:
   - published;
   - updated;
   - first seen;
   - deadline;
   - last verified active;
   - closed/expired.
6. Implement active-state verification:
   - direct ATS membership/currently published;
   - usable application route;
   - explicit deadline/closed state;
   - periodic canonical-link checks;
   - aggregator disappearance reconciled against the direct source.
7. Retain all source observations and attribution after deduplication.

### Candidate outcome

Candidates no longer waste time on duplicate, closed, or contextless opportunities.

### Exit criteria

- canonical deduplication precision >=98% on the gold corpus;
- no two Apply-now cards point to the same known requisition;
- live/closed classification precision >=95%;
- dead/closed records in Apply now <5%;
- 100% of opportunities show source and last-verification provenance;
- publication, update, and discovery time are never conflated in the UI/data contract;
- no adapter discards the full description needed for eligibility analysis.

### Stop condition

Do not expand broad aggregators until duplicate and lifecycle thresholds hold. A larger uncanonicalized corpus is regression, not progress.

## 8. Phase 2 — candidate applicability

### Goal

Ensure every Apply-now opportunity is something the specific candidate can realistically pursue.

### Work

1. Add the opportunity taxonomy:
   - internship/co-op;
   - new-grad/graduate program;
   - entry-level full-time;
   - selective one-to-three-year stretch;
   - exclude senior, freelance, non-technical, and unrelated categories.
2. Add the CSE technical taxonomy for software, AI/ML, data, cloud/DevOps, security, mobile, automation, embedded, and systems.
3. Normalize workplace and geography:
   - India onsite/hybrid;
   - India remote;
   - worldwide remote;
   - region/country restricted;
   - remote geography unknown.
4. Extract hard candidate requirements:
   - graduation and enrollment;
   - experience range;
   - degree/branch;
   - start date/duration/hours;
   - country, citizenship, work authorization, clearance;
   - timezone overlap.
5. Add deterministic safety policy for unpaid work, fees, deposits, bonds, exit penalties, free trials, original documents, and suspicious contact paths.
6. Return `eligible`, `likely_eligible`, `needs_review`, or `ineligible` with evidence for each decision.
7. Prevent fit or feedback scores from buying back a hard rejection.

### Candidate outcome

The candidate can trust Apply now as an action queue rather than another search-results page.

### Exit criteria

- early-career technical precision in Apply now >=95%;
- workplace/candidate-country eligibility precision >=95%;
- zero known hard-ineligible gold cases enter Apply now;
- 100% of material unknowns route to Needs review;
- 100% of hard blocks show exact source evidence or structured provider data;
- safety-block leakage into Apply now is zero on the gold corpus;
- correction of an extracted fact deterministically recomputes the decision.

### Stop condition

If Apply-now applicability precision is below 95%, improve rules/evidence before adding sources or AI ranking.

## 9. Phase 3 — direct and free coverage backbone

### Goal

Capture a meaningful portion of the priority market through durable direct sources before paying for broad duplicate-heavy data.

### Work

1. Route existing Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee, Personio, Teamtailor, Breezy, Pinpoint, BambooHR, Rippling, RSS, and JSON sources through the new truth/applicability pipeline.
2. Update Himalayas to its current filtered search contract.
3. Build a versioned registry of at least 300 priority companies:
   - 100 Indian startups/product companies;
   - 50 global remote-first startups;
   - 75 giants/GCCs/MNC engineering employers in India;
   - 50 AI/data/devtools/security/cloud specialists;
   - 25 additional companies discovered from pilot-relevant communities and referrals.
4. Add source health:
   - last attempt/success;
   - zero openings versus parser failure;
   - fetched/accepted/rejected/duplicate counts;
   - parser version;
   - rate-limit/backoff state.
5. Schedule respectful incremental scans using cache headers and payload hashes where possible.
6. Add missing enterprise ATS adapters in order of benchmark-company impact, not platform popularity.
7. Produce daily source-coverage and known-opening reports.

### Candidate outcome

Candidates receive current startup and large-company opportunities without manually checking hundreds of career pages.

### Exit criteria

- >=80% known-opening capture across the 100-employer benchmark;
- >=90% coverage of technically reachable boards in the 300-company registry;
- median direct-source discovery latency <=6 hours for frequently checked sources;
- no source failure aborts the full scan;
- every zero-result board is distinguishable from a failed board;
- direct employer/ATS application URL rate >=80% in Apply now;
- at least 10 qualified Apply-now opportunities per active pilot candidate per week, or a documented market-supply constraint.

### Stop condition

Do not interpret low yield as a ranking failure until source health and company-board coverage are proven.

## 10. Phase 4 — paid market expansion and source economics

### Goal

Purchase only the coverage that free/direct sources cannot provide efficiently.

### Work

1. Integrate provider-neutral connectors for:
   - SerpApi Google Jobs;
   - Adzuna India;
   - Jooble India;
   - one broad licensed vendor at a time, initially benchmarking TheirStack and Coresignal where contractually suitable.
2. Run every provider for the same seven-day query window and query matrix.
3. Deduplicate against the direct-source corpus before evaluating value.
4. Measure:
   - net-new eligible active opportunities;
   - India onsite/hybrid yield;
   - India-eligible remote yield;
   - early-career yield;
   - canonical-link rate;
   - stale/dead rate;
   - discovery latency;
   - cost per net-new eligible opportunity;
   - completed applications/interviews later attributed to the provider.
5. Establish daily/monthly credit caps and alerts at 50%, 80%, and 100%.
6. Store secrets only locally or in a server secret manager; never ship them in the desktop binary.
7. Confirm contractual display, caching, attribution, and retention rights before enabling a provider in production.

### Implementation checkpoint — 2026-08-24

The governed experiment layer is implemented but remains **disabled by default** and has made no paid calls:

- native adapters normalize [SerpApi Google Jobs](https://serpapi.com/google-jobs-api), [Adzuna Jobs Search](https://developer.adzuna.com/docs/search), and [Jooble REST](https://help.jooble.org/en/support/solutions/articles/60001448238-rest-api-documentation) into the same immutable-source/canonical-opportunity pipeline as direct sources;
- SerpApi covers India-originated internship/new-grad searches plus a worldwide-remote internship query; Adzuna and Jooble use their India/regional contracts;
- credentials are masked on settings reads and never enter source targets, health payloads, provider-status responses, or provider error messages;
- every network call requires an atomic local reservation against per-provider daily/monthly request caps and optional estimated-spend caps;
- provider telemetry exposes 50%/80%/100% alert states, response rows, successful/failed calls, canonical yield, and net-new eligible yield;
- persistent identity aliases keep the original canonical opportunity ID when a paid provider later observes an existing requisition;
- the UI exposes zero-spend/readiness/cap/yield state without exposing credentials;
- a provider remains experimental until at least 10 successful calls, then receives `retain` only at >=10% net-new eligible yield; otherwise it becomes `pause_and_review`.

Still required before enabling spend:

- owner-approved daily/monthly request and currency budgets based on the actual subscribed plan;
- provider-specific terms review for display, attribution, caching, and retention;
- API credentials entered locally;
- a seven-day same-window benchmark against the direct/free union;
- human liveness and eligibility review of the provider's unique results.

### Candidate outcome

The feed gains opportunities from otherwise inaccessible Indian platforms and broader market indexes without becoming noisier.

### Exit criteria

A paid source is retained only when at least one is true:

- adds >=10% net-new eligible active opportunities over the current union;
- materially fills an under-covered cohort such as Indian startups or remote internships;
- meaningfully reduces discovery latency for high-value opportunities;
- produces completed applications/replies/interviews at an acceptable cost.

Additional requirements:

- stale/dead rate <5%;
- eligibility precision remains >=95%;
- provider cost is visible per net-new eligible record;
- initial experimental spend remains within a separately approved budget cap;
- cancellation/degradation behavior is tested.

### Stop condition

Cancel providers that mostly duplicate direct sources or whose unique records fail quality/application-link thresholds. Sunk cost is not a reason to retain them.

## 11. Phase 5 — opportunity value and hiring confidence

### Goal

Help candidates decide what to apply to first without turning uncertainty into a fake universal score.

### Work

1. Keep separate visible dimensions:
   - eligibility;
   - candidate/project fit;
   - career-growth value;
   - compensation value/clarity;
   - hiring confidence;
   - deadline/freshness urgency;
   - application effort.
2. Build compensation normalization with source/provenance, currency, period, and cohort comparison.
3. Estimate hiring confidence only from observable evidence:
   - direct active requisition;
   - specific team/responsibilities;
   - application deadline/start timeline;
   - recent employer activity;
   - identifiable recruiter/contact;
   - evergreen/reposting behavior;
   - prior candidate outcomes.
4. Add Apply now, Strong stretch, Needs review, and Skip queues.
5. Make every top recommendation explain:
   - why the candidate is eligible;
   - matching evidence;
   - missing preferred skills;
   - why the role may accelerate growth;
   - pay evidence/unknowns;
   - hiring-confidence evidence/unknowns;
   - why it should be acted on now.

### Candidate outcome

The candidate receives a focused daily decision queue rather than hundreds of equivalently ranked cards.

### Exit criteria

- >=90% of the manually audited daily top ten are judged worth applying to by the candidate/reviewer;
- 100% of compensation labels retain original amount and provenance;
- undisclosed pay is never labeled high-paying;
- hiring confidence never claims guaranteed recruitment or unsupported ghost-job status;
- no single composite score hides a hard gate or material unknown;
- candidates can explain why the top result outranks the tenth result.

### Stop condition

If candidates repeatedly skip the top recommendations for reasons already present in the posting/profile, fix decision logic before improving model sophistication.

## 12. Phase 6 — interview-conversion workflow

### Goal

Turn Apply-now opportunities into completed applications while the opening is still valuable.

### Work

1. Create a daily queue capped to a manageable number of high-value actions.
2. For each Apply-now opportunity generate:
   - project/requirement evidence map;
   - grounded resume variant;
   - concise cover letter only when useful;
   - recruiter/founder outreach;
   - answers for common application questions;
   - missing facts the candidate must supply;
   - interview-preparation topics;
   - deadline and recommended action time.
3. Prevent unsupported claims, experience inflation, fake metrics, and invented availability/authorization.
4. Track application progress and friction:
   - opened;
   - package generated;
   - application started;
   - abandoned and reason;
   - submitted;
   - outreach sent;
   - reply/interview/rejection/offer.
5. Prioritize applications by deadline, likely interview value, fit evidence, and preparation time.
6. Surface follow-ups without spamming recruiters.

### Candidate outcome

Candidates spend less time rewriting documents and more time submitting strong applications early.

### Exit criteria

- median verified-opportunity-to-review-ready package <=5 minutes after candidate selection;
- median candidate review/edit time <=15 minutes for complete profiles;
- >=80% of accepted Apply-now recommendations become completed applications or have a recorded skip reason;
- >=80% of urgent/high-value applications are submitted within 24 hours of discovery;
- 100% of generated factual claims trace to the candidate profile;
- model unavailability still leaves a usable deterministic evidence checklist and application path;
- abandonment reasons are measurable and feed product corrections.

### Stop condition

If recommendation acceptance is high but completion is low, treat application friction—not discovery—as the primary problem.

## 13. Phase 7 — four-week real-candidate pilot

### Goal

Prove that the complete system produces recruiter responses and interviews for real friends.

### Pilot protocol

1. Five candidates participate for four consecutive weeks.
2. Target 20 completed, high-quality applications per candidate across the pilot, adjusted only when the verified market supply is lower.
3. Aim for at least 100 completed applications across the cohort.
4. Review every Apply-now false positive and every candidate skip reason weekly.
5. Record replies, screening calls, technical assessments, interviews, offers, and rejections.
6. Review source-to-outcome and recommendation-to-outcome conversion weekly.
7. Do not alter historical decisions after seeing outcomes; version rule/model changes.
8. Interview candidates weekly about trust, workload, irrelevant recommendations, and application friction.

### Validation targets

Minimum product-quality targets:

- >=95% audited live/applicable precision;
- <5% dead/closed Apply-now records;
- >=80% accepted-recommendation application completion;
- median application submission within 24 hours for urgent roles;
- no known unsafe or hard-ineligible applications caused by the system.

Outcome targets—not guarantees, but the bar used to judge the pilot:

- >=10 recruiter replies or meaningful next-step contacts across 100 applications;
- >=5 interviews/technical screening processes across the cohort;
- at least three of five candidates receive a recruiter reply or interview process;
- stretch outcome: at least one offer;
- enough labeled outcomes to compare source and recommendation quality.

### Failure-response rules

- **Low discovery supply:** expand missing companies/sources only after confirming source health.
- **High results, low application rate:** fix relevance explanations or application friction.
- **Applications, no replies after first 50:** audit candidate fit, role eligibility, timing, resume evidence, and source quality before adding volume.
- **Replies, no interviews:** improve screening/application answers and preparation.
- **Interviews, no offers:** improve interview preparation and role calibration; discovery may already be working.
- **High ineligible/dead rate:** halt source expansion and repair truth/eligibility gates.
- **Zero interviews after 100 audited applications:** the product is not validated; perform a structured failure review rather than declaring success from activity metrics.

### Exit decision

- **Proceed:** quality gates hold and the system produces credible interview processes.
- **Iterate:** quality holds but outcomes identify a correctable application, positioning, or source gap.
- **Stop expansion:** truth/applicability does not hold or candidates cannot trust Apply now.

## 14. Phase 8 — shared Opportunity Index and public beta

### Goal

Keep public-market discovery running continuously while preserving local candidate privacy.

### Work

1. Move scheduled public collectors to a shared ingestion plane.
2. Store public source records, canonical opportunities, source health, and lifecycle only.
3. Publish signed/versioned delta feeds or a read-only API.
4. Keep resumes, candidate graphs, personalized ranking, generated documents, applications, and outcomes local unless explicitly opted in.
5. Add replay, backup, provider-budget, circuit-breaker, and outage-degradation behavior.
6. Expand the company registry based on measured cohort gaps and pilot outcomes.
7. Run a 25-candidate beta before opening broadly.

### Candidate outcome

Candidates receive fresh opportunities without leaving their laptops running or duplicating paid source requests.

### Exit criteria

- candidate PII never enters central public-opportunity storage;
- desktop retains a functional local/degraded mode;
- scheduled-source availability >=99% excluding third-party provider outages;
- delta synchronization is idempotent and provenance-preserving;
- no provider secret ships to clients;
- public-beta quality does not fall below pilot liveness/applicability thresholds;
- infrastructure spend per active candidate remains visible and bounded.

## 15. Required instrumentation

Record immutable, versioned events:

```text
source_record_observed
source_fetch_failed
opportunity_canonicalized
duplicate_linked
opportunity_verified_active
opportunity_marked_closed
eligibility_decided
decision_corrected
opportunity_surfaced
candidate_opened
candidate_accepted_recommendation
candidate_skipped
package_generated
application_started
application_abandoned
application_submitted
outreach_sent
recruiter_replied
assessment_received
interviewing
offer_received
accepted
rejected
withdrawn
```

Each decision event records rule/model version, evidence references, and unknowns. Candidate content stays local.

## 16. Operating cadence

### Daily automated review

- source failures and rate limits;
- zero-result anomalies;
- dead-link rechecks;
- new high-priority opportunities;
- API spend and remaining credits;
- urgent deadlines;
- ingestion/deduplication anomalies.

### Weekly product review during development/pilot

- Apply-now false positives;
- candidate skip reasons;
- application completion and abandonment;
- replies/interviews/offers;
- source unique yield and cost;
- missing company/source cohorts;
- top-ranking errors;
- model/rule corrections;
- privacy/safety incidents.

### Phase review

Each phase produces:

- before/after metrics;
- failed cases;
- accepted technical debt;
- go/no-go decision;
- next phase's fixed scope;
- updated cost and risk forecast.

## 17. Source investment policy

Allocate engineering time and API spend based on verified downstream value:

```text
source value =
  unique eligible active opportunities
  × application completion
  × reply/interview conversion
  ÷ total source cost
```

Early in the pilot, opportunity count and application completion are leading proxies because interview samples are small. As outcomes accumulate, reply/interview conversion becomes the controlling signal.

Never allow one sparse outcome to overfit the whole ranker. Preserve deterministic hard gates and use minimum sample thresholds before changing source weights.

## 18. Project risks and explicit responses

| Risk | Response |
| --- | --- |
| More sources create more noise | Truth/applicability phases precede expansion |
| Listings appear live but are not processing candidates | Separate active state from hiring confidence and track outcomes |
| Remote roles exclude India | Hard geography gate; unknown routes to review |
| Paid APIs mostly duplicate free ATS data | Evaluate net-new eligible yield after canonical deduplication |
| Models invent eligibility or pay | Structured evidence, deterministic rules, unknown allowed |
| Candidates receive too many recommendations | Small prioritized daily queue |
| Great matches are submitted too late | Latency, deadlines, and 24-hour application SLA |
| Resume tailoring fabricates experience | Profile-grounded claims and human review |
| Pilot outcome sample is small | Transparent rules, manual audit, minimum samples before learning |
| Shared index threatens privacy | Public jobs central; candidate data local |
| Platform terms block direct collection | Official/approved/licensed paths or canonical public sources only |

## 19. Definition of MVP success

The MVP is successful only when all are true:

1. Five real candidates use it for four weeks.
2. Apply-now precision is at least 95% for liveness and applicability.
3. At least 100 high-quality applications are completed, unless audited market supply makes that impossible.
4. The cohort receives at least ten meaningful recruiter responses and enters at least five interview/screening processes.
5. No application is driven by a known hard-ineligible or unsafe recommendation.
6. The team can explain which sources, decisions, and application behaviors produced outcomes.
7. The system identifies its own unknowns and failures without presenting them as certainty.

Until these conditions hold, JustHireMe has promising infrastructure—not a validated interview-producing product.

## 20. Immediate next planning deliverables

Before implementation begins, produce and approve:

1. pilot candidate intake template;
2. 300-posting gold-corpus schema and review rubric;
3. 100-employer benchmark registry format;
4. canonical opportunity/source record contract;
5. event and metrics dictionary;
6. Phase 0 baseline report template;
7. API experiment budget cap;
8. explicit go/no-go owner for every phase.

Once these are approved, implementation starts with Phase 0 measurement and Phase 1 opportunity truth—not with adding more scraper volume.
