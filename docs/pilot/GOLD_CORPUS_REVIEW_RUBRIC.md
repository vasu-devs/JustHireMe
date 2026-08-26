# Gold Corpus Review Rubric

The Phase 0 corpus is the independent truth set used to evaluate future opportunity logic. Production classifiers must not author their own labels.

## Target distribution

| Category | Target |
| --- | ---: |
| India technical internships | 60 |
| India early-career full-time roles | 50 |
| India-eligible/worldwide remote | 40 |
| Remote roles excluding India | 35 |
| Seniority traps | 30 |
| Non-technical roles | 25 |
| Closed/expired/ambiguous | 25 |
| Unsafe/unpaid/fee/bond cases | 20 |
| Cross-source duplicate observations | 15 |
| Total | 300 |

At least 200 cases must be real public snapshots. Synthetic fixtures cover adversarial invariants but cannot establish market performance.

## Evidence capture

For public cases record:

- canonical/source URL;
- provider and provider record ID;
- capture time and reviewer;
- title, company, location, and a short necessary evidence excerpt;
- raw payload hash or permitted internal snapshot reference;
- published/updated/deadline/active facts without changing their semantics;
- expected candidate decision and decisive evidence.

Avoid copying unnecessary copyrighted posting text into the repository. Store only the excerpt needed to support the label plus a hash/reference to an internally retained permitted snapshot.

## Review questions

Each reviewer answers in order:

1. Is the source observation a job opportunity rather than navigation, talent community, article, or generic hiring page?
2. Is the canonical application route identifiable?
3. Was it active at capture time? What proves that?
4. Is it an internship, new-grad role, entry-level full-time role, supported stretch, or other?
5. Is the work CSE/technical under the configured taxonomy?
6. Is the workplace India onsite/hybrid or India-eligible/worldwide remote?
7. Does the posting state country, authorization, citizenship, graduation, enrollment, schedule, start-date, or experience blockers?
8. Is it paid, unpaid, suspicious, or unknown?
9. Are there fees, deposits, bonds, exit penalties, unpaid trials, or identity/contact mismatches?
10. For the pilot candidate facts, should it be Apply now, Strong stretch, Needs review, or Skip?

## Decision rules

- `Apply now`: active, hard-eligible, technical, safe, actionable.
- `Strong stretch`: active and hard-eligible; preferred skills are missing but adjacent evidence makes application rational.
- `Needs review`: a material fact is unresolved.
- `Skip`: closed, hard-ineligible, unsafe, non-technical, unsupported stage, or duplicate application.

Fit cannot override a hard block. Unknown remote reach does not become worldwide. A live page without an active application is not active.

## Double review

Every case must have two distinct reviewers before Phase 0 exits.

Disagreements are resolved as follows:

1. Compare exact evidence, not intuition.
2. Prefer structured employer/ATS facts over aggregator labels.
3. If the posting remains ambiguous, label Needs review/unknown.
4. Record both original labels, final label, resolver, date, and reasoning.
5. Version changes; never silently rewrite a historical expected label.

## Invariants

At least ten cases are product invariants. These fail CI regardless of aggregate accuracy. Initial invariants include:

- remote US-only is not India eligible;
- remote EU-only is not India eligible;
- remote without geography is Needs review;
- a senior role mentioning interns is not an internship;
- non-technical work at a tech company is not technical;
- closed overrides perfect fit;
- application/training fees block Apply now;
- unpaid bonded work blocks Apply now;
- direct worldwide remote can be India eligible;
- India onsite early-career technical work can be Apply now.

## Current status

Run:

```bash
cd backend
python -m evals.opportunity_harness
```

The report must say `NOT READY` until distribution, public-snapshot, double-review, and invariant targets are actually satisfied.
