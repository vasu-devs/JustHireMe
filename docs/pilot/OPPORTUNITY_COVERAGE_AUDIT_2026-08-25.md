# Opportunity coverage audit — 2026-08-25

This is execution evidence for the CSE/AI internship and early-career path. It
is not a claim that every job on the internet can be indexed: closed networks,
robots/terms restrictions, geography uncertainty, and unconfigured paid APIs
remain explicit boundaries.

## Production inventory

- 303 production free/direct scan targets across 37 provider families after removing
  13 provider/tenant pairs proven dead in the full live scan. Within that total,
  48 shallow Workday keyword targets were replaced by 19 deeper,
  country-faceted India/CSE plans; later verified ATS and public-market waves
  increased the overall inventory without restoring the shallow queries.
- Direct ATS coverage includes Greenhouse, Ashby, Lever, Workday, Workable,
  SmartRecruiters, Personio, Teamtailor, Rippling, Pinpoint, Breezy, and
  BambooHR. Zoho Recruit adds public Indian startup/company boards and one
  explicitly marketplace-labelled hiring surface without using its protected
  OAuth API. Freshteam adds 14 same-day-verified Indian employer boards through
  public current-board pages and first-party `JobPosting` JSON-LD; no applicant
  form or protected tenant API is used. Keka adds nine verified India-heavy
  boards across both of its current public portal generations, using only the
  public current-job collection and organization endpoints; application forms
  and candidate endpoints remain outside the adapter.
- Public market coverage includes Arbeitnow, The Muse, Himalayas, Remote OK,
  Remotive, Jobicy, Working Nomads, We Work Remotely, and the monthly Hacker
  News hiring thread. Y Combinator's public India and remote software-job
  marketplaces add an official startup lane. AICTE's National Internship Portal
  adds an official India-wide marketplace lane restricted at ingestion to paid,
  technical internships with a currently visible public application control.
- First-party custom coverage now includes Amazon India, Google India,
  Microsoft India, Qualcomm India, Deliveroo India, and IBM India
  internships/entry-level roles. Zeqo adds a server-rendered, first-party paid
  India-remote early-career feed. Starling's official careers page resolves to
  its public Workable board and is covered there.
- SerpApi, Adzuna, and Jooble are implemented as opt-in paid providers with
  reservation, hard-cap, and yield accounting. They remain disabled without
  credentials and an explicit budget.

## Live evidence

The initial complete scan attempted 222 targets and returned:

- 194 successful targets, 15 healthy zero-result targets, and 13 confirmed
  failures;
- 19,751 raw rows, 19,533 valid source observations, and 18,948 canonical
  opportunities;
- 585 duplicate observations collapsed;
- 198 explicit internships, 46 new-grad roles, and 95 entry-level full-time
  roles before candidate-specific applicability filtering.

The repaired-source delta then added or refreshed 5,884 raw rows from 13
sources, including current official ATS endpoints for Attentive, DoorDash
India, DoorDash USA, Sourcegraph, Benchling, Perplexity, and Hugging Face. All
13 succeeded. It added 791 net-new canonical opportunities.

The HN monthly-thread freshness repair recovered 224 additional live rows and
one initially reviewable row; a subsequent seniority audit correctly demoted
that `Sr.` false positive.

The custom-official delta added 46 complete source records from Deliveroo India
and Starling (42 Workable requisitions plus 4 Deliveroo requisitions). All were
correctly rejected for this final-year CSE profile because the current openings
are senior, non-early-career, or outside India; zero-yield is reported rather
than relabelled as applicable.

IBM's official v2 careers interface currently exposes 1 India internship and 4
India entry-level records. They collapse to 4 unique requisitions. All are
withheld from the apply queue: the internship explicitly requires prior
application through the Prime Minister's Internship Scheme, and the other roles
fail experience, accepted-city, or technical-track constraints. Core IBM fields
are 100% complete, including requisition ID, employer domain, location,
workplace, full description, publication/update times, apply URL, hashes, and
attribution. IBM does not expose a trustworthy application deadline, so none is
invented.

The rule-10 India expansion added Ema, PhonePe, NVIDIA, Adobe, and PayPal as
official direct-company targets. The first five-target delta produced 122 valid
records with zero conversion errors: Ema 41, PhonePe 68, and NVIDIA 13. Ema's
current AI/Data Resident is a paid six-month India-remote internship for
final-year CS students with a stated INR 65,000 monthly stipend and conversion
path, and is the one new immediate-apply result. PhonePe is a healthy India
watch board whose current technical openings are stretch/senior rather than
internships. NVIDIA produced three net-new eligible stretch candidates.

Workday now discovers each tenant's live India location facet, including three
incompatible schemas observed in production (`locationHierarchy1`,
`locationCountry`, and city-level `locations`). It applies the facet server-side,
exhausts employer-authored Intern/New-College-Graduate/University facets before
seven bounded CSE searches, rejects senior/nontechnical titles before detail
retrieval, de-duplicates requisitions, and fetches at most 30 ordinary stretch
descriptions or 60 employer-marked early-career descriptions per tenant. Live
India+early-career facets currently contain zero NVIDIA/Adobe rows, so the new
lane adds future coverage without fabricating present yield. Adobe's repaired
country facet produced 28 complete
India CSE records and one strong stretch. PayPal correctly remains a healthy
zero-CSE result: its two current Bangalore openings are Tax Analyst roles.

Amazon India and Microsoft India now have direct official adapters rather than
depending on syndicators. Amazon's public careers JSON is exhausted across a
bounded CSE/AI/early-career query matrix with the official India country filter;
Microsoft's current Eightfold search is paged by India location and each retained
role is enriched from the first-party JobPosting JSON-LD. The two-target live run
returned 353 complete observations with zero conversion errors: Amazon 329 and
Microsoft 24. They formed 301 canonicals after collapsing 52 duplicate query
observations, and all 301 were net-new to the isolated index (Amazon 277,
Microsoft 24). Requisition ID, employer domain, location, workplace, full
description, canonical/apply URL, hashes, and attribution were 100% populated.
The initial rule-10 delta labelled 4 apply and 200 bounded stretch roles; the
subsequent degree-level audit supersedes those candidate labels.

Google India and Qualcomm India now have first-party adapters. Google's
server-rendered public careers index is paged to exhaustion with its official
India and Early/Intern-and-Apprentice filters. Qualcomm's public Eightfold
index is exhausted across Intern, Campus Hire, Graduate, and Associate Engineer
queries, then enriched from each official JobPosting document. The live delta
returned 24 net-new canonicals (Google 11, Qualcomm 13), with both targets
successful and zero conversion errors. Requisition ID, employer/company
identity, canonical/apply URL, location, workplace, full description,
publication time, hashes, and attribution were 100% complete; Qualcomm supplied
deadlines for all 13 of its records. Google added one immediate university-
graduate role and seven bounded stretches. A post-run audit found Qualcomm's
underscore-delimited `Intern_2027_SW` and `Campus Hire_Engineer_SW` titles were
being missed by word boundaries; rule 12 repaired that centrally and recovered
eight live internships/campus hires for the representative B.Tech profile.

Seven current Ashby boards (Cerebras, Cohere, Composio, Deepgram, Modal,
Perplexity, and Snowflake) were re-read after Ashby's schema moved location,
secondary-location, workplace, publication, listing-status, and apply-link
fields. All seven succeeded: 899 raw rows became 896 canonical roles, all
correctly excluded for the representative India profile. The repair reduced
the manual-review queue from 22 to 6 without guessing geography.

Arbeitnow now uses one non-duplicative CSE/AI early-career target and pages up
to ten API pages (as many as 1,750 current rows) instead of downloading only
the first roughly 175 rows three separate times. It retains location,
workplace, timestamp, active status, slug, types, and tags. Its live repair
returned 387 targeted rows.

Himalayas was migrated from a deprecated arbitrary 5,000-row offset slice of
its 100k+ all-field feed to the official filtered search API. Two exhaustive
segments cover India/worldwide-eligible remote internships and India/worldwide-
eligible entry-level full-time jobs. The live search returned 90 internships
and 447 entry-level full-time rows. All 535 accepted records have source ID,
company slug, apply URL, location, workplace, full description, publication
time, deadline, employment type, seniority, salary fields, timezones,
categories, hashes, and attribution populated where the API exposes them.

The first targeted run surfaced 43 apply-now and 14 stretch candidates. A
title-by-title audit caught 11 non-CSE false positives (recruitment,
copywriting, growth, procurement, advertising, operations, data entry, and
generic internships). Rule 5 prevents nontechnical titles from being rescued
by AI/software buzzwords while still allowing genuinely vague engineering,
QA, systems, network, and research titles to use description evidence.
Subsequent language evidence added AND/OR-aware requirements: required
Mandarin and required Russian-or-Ukrainian roles are now excluded for the
English-only synthetic candidate, while optional German remains nonblocking.

Pre-lifecycle-refresh isolated index state after the rule-14 full consistency pass, the
Atlassian, Razorpay, Freshworks, Oracle, Swiggy, Dell, Visa, and Bosch official-
source cycle, and the provider-identity repair:

- 34,734 immutable source records/observations;
- 22,171 canonical opportunities, including 21,193 currently active roles;
- 49 `apply_now`, 319 `strong_stretch`, 37 `needs_review`, and 21,766 `skip` for
  the non-private representative India CSE candidate;
- the action queue contains 36 internships, 5 new-grad roles, 37 entry-level
  full-time roles, and 290 bounded 1-3-year stretch roles; 63 are India-remote,
  283 India-onsite, 7 India-hybrid, and 15 explicitly worldwide-remote;
- no foreign onsite or explicitly non-India remote role remains in the
  `apply_now`/`strong_stretch` queue.

The conservative queue is intentional: geography, work authorization,
seniority, non-technical roles, unpaid work, service bonds, fees/deposits,
graduation year, enrollment, candidate city preferences, compensation, and
internship duration can all block or hold a role for review.

A subsequent lifecycle audit profiled all 971 unresolved canonicals by provider.
Current-list membership is now treated as positive active evidence only for eight
audited current/open-job interfaces; the HN monthly archive and arbitrary RSS
feeds deliberately remain non-authoritative. A live ten-target refresh across
Himalayas, The Muse, Remote OK, We Work Remotely, Jobicy, Working Nomads, and
Remotive accepted 834 of 836 rows. It added 16 canonicals, moved 210 historical
unknowns to active, and reported zero net-new eligible roles for the representative
candidate instead of inflating yield. The two rejected Himalayas rows exposed
overlong country-restriction display text; compact display now retains explicit
India eligibility while preserving every country in source metadata. A backed-up
Himalayas rerun then accepted all 530 rows with zero conversion errors and added
two more canonicals. The corrected index contains 36,098 source
records/observations, 22,189 canonicals, 59,216 aliases, 21,421 active roles, 761
honestly unresolved historical roles, and 7 expired roles.

The Y Combinator startup lane exhausts the public India-software and remote-
software listing pages, then enriches every retained card from first-party
`JobPosting` JSON-LD. Three audited runs accepted 163 immutable observations
with zero conversion errors and added 55 startup canonicals. Structured
applicant-location requirements outrank misleading card geography: a title that
mentions India cannot override structured United States-only eligibility. The
current 54-card live read supplies employment type, salary, employer domain,
and company logo for all 54 records and explicit applicant-location restrictions
for 42. One listing that disappeared between runs remains historical evidence
until the conservative missing-run lifecycle threshold is met.

That live audit also produced rule 15. ISO country codes in structured job
addresses now normalize to country names; country-only India onsite listings
with no accepted city are held for review; mechanical-engineering titles cannot
be rescued by incidental cloud terms; explicit volunteer internships are treated
as unpaid; and numeric phrases such as `30+ years of history` or `20 years ago`
no longer masquerade as required experience. A backed-up complete rule-15 pass
validated all 22,244 canonicals and produced 48 `apply_now`, 317
`strong_stretch`, 44 `needs_review`, and 21,835 `skip` decisions for the
non-private representative profile.

The post-YC public artifact contained 36,261 immutable source records/observations,
22,244 canonicals, 59,434 identity aliases, 21,476 active roles, 761 unresolved
roles, and 7 expired roles. Read-only preflight reports SQLite integrity `ok`,
zero orphan observations or aliases, and SHA-256
`bd3029d6a230ae690cfe40f0cecb4e3baea7aa966fb48a053c442f4ac77fba2d`.

A follow-up direct-board audit admitted only two boards that passed a same-day
live read: Outmarket (Ashby, including Remote India engineering) and Merkle
Science (Lever, Bangalore). A stale Flent search result failed its live ATS read
and was removed rather than counted. The two accepted targets returned 49/49
valid records with zero conversion errors and added 49 net-new canonicals. All
49 are skips for the representative candidate today: Outmarket's previously
indexed AI internship has closed, and Merkle's current final-year backend
internship advertises a two-year service lock-in. Rule 15 now treats explicit
`service lock-in` language as an employment bond; the live Merkle role is blocked
solely by that safety evidence.

The post-targeted-board artifact contained 36,310 source records/observations, 22,293
canonicals, 59,581 aliases, 21,525 active roles, 761 unresolved roles, and 7
expired roles. A second complete rescore produced 48 `apply_now`, 317
`strong_stretch`, 44 `needs_review`, and 21,884 `skip`, exactly the prior totals
plus the 49 new safe exclusions. Its SQLite quick-check is `ok`, both orphan
counts are zero, and SHA-256 is
`71298fd6cb362a58eefa58c326281f8f753162d2fdfc72520a3eee3b389e9527`.

A current India internship community index was then used only as a discovery
signal, not copied as source truth. It exposed direct employer boards for Warner
Bros. Discovery, Red Hat, Lilly, and Glance. All four official ATS endpoints
were live: Glance returned 48 complete Greenhouse records; Warner and Lilly
returned three current Workday records; Red Hat was a healthy zero after its
previously indexed SRE internship closed.

That audit exposed two generic Workday capture gaps. Some tenants use opaque
facet parameters such as `a` with a human descriptor of `Country`, and generic
employer-authored `Campus Program` titles can contain technical internship facts
only in their detail documents. The connector now recognizes both parameter and
descriptor location schemas, and it detail-enriches bounded Intern/Campus/
Graduate titles before downstream CSE classification. Warner's two HR-oriented
internships remain skips. Lilly's first-party Campus Program explicitly lists
AI/ML, automation, data privacy, cybersecurity, Salesforce, statistical
programming, and database operations internships.

Rule 16 evidence-gates generic campus/university programs: both explicit
internship/new-grad evidence and explicit technical-program language are
required. Across all 22,344 opportunities, the rule-15-to-rule-16 decision diff
is exactly one row: Lilly Campus Program moved from `skip` to `apply_now`; no
other decision or eligibility label changed. Final representative decisions are
49 `apply_now`, 317 `strong_stretch`, 44 `needs_review`, and 21,934 `skip`.

The final artifact contains 36,361 source records/observations, 22,344
canonicals, 59,730 aliases, 21,576 active roles, 761 unresolved roles, and 7
expired roles. SQLite integrity and both orphan checks are clean; SHA-256 is
`8ee28620b5d5dba867d9b57df799a880c24a638e236dc1630196936daaa38653`.

The Zoho Recruit expansion then added ten same-day-verified employer boards and
one separately labelled Indian hiring marketplace. The public adapter reads the
current-board payload embedded in the employer page, rejects unpublished rows,
retains every exposed publication/location/workplace/job-type/industry/control
field, and performs bounded detail enrichment only for technical non-senior
titles when a tenant omits descriptions from its collection payload. It never
requests candidate forms, contact data, credentials, or the protected Zoho API.

All 11 live targets succeeded. The ten direct boards contributed 200 rows and
TestHiring contributed 350 recruiter-mediated rows; all 550 converted with zero
errors and produced 550 net-new canonicals. Full descriptions recovered from
the detail payload promoted two genuinely technical roles that title-only data
could not prove. The representative candidate delta is 13 `apply_now`, 7
`strong_stretch`, 17 `needs_review`, and 513 `skip`: 20 net-new eligible paths,
while non-CSE, senior, foreign-onsite, uncertain-geography, and unsafe roles
remain withheld.

Rule 17 prevents conditional phrases such as `potential stipend based on
performance` from being presented as confirmed pay. Across all 22,894
canonicals, the only rule-16-to-rule-17 semantic change is that pay label on the
BWS remote full-stack internship (`paid` to `unknown`); no opportunity decision
or eligibility label changed. The complete consistency pass also refreshed
30 evidence payloads without changing their decisions. Post-first-wave totals were 62 `apply_now`, 324
`strong_stretch`, 61 `needs_review`, and 22,447 `skip`.

The second Zoho discovery wave admitted three more live boards only after direct
probing: Overt Minds, HyperHorizon, and Binary Web Solutions. Their 52/52 rows
converted with zero errors and formed 52 net-new canonicals. The representative
delta contains two `apply_now`, one `strong_stretch`, six `needs_review`, and 43
safe skips. Accepted-city and unknown remote-geography constraints correctly
hold the Ahmedabad, Hosur, and unspecified-remote roles for review rather than
silently treating them as applicable.

