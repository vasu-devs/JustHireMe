# Changelog

## 1.0.2 - 2026-05-18

- Added the execution and stability records to the repository release branch.
- Fixed Linux CI mypy checks for Windows-only SQLite migration locking.

## 1.0.1 - 2026-05-18

- Added cross-platform `release:smoke` CI coverage across Linux, Windows, and macOS.
- Added profile-to-score-to-generate integration coverage plus startup, lead-store, generation-readiness, and scoring invariant tests.
- Tightened profile parsing utilities by replacing unsafe `as any` casts with explicit unknown narrowing.
- Fixed startup validation so built-in default job targets do not produce false broad-target warnings.

## 1.0.0 - 2026-05-18

- Added thread-local SQLite connection pooling with shutdown cleanup to reduce lock churn.
- Made WebSocket broadcast, event recording, frontend message parsing, and LLM fallback failures visible.
- Replaced race-prone scan/reevaluation globals with an atomic task registry and `/api/v1/status`.
- Isolated graph work onto a dedicated executor with lock timeouts for degraded-but-responsive graph reads.
- Added frontend state reconciliation after WebSocket reconnects plus progress indicators for long scans.
- Added sidecar stale-PID validation and capped auto-restart after crashes.
- Reworked lead row mapping to use SQLite column names instead of positional indexes.
- Added settings validation, local structured diagnostics, and release smoke coverage for core API endpoints.
- Removed the deprecated `backend/db` compatibility facade.
