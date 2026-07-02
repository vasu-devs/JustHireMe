# Contributing to JustHireMe

Thank you for helping build JustHireMe.

JustHireMe is a local-first OSS job intelligence workbench. The goal is not to build a spammy auto-apply machine. The goal is to help users find better jobs, understand fit, and generate stronger application material while keeping their data local.

## Project Scope

The core OSS scope is:

- scraping job leads from reliable sources
- filtering low-quality leads
- ranking candidate/job fit
- using graph and vector data for profile-aware matching
- generating tailored resume, cover letter, and outreach drafts
- maintaining a local-first desktop experience

Experimental scope:

- browser automation
- auto-apply
- form reading/filling

Automation code can be improved, but it should not dominate the main product experience or public docs.

## Code Of Conduct

Contributors are expected to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). In short:

- Be respectful.
- Assume good intent.
- Keep feedback specific and actionable.
- Do not shame people for beginner mistakes.
- Do not pressure maintainers for unpaid urgency.
- Do not post private user data, secrets, cookies, or resumes.

## License And CLA

JustHireMe is licensed under [AGPL-3.0-only](LICENSE). By contributing, you
agree that your contribution may be distributed under AGPL-3.0-only and under
separate commercial licenses offered by Vasudev Siddh / vasu-devs.

Read [CLA.md](CLA.md) before submitting a pull request. Maintainers may require
CLA assistant or another signoff workflow before merging.

## How To Contribute

### 1. Pick An Issue

Good starting points:

- `good first issue`
- `documentation`
- `scraper`
- `source`
- `ranker`
- `scoring`

If you want to add a source adapter, open or claim a scraper source issue first so work is not duplicated.

### 2. Discuss Bigger Changes First

Open an issue before starting work if your change:

- adds a new dependency
- changes lead schema or API behavior
- changes ranking semantics
- affects local data storage
- changes packaging or release behavior
- touches experimental auto-apply
- rewrites major UI flows

Small docs, tests, parser fixes, and source adapters can usually go straight to a PR.

### 3. Keep Pull Requests Focused

Prefer small PRs. A good PR usually does one thing:

- add one source adapter
- fix one ranking bug
- add one group of tests
- improve one docs page
- clean up one UI flow

Avoid mixing unrelated refactors with feature work.

## Local Development Setup

### Requirements

- Node.js 24 (matches CI)
- Python 3.13+
- Rust stable
- uv
- Git

Optional:

- Ollama for local model testing
- Playwright browser dependencies for experimental automation work

### Install Dependencies

```bash
npm install
cd backend
uv sync --dev
cd ..
```

### Run The App

```bash
npm run tauri dev
```

### Run Frontend Only

```bash
npm run dev
```

### Run Backend Tests

Windows:

```bash
backend/.venv/Scripts/python.exe -m pytest backend/tests
```

macOS/Linux:

```bash
backend/.venv/bin/python -m pytest backend/tests
```

### Run Frontend Checks

```bash
npm run typecheck
npm test
npm run build
```

### Run Rust Check

```bash
cd src-tauri
cargo check
```

## Pull Request Checklist

Before opening a PR:

- [ ] I ran the relevant tests/checks.
- [ ] I added tests for behavior changes.
- [ ] I updated docs for user-facing or contributor-facing changes.
- [ ] I kept the PR focused.
- [ ] I did not commit local app data, databases, generated PDFs, API keys, cookies, or resumes.
- [ ] I made experimental automation changes opt-in and clearly labeled.
- [ ] I explained the user impact in the PR description.
- [ ] I understand contributions are covered by [CLA.md](CLA.md).

## Testing Expectations

### Scraper Changes

Add tests for:

- one valid lead
- one noisy or rejected lead
- URL normalization or dedupe behavior when relevant
- date/freshness behavior when relevant
- quality gate behavior when relevant

### Ranking Changes

Add tests for:

- expected score band
- seniority mismatch
- wrong-field or low-quality lead
- semantic fallback if vector search is unavailable
- edge cases that caused the bug

### UI Changes

At minimum:

- run `npm run typecheck`
- run `npm test`
- run `npm run build`