The post-Zoho public artifact contained 36,963 source records/observations, 22,946
canonicals, 61,498 aliases, 22,178 active roles, 761 unresolved roles, and 7
expired roles. SQLite quick-check is `ok`, both orphan counts are zero, every
source/canonical payload validates, and forbidden public-metadata keys are zero.
Final representative totals are 64 `apply_now`, 325 `strong_stretch`, 67
`needs_review`, and 22,490 `skip`. The 1,175,146,496-byte artifact SHA-256 is
`fc931f08de07e024786bfae70452455e2dcfbee391a96a9216f9370d840184bc`.

Freshteam was then added as the 34th production provider family. The adapter
handles both public templates observed live: newer cards with stable
`data-portal-*` attributes and older/custom themes whose title, summary, and
location are separate links to the same requisition. Every current card is
detail-enriched from first-party `JobPosting` JSON-LD for the stable job ID,
full description, employer, posting date, employment type, remote flag, and
structured address. Requests are concurrency-bounded, presence on the current
board is recorded as active evidence, and failed detail reads fall back to the
current card rather than dropping the role.

All 14 admitted boards succeeded: IndianPix, Restat, Credit Saison India,
Codvo, Anaxee, SarvM, Robic Rufarm, Intugine, Out Of The Blue, Digitap,
SmartX, Aurochs, Cashflo, and CES. They returned 398/398 valid records with
zero conversion errors and formed 398 net-new canonicals. Under rule 17 the
representative delta was 5 `apply_now`, 18 `strong_stretch`, 2 `needs_review`,
and 373 `skip`. Unpaid MyRufarm work and SarvM's unpaid evaluation/training
period remained withheld rather than being presented as opportunities to
apply to.

The role-level audit found two precision issues and introduced rule 18. A
stipend available only after one month's performance is now `unknown`, not
confirmed paid; this corrected IndianPix and one older Enterpret record. A
3+ year mentor hired to run an internship program is now classified as program
staff, not as an intern. Across all 23,344 canonicals the exact rule-17-to-18
diff is one decision change (SmartX mentor: `strong_stretch` to `skip`), one
eligibility change, two `paid` to `unknown` transitions, and no unrelated apply
decision changes. Freshteam's final representative delta is therefore 5
`apply_now`, 17 `strong_stretch`, 2 `needs_review`, and 374 `skip`.

The metadata-complete public artifact contains 37,759 source records/observations, 23,344
canonicals, 62,692 aliases, 22,576 active roles, 761 unresolved roles, and 7
expired roles. Final representative totals are 69 `apply_now`, 342
`strong_stretch`, 69 `needs_review`, and 22,864 `skip`. SQLite quick-check is
`ok`; orphan observation/alias counts, invalid source/canonical payloads, and
forbidden Freshteam public-metadata keys are all zero. The 1,230,409,728-byte
artifact SHA-256 is
`313849dffde2d276e92a8eb8c39b5c981d6ee52809f2763c009524787827713f`.
The second Freshteam observation cycle retained first-class workplace data on
398/398 latest records and the first-party JSON-LD canonical URL on 397/398;
one detail page omitted JSON-LD and safely retained its current-card evidence.
No current role exposes `validThrough`, salary, or applicant-location fields,
so those fields remain absent rather than inferred.

Keka was then added as the 35th production provider family. The adapter
discovers each tenant's public identifier from the employer career shell and
reads only the public current-job collection plus public organization facts.
It retains the stable numeric requisition ID, complete HTML-normalized
description, exact structured multi-location objects and country codes,
department, employment type, experience, publication timestamp, salary
minimum/maximum/currency/period ID, rendered salary range, skills, current-board
active evidence, canonical detail/apply URL, and employer domain when exposed.
No application form, screening question, candidate record, CSRF material, or
submission endpoint is requested or persisted.

All five admitted boards succeeded in both live reads: Comprinno 28, Vajro/RAP
4, Solytics 70, BeBetta 2, and Zenskar/Evolve 20. The first 124/124-row read had
zero conversion errors and added 124 net-new canonicals; the metadata-corrected
read added 124 immutable observations to the same canonicals and no duplicate
canonical. The final representative Keka delta is 11 `apply_now`, 5
`strong_stretch`, 2 `needs_review`, and 106 `skip`: 16 eligible paths plus two
missing-location reviews. All 18 non-skip detail URLs independently returned
HTTP 200, contained the exact title and visible apply control, and contained no
unavailable marker.

Keka's host-resolved 2026 portal generation was then added. Unlike the embedded
generation, its employer shell contains no tenant UUID; the public UI reads
`/careers/api/jobs/default/active` on the tenant host. POP and Codewinglet both
passed live probes and two repeat reads. Their 29/29 current rows (POP 25,
Codewinglet 4) converted without error and formed 29 net-new canonicals. A
bounded prose fallback recovered seven locations only when structured locations
were absent; for example `Location: Bengaluru Type: Full-Time` now yields
`Bengaluru`, not `Bengaluru Type`. The wave adds two `apply_now` roles (POP QA
software-testing intern and 0-2-year data analyst) plus one `strong_stretch`
(POP SDE-1 backend). All three detail pages independently passed the live-title,
apply-control, and unavailable-marker audit. Codewinglet's current SDET remains
indexed but candidate-specific city/experience constraints keep it out of this
representative queue.

