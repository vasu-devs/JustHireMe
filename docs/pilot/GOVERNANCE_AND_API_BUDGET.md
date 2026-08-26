# Phase Governance and API Experiment Budget

## Decision ownership

Until a larger team exists, the project maintainer is the accountable owner for scope, engineering, budget, privacy, and phase decisions. Review evidence must still come from people other than the decision owner where the roadmap requires double review.

| Decision | Accountable owner | Required reviewers/evidence |
| --- | --- | --- |
| Corpus label | Corpus reviewer | Second independent reviewer |
| Corpus dispute | Project maintainer | Both labels, evidence, written resolution |
| Phase exit | Project maintainer | Phase metrics and failure report |
| Paid trial start | Project maintainer | Contract/terms check and approved cap |
| Paid source retention | Project maintainer | Unique-yield, quality, cost, and later outcome report |
| Privacy boundary change | Project maintainer | Explicit candidate consent and documented data flow |
| Safety policy change | Project maintainer | Adversarial fixtures and pilot review |

The same person may implement and decide during the solo-builder stage, but may not single-review corpus evidence used to claim phase completion.

## Initial spend policy

No paid provider is needed for Phases 0–3 except a separately approved, narrowly scoped diagnostic request.

Recommended Phase 4 experiment envelope:

- total initial experiment cap: **INR 10,000**;
- maximum per provider before evidence review: **INR 4,000**;
- no annual contracts;
- no automatic plan upgrades;
- no usage-based overage without an explicit stop/cap;
- secrets never committed or shipped in desktop binaries;
- purchases require a terms/display-rights check and recorded owner approval.

The cap is a governance recommendation, not authorization to purchase. Actual spend requires a separate explicit approval at the time of purchase.

## Live-pilot activation checklist

The system remains in zero-spend, no-go mode until every item below is recorded:

- five completed candidate intake files based on `CANDIDATE_INTAKE_TEMPLATE.json`;
- each candidate's confirmed consent timestamp and reviewed eligibility preferences;
- each candidate's own complete application profile linked after consent; saved IDs without both requirements remain pending and do not count toward the five-person cohort;
- the displayed profile name and evidence counts reviewed in the product before confirmation; linking posts the exact reviewed SHA-256 fingerprint and must fail if the current Profile changes before confirmation;
- for multi-candidate onboarding, upload each candidate's PDF, DOCX, TXT, or Markdown resume directly in that candidate's opportunity workspace; this path uses deterministic local parsing only, never a configured cloud LLM, and still requires name/evidence review plus fingerprint confirmation;
- an approved provider (`serpapi`, `adzuna`, or `jooble`) and a locally entered API credential;
- provider daily and monthly request caps, estimated cost per request, and daily/monthly USD spend caps;
- a named owner who has reviewed the provider's current contract, terms, display rights, and retention rules;
- a seven-day experiment window and an owner for manually reviewing returned opportunities.

API credentials must be entered through local settings or environment configuration. They must not be placed in candidate intake files, this document, source control, chat messages, screenshots, or pilot exports. Enabling a provider without all controls above is not an approved pilot.

The shared/cloud rollout remains a separate decision. It additionally requires an approved hosting region, infrastructure budget, privacy/data-retention owner, and deployment authority.

## Provider experiment protocol

1. Use free trials, preview, or count endpoints first.
2. Run the same seven-day query matrix.
3. Canonicalize/deduplicate against free/direct sources.
4. Measure net-new eligible active opportunities.
5. Audit at least 30 unique returned records when available.
6. Record stale/dead rate, canonical link rate, India eligibility, and early-career precision.
7. Compute cost per net-new eligible opportunity.
8. Retain only if the roadmap's Phase 4 exit condition holds.

## Phase go/no-go record

Every phase decision records:

- decision date;
- owner;
- evidence window;
- exit metrics and sample sizes;
- unmet criteria;
- accepted risks/debt;
- spend to date;
- proceed, iterate, or stop-expansion decision;
- exact next-phase scope.

No phase advances because work was performed or a deadline arrived. It advances only when the candidate-facing outcome gate is met.