If the change affects layout, manually check the relevant screen in the app.

### Storage/API Changes

Add backend regression tests and explain migration behavior. Avoid breaking existing local user data.

## Source Adapter Contribution Guide

The easiest way to contribute is adding a scraper source. Read [docs/source-adapters.md](docs/source-adapters.md) before implementing.

### Preferred Sources

Best:

- direct ATS APIs
- public company career pages
- structured RSS/API feeds
- well-known community hiring threads

Lower confidence:

- broad search results
- scraped HTML without stable structure
- sources that require cookies
- sources that frequently block automation

Avoid:

- sources requiring private credentials for basic scraping
- sources that violate terms of service
- spammy lead marketplaces
- sources where every result is vague or unverifiable

### Normalized Lead Contract

A source adapter should return dictionaries with:

- `title`
- `company`
- `url`
- `platform`
- `description`

Recommended fields:

- `posted_date`
- `location`
- `tech_stack`
- `signal_score`
- `signal_reason`
- `signal_tags`
- `source_meta`

The quality gate can then attach:

- `source_meta.lead_quality_score`
- `source_meta.lead_quality_reason`
- `source_meta.lead_quality_accepted`

### Source Adapter Checklist

- [ ] The adapter returns normalized lead fields.
- [ ] It does not save duplicates.
- [ ] It preserves useful source metadata.
- [ ] It passes or uses the lead quality gate.
- [ ] It has tests with realistic sanitized fixtures.
- [ ] It documents how to enable/configure the source.
- [ ] It fails gracefully when the source is unavailable.

## Ranking And Quality Rules

Ranking work should preserve these principles:

- Do not overrate senior jobs for junior/fresher users.
- Do not hide uncertainty.
- Do not invent candidate facts.
- Penalize low-quality scraped posts.
- Prefer direct evidence from projects/experience.
- Make reasons useful to users and contributors.

If you change scoring behavior, update or add tests in `backend/tests/test_regressions.py`.

## Frontend Contribution Guidelines

The frontend should make the product feel like a workbench, not a marketing site.

Guidelines:

- Keep the core workflow obvious: leads, ranking, profile, customization.
- Do not make auto-apply look like the main product.
- Use existing components and styling conventions.
- Keep text concise and honest.
- Show explanations where ranking/filtering decisions matter.
- Avoid adding heavy UI dependencies unless necessary.

## Backend Contribution Guidelines

Guidelines:

- Keep scraper logic deterministic where possible.
- Avoid network calls in tests.
- Lazy-load heavy ML/model dependencies.
- Fail soft when optional systems are unavailable.
- Keep local data migrations backward-compatible.
- Prefer small helper modules over giant agent files when adding reusable logic.

## Security And Privacy Rules

Never commit:

- API keys
- cookies
- bearer tokens
- local app data
- SQLite databases
- Kuzu/LanceDB data directories
- generated PDFs with personal information
- real resumes
- screenshots containing secrets

When opening issues:

- sanitize job snippets
- remove contact details
- use fake keys
- avoid uploading local database files

See [SECURITY.md](SECURITY.md).

## Documentation Standards

Docs should be:

- accurate
- beginner-friendly
- explicit about current limitations
- clear about what is core vs experimental
- easy to follow on Windows

If a command is platform-specific, say so.

## Commit Message Style

Use clear, practical commit messages:

- `Add Greenhouse source adapter`
- `Fix seniority cap for junior profiles`
- `Document Windows sidecar build`
- `Show lead quality reason on cards`

Avoid vague messages like:

- `updates`
- `fix stuff`
- `final changes`

## Review Process

Maintainers will look for:

- correctness
- test coverage
- user impact
- privacy impact
- maintainability
- whether the change fits the OSS direction

PRs may be asked to split scope, add tests, or update docs. That is normal.

## Release Contributions

Windows release work should follow [docs/windows-release.md](docs/windows-release.md).

Release-related PRs should mention:

- OS tested
- installer/bundle generated
- smoke test result
- sidecar behavior
- known limitations

## Questions

Open a GitHub issue if you are unsure where a change belongs. For scraper ideas, use the scraper source request template and include a public example URL.