A third Keka wave admitted The Whole Truth Foods and Adit only after live-yield
probes. Their two repeat reads each returned 52/52 rows without conversion
errors: The Whole Truth 15 and Adit 37. The first read formed 52 net-new
canonicals; the second added 52 immutable observations and zero duplicate
canonicals or aliases. The final wave decisions are two `apply_now` (The Whole
Truth's paid Mumbai enterprise-data internship and Adit's 0-1-year junior
systems role), one `strong_stretch` (Adit's junior AI engineer), one location
review, and 48 skips. All four non-skip detail pages independently returned HTTP
200, contained the exact title and a visible apply control, and contained no
unavailable marker.

The Keka role audit rejected three intermediate rule drafts before accepting
rule 22. QA titles now require software/engineering evidence, explicit
clinical/GMP/call-centre/linguistic QA remains nontechnical, and ambiguous QA
stays unknown rather than being invented as CSE or non-CSE. GTM internships
and commercial roles cannot become technical merely because their titles say
AI, while engineers on GTM data teams remain technical. Repeated scans now use
the newest observation that is at least 80% as complete as the richest scan for
that source identity; this lets corrected current facts win without allowing a
transient card-only fallback to erase a full description.

The exact rule-18-to-22 diff paired all 23,468 canonicals. Exactly one decision
and eligibility label changed (`AI GTM Intern`: `strong_stretch` to `skip`),
four structured-salary internships changed from pay unknown to confirmed paid,
and no opportunity type or workplace changed. All 99 track corrections carried
an explicit QA/GTM title signal; no unrelated eligibility decision moved.

Rule 24 fixes a separate experience-boundary defect: phrases such as "up to one
year" and "maximum five years" are upper bounds, not minimum requirements. Its
exact diff paired all 23,549 canonicals. Eighteen minimum-experience values
changed, each with an explicit `up to`, `maximum`, or `max` phrase. Two decisions
moved: The Whole Truth internship changed `strong_stretch` to `apply_now`, and a
marketplace-labelled TestHiring software role changed `skip` to
`strong_stretch` because its full requirement is explicitly minimum two years,
maximum five. No technical track, opportunity type, workplace, pay status, or
unrelated decision changed.

The accepted public artifact contains 38,169 source records/observations,
23,549 canonicals, 63,360 aliases, 22,781 active roles, 761 unresolved roles,
and 7 expired roles. Final representative totals are 80 `apply_now`, 347
`strong_stretch`, 71 `needs_review`, and 22,970 `skip` at the first-wave rule-22
checkpoint; after the native wave and rule 23 they are 83 `apply_now`, 349
`strong_stretch`, 71 `needs_review`, and 22,994 `skip`; after wave three and
rule 24 they are 85 `apply_now`, 351 `strong_stretch`, 72 `needs_review`, and
23,041 `skip`. SQLite quick-check is
`ok`; orphan observations/aliases, invalid source/canonical payloads, and
forbidden Keka metadata keys are all zero. The 1,412,702,208-byte artifact
was the first-wave checkpoint; the final 1,503,977,472-byte artifact SHA-256 is
`d675d193390cca238336d72da8e22863a7bb7fea7a457967cfc2e75930511a2c`.

Keka's 205 latest records are 100% complete for stable requisition ID,
canonical/apply URL, full description, publication text/time, employment type,
active evidence, board/API attribution, and tenant identity. Experience is
present on 200, structured locations on 179 (199 rendered locations), workplace
on 190, salary range on 96, salary minimum on 97, and explicit skill lists on 30.
Missing source fields remain absent rather than inferred.

Quicko was then admitted as the fifteenth Zoho Recruit target only after its
official public board returned 12 current requisitions. Four complete live
Zoho cycles each accepted 614/614 rows across all 15 targets with zero
conversion errors. The first pair repaired the provider-wide workplace
projection and added Quicko's 12 canonicals; the second pair projected the
public employment type, experience, salary, and workplace facts into the full
posting evidence used by applicability. The final repeat added 614 immutable
observations and zero canonicals or aliases, proving the enriched identity set
is stable. Across the complete wave, the artifact gained 2,456 observations,
12 canonicals, and 614 identity aliases.

Rule 25 made structured provider facts actionable. Plural titles such as `AI
Interns`, explicit `Employment type: Internship`, and technical roles with a
provider-authored zero-to-three-year band are recognized without weakening the
nontechnical-title guard. It also passes the first-class workplace field into
classification, so a posting cannot lose remote evidence merely because its
description omits the word. Its exact rule-24-to-25 diff paired all 23,561
canonicals. Nine decisions moved; every movement was inspected, and no
nontechnical role entered the apply or stretch queue.

Rule 26 then fixed the remaining structured-experience boundary: a zero-year
lower bound is not an experience blocker, while `Experience: 1-3 years` is a
bounded stretch for a technical title. Its exact rule-25-to-26 diff again
paired all 23,561 canonicals. Nineteen decisions moved into stretch/review/apply
lanes, including Qualcomm Associate Engineer and current Bosch, Solytics,
Cashflo, and India startup engineering roles. Every decision movement was
reviewed; no nontechnical role was promoted. The final representative totals
are 90 `apply_now`, 373 `strong_stretch`, 70 `needs_review`, and 23,028 `skip`.

Quicko's Flutter Developer, Full Stack Developer, Functional Analyst, and
DevOps detail pages independently returned HTTP 200, exposed an application
control, contained no unavailable marker, and resolved through the production
adapter to the exact requisition and title. Flutter and Full Stack are now
correctly typed as zero-year entry-level technical roles. They remain outside
the representative queue only because that synthetic profile does not accept
Ahmedabad; both remain discoverable in the all-India public index.

The accepted rule-26 artifact contains 40,625 source records/observations,
23,561 canonicals, 63,974 aliases, 22,793 active roles, 761 unresolved roles,
and 7 expired roles. SQLite quick-check is `ok`; orphan observation/alias
counts, invalid source/canonical payloads, and forbidden public-metadata keys
are all zero. The 1,612,664,832-byte artifact SHA-256 is
`743f07f0cd88c8cef3162ee9f0b431daef4458457c77b2d000da2cbe42297260`.

The next discovery wave live-probed six more first-party boards rather than
trusting search-index freshness. Restat was already in production. Fairdeal
Market's indexed frontend internship was absent from its current Keka feed;
Identix had no current early-career technical yield. FutureAcad was rejected as
a production source even though its public Zoho board produced apparent yield:
the board mixes copied third-party jobs with classroom curricula described as
internships, and its unidentified three-month programs do not provide enough
employer/directness evidence for an apply-now lane.

That audit produced rule 27. Explicit classroom/training phases presented as
internships, and `What You Will Learn` curricula without employer
responsibilities or numeric pay evidence, are now safety-blocked as
`training_presented_as_internship`. Genuine paid/employer internships may still
describe mentorship and learning. The rule-26-to-27 exact diff paired all
23,561 pre-wave canonicals and changed zero existing decisions or evidence;
seven live FutureAcad course-style probes were independently blocked. The
marketplace remains excluded until source provenance can force unidentified
postings to review instead of apply-now.

Aatmia and ECS ME passed the live provenance and yield gates and became
production targets 248 and 249. Two repeat reads each accepted 170/170 records
with zero conversion errors. The first read formed 170 net-new canonicals; the
repeat added 170 immutable observations and zero canonicals or aliases. Aatmia
adds a current Chennai Developer Internship and zero-year Developer role as two
`apply_now` paths. ECS ME adds four Hyderabad technical stretches in AI,
Flutter, React/Next.js, and React Native. All six detail pages returned HTTP
200, contained their exact titles and an apply control, and contained no
unavailable marker.

The accepted rule-27 artifact contains 40,965 source records/observations,
23,731 canonicals, 64,484 aliases, 22,963 active roles, 761 unresolved roles,
and 7 expired roles. Final representative totals are 92 `apply_now`, 377
`strong_stretch`, 70 `needs_review`, and 23,192 `skip`. SQLite quick-check is
`ok`; orphan observation/alias counts, invalid source/canonical payloads, and
forbidden public-metadata keys are all zero. The 1,661,460,480-byte artifact
SHA-256 is
`35a16cab5276a761d04584056362e6dddc1bcb67af9fb1224c67b86e4d72e809`.

Rule 28 repairs the Lever adapter rather than inflating coverage with a new
source label. Lever's public response carries substantial job truth outside its
short description: structured salary, salary-description text, workplace type,
country and multi-location values, commitment, team/department, requisition ID,
and hosted/apply URLs. These fields are now retained in the bounded public
metadata and substantive description. Monthly INR ranges with commas and a
currency symbol on both bounds are parsed conservatively at their lower bound.
The exact rule-27-to-28 diff paired all 23,731 pre-wave canonicals and changed
zero decisions, eligibility results, tracks, geography, or safety results; its
six changes were compensation corrections only.

Weekday's public Lever board is production target 250 and remains explicitly
marketplace-labelled. Two full Lever reads each accepted 1,517/1,517 rows with
zero conversion errors. The first formed 62 net-new canonicals and 1,639 new
aliases; the repeat formed zero canonicals and zero aliases, proving stable
identity and deduplication. Candidate-relevant Lever yield is seven roles: three
Fi internships in Bangalore, three Meesho India technical stretches, and one
Weekday Software Engineer Intern. All seven exact detail URLs independently
returned HTTP 200, contained the exact title and an application control, and
contained no unavailable marker. The Weekday role is classified as paid,
India-remote, 2–6 months, with a published ₹30,000–₹50,000 monthly range; the
priority model retains ₹30,000 as the conservative lower bound.

The accepted rule-28 artifact contains 43,999 source records/observations,
23,793 canonicals, 66,123 aliases, 23,025 active roles, 761 unresolved roles,
and 7 expired roles. Final representative totals are 93 `apply_now`, 380
`strong_stretch`, 70 `needs_review`, and 23,250 `skip`. SQLite quick-check is
`ok`; orphan observation/alias counts, invalid source/canonical payloads, and
forbidden public-metadata keys are all zero. The 1,756,745,728-byte artifact
SHA-256 is
`bdbb9e79f48b2e4a2eea4fbcc0673aaca325c3a1cf32f007854ba234ef4b55ab`.

Rule 29 adds 17 verified India-priority boards: Paytm, InMobi, Sarvam,
DevRev, Slice, Hevo, HackerRank, Porter, Netomi, Zeta, Mindtickle, Appfire,
Observe.AI, Sumo Logic, CloudSEK, Groww, and the explicitly marketplace-labelled
Hyreo board. The accepted targeted scan returned 775/775 valid records with
zero conversion errors and 26 relevant roles for the representative profile:
5 `apply_now` and 21 `strong_stretch`. All five immediate-apply pages returned
HTTP 200, contained the exact title and an application control, and contained
no unavailable marker. Rule 29 also recognizes bounded `SDE`/`SWE` titles as
technical context while allowing explicit description evidence to select a
more specific track. Its exact rule-28-to-rule-29 diff changed eight evidence
payloads and promoted only three bounded India technical roles from skip to
stretch.

Two reordered near-verbatim Netomi/Himalayas copies exposed an order-sensitive
historical dedupe gap. Cross-source reconciliation now accepts either 97%
sequence similarity or 97% token-multiset overlap, while still requiring the
same normalized employer/title, different providers, authoritative-versus-
aggregator provenance, long-form content, and no provider requisition conflict.
The real replay merged exactly those two rows. A complete current
Greenhouse/Ashby refresh then accepted 13,300 of 13,301 upstream rows, found
195 newly posted requisitions, and reconciled 88 additional historical alias
owners. The sole rejected row was an Ashby/Composio item with an empty title;
the adapter now filters it at the boundary, and a 31/31 replay completed with
zero conversion errors and zero duplicate canonicals.

The accepted rule-29 artifact contains 59,655 immutable source observations,
24,673 canonicals, 79,219 aliases, 23,909 active roles, 757 unresolved roles,
and 7 expired roles. Representative totals are 98 `apply_now`, 406
`strong_stretch`, 53 `needs_review`, and 24,116 `skip`. Strict validation found
zero invalid source records or canonicals, zero orphan relationships, and
SQLite quick-check `ok`. Its 2,078,539,776-byte SHA-256 is
`fe153f4e8a1c0bcf5b94437fe7556b76298145bedf71d081c4f635039059fcd5`.

Rule 30 adds Zeqo's official careers page through a dynamic visible-card
parser, not hardcoded job rows. It admitted three paid India-remote technical
roles: Founding Full Stack Engineer (Intern to FTE), UI/UX Designer & Flutter
Developer, and Cloud Infrastructure Engineer (LLM Routing). All three are
zero-experience `apply_now` results for the representative CSE profile, with
monthly compensation evidence of at least ₹20,000–₹35,000 and an explicit
₹25,000 minimum for the intern-to-FTE role. The live handoff audit returned
HTTP 200 for all three role-specific URLs, found each exact title and an apply
control, and found no closure marker. BrowserStack's official Workday board was
also probed through its India/CSE plan but currently yielded zero qualifying
requisitions, so it remains an honest watch/exclusion rather than a registered
zero-yield source.

The rule-29-to-rule-30 full-index diff changed no queue decisions. It correctly
reclassified one existing India role whose explicit `0–2 years of experience`
evidence had previously been treated as a stretch; tightened negative tests
prevent incidental phrases such as `Developer Success`, mechanical design, or
sales-engineering titles from bypassing the nontechnical gate. The accepted
Zeqo scan produced 3/3 valid records, zero conversion errors, three net-new
canonicals, and three net-new eligible opportunities. Its repeat read left
canonicals and aliases unchanged and appended only immutable observations.

The accepted rule-30 artifact contains 59,661 immutable source observations,
24,676 canonicals, 79,228 aliases, 23,912 active roles, 757 unresolved roles,
and 7 expired roles. Representative totals are 101 `apply_now`, 406
`strong_stretch`, 53 `needs_review`, and 24,116 `skip`. Strict validation found
zero invalid source/canonical payloads, zero orphan relationships, zero
forbidden Zeqo metadata keys, and SQLite quick-check `ok`. Its
2,125,434,880-byte SHA-256 is
`d5bbff2f9ffd997aef5c4619500dd2438211cce4165f6fb23c9cf4d0c357cbc4`.

Rule 31 admits five additional official, positive-yield targets after live
candidate-board audits: Portcast on Lever, Jumio on Greenhouse, and Fox,
IQVIA, and Dentsu on Workday. The bounded refresh accepted 62/62 rows with
zero conversion errors and created 61 canonicals. Its representative-profile
delta contained one immediate-apply result and eight strong stretches.
Portcast's live Data Analyst Intern is explicitly remote and India-eligible,
requires zero years of experience, and scores 91 for the representative
final-year CSE profile. The six-board Workday candidate audit also records
honest exclusions: GE HealthCare and General Motors returned no current API
requisitions, while Walmart's 31 current rows were all inapplicable rather
than force-promoted.

The Workday adapter is now parser version 2. It retains the stable requisition
ID, internal/job-posting/site IDs, absolute and relative publication evidence,
time type, additional locations, country/code, hiring organization, external
URL, and the authoritative `canApply`/`posted` lifecycle flags. Canonical
identity parsing now also recognizes requisitions embedded in slugged Workday
URLs such as `_R123` and `_JR-123`. A metadata replay enriched all 24 admitted
Workday records without creating a second canonical. The live-handoff auditor
uses Workday's public lifecycle flags for its JavaScript-rendered Apply button,
collapses legacy/v2 observations by tenant and canonical URL, and supports
target-scoped audits. The final public-page checks passed 62/62 role URLs:
HTTP 200, exact title present, application evidence present, and no closure
marker.

The accepted rule-31 artifact contains 59,785 immutable source observations,
24,737 canonicals, 79,423 aliases, 23,973 active roles, 757 unresolved roles,
and 7 expired roles. Representative rule-30 totals are 101 `apply_now`, 414
`strong_stretch`, 53 `needs_review`, and 24,169 `skip`; no taxonomy change was
needed for this source expansion. Strict validation found zero invalid source
or canonical payloads, zero orphan relationships, and SQLite quick-check
`ok`. Its 2,127,609,856-byte SHA-256 is
`5f6e1184fd2dda15ae8363f4cf6985b31f345c55b627f5c446513b05b38e01ad`.

Rule 31 waves 12–14 add four more official, positive-yield company feeds:
Drivetrain on Lever, Altimate on Ashby, and the India/CSE subsets of Eurofins
and Wabtec on SmartRecruiters. Candidate-board audits rejected stale or
zero-yield boards instead of inflating production coverage. The bounded refresh
accepted 112/112 current records with zero conversion errors, creating 105
net-new canonicals; its source-record decisions included two `apply_now` and nine
`strong_stretch` results. Every admitted handoff then passed live verification:
Drivetrain 34/34, Altimate 6/6, and Eurofins/Wabtec 72/72.

The live audit exposed a high-impact deduplication edge case before installation:
two distinct Drivetrain requisitions with near-identical copy (India and United
States) could be transitively bridged through one historical syndicated record.
Country-disjoint syndication is now rejected, and batch persistence rechecks
same-provider/tenant requisition conflicts against earlier planned writes in the
same transaction. The artifact was rolled back to the retained clean pre-wave
snapshot and rebuilt. An exact rule-30 diff paired all 24,737 old canonicals and
found zero changes to existing decisions, eligibility, scores, evidence, or
blockers; the corrected rebuild preserves the extra requisition as its own
canonical.

The final wave-14 artifact contains 59,897 immutable source observations, 24,842
canonicals, 79,765 aliases, 24,078 active roles, 757 unresolved roles, and 7
expired roles. Representative rule-30 totals are 101 `apply_now`, 423
`strong_stretch`, 53 `needs_review`, and 24,265 `skip`. Strict validation found
zero invalid source/canonical payloads and SQLite quick-check `ok`. Its
2,129,920,000-byte SHA-256 is
`8d6d8dc3a2f87faf5138eae2082e28a37194050eb0dcc220249975cc320223e1`.

Rule 31 waves 15–16 add five more official, positive-yield company feeds:
Instawork, MFSG Technologies India, and YipitData on Greenhouse, plus the
India/CSE subsets of Automation Anywhere and Revvity on Workday. Two live
candidate-board audits inspected 351 current rows across 15 boards and admitted
only the five feeds with applicable representative-profile yield. The bounded
refresh accepted 113/113 records with zero conversion errors, and every record
created a net-new canonical. Its source-record decisions include eight
`apply_now`, seven `strong_stretch`, and 98 `skip` results. The admitted
immediate-apply set includes Bengaluru robotics/AI and QA internships,
Hyderabad-remote QA test engineering, Bengaluru SDET, Mumbai AI, and paid
India-remote Data QA roles. Zero-yield current boards and one duplicate global
MFSG tenant remain excluded rather than inflating the target count.

Every admitted handoff passed a fresh official-page audit: Greenhouse 108/108
and Workday 5/5 returned HTTP 200, the exact title, an application control, and
no unavailable marker. An exact semantic diff paired all 24,842 pre-wave
canonicals and found zero changes to their decisions, eligibility, scores,
evidence, blockers, or compared opportunity fields. The final wave-16 artifact
contains 60,010 immutable source observations, 24,955 canonicals, 80,095 aliases,
24,191 active roles, 757 unresolved roles, and 7 expired roles. Representative
rule-30 totals are 109 `apply_now`, 430 `strong_stretch`, 53 `needs_review`, and
24,363 `skip`. Strict source, provider, artifact, and installed-store audits all
report zero invalid payloads and SQLite quick-check `ok`. Its
2,132,299,776-byte SHA-256 is
`44a84b4863f8e9376908a9b1d13c964a38c7836c72636b4c366bb73fb2161fbf`.

Rule 31 wave 17 adds AICTE's official National Internship Portal as a public
marketplace, not an employer-direct board. One broad current-list request exposed
1,005 internship cards; 430 were technical and 362 of those explicitly had no
stipend. The adapter rejects unpaid/no-stipend cards before detail fetching,
uses at most four concurrent public detail reads, and admitted 66 paid technical
internships only after confirming a visible `Apply Now` control. It never reads
or persists login, CAPTCHA, CSRF, application-question, or candidate fields.

All 66 accepted rows created net-new canonicals. For the representative final-year
B.Tech CSE profile, 14 are `apply_now`, 2 are `strong_stretch`, 8 need review,
and 42 are correctly skipped, producing 16 new apply/stretch opportunities.
The admitted set contains paid Pan-India remote AI/ML, data science, Python,
Java/full-stack, and web roles plus India on-site roles including Bengaluru and
Hyderabad. A title-only M.Tech eligibility constraint exposed a degree-parser
gap before installation; rule 31 now reads degree requirements from title and
description, recognizes common B.Tech/M.Tech forms, and blocks the M.Tech-only
role for the B.Tech profile. The exact rule-30-to-rule-31 audit paired all 24,955
pre-wave canonicals: 86 changed only intended degree evidence, 12 gained an
additional hard blocker while already skipped, and zero prior decisions, scores,
geography, or safety classifications moved.

Fresh public-page verification passed 66/66 handoffs with HTTP 200, exact
whitespace-normalized titles, application evidence, and no unavailable marker.
The second metadata replay preserved canonical identity while adding 66 immutable
observations and parsing every exposed publication date and deadline. Across the
latest AICTE observations, canonical/apply URLs, descriptions, hashes, location,
workplace, requisition IDs, raw and parsed publication dates, raw and parsed
deadlines, attribution, and bounded public metadata are 66/66; 64 expose
structured INR monthly stipends and 58 expose credits. The strict privacy audit
found zero forbidden metadata keys.

The final wave-17 artifact contains 60,142 immutable source observations, 25,021
canonicals, 80,293 aliases, 24,257 active roles, 757 unresolved roles, and 7
expired roles. Representative rule-31 totals are 123 `apply_now`, 432
`strong_stretch`, 61 `needs_review`, and 24,405 `skip`. Strict provider, whole-
artifact, preflight, and installed-store audits report zero invalid payloads,
zero orphan relationships, and SQLite quick-check `ok`. The 2,181,308,416-byte
artifact SHA-256 is
`b1743705d915d139fa8d17a1f94bc323465b26e701b9770a87cc168e60c33b7a`.

Rule 32 wave 18 expands employer/startup discovery through live first-party ATS
surfaces. Twelve India-relevant boards were audited; Salesforce, Criteo, and
Immunity produced no current CSE/AI early-career yield and were not admitted.
Seven employer-direct boards were added for Mactores, TalkingLands, Indea Design
Systems, MELSS, Madhi Foundation, CityGreens, and KOTS. Quadeye and Spikewell are
explicitly labelled as PeoplePlus marketplace surfaces because their public Zoho
pages identify that intermediary; they are not misrepresented as employer-direct.

The first refresh surfaced 164 collection rows, but a fresh detail-page audit
found ten Quadeye collection ghosts whose detail pages no longer exposed the
exact role or a live application control. The refresh was rolled back, the Zoho
adapter was hardened to verify current detail pages for bounded-size boards, and
the corrected refresh admitted 154/154 freshly verified handoffs: 32 Mactores
Lever roles and 122 Zoho Recruit roles. It added 148 net-new canonicals, 154
immutable observations, and 457 identity aliases. The six canonical collisions
were reconciled safely; the same-rule before/after audit paired all 25,021 prior
canonicals and found only six Mactores location enrichments from empty to Mumbai,
with no prior decision, eligibility, score, or safety change.

The representative final-year CSE audit classifies the 154 accepted source rows
as 10 `apply_now`, 3 `strong_stretch`, 7 `needs_review`, and 134 `skip`. A
title-only "2028 Batch" role exposed another eligibility gap before installation.
Rule 32 now reads explicit batch years from title as well as description, so the
2027 representative profile no longer receives that role. The exact rule-31-to-
rule-32 audit paired all 25,021 pre-wave canonicals and found four evidence-level
changes; only one decision moved (`apply_now` to `skip`), the intended Google
2026-graduation exclusion for the 2027 profile.

The final wave-18 artifact contains 60,296 source observations, 25,169 canonicals,
80,750 aliases, 24,405 active roles, 757 unresolved roles, and 7 expired roles.
Representative rule-32 totals are 128 `apply_now`, 435 `strong_stretch`, 68
`needs_review`, and 24,538 `skip`. Strict Lever, Zoho, whole-artifact, preflight,
and installed-store audits report zero invalid payloads, zero orphan
relationships, no private-table imports, and SQLite quick-check `ok`. The
2,231,062,528-byte artifact SHA-256 is
`d6da1ce979d58f405442873fdf34af843f1c15aed5dbcc990888119950d634a7`.

Rule 33 wave 19 expands the current India employer-direct lane again. Broad
discovery attempted 25 distinct first-party boards through the existing Ashby,
SmartRecruiters, Workday, and Zoho Recruit adapters. The candidate-board audit
now records bounded skip-reason counts and representative rejected rows, making
zero-yield decisions reproducible instead of merely reporting a zero. A fresh
same-rule replay audited 350 current rows across the ten surviving candidate
boards and found 21 relevant rows; Sun360's six rows were all correctly rejected,
so that board was not admitted. Nine boards with current positive yield were
registered: Almabase, Josys, IIDE, CEEW, Stutzen, GalaxEye, Futuristic Labs,
Perceptive Analytics, and Infusory.

The audit exposed four taxonomy edge cases before ingestion. Rule 33 now admits
`data analytics` and IT/system/network administrator roles into their intended
technical tracks, while program-coordinator and design-engineering roles no
longer become false CSE/AI positives merely because their titles contain `AI` or
`engineering intern`. The full Rule-32-to-Rule-33 rescore paired all 25,169
existing canonicals: 111 received intended taxonomy/evidence corrections, but
zero prior representative decisions changed.

The nine-board refresh accepted 344/344 source rows with zero conversion errors.
Every row created a net-new canonical, adding 1,009 identity aliases. For the
representative final-year B.Tech CSE profile, the source delta contains 7
`apply_now`, 2 `strong_stretch`, 12 `needs_review`, and 323 correctly skipped
rows. Independent first-party handoff verification passed all 33 Ashby and all
311 Zoho Recruit postings: HTTP 200, exact normalized title, a visible apply
control, and no unavailable marker. The same-rule before/after diff paired all
25,169 prior canonicals with zero changes or losses and identified exactly 344
new canonicals.

The final wave-19 artifact contains 60,640 immutable source observations, 25,513
canonicals, 81,759 aliases, 24,749 active roles, 757 unresolved roles, and 7
expired roles. Representative rule-33 totals are 135 `apply_now`, 437
`strong_stretch`, 80 `needs_review`, and 24,861 `skip`. Strict Ashby, Zoho,
whole-artifact, preflight, and installed-store audits report zero invalid
payloads, zero orphan relationships, zero foreign-key violations, no
private-table imports, and SQLite quick-check `ok`. The 2,283,446,272-byte
artifact SHA-256 is
`3e011358910374b85fc82031150aea8f12bd4c2639b87ceb41b597855280556d`.

Rule 34 wave 20 strengthens admission evidence and exploitation controls while
adding two maintained employer boards. Candidate-board reports now retain
bounded lifecycle and provenance data for every relevant row and sampled
rejection: live status, first/last seen and verified-active timestamps,
publication/update/deadline values, posting age, freshness band, provider,
tenant, requisition ID, active hint, attribution, and source kind. This exposed
five discovery paths that a simple live-page check would have overstated:
Subconscious Compute's five relevant-looking roles were 674–898 days old;
FutureAcad mixed undated or aged training programs and third-party employers;
Blue5Green had zero CSE yield; Lebara's board returned HTTP 502 on both retries;
and the indexed Arrcus internship returned HTTP 410 Gone.

Brainwonders exposed a separate safety failure: its fresh AI internship
advertised a six-month mandatory tenure with a ₹1 lakh completion benefit
payable only after successful completion and subject to satisfactory performance
and attendance. Rule 34 adds `conditional_completion_compensation` as a hard
safety blocker unless the same posting independently guarantees recurring pay.
It also directly blocks phrases such as `internship training program`, even when
course copy contains a generic responsibilities heading. Regression coverage
proves that a guaranteed monthly stipend plus a separate completion bonus remains
paid and eligible. The full Rule-33-to-Rule-34 rescore paired all 25,513 existing
canonicals and changed zero existing decisions or evidence fields.

Embark GCC was admitted for its current Bangalore System Administrator internship.
Brainwonders was admitted as a maintained safety-watch board so current and future
technical roles are observed, while the exploitative conditional-compensation
role remains indexed only as `skip`. The two-board refresh accepted 70/70 rows
with zero conversion errors, added 70 net-new canonicals and 209 aliases, and
classified the delta as 1 `apply_now` plus 69 `skip`. The same-rule exact diff
paired all 25,513 pre-wave canonicals with zero changes or losses. Independent
first-party handoff checks passed 60/60 Embark and 10/10 Brainwonders rows with
HTTP 200, exact normalized titles, visible application controls, and no
unavailable marker.

The final wave-20 artifact contains 60,710 immutable source observations, 25,583
canonicals, 81,968 aliases, 24,819 active roles, 757 unresolved roles, and 7
expired roles. Representative rule-34 totals are 136 `apply_now`, 437
`strong_stretch`, 80 `needs_review`, and 24,930 `skip`. Strict SmartRecruiters,
Zoho, whole-artifact, preflight, and installed-store audits report zero invalid
payloads, zero orphan relationships, zero foreign-key violations, no private-
table imports, and SQLite quick-check `ok`. The 2,333,097,984-byte artifact
SHA-256 is
`30ed44de52e4178502cbaff45d66f473a62cdc17d34134efa0575b00e41e8d15`.

Wave 21 adds a generic Oracle Recruiting Cloud / Oracle HCM adapter instead of
hard-coding another employer-specific page scraper. Public Candidate Experience
redirects established the current site identifiers for KPMG (`CX_3`), Coherent
(`CX_8001`), and WSP (`CX_2001`). The adapter validates Oracle Cloud hosts and
site IDs, searches a bounded early-career/CSE matrix, locally rejects Oracle's
fuzzy false matches (`intern` also matches `internal`), requires exact India and
technical evidence, de-duplicates by authoritative requisition ID, and then
rechecks every retained requisition through the public detail endpoint. A row
whose detail endpoint is empty is treated as closed between collection and
projection. No application-question or candidate-form schema is requested.

The projected records retain every useful public role fact exposed by these
tenants: stable requisition ID, publication/deadline values, primary and
secondary India locations, workplace mode, legal employer, business unit,
department, organization, job family/function/type/schedule/shift, worker and
contract type, study/manager level, duration/hours/days, travel requirements,
provider flags, full description, responsibilities, qualifications, discovery
queries, employer domain, host, and site number. Private/form-key filtering
remains enforced at canonicalization. Direct detail checks also invalidated two
community-index pointers that had already closed (KPMG 30047604 and Coherent
2011938), demonstrating why a current search result alone is not admission
evidence.

The three live production tenants returned 53/53 accepted rows with zero
conversion errors: 34 KPMG, 3 Coherent, and 16 WSP. Rule 34 classified the
delta as 6 `apply_now`, 5 `strong_stretch`, and 42 `skip`; all 11 relevant rows
are net-new. Current clean early-career wins include KPMG's Cyber IAM internship,
WSP's Graduate Security Risk Management role, and WSP's Building Technology
Systems internship. KPMG's separately numbered DLP conversion requisitions stay
separate because the employer exposes distinct authoritative application doors;
their full descriptions explicitly accept pursuing/completed B.Tech candidates
and contain fresh-applicant intern duties, so title-only suppression would be a
false negative.

The final wave-21 artifact contains 60,763 immutable source observations,
25,636 canonicals, 82,121 aliases, 24,872 active roles, 757 unresolved roles,
and 7 expired roles. Representative rule-34 totals are 142 `apply_now`, 442
`strong_stretch`, 80 `needs_review`, and 24,972 `skip`. The production registry
now contains 306 targets across 38 provider families. Oracle-provider,
whole-artifact, preflight, and both installed-store audits report zero invalid
payloads, zero forbidden private/form metadata keys, zero orphan relationships,
zero foreign-key violations, no private-table imports, and SQLite quick-check
`ok`. Both installed stores preserve their pre-existing 17,654 and 849 leads.
The 2,334,060,544-byte artifact SHA-256 is
`8230002981f3eec025a8071bf96d2cda4f9c17b33cf550c9361791bdd3d8d9c3`.

Wave 22 adds a generic Eightfold adapter covering both the newer PCS-X search
API and the classic public careers API. It accepts only one-label
`*.eightfold.ai` hosts, uses a bounded early-career/CSE query matrix, locally
re-filters exact India locations because the public API can return fuzzy
matches, de-duplicates by authoritative position ID, and requires a live
same-host public `JobPosting` detail page before admitting a row. The detail
enrichment retains the public description, requisition/display/position IDs,
employer domain/name, all standardized locations, workplace and employment
types, department, discovery queries, publication/creation epochs, deadline,
and platform flags. Application forms and questions are deliberately not
collected.

Candidate-board audits were admission gates rather than volume exercises.
Micron returned 14 live India rows, but its only umbrella internship did not
identify a technical track and the remaining early-career rows were
manufacturing graduate roles; it was therefore not added to production.
Eightfold's own board, Fortive, and Vodafone returned 33 live India technical
rows with zero conversion errors and four relevant outcomes: Fortive's fresh
zero-experience Associate Data Scientist is `apply_now`; Eightfold's Bangalore
AI-SDET Engineer, Fortive's Bengaluru Mobile QA role, and Vodafone's Pune
Digital Video Test Engineer are transparent one- or two-year
`strong_stretch` roles. All 33 rows and all four eligible outcomes are net-new.

The final wave-22 artifact contains 60,796 immutable source observations,
25,669 canonicals, 82,216 aliases, 24,905 active roles, 757 unresolved roles,
and 7 expired roles. Representative rule-34 totals are 143 `apply_now`, 445
`strong_stretch`, 80 `needs_review`, and 25,001 `skip`. The production registry
now contains 309 targets across 39 provider families. Provider, whole-artifact,
preflight, and both installed-store audits report zero invalid payloads, zero
forbidden private/form metadata keys, zero orphan relationships, zero
foreign-key violations, zero collisions or missing rows, no private-table
imports, and SQLite quick-check `ok`. Both installed stores preserve their
pre-existing 17,654 and 849 leads. The 2,334,826,496-byte artifact SHA-256 is
`c75013b883e88342acfe3f50a87f7378f2ca857c020148f58b057faf2803e3b9`.

Wave 23 adds a generic iCIMS hosted-portal adapter. It accepts only one-label
`*.icims.com` HTTPS hosts, walks at most 30 public search pages with courtesy
pacing, supports both observed iCIMS card themes (dt/dd facts and separate
header label/value spans), requires exact India location evidence, and retains
only early-career or bounded-stretch technical titles. Every retained card is
rechecked through its same-host public detail page and must still expose a
valid `JobPosting` node. Public description, numeric job ID, employer identity,
structured locations, employment/workplace type, card taxonomy, publication
date, deadline, and direct-apply flag are retained. Application forms,
questions, and candidate endpoints are never requested.

The live admission gate caught a multiline themed-location parser defect as a
zero-result audit before any source was registered; the corrected fixture now
covers that exact markup. PowerSchool and Waters internships found in search
indexes had already closed and were not ingested. Orange, Applied Systems,
StoneX, Waters, and PowerSchool were then excluded because their current India
CSE rows were experienced-only or zero-yield. Seismic alone met the production
threshold with two live Hyderabad roles and one eligible outcome: Software
Engineer II is a paid two-year `strong_stretch`. Both Seismic rows and the
eligible row are net-new.

This wave also fixes a cross-provider ranking error uncovered by the Seismic
audit: structured `onsite`/`hybrid` values now outrank incidental prose such as
"remote teams" or the public fact "Remote: No". Rule 35 rescored all 25,669
pre-iCIMS canonicals. The exact Rule 34-to-35 diff has no missing IDs, changes
273 workplace scopes, and changes only four decisions: three Adit roles in
Ahmedabad and one Restat internship in New Delhi are no longer falsely treated
as remote and are correctly excluded by the candidate's accepted-city policy.
A verified live `Banglore` spelling is normalized to Bengaluru, preserving the
Numatix Quantitative Developer internship as `apply_now`.

The final wave-23 artifact contains 60,798 immutable source observations,
25,671 canonicals, 82,222 aliases, 24,907 active roles, 757 unresolved roles,
and 7 expired roles. Representative rule-35 totals are 140 `apply_now`, 445
`strong_stretch`, 80 `needs_review`, and 25,006 `skip`. The production registry
now contains 310 targets across 40 provider families. Provider, whole-artifact,
preflight, and both installed-store audits report zero invalid payloads, zero
forbidden private/form metadata keys, zero orphan relationships, zero
foreign-key violations, zero collisions or missing rows, no private-table
imports, and SQLite quick-check `ok`. Both installed stores preserve their
pre-existing 17,654 and 849 leads. The 2,383,806,464-byte artifact SHA-256 is
`82d25317341cc827f10e21b22e2351f62acaa6c90a6534504cea27b866eb8d25`.

Wave 24 adds a generic Avature career-portal adapter based on the current public
server-rendered contract. It accepts only one-label `*.avature.net` HTTPS hosts
and allowlisted portal paths, prefers the board's own India country facet, and
falls back to a public `India` search only when the branded portal exposes no
country facet. Every no-facet result must still carry exact India evidence in
its card or detail fields. Pagination is bounded to 60 pages with courtesy
pacing and automatically verifies `jobOffset`, falling back to the branded
`offset` variant only when the first ID repeats. Retained cards must have a
non-senior technical title and are rechecked through the exact same-host public
`JobDetail` page. Numeric requisition ID, same-host apply URL, full description,
all non-description public detail fields, city/state/country, workplace,
employment/seniority facts, and normalized publication date are retained. No
login form, candidate profile, application question, or application payload is
requested.

The live tenant audit scanned all 141 India-faceted Synopsys cards and the
branded Xerox India-search path. Synopsys returned two live Bengaluru
Salesforce Developer requisitions; both ask for two years and are correctly
ranked as paid priority-70 `strong_stretch` opportunities. Xerox returned one
live Kolkata `SOFTWARE ENGINEER 3` role, correctly retained in public truth but
skipped for the representative candidate because its experience bar and city
constraints do not fit. IBM's public portal answered the audited request with
an empty HTTP 202 and was not admitted. The production refresh accepted all
three rows with zero conversion errors; all three canonicals and both relevant
outcomes are net-new.

The final wave-24 artifact contains 60,801 immutable source observations,
25,674 canonicals, 82,231 aliases, 24,910 active roles, 757 unresolved roles,
and 7 expired roles. Representative rule-35 totals are 140 `apply_now`, 447
`strong_stretch`, 80 `needs_review`, and 25,007 `skip`. The production registry
now contains 312 targets across 41 provider families. Provider, whole-artifact,
preflight, and both installed-store audits report zero invalid payloads, zero
forbidden private/form metadata keys, zero orphan relationships, zero
foreign-key violations, zero collisions or missing rows, no private-table
imports, and SQLite quick-check `ok`. Both installed stores preserve their
pre-existing 17,654 and 849 leads. The 2,383,872,000-byte artifact SHA-256 is
`13b230bfb600d476112a00a7d21cfe5bea93f02b6edd32605d1c43dd0355cf53`.

Wave 25 adds a generic Jobvite adapter for the current public
`jobs.jobvite.com/{company}` contract. It parses server-rendered category
tables, retains bounded non-senior India CSE/security candidates, and rechecks
every retained row through an exact same-host public `JobPosting` detail. The
detail title and requisition ID must match the board card; structured country
data overrides ambiguous city text, closed-listing responses are rejected, and
only exact same-host apply links are retained. Full description, structured
address, workplace, dates, employer identity/domain, employment/industry,
salary, skills, education, experience, qualifications, responsibilities,
benefits, and applicant-location facts are preserved when the employer
publishes them. Candidate pages, application forms/questions, and saved-job
flows are never requested.

The live admission audit covered Barracuda, Genpact Experience, and Progress.
It accepted five public rows with zero conversion errors. Barracuda yielded
four live Bangalore technical roles, including an Application Security
Engineer and Software Engineer II that are correctly ranked as two-year
`strong_stretch` opportunities. Its other two rows are correctly skipped for a
five-year requirement and lack of early-career evidence. Genpact's one live
India-wide Workfront role is experienced-only and Progress currently yields no
qualifying row, so neither was admitted. The production refresh accepted all
four Barracuda rows and produced four net-new canonicals, twelve aliases, and
two net-new eligible outcomes.

The final wave-25 artifact contains 60,805 immutable source observations,
25,678 canonicals, 82,243 aliases, 24,914 active roles, 757 unresolved roles,
and 7 expired roles. Representative rule-35 totals are 140 `apply_now`, 449
`strong_stretch`, 80 `needs_review`, and 25,009 `skip`. The production registry
now contains 313 targets across 42 provider families. Provider, whole-artifact,
preflight, and both installed-store audits report zero invalid payloads, zero
forbidden private/form metadata keys, zero orphan relationships, zero
foreign-key violations, zero collisions or missing rows, no private-table
imports, and SQLite quick-check `ok`. Both installed stores preserve their
pre-existing 17,654 and 849 leads. The 2,383,945,728-byte artifact SHA-256 is
`46835d160298bc474bc70bf3084b858caef24bd68700eee31b8324eb7e2f56b0`.

Wave 26 adds a generic SuccessFactors Career Site Builder adapter covering the
current public JSON search service and SAP's documented external-job XML feed.
Tenant, locale, and vendor-host syntax are fail-closed; the XML path discovers
only the exact SuccessFactors host declared by the branded public board and is
parsed with `defusedxml`. SAP's requisition ID and separate opaque career-page
ID are modeled independently: a requisition-ID query against the branded
server-rendered search must resolve exactly one same-host, exact-title job link,
and the visible detail must repeat the requisition ID before its opaque-ID Apply
control is accepted. Full public descriptions, publication/deadline fields,
India-only locations, coordinates, locale/category/experience values,
employment/workplace/business-unit facts, and all labelled detail fields are
retained. Candidate, form, question, and talent-community data are not fetched.

Live audits verified three Danfoss rows and nine SAP India technical/adjacent
rows with zero conversion errors. The Danfoss roles and all SAP rows were
correctly skipped for experience, technical-track, city, or graduation-profile
constraints; Tetra Pak yielded zero current qualifying rows. SuccessFactors is
therefore implemented and live-proven but no zero-yield tenant was admitted to
the bounded production registry.

Wave 27 adds a generic Jibe/iCIMS Attract adapter based on the public API used
by AMD's visible career UI. It walks the complete provider-side India facet,
filters senior and nontechnical rows before detail calls, then re-reads every
retained requisition through the locale-specific public detail endpoint. Exact
client, requisition, title, India country, `searchable`, `applyable`, and
non-internal state are required, as is an exact public `*.icims.com` Apply URL.
The adapter preserves full description/hash, requisition and ATS identities,
publication/create/update times, employment/category/department/tags,
qualifications, responsibilities, benefits, hiring organization, language and
application flags, street/city/state/country/postal location, latitude and
longitude, public iCIMS revision/site evidence, and bounded Google Jobs-derived
category/location facts.

AMD's complete India scan produced 19 fresh verified non-senior technical rows
with zero conversion errors. Eighteen are correctly skipped for experience,
degree, technical-role, or early-career constraints. A Bangalore hybrid
Security Vulnerability Testing/Assessment Engineer role is a paid three-year
priority-72 `strong_stretch`, making the board production-positive. The refresh
added 19 net-new canonicals, 56 aliases, 19 immutable observations, and one
net-new eligible outcome.

The final wave-27 artifact contains 60,824 immutable source observations,
25,697 canonicals, 82,299 aliases, 24,933 active roles, 757 unresolved roles,
and 7 expired roles. Representative rule-35 totals are 140 `apply_now`, 450
`strong_stretch`, 80 `needs_review`, and 25,027 `skip`. The production registry
now contains 314 targets across 43 provider families. Provider, whole-artifact,
preflight, and both installed-store audits report zero invalid payloads, zero
forbidden public-metadata keys, zero orphan relationships, zero foreign-key
violations, zero collisions or missing rows, no private-table imports, and
SQLite quick-check `ok`. Both installed stores preserve their pre-existing
17,654 and 849 leads. The 2,384,687,104-byte artifact SHA-256 is
`f090ce4d226b68f94b649cc0c0f9c87b3a6d3b829fead85e269cffc6ee466523`.

## Data completeness

- source target, canonical source URL, apply URL, full description, description
  hash, raw payload hash, and attribution: 100%;
- location: 96.86%;
- workplace: 42.67%;
- provider publication text: 71.34%;
- parsed publication time: 70.07%;
- provider requisition ID: 72.54%;
- provider update text/time: 20.24%/20.23%;
- provider deadline text/time: 4.43%/4.32%;
- provider/company tenant: 100%;
- employer domain: 1.16% because most public ATS/aggregator responses do not
  expose it. Missing fields remain missing rather than inferred.

The newer 535-record targeted Himalayas delta is 100% complete for source
target, provider/company identity, requisition ID, canonical/apply URL,
location, workplace, full description, publication time, deadline, hashes,
and attribution. Employer domain and provider update time remain 0% because
the official response does not provide them. Structured employment type,
seniority, salary/currency/period, timezones, categories, company logo, and
location restrictions are retained in source metadata.

All adapters may now retain bounded `public_metadata` alongside the strict core
fields. Nested private-key filtering removes candidate identity, email, phone,
resume/CV, credentials, cookies, demographics, and application-form/question
material before persistence. A strict whole-artifact audit deserialized all
60,824 source payloads and all 25,697 canonical payloads with zero failures; the
latest public metadata contains zero forbidden keys.

## Verification

- focused IBM/source/applicability/rescore suites passed, including exhaustive
  boundary-equivalence checks for every technology taxonomy alias;
- a full rule-v4 consistency pass evaluated all 20,013 canonical opportunities;
  it also exposed and fixed a silent 20,000-row rescore default that left 13
  older records stale;
- profiling found technology extraction consumed 75.2% of worst-case evaluation
  time. Replacing the giant alternation regex with boundary-safe literal matching
  reduced the 250-largest-record benchmark from 33.52s to 8.16s (75.7% faster),
  and technology extraction from 25.21s to 0.35s (98.6% faster);
- the corrected full 20,013-record rescore completed in 423.45s with identical
  decision counts and zero invalid canonical records, down from more than 20
  minutes before optimization;
- rule 7 then evaluated the enlarged 20,913-record index in 461.28s with zero
  invalid records. Its only change from rule 6 was the intended exclusion of a
  role requiring Russian or Ukrainian;
- rule 8 introduced evidence-gated resident/fellow classification, campus-hire
  recognition, bounded 1-3-year technical stretches, and correct lower-bound
  parsing for experience ranges. Its full 21,053-row pass completed in 342.81s
  with zero invalid records and transactionally reconciled two duplicate
  canonical identities;
- the rule-8 title audit found and fixed explicit AMERICAS/EMEA/APAC remote-region
  handling plus technical-writer, data-annotator, domain-expert, and Data QA
  edge cases. Rule 10 evaluated all 21,051 surviving canonicals in 296.96s with
  zero invalid records. The final rule-9-to-rule-10 diff was exactly one expected
  APAC/Australia row returning from review to skip;
- conservative cross-source reconciliation subsequently consolidated nine
  Greenhouse/Himalayas copies whose normalized employer/title matched and
  substantive descriptions were 99.48%–99.80% similar. All observations,
  aliases, candidate decisions, events, and lead links migrate transactionally
  to the stable canonical ID. A Twilio same-title pair at only 81.40%
  similarity remains separate. Post-reconciliation SQLite integrity is `ok`,
  all 20,904 canonical payloads validate, and orphan observation/event/lead
  counts are zero;
- candidate spoken languages now flow through the strict API contract, private
  profile persistence, setup UI, and rule-7 rescoring. This prevents explicit
  language requirements from being guessed or silently ignored;
- rule 11 carries the candidate's current degree level through the strict API,
  private profile persistence, setup UI, and applicability evidence. Its complete
  21,352-row pass produced zero invalid canonicals. The rule-10-to-rule-11 diff
  is exactly one intended transition: Microsoft's `Research Sciences INTERN`
  moved from apply to skip because it explicitly requires a master's or
  doctorate. A title-by-title transition audit also caught and fixed the word
  `master` used as a verb in two Branch internship descriptions before the final
  pass;
- rule 12 normalizes ATS underscores before title-boundary classification and
  recognizes `SW`/`HW` technical abbreviations. Its complete 21,376-row pass
  produced zero invalid canonicals. The rule-11-to-rule-12 diff is exactly eight
  Qualcomm skip-to-apply transitions: four current internships and four 2027
  campus hires. No existing decision changed;
- the next official-source cycle added Atlassian's first-party India feed,
  Razorpay's official Greenhouse board, Freshworks' official SmartRecruiters
  board, Oracle's exact India 0-2-year and Student/Intern facets, and Swiggy's
  official NextHire feed, and Dell's replacement Oracle Recruiting Cloud board.
  The production registry now contains 201 targets across 31 provider families;
- SmartRecruiters pagination and full-detail enrichment recovered Freshworks'
  complete 167-posting board instead of the former 100-row cap. Stable provider
  IDs, full descriptions, qualifications, employment/experience labels,
  workplace mode, apply URL, and public reference fields are now retained.
  SmartRecruiters slug normalization then transactionally consolidated the 100
  summary/detail duplicate canonicals; 434 immutable Freshworks observations
  map to exactly 167 distinct opportunities;
- current live yield from the added boards is deliberately conservative:
  Atlassian returned 8 India technical roles and Razorpay 24 postings, all
  skipped for this student cohort; Freshworks returned 167 postings, with one
  3-year Data Platform Engineering strong stretch and 166 skips; Oracle's exact
  early facets returned one CSE-adjacent support-integration role, skipped for
  prior HCIT experience; Swiggy returned two technical roles, both skipped at
  6-8 years required experience;
- Dell's retired Workday path was replaced by its current public Oracle
  Recruiting Cloud site. Five distinct India technical roles were recovered.
  Full-detail parsing found three visible cards with already-passed application
  closing dates and marked them expired; the two remaining active roles require
  eight years. All five are skips, so no stale Dell card reaches the action
  queue;
- Visa's official early-careers page now resolves to its current Workday site.
  The live board exposes 12 global early-career records and exactly one India
  record today; that record is `Staff SW Engineer- Java backend with GenAI
  experience`, so the India/CSE lane correctly returns zero rather than
  presenting a senior role to students. Bosch's retired empty SmartRecruiters
  tenant was replaced by the current `BoschGroup` tenant. Its server-side India
  slice returned 114 rows, 113 valid unique requisitions, eight strong stretches,
  and 105 skips; one provider-marked inactive row is now preserved as canonical
  `closed` lifecycle evidence instead of failing enum conversion;
- rule 13 recognizes explicit systems/technical integration descriptions as a
  cloud/integration technical track without rescuing generic internships via
  employer buzzwords. Its complete 21,576-row pass produced 49 apply, 267
  strong-stretch, 37 review, 21,223 skip, and zero invalid canonicals. The two
  later Swiggy and Dell observations were evaluated directly under rule 13,
  bringing the complete pre-identity-repair rule-13 cardinality to all 21,583
  canonicals;
- a corpus-wide provider-identity audit then found 298 historical canonical
  clusters where exact employer/title/location/description templates had
  overruled distinct authoritative requisition IDs. Content and fuzzy-
  syndication merges now reject both direct and transitive same-provider/tenant
  ID conflicts, and persistence applies the same invariant. With zero linked
  leads or candidate events, the backed-up repair replaced those 298 rows with
  773 canonicals from 807 immutable observations. The complete index now has
  zero same-provider/tenant multi-ID clusters;
- the repaired 22,171-row rule-13 pass completed in 493.62s and produced 49
  apply, 319 strong-stretch, 37 review, and 21,766 skip decisions. Rescoring now
  persists candidate decisions without re-resolving or rewriting canonical
  truth; tests prove canonical rows and identity aliases remain byte-for-byte
  unchanged;
- profiling the real 1,000-opportunity workload found the graduation-clause
  regex consumed 21.19s of a 35.76s evaluation by retrying its bounded prefix
  across long descriptions. Rule 14 replaces it with boundary-checked literal
  signal discovery plus the same punctuation-bounded 80-character evidence
  windows. The sample fell to 6.34s (82.3% faster), and the complete 22,171-row
  rescore fell from 493.62s to 177.53s (64.0% faster end-to-end). All 22,171
  rule-13/rule-14 payloads were compared after excluding the version field:
  exactly one Regions posting now correctly retains both published graduation
  years, 2027 and 2028; zero decisions or eligibility labels changed;
- all 36,098 source payloads and all 22,189 canonical payloads validate against
  their strict models. SQLite integrity is `ok`, the foreign-key check is empty,
  provider-identity conflicts and orphan source observations are zero. All
  22,189 canonicals have current rule-14 representative decisions; the 22,171
  pre-refresh canonicals additionally retain their historical rule-13 decisions;
- candidate-scoped application snapshots now require a validated email and
  phone number in addition to the candidate's resume evidence. Readiness
  responses expose only completeness flags, never the stored contact values.
  Preview, manual submission, and Ghost submission all re-check explicit
  candidate consent and snapshot readiness at the final automation boundary.
  Candidate-scoped leads resolve identity and application evidence exclusively
  from that candidate's private snapshot and cannot fall back to the account
  owner's shared profile or settings. Legacy single-user leads retain their
  existing behavior;
- a public-index synchronizer now validates and SHA-256-hashes an audited source,
  rejects orphan relationships and incompatible stable-key collisions, obtains
  a destination write lock, creates a SQLite-consistent backup, and atomically
  merges only source records, canonicals, observation links, and identity
  aliases. It never selects candidate profiles, application identities,
  decisions, outcomes, leads, settings, or spend records. Re-running the same
  source is idempotent, and every completed synchronization records provenance,
  source/inserted counts, freshness, and the backup label;
- the synchronizer also refreshes mutable canonical payload/lifecycle truth only
  when source lifecycle evidence is strictly newer. Stable identity collisions
  still fail closed and fresher destination evidence wins. The behavior is covered
  by atomicity, idempotence, collision, orphan, and newer/older evidence tests;
- the corrected 1,035,894,784-byte market artifact passed read-only preflight with
  SHA-256
  `905b9ec8f7fdefb1b71dd211f4095f66bde850700aa1bae0a401f2841fc2d047`,
  SQLite quick-check `ok`, and zero orphan observations or aliases. A full-scale
  isolated installation then transferred all 150,816 public table rows in about
  nine seconds with zero collisions, missing rows, or foreign-key violations;
- the initial transaction populated the actual installed app database from zero
  to 34,734 source records, 22,171 canonicals, 34,734 observation links, and
  59,177 identity aliases. The protected lifecycle sync then inserted 1,364
  source records/observations, 18 canonicals, and 39 aliases, and refreshed 737
  existing canonicals from strictly newer evidence. Installed totals now exactly
  match the corrected artifact: 36,098 source records/observations, 22,189
  canonicals, and 59,216 aliases. Full installed-database integrity is `ok`; foreign-key,
  observation-orphan, and alias-orphan counts are zero. All 17,654 pre-existing
  leads remain present, while candidate profiles, application snapshots,
  and decisions remain at zero. The verified pre-lifecycle rollback backup
  contains the same 17,654 leads and 22,171 pre-refresh canonicals;
- backend suite: 1,874 passed, 14 skipped; the only warning is an upstream
  Starlette `httpx` deprecation;
- frontend suite: 89 passed;
- TypeScript typecheck: passed;
- production frontend build: passed;
- isolated real-web smoke: the spoken-language control rendered, saved
  `English, Hindi` through the live API into a synthetic local profile, and
  retained the value after a full reload with zero browser console errors;
- a second isolated real-web smoke verified the candidate identity boundary:
  consent without email and phone leaves current-profile linking disabled;
  adding both required contact fields enables it; no synthetic profile or
  consent was persisted and the browser console remained error-free;
- a read-only aggregate check of the installed pilot database confirms the
  starting state is still zero candidate constraint profiles, zero recorded
  candidate consents, and zero candidate application snapshots. Consequently,
  no real-candidate scan, document generation, or submission can start yet;
- a third isolated real-web smoke loaded the initial populated installed database
  through the production API and rendered 22,171 indexed canonicals, 21,193
  verified-active roles, 971 explicitly unresolved lifecycle statuses, 34,734 indexed
  observations, the source freshness timestamp, and the installation timestamp.
  Candidate-specific refresh counters remain separately labelled at zero, so an
  unrun candidate refresh cannot be mistaken for an empty public index. The
  browser console remained error-free;
- the post-lifecycle real-web smoke rendered 22,189 indexed canonicals, 21,421
  verified-active roles, 761 unresolved statuses, 36,098 observations, and the
  corrected source/install timestamps. It also rendered 201 free/direct targets,
  31 provider families plus 3 paid experiments, zero candidate refresh failures,
  disabled zero-spend paid providers, and consent/contact-gated candidate actions.
  Browser logs contained no errors;
- all changed source, registry, applicability, rescore, and regression-test files
  pass Ruff;
- installed SQLite database: additive migrations applied, public index populated,
  rollback backup verified, integrity `ok`, and all 17,654 pre-existing leads
  preserved;
- the final YC/rule-15 synchronization inserted 163 source records/observations,
  55 canonicals, and 218 aliases into the installed database with zero stable-key
  collisions, missing rows, foreign-key violations, or private-table imports.
  Installed totals exactly matched the then-current artifact. The post-sync strict audit
  found zero invalid payloads and zero candidate opportunity profiles,
  application profiles, decisions, or events; all 17,654 existing leads remain.
  The pre-sync rollback database independently passes SQLite integrity and orphan
  checks;
- the targeted direct-board synchronization then inserted 49 source records,
  observations, and canonicals plus 147 aliases, again with zero collisions,
  missing rows, foreign-key violations, or private-table imports. The final
  installed strict audit matched the 22,293/36,310/59,581 artifact counts, found
  zero invalid payloads or private candidate/application rows, and preserved all
  17,654 leads;
- the final rule-16 synchronization inserted 51 source records, observations,
  and canonicals plus 149 aliases, with zero collisions, missing rows, foreign-
  key violations, or private-table imports. The installed strict audit matches
  the final artifact, contains zero invalid or private candidate/application
  rows, and preserves all 17,654 leads;
- the Zoho/rule-17 synchronization inserted 550 source records, observations,
  and canonicals plus 1,612 aliases. It reported zero stable-key collisions,
  missing rows, foreign-key violations, or private-table imports. Installed
  totals exactly match 36,911 source records/observations, 22,894 canonicals,
  and 61,342 aliases; strict validation found zero invalid payloads, all 17,654
  existing leads remain, and candidate opportunity profiles, application
  profiles, decisions, and events remain zero;
- the second Zoho synchronization inserted 52 source records, observations, and
  canonicals plus 156 aliases, again with zero collisions, missing rows,
  foreign-key violations, or private-table imports. Installed totals exactly
  match 36,963 source records/observations, 22,946 canonicals, and 61,498 aliases;
  all 17,654 leads and all zero-valued private candidate/application tables are
  preserved;
- the Freshteam/rule-18 synchronization inserted 398 source records,
  observations, and canonicals plus 1,194 aliases. It reported zero stable-key
  collisions, missing rows, foreign-key violations, or private-table imports.
  The metadata follow-up then added 398 scan-time source observations, updated
  the same 398 canonicals, and added no duplicate canonicals or aliases.
  Installed totals exactly match 37,759 source records/observations, 23,344
  canonicals, and 62,692 aliases. The final strict installed audit found zero invalid
  payloads or forbidden public metadata, preserved all 17,654 leads, and left
  candidate opportunity profiles, application profiles, decisions, and events
  at zero;
- the Keka/rule-22 synchronization inserted 248 immutable source
  records/observations from two verified scans, 124 canonicals, and 421 aliases.
  It reported zero canonical/source/alias collisions, zero missing rows, zero
  foreign-key violations, and no private-table imports. Installed public totals
  exactly match 38,007 observations, 23,468 canonicals, and 63,113 aliases. The
  installed strict audit validates every payload, finds zero forbidden Keka
  metadata keys, preserves all 17,654 existing leads, and leaves candidate
  opportunity profiles, application profiles, decisions, and events at zero;
- the Keka native-portal/rule-23 synchronization then inserted 58 immutable
  source records/observations from two verified scans, 29 canonicals, and 94
  aliases. Installed totals exactly match the accepted artifact at 38,065
  observations, 23,497 canonicals, and 63,207 aliases, with zero collisions,
  missing rows, foreign-key violations, or private-table imports. The strict
  installed audit validates every payload, preserves all 17,654 existing leads,
  and leaves candidate opportunity profiles, application profiles, decisions,
  and events at zero;
- the Keka wave-three/rule-24 synchronization into the active Tauri/Roaming
  store inserted 104 immutable source records/observations from two verified
  scans, 52 canonicals, and 153 aliases. Installed totals exactly match 38,169
  observations, 23,549 canonicals, and 63,360 aliases, with zero collisions,
  missing rows, foreign-key violations, or private-table imports. The strict
  post-install audit validates every payload, preserves all 17,654 leads, and
  leaves candidate opportunity profiles, application profiles, decisions, and
  events at zero. The standalone installer now explicitly adopts an existing
  Tauri data root before resolving its default path; the Local development store
  was separately audited and preserves its 849 leads;
- the Quicko/Zoho/rule-26 synchronization inserted 2,456 immutable source
  records/observations from four successful provider cycles, 12 canonicals, and
  614 aliases into both the active Roaming store and the Local development
  store. Both installations exactly match 40,625 observations, 23,561
  canonicals, and 63,974 aliases with zero collisions, missing rows, foreign-key
  violations, or private-table imports. Strict post-install audits validate
  every payload, preserve all 17,654 Roaming leads and 849 Local leads, and
  leave candidate opportunity profiles, application profiles, decisions, and
  events at zero;
- the Aatmia/ECS ME/rule-27 synchronization inserted 340 immutable source
  records/observations from two repeat reads, 170 canonicals, and 510 aliases
  into both installed stores. Both exactly match 40,965 observations, 23,731
  canonicals, and 64,484 aliases with zero collisions, missing rows, foreign-key
  violations, or private-table imports. Strict audits preserve all 17,654
  Roaming leads and 849 Local leads and leave all candidate/application tables
  untouched;
- the Lever-enrichment/Weekday/rule-28 synchronization inserted 3,034 immutable
  source records/observations from two complete provider reads, 62 canonicals,
  and 1,639 aliases into both installed stores. Both exactly match 43,999
  observations, 23,793 canonicals, and 66,123 aliases. Strict audits report zero
  invalid payloads, forbidden metadata keys, orphan relationships, missing rows,
  foreign-key violations, or private-table imports, while preserving all 17,654
  Roaming leads and 849 Local leads. The installer also exposed seven safe title
  refreshes on unchanged employer/requisition identities. It now treats titles
  as freshness-gated mutable truth while continuing to fail closed on employer,
  canonical URL, source-record, and alias identity collisions;
- the final backend suite passes 1,802 tests with 14 environment-dependent
  skips and one upstream Starlette/httpx deprecation warning. The frontend
  remains 89/89, TypeScript typecheck passes, and the production build passes;
- the final escalated live web smoke exercised every desktop/mobile view against
  the installed database, wrote 41 screenshots, loaded the dashboard overview
  in 553 ms, and finished with zero browser-console errors and zero failures. It
  deliberately omitted `JHM_APP_DATA_DIR` and proved that the backend selected
  the Roaming/Tauri store and its existing ONNX model. The rule-28 rerun again
  wrote all 41 screenshots and persisted a machine-readable result containing
  zero console errors, zero failures, 17,654 preserved leads, and 79 currently
  verified/confirmed leads;
- the rule-29 public-index installer transactionally reconciled 90 obsolete
  installed canonical IDs through exact identity aliases, refreshed 12,690
  canonicals from newer lifecycle evidence, and installed matching public
  totals into both Roaming and Local stores. Both report zero missing rows,
  zero foreign-key violations, SQLite integrity `ok`, and no private-table
  imports. Strict installed audits validate all 59,655 source payloads and
  24,673 canonical payloads, preserve 17,654 Roaming leads and 849 Local leads,
  and leave candidate constraint profiles, application profiles, decisions,
  and events at zero;
- the rule-29 integration gate passes 1,806 backend tests, 89 frontend tests,
  TypeScript, frontend and
  website production builds, Rust check, and 5 Rust tests. Focused
  adapter/dedupe/storage/architecture coverage adds reordered-description,
  historical-arrival, malformed-title, stable-requisition, and installed-ID
  reconciliation cases. The 41-screen browser smoke reports zero console
  errors and zero failures;
- the rule-30 Zeqo synchronization inserted 6 immutable observations from the
  admitted read plus idempotence replay, 3 canonicals, and 9 aliases into both
  installed stores. Both stores exactly match 59,661 observations, 24,676
  canonicals, and 79,228 aliases with zero collisions, missing rows, foreign-key
  violations, or private-table imports. Strict audits preserve all 17,654
  Roaming leads and 849 Local leads and leave candidate/application tables
  untouched;
- the rule-30 whole-repository gate passes 1,815 backend tests with 14
  environment-dependent skips, 89 frontend tests, TypeScript, both production
  web builds, Rust check, and 5 Rust tests. The installed-data browser smoke
  wrote 41 desktop/mobile screenshots, loaded the dashboard API in 948 ms, and
  reported zero console errors and zero failures;
- the rule-31 synchronization installed 124 immutable observations from the
  admitted feeds and their metadata/idempotence replays, 61 net-new canonicals,
  and 195 aliases into both public stores. Each store now exactly matches
  59,785 observations, 24,737 canonicals, and 79,423 aliases with zero missing
  rows, identity collisions, foreign-key violations, or private-table imports.
  Strict installed audits preserve all 17,654 Roaming leads and 849 Local
  leads. Candidate profiles, application profiles, decisions, and events remain
  untouched, and both pre-install stores remain available as rollback files;
- the rule-31 whole-repository gate passes 1,820 backend tests with 14
  environment-dependent skips and one upstream Starlette/httpx deprecation
  warning, 89 frontend tests, TypeScript, frontend and website production
  builds, Rust check, and 5 Rust tests. A real installed-data browser smoke
  rendered the Opportunities inventory with 24,737 canonicals, 23,973 active
  roles, 59,785 observations, 273 free/direct targets, and 36 provider families
  plus 3 disabled paid experiments. It preserved 17,654 Roaming leads, emitted
  zero console warnings/errors, and correctly kept the candidate-specific queue
  empty until a real candidate supplies consent and constraints;
- the wave-14 synchronization installed 112 additional immutable observations,
  105 net-new canonicals, and 342 aliases into each installed store. Roaming and
  Local now exactly match 59,897 observations, 24,842 canonicals, and 79,765
  aliases with zero missing rows, orphan relationships, invalid payloads, or
  foreign-key violations. Strict installed audits preserve all 17,654 Roaming
  leads and 849 Local leads; no private candidate, application, decision, or
  event table was imported. Separate pre-install rollback backups were retained;
- the wave-14 whole-repository gate passes 1,824 backend tests with 14
  environment-dependent skips and one upstream Starlette/httpx deprecation
  warning, 89 frontend tests, TypeScript, frontend and website production
  builds, Rust check, and 5 Rust tests. The focused source, live-handoff,
  registry, applicability, and persistence suite passes 88 tests, including the
  disjoint-country and same-batch transitive-bridge regressions;
- the wave-16 synchronization installed 113 additional immutable observations,
  113 net-new canonicals, and 330 aliases into each installed store. Roaming and
  Local now exactly match 60,010 observations, 24,955 canonicals, and 80,095
  aliases with zero missing rows, collisions, foreign-key violations, or
  private-table imports. Strict installed audits preserve all 17,654 Roaming
  leads and 849 Local leads; candidate/application/decision/event tables remain
  untouched, and separate rollback backups were retained for both stores;
- the wave-16 whole-repository gate passes 1,824 backend tests with 14
  environment-dependent skips and one upstream Starlette/httpx deprecation
  warning, 89 frontend tests, TypeScript, frontend and website production
  builds, Rust check, and 5 Rust tests. The focused registry suite passes 88
  tests, both installed SQLite stores pass strict payload and quick-check
  validation, and live handoff coverage is 113/113;
- the AICTE wave-17 synchronization installed 132 immutable observations from
  the admitted feed and its date-enrichment replay, 66 net-new canonicals, and
  198 aliases into each installed store. Roaming and Local now exactly match
  60,142 observations, 25,021 canonicals, and 80,293 aliases with zero missing
  rows, collisions, foreign-key violations, or private-table imports. Strict
  installed audits preserve all 17,654 Roaming leads and 849 Local leads;
  candidate/application/decision/event/profile tables remain untouched;
- the AICTE wave-17 whole-repository gate passes 1,829 backend tests with 14
  environment-dependent skips and one upstream Starlette/httpx deprecation
  warning, 89 frontend tests, TypeScript, frontend and website production
  builds, Rust check, and 5 Rust tests. The focused source, registry,
  applicability, truth, and handoff suite passes 134 tests, and the live
  handoff audit passes 66/66;
- the direct-India wave-18 synchronization installed 154 immutable observations,
  148 net-new canonicals, and 457 aliases into each installed store. Roaming and
  Local now exactly match 60,296 observations, 25,169 canonicals, and 80,750
  aliases with zero missing rows, orphan relationships, invalid payloads,
  foreign-key violations, or private-table imports. Strict installed audits
  preserve all 17,654 Roaming leads and 849 Local leads; candidate, application,
  decision, event, and profile tables remain untouched. Separate pre-install
  rollback backups were retained for both stores;
- the wave-18 whole-repository gate passes 1,831 backend tests with 14
  environment-dependent skips and one upstream Starlette/httpx deprecation
  warning, 89 frontend tests, TypeScript, frontend and website production
  builds, Rust check, and 5 Rust tests. The focused ATS, registry,
  applicability, truth, and handoff suite passes 166 tests, Ruff passes for all
  changed Python files, and fresh live handoff coverage is 154/154;
- the wave-19 synchronization installed 344 immutable observations, 344 net-new
  canonicals, and 1,009 aliases into each installed store. Roaming and Local now
  exactly match 60,640 observations, 25,513 canonicals, and 81,759 aliases with
  zero missing rows, orphan relationships, invalid payloads, foreign-key
  violations, or private-table imports. Strict installed audits preserve all
  17,654 Roaming leads and 849 Local leads; candidate, application, decision,
  event, and profile tables remain untouched. Separate pre-install rollback
  backups were retained for both stores;
- the wave-19 whole-repository gate passes 1,836 backend tests with 14
  environment-dependent skips and one upstream Starlette/httpx deprecation
  warning, 89 frontend tests, TypeScript, frontend and website production
  builds, Rust check, and 5 Rust tests. The focused Rule-33 applicability,
  registry, and candidate-board audit suite passes 95 tests, Ruff and diff
  hygiene pass, and fresh first-party handoff coverage is 344/344;
- the wave-20 synchronization installed 70 immutable observations, 70 net-new
  canonicals, and 209 aliases into each installed store. Roaming and Local now
  exactly match 60,710 observations, 25,583 canonicals, and 81,968 aliases with
  zero collisions, missing rows, orphan relationships, invalid payloads,
  foreign-key violations, or private-table imports. Strict installed audits
  preserve all 17,654 Roaming leads and 849 Local leads; candidate, application,
  decision, event, and profile tables remain untouched. Separate rollback
  backups were retained for the rescore, refresh, and both installed stores;
- the first wave-20 full gate exposed that two new India-priority boards pushed
  BambooHR out of the bounded 120-target production slice. The registry now
  reserves one live anchor each for Rippling, Teamtailor, Pinpoint, Breezy, and
  BambooHR whenever a bounded scan is truncated, while retaining both wave-20
  boards. The repeated whole-repository gate passes 1,839 backend tests with 14
  environment-dependent skips and one upstream Starlette/httpx deprecation
  warning, 89 frontend tests, TypeScript, frontend and website production
  builds, Rust check, and 5 Rust tests. Ruff and targeted diff hygiene pass;
- the wave-22 synchronization installed 33 immutable observations, 33 net-new
  canonicals, and 95 aliases into each installed store. Both stores exactly
  match 60,796 observations, 25,669 canonicals, and 82,216 aliases and preserve
  their existing 17,654 and 849 leads. Independent installed-data readbacks
  validate all 33 Eightfold rows and every canonical/source payload with zero
  forbidden metadata keys. The whole backend gate passes 1,847 tests with 14
  environment-dependent skips and one upstream Starlette/httpx warning; 89
  frontend tests, the production frontend build, and 5 Rust tests pass. All
  Wave-22 Python files pass Ruff. A repository-wide Ruff sweep also surfaces 50
  unrelated pre-existing findings, which are not misreported as Wave-22
  regressions;
- the wave-23 synchronization installed 2 immutable observations, 2 net-new
  canonicals, and 6 aliases into each installed store. Both stores exactly
  match 60,798 observations, 25,671 canonicals, and 82,222 aliases and preserve
  their existing 17,654 and 849 leads. The full Rule-35 backend gate passes
  1,852 tests with 14 environment-dependent skips and one upstream
  Starlette/httpx warning; 89 frontend tests, the production frontend build,
  and 5 Rust tests pass. The 159-test focused workplace/iCIMS gate and all
  changed-file Ruff checks pass;
- the wave-24 synchronization installed 3 immutable observations, 3 net-new
  canonicals, and 9 aliases into each installed store. Both stores exactly
  match 60,801 observations, 25,674 canonicals, and 82,231 aliases and preserve
  their existing 17,654 and 849 leads. Independent artifact and installed
  readbacks validate all 3 Avature rows, all public payloads, publication dates,
  requisition identities, and apply URLs with zero forbidden metadata keys.
  The full backend gate passes 1,858 tests with 14 environment-dependent skips
  and one upstream Starlette/httpx warning; 89 frontend tests, the production
  frontend build, and 5 Rust tests pass. The 64-test ATS file includes the
  country-facet, exact-India fallback, hostile-host/path, rich-detail,
  same-host-apply, date-theme, target-dispatch, and pagination auto-heal cases;
  all changed-file Ruff checks pass;
- the valid pre-wave public-index rollback was SHA-256 verified after relocation
  to `<external-evidence>/full_market_index_before_rule31_aicte_wave17_2026-08-26.sqlite3`
  because the workspace volume filled during metadata replay. The separate
  pre-date-enrichment snapshot was also SHA-256 verified and relocated to the
  same temporary evidence directory, alongside the wave-18 pre-rescore,
  pre-refresh, and pre-install Roaming and Local rollback backups;
- the post-Zoho live web smoke exercised all desktop/mobile views and the real job
  detail drawer, wrote 23 screenshots, measured dashboard overview at 675 ms,
  and finished with zero browser-console errors and zero failures;
- the earlier rule-16 real-web smoke rendered 22,344 indexed canonicals, 21,576 verified-
  active roles, 761 unresolved statuses, 36,361 observations, 209 free/direct
  targets, and 32 provider families plus 3 disabled paid experiments. It also
  rendered the honest pilot state (0/5 consented candidates, 0 applications,
  0 interviews) and produced no browser console errors;
- that checkpoint's frontend test suite remained 89/89, TypeScript typecheck and production
  build pass, Ruff passes for all changed Python files, and ESLint reports zero
  errors (35 pre-existing warnings).

## Official-source exclusions from this audit cycle

- Flipkart's official careers page advertised 69 cards when inspected, but the
  cards were truncated static text with no requisition IDs, detail URLs, or
  apply links; its "Show More" handler was only a placeholder alert. It is not
  ingested until the official site exposes independently verifiable live jobs.
- Eternal/Zomato's official careers page currently says applications are
  accepted only through employee referrals and exposes no public requisition
  list. It is therefore not represented as an open, directly applicable job
  source.
- These are explicit coverage gaps, not silent successes. Neither employer is
  counted in live opportunity yield, and no third-party copy is presented as an
  official application path.

## Evidence artifacts

- `backend/evals/output/full_market_baseline_2026-08-25.json`
- `backend/evals/output/replacement_remote_delta_2026-08-25.json`
- `backend/evals/output/hn_hiring_delta_2026-08-25.json`
- `backend/evals/output/official_custom_delta_2026-08-25.json`
- `backend/evals/output/ibm_official_delta_2026-08-25.json`
- `backend/evals/output/ashby_location_repair_delta_2026-08-25.json`
- `backend/evals/output/aggregator_evidence_repair_delta_2026-08-25.json`
- `backend/evals/output/himalayas_targeted_delta_2026-08-25.json`
- `backend/evals/output/syndicated_reconciliation_delta_2026-08-25.json`
- `backend/evals/output/rule8_india_expansion_delta_2026-08-25.json`
- `backend/evals/output/rule8_workday_facet_repair_delta_2026-08-25.json`
- `backend/evals/output/official_giants_delta_2026-08-25.json`
- `backend/evals/output/official_google_qualcomm_delta_2026-08-25.json`
- `backend/evals/output/official_atlassian_razorpay_freshworks_delta_2026-08-25.json`
- `backend/evals/output/official_freshworks_full_detail_delta_2026-08-25.json`
- `backend/evals/output/official_freshworks_post_dedupe_delta_2026-08-25.json`
- `backend/evals/output/official_oracle_india_early_delta_v2_2026-08-25.json`
- `backend/evals/output/official_swiggy_india_cse_delta_2026-08-25.json`
- `backend/evals/output/official_dell_india_cse_delta_v2_2026-08-25.json`
- `backend/evals/output/official_visa_bosch_recovery_delta_2026-08-25.json`
- `backend/evals/output/official_visa_bosch_identity_validation_2026-08-25.json`
- `backend/evals/output/installed_public_index_preflight_2026-08-25.json`
- `backend/evals/output/public_index_install_scale_validation_2026-08-25.json`
- `backend/evals/output/installed_public_index_sync_2026-08-25.json`
- `backend/evals/output/current_feed_lifecycle_delta_2026-08-25.json`
- `backend/evals/output/himalayas_location_compaction_delta_2026-08-25.json`
- `backend/evals/output/corrected_public_index_preflight_2026-08-25.json`
- `backend/evals/output/installed_public_index_lifecycle_sync_2026-08-25.json`
- `backend/evals/output/ycombinator_startup_delta_2026-08-25.json`
- `backend/evals/output/ycombinator_country_normalization_delta_2026-08-25.json`
- `backend/evals/output/ycombinator_structured_metadata_delta_2026-08-25.json`
- `backend/evals/output/rule15_final_full_rescore_2026-08-25.json`
- `backend/evals/output/ycombinator_rule15_strict_audit_2026-08-25.json`
- `backend/evals/output/ycombinator_rule15_public_index_preflight_2026-08-25.json`
- `backend/evals/output/installed_ycombinator_rule15_sync_2026-08-25.json`
- `backend/evals/output/installed_ycombinator_rule15_strict_audit_2026-08-25.json`
- `backend/evals/output/installed_crm_before_ycombinator_rule15_2026-08-25.sqlite3`
- `backend/evals/output/targeted_direct_expansion_delta_2026-08-25.json`
- `backend/evals/output/rule15_service_lockin_full_rescore_2026-08-25.json`
- `backend/evals/output/final_market_index_strict_audit_2026-08-25.json`
- `backend/evals/output/final_market_index_preflight_2026-08-25.json`
- `backend/evals/output/installed_targeted_direct_expansion_sync_2026-08-25.json`
- `backend/evals/output/installed_final_market_index_strict_audit_2026-08-25.json`
- `backend/evals/output/installed_crm_before_targeted_direct_expansion_2026-08-25.sqlite3`
- `backend/evals/output/community_discovered_direct_boards_delta_2026-08-25.json`
- `backend/evals/output/workday_opaque_country_repair_delta_2026-08-25.json`
- `backend/evals/output/workday_generic_early_repair_delta_2026-08-25.json`
- `backend/evals/output/rule16_full_rescore_2026-08-25.json`
- `backend/evals/output/rule16_final_market_index_strict_audit_2026-08-25.json`
- `backend/evals/output/rule16_final_market_index_preflight_2026-08-25.json`
- `backend/evals/output/installed_rule16_direct_expansion_sync_2026-08-25.json`
- `backend/evals/output/installed_rule16_final_strict_audit_2026-08-25.json`
- `backend/evals/output/installed_crm_before_rule16_direct_expansion_2026-08-25.sqlite3`
- `backend/evals/output/zohorecruit_expansion_refresh_2026-08-25.json`
- `backend/evals/output/rule17_full_rescore_2026-08-25.json`
- `backend/evals/output/rule16_to_rule17_exact_diff_2026-08-25.json`
- `backend/evals/output/rule17_final_market_index_strict_audit_2026-08-25.json`
- `backend/evals/output/rule17_final_market_index_preflight_2026-08-25.json`
- `backend/evals/output/installed_rule17_zohorecruit_initial_sync_2026-08-25.json`
- `backend/evals/output/installed_rule17_final_hash_idempotent_sync_2026-08-25.json`
- `backend/evals/output/installed_rule17_zohorecruit_strict_audit_2026-08-25.json`
- `backend/evals/output/installed_crm_before_rule17_zohorecruit_2026-08-25.sqlite3`
- `backend/evals/output/zohorecruit_wave2_refresh_2026-08-25.json`
- `backend/evals/output/installed_rule17_zohorecruit_wave2_sync_2026-08-25.json`
- `backend/evals/output/installed_crm_before_rule17_zohorecruit_wave2_2026-08-25.sqlite3`
- `backend/evals/output/freshteam_expansion_refresh_2026-08-25.json`
- `backend/evals/output/rule18_full_rescore_2026-08-25.json`
- `backend/evals/output/rule17_to_rule18_exact_diff_2026-08-25.json`
- `backend/evals/output/rule18_freshteam_strict_audit_2026-08-25.json`
- `backend/evals/output/rule18_freshteam_final_market_index_preflight_2026-08-25.json`
- `backend/evals/output/installed_rule18_freshteam_sync_2026-08-25.json`
- `backend/evals/output/installed_rule18_freshteam_strict_audit_2026-08-25.json`
- `backend/evals/output/full_market_index_before_freshteam_2026-08-25.sqlite3`
- `backend/evals/output/full_market_index_before_rule18_2026-08-25.sqlite3`
- `backend/evals/output/installed_crm_before_rule18_freshteam_2026-08-25.sqlite3`
- `backend/evals/output/freshteam_metadata_refresh_2026-08-25.json`
- `backend/evals/output/rule18_freshteam_metadata_strict_audit_2026-08-25.json`
- `backend/evals/output/rule18_freshteam_metadata_preflight_2026-08-25.json`
- `backend/evals/output/installed_freshteam_metadata_refresh_sync_2026-08-25.json`
- `backend/evals/output/installed_freshteam_metadata_refresh_strict_audit_2026-08-25.json`
- `backend/evals/output/full_market_index_before_freshteam_metadata_refresh_2026-08-25.sqlite3`
- `backend/evals/output/installed_crm_before_freshteam_metadata_refresh_2026-08-25.sqlite3`
- `backend/evals/output/keka_expansion_refresh_2026-08-25.json`
- `backend/evals/output/keka_rule19_metadata_refresh_2026-08-25.json`
- `backend/evals/output/rule22_full_rescore_2026-08-25.json`
- `backend/evals/output/rule18_to_rule22_exact_diff_2026-08-25.json`
- `backend/evals/output/rule22_keka_strict_audit_2026-08-25.json`
- `backend/evals/output/rule22_keka_preflight_2026-08-25.json`
- `backend/evals/output/rule22_keka_metadata_completeness_2026-08-25.json`
- `backend/evals/output/rule22_keka_live_apply_audit_2026-08-25.json`
- `backend/evals/output/installed_rule22_keka_sync_2026-08-25.json`
- `backend/evals/output/installed_rule22_keka_strict_audit_2026-08-25.json`
- `backend/evals/output/keka_native_wave2_refresh_2026-08-25.json`
- `backend/evals/output/keka_native_wave2_rule23_refresh_2026-08-25.json`
- `backend/evals/output/rule23_full_rescore_2026-08-25.json`
- `backend/evals/output/rule22_to_rule23_exact_diff_2026-08-25.json`
- `backend/evals/output/rule23_keka_native_wave2_live_apply_audit_2026-08-25.json`
- `backend/evals/output/rule23_keka_strict_audit_2026-08-25.json`
- `backend/evals/output/rule23_keka_native_wave2_preflight_2026-08-25.json`
- `backend/evals/output/rule23_keka_metadata_completeness_2026-08-25.json`
- `backend/evals/output/installed_rule23_keka_native_wave2_sync_2026-08-25.json`
- `backend/evals/output/installed_rule23_keka_native_wave2_strict_audit_2026-08-25.json`
- `backend/evals/output/keka_wave3_refresh_2026-08-25.json`
- `backend/evals/output/keka_wave3_rule24_refresh_2026-08-25.json`
- `backend/evals/output/rule24_full_rescore_2026-08-25.json`
- `backend/evals/output/rule23_to_rule24_exact_diff_2026-08-25.json`
- `backend/evals/output/rule24_keka_wave3_live_apply_audit_2026-08-25.json`
- `backend/evals/output/rule24_keka_wave3_strict_audit_2026-08-25.json`
- `backend/evals/output/rule24_keka_wave3_preflight_2026-08-25.json`
- `backend/evals/output/installed_rule24_keka_wave3_sync_2026-08-25.json`
- `backend/evals/output/installed_rule24_keka_wave3_local_strict_audit_2026-08-26.json`
- `backend/evals/output/installed_rule24_keka_wave3_roaming_sync_2026-08-26.json`
- `backend/evals/output/installed_rule24_keka_wave3_roaming_strict_audit_2026-08-26.json`
- `backend/evals/output/zohorecruit_workplace_quicko_wave4_refresh_2026-08-26.json`
- `backend/evals/output/zohorecruit_wave4_repeat_refresh_2026-08-26.json`
- `backend/evals/output/rule25_rescore_2026-08-26.json`
- `backend/evals/output/rule24_to_rule25_exact_diff_2026-08-26.json`
- `backend/evals/output/zohorecruit_enrichment_rule25_wave5_refresh_2026-08-26.json`
- `backend/evals/output/zohorecruit_enrichment_rule25_wave5_repeat_2026-08-26.json`
- `backend/evals/output/rule26_rescore_2026-08-26.json`
- `backend/evals/output/rule25_to_rule26_exact_diff_2026-08-26.json`
- `backend/evals/output/rule26_zohorecruit_quicko_wave4_strict_audit_2026-08-26.json`
- `backend/evals/output/rule26_quicko_wave4_live_apply_audit_2026-08-26.json`
- `backend/evals/output/rule26_quicko_wave4_install_preflight_2026-08-26.json`
- `backend/evals/output/installed_rule26_quicko_wave4_roaming_sync_2026-08-26.json`
- `backend/evals/output/installed_rule26_quicko_wave4_roaming_strict_audit_2026-08-26.json`
- `backend/evals/output/installed_rule26_quicko_wave4_local_sync_2026-08-26.json`
- `backend/evals/output/installed_rule26_quicko_wave4_local_strict_audit_2026-08-26.json`
- `backend/evals/output/rule27_rescore_2026-08-26.json`
- `backend/evals/output/rule26_to_rule27_exact_diff_2026-08-26.json`
- `backend/evals/output/aatmia_ecsme_rule27_wave6_refresh_2026-08-26.json`
- `backend/evals/output/aatmia_ecsme_rule27_wave6_repeat_2026-08-26.json`
- `backend/evals/output/rule27_aatmia_ecsme_wave6_live_apply_audit_2026-08-26.json`
- `backend/evals/output/rule27_aatmia_ecsme_wave6_freshteam_strict_audit_2026-08-26.json`
- `backend/evals/output/rule27_aatmia_ecsme_wave6_zohorecruit_strict_audit_2026-08-26.json`
- `backend/evals/output/rule27_aatmia_ecsme_wave6_install_preflight_2026-08-26.json`
- `backend/evals/output/installed_rule27_aatmia_ecsme_wave6_roaming_sync_2026-08-26.json`
- `backend/evals/output/installed_rule27_aatmia_ecsme_wave6_roaming_strict_audit_2026-08-26.json`
- `backend/evals/output/installed_rule27_aatmia_ecsme_wave6_local_sync_2026-08-26.json`
- `backend/evals/output/installed_rule27_aatmia_ecsme_wave6_local_strict_audit_2026-08-26.json`
- `backend/evals/output/full_market_index_before_aatmia_ecsme_rule27_wave6_2026-08-26.sqlite3`
- `backend/evals/output/rule28_rescore_2026-08-26.json`
- `backend/evals/output/rule27_to_rule28_exact_diff_2026-08-26.json`
- `backend/evals/output/lever_enrichment_weekday_rule28_wave7_refresh_2026-08-26.json`
- `backend/evals/output/lever_enrichment_weekday_rule28_wave7_repeat_2026-08-26.json`
- `backend/evals/output/lever_enrichment_weekday_rule28_wave7_audit_2026-08-26.json`
- `backend/evals/output/rule28_lever_weekday_wave7_live_apply_audit_2026-08-26.json`
- `backend/evals/output/lever_enrichment_weekday_rule28_wave7_preflight_2026-08-26.json`
- `backend/evals/output/installed_rule28_lever_weekday_wave7_roaming_2026-08-26.json`
- `backend/evals/output/installed_rule28_lever_weekday_wave7_roaming_audit_2026-08-26.json`
- `backend/evals/output/installed_rule28_lever_weekday_wave7_local_2026-08-26.json`
- `backend/evals/output/installed_rule28_lever_weekday_wave7_local_audit_2026-08-26.json`
- `backend/evals/output/backend_rule28_lever_weekday_wave7_pytest_2026-08-26.xml`
- `backend/evals/output/full_market_index_before_lever_enrichment_weekday_rule28_wave7_2026-08-26.sqlite3`
- `backend/evals/output/installed_crm_before_rule28_lever_weekday_wave7_roaming_2026-08-26.sqlite3`
- `backend/evals/output/installed_crm_before_rule28_lever_weekday_wave7_local_2026-08-26.sqlite3`
- `backend/evals/output/india_ai_boards_probe_rule29_wave8_2026-08-26.json`
- `backend/evals/output/india_positive_yield_boards_rule29_wave8_candidate_audit_2026-08-26.json`
- `backend/evals/output/rule28_to_rule29_exact_diff_2026-08-26.json`
- `backend/evals/output/rule29_india_boards_wave8_live_apply_audit_2026-08-26.json`
- `backend/evals/output/rule29_india_boards_wave8_refresh_2026-08-26.json`
- `backend/evals/output/rule29_india_boards_wave8_dedupe_reconciliation_2026-08-26.json`
- `backend/evals/output/rule29_india_boards_wave8_idempotence_replay_2026-08-26.json`
- `backend/evals/output/rule29_greenhouse_ashby_full_enrichment_2026-08-26.json`
- `backend/evals/output/rule29_composio_zero_error_replay_2026-08-26.json`
- `backend/evals/output/rule29_full_market_index_final_audit_2026-08-26.json`
- `backend/evals/output/rule29_final_install_preflight_2026-08-26.json`
- `backend/evals/output/rule29_install_roaming_2026-08-26.json`
- `backend/evals/output/rule29_install_local_2026-08-26.json`
- `backend/evals/output/rule29_installed_roaming_strict_audit_2026-08-26.json`
- `backend/evals/output/rule29_installed_local_strict_audit_2026-08-26.json`
- `backend/evals/output/full_market_index_before_rule29_sde_swe_wave8_2026-08-26.sqlite3`
- `backend/evals/output/full_market_index_before_rule29_greenhouse_ashby_enrichment_2026-08-26.sqlite3`
- `backend/evals/output/installed_crm_before_rule29_extensive_internship_roaming_2026-08-26.sqlite3`
- `backend/evals/output/installed_crm_before_rule29_extensive_internship_local_2026-08-26.sqlite3`
- `backend/evals/output/rule29_browserstack_workday_candidate_audit_2026-08-26.json`
- `backend/evals/output/rule30_zeqo_early_career_candidate_audit_2026-08-26.json`
- `backend/evals/output/rule30_full_index_rescore_final_2026-08-26.json`
- `backend/evals/output/rule29_to_rule30_exact_diff_final_2026-08-26.json`
- `backend/evals/output/rule30_zeqo_wave9_refresh_2026-08-26.json`
- `backend/evals/output/rule30_zeqo_wave9_repeat_refresh_2026-08-26.json`
- `backend/evals/output/rule30_zeqo_live_handoff_audit_2026-08-26.json`
- `backend/evals/output/rule30_zeqo_strict_audit_2026-08-26.json`
- `backend/evals/output/rule30_full_market_index_strict_audit_2026-08-26.json`
- `backend/evals/output/rule30_final_install_preflight_2026-08-26.json`
- `backend/evals/output/rule30_install_roaming_2026-08-26.json`
- `backend/evals/output/rule30_install_local_2026-08-26.json`
- `backend/evals/output/rule30_installed_roaming_strict_audit_2026-08-26.json`
- `backend/evals/output/rule30_installed_local_strict_audit_2026-08-26.json`
- `backend/evals/output/full_market_index_before_rule30_mixed_technical_titles_2026-08-26.sqlite3`
- `backend/evals/output/installed_crm_before_rule30_zeqo_roaming_2026-08-26.sqlite3`
- `backend/evals/output/installed_crm_before_rule30_zeqo_local_2026-08-26.sqlite3`
- `backend/evals/output/rule31_candidate_boards_wave10_audit_2026-08-26.json`
- `backend/evals/output/rule31_candidate_boards_workday_wave11_audit_2026-08-26.json`
- `backend/evals/output/rule31_portcast_candidate_audit_2026-08-26.json`
- `backend/evals/output/rule31_positive_yield_wave10_11_refresh_2026-08-26.json`
- `backend/evals/output/rule31_workday_v2_metadata_replay_2026-08-26.json`
- `backend/evals/output/rule31_portcast_jumio_idempotence_replay_2026-08-26.json`
- `backend/evals/output/rule31_portcast_live_handoff_audit_2026-08-26.json`
- `backend/evals/output/rule31_jumio_live_handoff_audit_2026-08-26.json`
- `backend/evals/output/rule31_workday_wave11_live_handoff_audit_v3_2026-08-26.json`
- `backend/evals/output/rule31_full_market_index_strict_audit_2026-08-26.json`
- `backend/evals/output/rule31_workday_v2_strict_audit_2026-08-26.json`
- `backend/evals/output/rule31_final_install_preflight_2026-08-26.json`
- `backend/evals/output/rule31_install_roaming_2026-08-26.json`
- `backend/evals/output/rule31_install_local_2026-08-26.json`
- `backend/evals/output/rule31_installed_roaming_strict_audit_2026-08-26.json`
- `backend/evals/output/rule31_installed_local_strict_audit_2026-08-26.json`
- `backend/evals/output/rule31_installed_browser_smoke_2026-08-26.json`
- `backend/evals/output/full_market_index_before_rule31_wave10_11_2026-08-26.sqlite3`
- `backend/evals/output/installed_crm_before_rule31_roaming_2026-08-26.sqlite3`
- `backend/evals/output/installed_crm_before_rule31_local_2026-08-26.sqlite3`
- `backend/evals/output/rule31_candidate_boards_wave12_audit_2026-08-26.json`
- `backend/evals/output/rule31_altimate_wave13_candidate_audit_2026-08-26.json`
- `backend/evals/output/rule31_smartrecruiters_wave14_candidate_audit_2026-08-26.json`
- `backend/evals/output/rule31_positive_yield_wave12_14_refresh_v2_2026-08-26.json`
- `backend/evals/output/rule31_wave11_to_wave14_exact_diff_v2_2026-08-26.json`
- `backend/evals/output/rule31_drivetrain_live_handoff_audit_v2_2026-08-26.json`
- `backend/evals/output/rule31_altimate_live_handoff_audit_v3_2026-08-26.json`
- `backend/evals/output/rule31_smartrecruiters_wave14_live_handoff_audit_v3_2026-08-26.json`
- `backend/evals/output/rule31_wave14_full_market_index_strict_audit_v2_2026-08-26.json`
- `backend/evals/output/rule31_wave14_ashby_strict_audit_v2_2026-08-26.json`
- `backend/evals/output/rule31_wave14_smartrecruiters_strict_audit_v2_2026-08-26.json`
- `backend/evals/output/rule31_wave14_final_install_preflight_2026-08-26.json`
- `backend/evals/output/rule31_wave14_install_roaming_2026-08-26.json`
- `backend/evals/output/rule31_wave14_install_local_2026-08-26.json`
- `backend/evals/output/rule31_wave14_installed_roaming_strict_audit_2026-08-26.json`
- `backend/evals/output/rule31_wave14_installed_local_strict_audit_2026-08-26.json`
- `backend/evals/output/full_market_index_before_rule31_wave12_14_2026-08-26.sqlite3`
- `backend/evals/output/installed_crm_before_rule31_wave14_roaming_2026-08-26.sqlite3`
- `backend/evals/output/installed_crm_before_rule31_wave14_local_2026-08-26.sqlite3`
- `backend/evals/output/rule31_candidate_boards_wave15_audit_2026-08-26.json`
- `backend/evals/output/rule31_candidate_boards_workday_wave16_audit_2026-08-26.json`
- `backend/evals/output/rule31_positive_yield_wave15_16_refresh_2026-08-26.json`
- `backend/evals/output/rule31_wave14_to_wave16_exact_diff_2026-08-26.json`
- `backend/evals/output/rule31_wave15_greenhouse_live_handoff_audit_2026-08-26.json`
- `backend/evals/output/rule31_wave16_workday_live_handoff_audit_2026-08-26.json`
- `backend/evals/output/rule31_wave16_full_market_index_strict_audit_2026-08-26.json`
- `backend/evals/output/rule31_wave16_greenhouse_strict_audit_2026-08-26.json`
- `backend/evals/output/rule31_wave16_workday_strict_audit_2026-08-26.json`
- `backend/evals/output/rule31_wave16_install_preflight_2026-08-26.json`
- `backend/evals/output/rule31_wave16_install_roaming_2026-08-26.json`
- `backend/evals/output/rule31_wave16_install_local_2026-08-26.json`
- `backend/evals/output/rule31_wave16_installed_roaming_strict_audit_2026-08-26.json`
- `backend/evals/output/rule31_wave16_installed_local_strict_audit_2026-08-26.json`
- `backend/evals/output/full_market_index_before_rule31_wave15_16_2026-08-26.sqlite3`
- `backend/evals/output/installed_crm_before_rule31_wave16_roaming_2026-08-26.sqlite3`
- `backend/evals/output/installed_crm_before_rule31_wave16_local_2026-08-26.sqlite3`
- `backend/evals/output/rule31_degree_title_full_rescore_2026-08-26.json`
- `backend/evals/output/rule30_to_rule31_degree_title_exact_diff_2026-08-26.json`
- `backend/evals/output/full_market_index_before_rule31_degree_title_2026-08-26.sqlite3`
- `backend/evals/output/rule31_aicte_wave17_candidate_audit_v2_2026-08-26.json`
- `backend/evals/output/rule31_aicte_wave17_refresh_2026-08-26.json`
- `backend/evals/output/rule31_wave16_to_aicte_wave17_exact_diff_2026-08-26.json`
- `backend/evals/output/rule31_aicte_wave17_datetime_enrichment_refresh_2026-08-26.json`
- `backend/evals/output/rule31_aicte_wave17_live_handoff_audit_v3_2026-08-26.json`
- `backend/evals/output/rule31_aicte_wave17_provider_strict_audit_v2_2026-08-26.json`
- `backend/evals/output/rule31_aicte_wave17_full_market_strict_audit_v2_2026-08-26.json`
- `backend/evals/output/rule31_aicte_wave17_install_preflight_2026-08-26.json`
- `backend/evals/output/rule31_aicte_wave17_install_roaming_2026-08-26.json`
- `backend/evals/output/rule31_aicte_wave17_install_local_2026-08-26.json`
- `backend/evals/output/rule31_aicte_wave17_installed_roaming_strict_audit_2026-08-26.json`
- `backend/evals/output/rule31_aicte_wave17_installed_local_strict_audit_2026-08-26.json`
- `<external-evidence>/full_market_index_before_rule31_aicte_datetime_enrichment_2026-08-26.sqlite3`
- `backend/evals/output/rule32_batch_title_full_rescore_2026-08-26.json`
- `backend/evals/output/rule31_to_rule32_batch_title_exact_diff_2026-08-26.json`
- `backend/evals/output/rule32_direct_india_wave18_candidate_audit_v3_2026-08-26.json`
- `backend/evals/output/rule32_direct_india_wave18_corrected_refresh_2026-08-26.json`
- `backend/evals/output/rule32_wave17_to_direct_india_wave18_exact_diff_v2_2026-08-26.json`
- `backend/evals/output/rule32_mactores_wave18_live_handoff_audit_2026-08-26.json`
- `backend/evals/output/rule32_zohorecruit_wave18_live_handoff_audit_v2_2026-08-26.json`
- `backend/evals/output/rule32_lever_wave18_strict_audit_2026-08-26.json`
- `backend/evals/output/rule32_zohorecruit_wave18_strict_audit_2026-08-26.json`
- `backend/evals/output/rule32_wave18_full_market_strict_audit_2026-08-26.json`
- `backend/evals/output/rule32_wave18_install_preflight_2026-08-26.json`
- `backend/evals/output/rule32_wave18_install_roaming_2026-08-26.json`
- `backend/evals/output/rule32_wave18_install_local_2026-08-26.json`
- `backend/evals/output/rule32_wave18_installed_roaming_strict_audit_2026-08-26.json`
- `backend/evals/output/rule32_wave18_installed_local_strict_audit_2026-08-26.json`
- `backend/evals/output/rule32_wave19_candidate_board_audit_v3_2026-08-26.json`
- `backend/evals/output/rule32_wave19_candidate_board_audit_v4_2026-08-26.json`
- `backend/evals/output/rule33_wave19_candidate_board_audit_v5_2026-08-26.json`
- `backend/evals/output/rule33_taxonomy_full_rescore_2026-08-26.json`
- `backend/evals/output/rule32_to_rule33_taxonomy_exact_diff_2026-08-26.json`
- `backend/evals/output/rule33_wave19_refresh_2026-08-26.json`
- `backend/evals/output/rule33_wave18_to_wave19_exact_diff_2026-08-26.json`
- `backend/evals/output/rule33_wave19_ashby_live_handoff_audit_2026-08-26.json`
- `backend/evals/output/rule33_wave19_zohorecruit_live_handoff_audit_2026-08-26.json`
- `backend/evals/output/rule33_wave19_ashby_strict_audit_2026-08-26.json`
- `backend/evals/output/rule33_wave19_zohorecruit_strict_audit_2026-08-26.json`
- `backend/evals/output/rule33_wave19_full_market_strict_audit_2026-08-26.json`
- `backend/evals/output/rule33_wave19_install_preflight_2026-08-26.json`
- `backend/evals/output/rule33_wave19_install_roaming_2026-08-26.json`
- `backend/evals/output/rule33_wave19_install_local_2026-08-26.json`
- `backend/evals/output/rule33_wave19_installed_roaming_strict_audit_2026-08-26.json`
- `backend/evals/output/rule33_wave19_installed_local_strict_audit_2026-08-26.json`
- `backend/evals/output/rule33_wave20_candidate_board_audit_v3_2026-08-26.json`
- `backend/evals/output/rule34_wave20_candidate_board_audit_v4_2026-08-26.json`
- `backend/evals/output/rule34_safety_full_rescore_2026-08-26.json`
- `backend/evals/output/rule33_to_rule34_safety_exact_diff_2026-08-26.json`
- `backend/evals/output/rule34_wave20_refresh_2026-08-26.json`
- `backend/evals/output/rule34_wave19_to_wave20_exact_diff_2026-08-26.json`
- `backend/evals/output/rule34_wave20_embarkgcc_live_handoff_audit_2026-08-26.json`
- `backend/evals/output/rule34_wave20_brainwonders_live_handoff_audit_2026-08-26.json`
- `backend/evals/output/rule34_wave20_smartrecruiters_strict_audit_2026-08-26.json`
- `backend/evals/output/rule34_wave20_zohorecruit_strict_audit_2026-08-26.json`
- `backend/evals/output/rule34_wave20_full_market_strict_audit_2026-08-26.json`
- `backend/evals/output/rule34_wave20_install_preflight_2026-08-26.json`
- `backend/evals/output/rule34_wave20_install_roaming_2026-08-26.json`
- `backend/evals/output/rule34_wave20_install_local_2026-08-26.json`
- `backend/evals/output/rule34_wave20_installed_roaming_strict_audit_2026-08-26.json`
- `backend/evals/output/rule34_wave20_installed_local_strict_audit_2026-08-26.json`
- `backend/evals/output/wave21_oraclehcm_candidate_audit_2026-08-26.json`
- `backend/evals/output/wave21_oraclehcm_refresh_2026-08-26.json`
- `backend/evals/output/wave21_oraclehcm_strict_audit_2026-08-26.json`
- `backend/evals/output/wave21_full_market_strict_audit_2026-08-26.json`
- `backend/evals/output/wave21_install_preflight_2026-08-26.json`
- `backend/evals/output/wave21_install_roaming_2026-08-26.json`
- `backend/evals/output/wave21_install_local_2026-08-26.json`
- `backend/evals/output/wave21_installed_roaming_strict_audit_2026-08-26.json`
- `backend/evals/output/wave21_installed_local_strict_audit_2026-08-26.json`
- `<external-evidence>/full_market_index_before_wave21_oraclehcm_2026-08-26.sqlite3`
- `<external-evidence>/installed_crm_before_wave21_oraclehcm_roaming_2026-08-26.sqlite3`
- `<external-evidence>/installed_crm_before_wave21_oraclehcm_local_2026-08-26.sqlite3`
- `backend/evals/output/wave22_eightfold_micron_candidate_audit_2026-08-26.json`
- `backend/evals/output/wave22_eightfold_candidate_tenant_audit_2026-08-26.json`
- `backend/evals/output/wave22_eightfold_refresh_2026-08-26.json`
- `backend/evals/output/wave22_eightfold_strict_audit_2026-08-26.json`
- `backend/evals/output/full_market_index_strict_audit_after_wave22_2026-08-26.json`
- `backend/evals/output/wave22_eightfold_preflight_2026-08-26.json`
- `backend/evals/output/wave22_install_roaming_2026-08-26.json`
- `backend/evals/output/wave22_install_local_2026-08-26.json`
- `backend/evals/output/wave22_installed_roaming_eightfold_audit_2026-08-26.json`
- `backend/evals/output/wave22_installed_local_eightfold_audit_2026-08-26.json`
- `<external-evidence>/full_market_index_before_wave22_eightfold_2026-08-26.sqlite3`
- `<external-evidence>/installed_crm_before_wave22_eightfold_roaming_2026-08-26.sqlite3`
- `<external-evidence>/installed_crm_before_wave22_eightfold_local_2026-08-26.sqlite3`
- `backend/evals/output/wave23_icims_candidate_audit_2026-08-26.json`
- `backend/evals/output/wave23_icims_candidate_audit_v2_2026-08-26.json`
- `backend/evals/output/wave23_icims_candidate_cohort_audit_v2_2026-08-26.json`
- `backend/evals/output/wave23_icims_candidate_cohort_audit_rule35_2026-08-26.json`
- `backend/evals/output/rule35_workplace_full_rescore_final_2026-08-26.json`
- `backend/evals/output/rule34_to_rule35_workplace_exact_diff_final_2026-08-26.json`
- `backend/evals/output/wave23_icims_refresh_2026-08-26.json`
- `backend/evals/output/wave23_icims_strict_audit_2026-08-26.json`
- `backend/evals/output/wave23_icims_preflight_2026-08-26.json`
- `backend/evals/output/wave23_install_roaming_2026-08-26.json`
- `backend/evals/output/wave23_install_local_2026-08-26.json`
- `backend/evals/output/wave23_installed_roaming_icims_audit_2026-08-26.json`
- `backend/evals/output/wave23_installed_local_icims_audit_2026-08-26.json`
- `backend/evals/output/wave24_avature_candidate_cohort_audit_rule35_2026-08-26.json`
- `backend/evals/output/wave24_avature_refresh_2026-08-26.json`
- `backend/evals/output/wave24_avature_strict_audit_2026-08-26.json`
- `backend/evals/output/wave24_full_market_strict_audit_2026-08-26.json`
- `backend/evals/output/wave24_avature_preflight_2026-08-26.json`
- `backend/evals/output/wave24_install_roaming_2026-08-26.json`
- `backend/evals/output/wave24_install_local_2026-08-26.json`
- `backend/evals/output/wave24_installed_roaming_avature_audit_2026-08-26.json`
- `backend/evals/output/wave24_installed_local_avature_audit_2026-08-26.json`
- `backend/evals/output/backend_wave24_avature_pytest_2026-08-26.xml`
- `backend/evals/output/wave25_jobvite_candidate_cohort_audit_rule35_2026-08-26.json`
- `backend/evals/output/wave25_jobvite_refresh_2026-08-26.json`
- `backend/evals/output/wave25_jobvite_strict_audit_2026-08-26.json`
- `backend/evals/output/wave25_full_market_strict_audit_2026-08-26.json`
- `backend/evals/output/wave25_jobvite_preflight_2026-08-26.json`
- `backend/evals/output/wave25_install_roaming_2026-08-26.json`
- `backend/evals/output/wave25_install_local_2026-08-26.json`
- `backend/evals/output/wave25_installed_roaming_jobvite_audit_2026-08-26.json`
- `backend/evals/output/wave25_installed_local_jobvite_audit_2026-08-26.json`
- `backend/evals/output/backend_wave25_jobvite_pytest_2026-08-26.xml`
- `backend/evals/output/wave26_successfactors_candidate_cohort_audit_rule35_2026-08-26.json`
- `backend/evals/output/wave26_successfactors_sap_candidate_cohort_audit_rule35_2026-08-26.json`
- `backend/evals/output/wave26_successfactors_tetrapak_candidate_cohort_audit_rule35_2026-08-26.json`
- `backend/evals/output/wave27_jibe_amd_candidate_cohort_audit_rule35_2026-08-26.json`
- `backend/evals/output/wave27_jibe_refresh_2026-08-26.json`
- `backend/evals/output/wave27_jibe_rule35_rescore_2026-08-26.json`
- `backend/evals/output/wave27_jibe_strict_audit_2026-08-26.json`
- `backend/evals/output/wave27_full_market_strict_audit_2026-08-26.json`
- `backend/evals/output/wave27_jibe_preflight_2026-08-26.json`
- `backend/evals/output/wave27_install_roaming_2026-08-26.json`
- `backend/evals/output/wave27_install_local_2026-08-26.json`
- `backend/evals/output/wave27_installed_roaming_jibe_audit_2026-08-26.json`
- `backend/evals/output/wave27_installed_local_jibe_audit_2026-08-26.json`
- `backend/evals/output/backend_wave27_jibe_pytest_2026-08-26.xml`
- `D:\JustHireMe-evidence\full_market_index_before_wave27_jibe_2026-08-26.sqlite3`
- `D:\JustHireMe-evidence\full_market_index_refresh_backup_wave27_jibe_2026-08-26.sqlite3`
- `D:\JustHireMe-evidence\full_market_index_before_wave27_rule35_rescore_2026-08-26.sqlite3`
- `D:\JustHireMe-evidence\installed_crm_before_wave27_jibe_roaming_2026-08-26.sqlite3`
- `D:\JustHireMe-evidence\installed_crm_before_wave27_jibe_local_2026-08-26.sqlite3`
- `D:\JustHireMe-evidence\full_market_index_before_wave25_jobvite_2026-08-26.sqlite3`
- `D:\JustHireMe-evidence\installed_crm_before_wave25_jobvite_roaming_2026-08-26.sqlite3`
- `D:\JustHireMe-evidence\installed_crm_before_wave25_jobvite_local_2026-08-26.sqlite3`
- `<external-evidence>/full_market_index_before_wave24_avature_2026-08-26.sqlite3`
- `D:\JustHireMe-evidence\installed_crm_before_wave24_avature_roaming_2026-08-26.sqlite3`
- `D:\JustHireMe-evidence\installed_crm_before_wave24_avature_local_2026-08-26.sqlite3`
- `<external-evidence>/full_market_index_before_rule35_workplace_retry_2026-08-26.sqlite3`
- `<external-evidence>/full_market_index_before_wave23_icims_2026-08-26.sqlite3`
- `<external-evidence>/installed_crm_before_wave23_icims_roaming_2026-08-26.sqlite3`
- `<external-evidence>/installed_crm_before_wave23_icims_local_2026-08-26.sqlite3`
- `<external-evidence>/full_market_index_before_rule31_degree_title_2026-08-26.sqlite3`
- `.smoke-web-ui/smoke-results.json`
- `backend/evals/output/full_market_index_before_keka_2026-08-25.sqlite3`
- `backend/evals/output/full_market_index_before_rule22_2026-08-25.sqlite3`
- `backend/evals/output/installed_crm_before_rule22_keka_2026-08-25.sqlite3`
- `backend/evals/output/installed_crm_before_public_index_2026-08-25.sqlite3`
- `backend/evals/output/installed_crm_before_current_feed_lifecycle_2026-08-25.sqlite3`
- `backend/evals/output/full_market_index_2026-08-25.sqlite3`

Generated SQLite and report outputs are local evidence artifacts and are not
intended for source control.

## Remaining outcome gates

1. Obtain explicit consent and application profiles for the five friends;
   synthetic profiles must not be used to submit applications.
2. Configure only the paid providers whose small, capped experiments show
   positive net-new eligible yield.
3. Continue reconciling syndicated candidates only above the proven
   cross-source employer/title and 97% substantive-description threshold;
   prefer a visible duplicate over an unsafe false merge.
4. Track applications through started, submitted, screening, interview,
   offer, rejection, and stale states. Coverage is an input; interviews per
   consented candidate are the actual success metric.
5. Continue adding compliant custom-careers adapters only where stable public
   interfaces permit it. HashiCorp now redirects into IBM; IBM, Deliveroo,
   Starling, DoorDash, Amazon, Google, Microsoft, and Qualcomm are recovered
   through their current official paths.
