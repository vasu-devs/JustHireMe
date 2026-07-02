# Roadmap

> Status: JustHireMe ships stable **v1.x** (currently 1.3.0). The early milestones
> below are largely shipped (see the README "Shipped" roadmap and CHANGELOG);
> items marked ✓ are done. This file tracks direction, not release order.

## v0.1 OSS Readiness

- Reframe the app as scraper, ranker, vector matching, and customizer.
- Add contributor docs (project is licensed AGPL-3.0-only; see LICENSE).
- Add source adapter contract and scraper contribution issues.
- Add lead quality gate before saving low-value leads.
- Improve Windows-first release instructions.

## v0.2 Source Ecosystem

- Add more ATS adapters.
- Add parser fixtures for source regression tests.
- Add source quality dashboards and "why shown / why filtered" explanations.
- Add contributor-friendly source plugin boundaries.

## v0.3 Ranking And Evaluation

- ✓ Add a small evaluation dataset for lead quality. (shipped: `backend/evals/`)
- Improve feedback learning.
- Make semantic matching state visible in the UI.
- Add ranker benchmarks.

## Future

- OS keychain storage for API keys.
- ✓ Cross-platform installers. (shipped: Windows / macOS / Linux from CI)
- Optional automation plugin separation.
- Hosted source catalog, while keeping user data local.
