# JustHireMe Opportunity System Fundamentals

**Status:** Product and engineering constitution
**North star:** Help candidates reach credible interviews and offers
**Applies to:** Discovery, source adapters, opportunity intelligence, ranking, generation, pipeline, and reporting

## 1. Mission

JustHireMe does not exist to collect job links. It exists to help a candidate find a currently open opportunity they can actually pursue, submit a strong and truthful application quickly, and progress to an interview.

The system succeeds through candidate outcomes, not scrape volume.

## 2. The Apply Now invariant

An opportunity may enter `Apply now` only when:

```text
LIVE ∧ APPLICABLE ∧ TECH_RELEVANT ∧ SAFE ∧ ACTIONABLE
```

- **Live:** The canonical employer/application endpoint is currently open or recently verified active.
- **Applicable:** No known location, authorization, graduation, experience, schedule, or other hard requirement excludes the candidate.
- **Tech-relevant:** The work belongs to the configured technical taxonomy and candidate stage.
- **Safe:** No evidenced fee, unpaid-work, coercive-bond, impersonation, or similar blocker violates the candidate's policy.
- **Actionable:** The system has a real application path, sufficient role context, and a decision the candidate can act on now.

Unknown material facts do not silently pass. They route the opportunity to `Needs review`.

## 3. Fundamental truths

### 3.1 A source record is not an opportunity

One role can appear on an ATS, employer page, Google Jobs, LinkedIn, Adzuna, Jooble, and multiple aggregators. Preserve every observation but show one canonical opportunity.

### 3.2 A reachable URL is not proof of an open requisition

Verify employer/ATS active state, application availability, deadline, and last successful observation. Keep published, updated, first-seen, last-seen-active, and closed dates distinct.

### 3.3 Remote is not a geography

Remote eligibility must state worldwide, India, a region containing India, a country list, or unknown. `Remote — US only` is not applicable to an India-based candidate.

### 3.4 Skill fit cannot buy back hard ineligibility

A perfect project match cannot override citizenship, work authorization, onsite location, graduation window, start date, schedule, or an explicit experience minimum.

### 3.5 Unknown is a valid and necessary answer

Missing compensation, remote scope, authorization, or deadline remains unknown. Models may extract evidence; they may not manufacture certainty.

### 3.6 Direct evidence outranks inferred evidence

Employer/ATS structured fields and exact posting text outrank aggregator labels, search snippets, and model inference. Preserve provenance for every material fact.

### 3.7 Fast action matters

Discovery latency, deadline awareness, application readiness, and candidate notification are part of quality. A strong role discovered after closure has no value.

### 3.8 Coverage must be measured

No source is trusted because it returns many rows. Measure unique eligible active opportunities, company-board coverage, known-opening capture, latency, stale rate, and cost after canonical deduplication.

### 3.9 Hiring confidence is separate from fit

A candidate can fit a role that the employer is not seriously processing. Estimate hiring confidence only from observable signals such as a direct active requisition, specific team and responsibilities, recent employer activity, clear timeline, canonical application path, and verified outcome history. Never promise that an employer will hire or call an unsupported posting a ghost job.

### 3.10 The application is part of the product

For an Apply-now opportunity, JustHireMe should immediately provide grounded project evidence, a truthful tailored resume, concise outreach, missing-answer prompts, interview topics, deadline/urgency, and tracking. Discovery without action support is incomplete.

### 3.11 Outcomes close the loop

Track:

```text
discovered -> verified -> shortlisted -> applied -> replied
  -> interviewing -> offer -> accepted/rejected/withdrawn/closed
```

Interview and offer outcomes should improve source selection, classification, ranking, application quality, and follow-up behavior. Feedback must not override hard safety or eligibility rules.

### 3.12 Candidate data remains private by default

Public opportunities may be centrally indexed. Resumes, profile graphs, personalized scores, generated documents, feedback, applications, and outcomes remain local unless the candidate explicitly opts into sharing a narrowly defined signal.

## 4. Decision order

The system must evaluate in this order:

1. Canonicalize and deduplicate the opportunity.
2. Establish active/live status.
3. Classify opportunity type, technical track, seniority, and workplace.
4. Evaluate candidate hard eligibility.
5. Apply safety and user-minimum policies.
6. Evaluate candidate/project fit.
7. Evaluate hiring confidence.
8. Evaluate career growth, compensation, and urgency.
9. Assign Apply now, Strong stretch, Needs review, or Skip.
10. Prepare and track the application.

Ranking must never run first and hide a failed hard gate behind a high score.

## 5. User-visible decisions

- **Apply now:** verified live, applicable, safe, actionable, and high priority.
- **Strong stretch:** verified live and applicable; some preferred skills are missing, but adjacent evidence and growth value justify applying.
- **Needs review:** promising, but a material fact such as geography, authorization, compensation, deadline, or candidate-stage requirement is unresolved.
- **Skip:** closed, incompatible, unsafe, irrelevant, duplicate, or below an explicit candidate minimum.

Every decision must show the decisive evidence and unknowns.

## 6. North-star metrics

Primary:

- interviews per 20 completed applications;
- offers per interview and per completed application;
- qualified Apply-now opportunities per candidate per week;
- median discovery-to-application time;
- candidate response/reply rate;
- verified live/applicable precision.

Supporting:

- publication-to-discovery latency;
- dead/closed rate in Apply now;
- ineligible leakage rate;
- unique eligible yield per source and per rupee;
- canonical direct-application rate;
- application completion rate;
- source-to-interview and source-to-offer conversion;
- extraction corrections and Needs-review resolution rate.

Raw scraped rows, database size, and model-generated score averages are not success metrics.

## 7. Current-system gap inventory

The existing system provides useful foundations but does not yet satisfy the invariant.

### Data model

- A single `Lead` currently conflates a source observation, canonical opportunity, candidate decision, and application record.
- Identity is primarily URL-derived, so the same requisition from different providers is not reliably consolidated.
- Critical opportunity facts are mostly free text or generic `source_meta`, not normalized, queryable evidence.
- Publication, deadline, last-verified-active, and closure are not first-class lead lifecycle fields.

### Source ingestion

- Source coverage depends heavily on local scans and configured targets rather than a continuously measured company/source universe.
- Several adapters truncate descriptions before downstream eligibility and safety extraction, which can remove decisive requirements.
- Provider date semantics are not normalized consistently; `updated_at`, publication, first observation, and active status can be conflated.
- Source failure, zero relevant openings, and lost market coverage are not yet one coherent operational model.

### Liveness

- The generic quality gate primarily uses a seven-day date heuristic and score penalty.
- There is no canonical opportunity lifecycle that independently re-verifies active application state and records closure.
- A posting can be recent but closed, or old but still actively hiring; age alone cannot determine availability.

### Applicability

- Seniority is coarse and location is largely an unstructured string.
- Remote scope, candidate-country eligibility, work authorization, graduation window, availability, timezone, and education requirements are not complete hard-gate domains.
- Fit scoring can explain skill alignment, but hard candidate applicability needs to precede it.

### Opportunity and hiring quality

- Existing signal/fit scores do not independently represent liveness, applicability, hiring confidence, career growth, compensation value, and actionability.
- The system does not yet identify evergreen/reposted ambiguity or clearly separate “active page” from “evidence that a team is processing candidates.”
- Compensation lacks a normalized, provenance-aware comparison model.

### Outcome loop

- The backend already contains interviewing, offer, acceptance/rejection, reporting, and feedback-learning foundations.
- These outcomes are not yet the governing objective for source budgets, market coverage, opportunity decisions, and the primary user experience.
- Sparse early pilot outcomes require transparent rules and careful calibration rather than premature prediction claims.

### User action

- Resume/outreach generation and pipeline tracking exist, but they are not yet orchestrated around a verified Apply-now decision, application deadline, required answers, and time-to-submit target.
- The system needs a clearer daily queue that tells the candidate what to apply to first and why.

## 8. Engineering acceptance question

Before shipping any discovery, ranking, AI, or UI change, ask:

> Does this make it more likely that the right candidate finds a currently open, applicable opportunity and reaches an interview—without weakening evidence, privacy, or safety?

If the answer cannot be measured or explained, the change is not foundational.
