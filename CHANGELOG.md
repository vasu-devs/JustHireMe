# Changelog

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
