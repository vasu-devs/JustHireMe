-- Paid job-market providers are opt-in and request reservations are recorded
-- before network I/O so concurrent scans cannot exceed a configured hard cap.
CREATE TABLE IF NOT EXISTS paid_provider_requests(
    request_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    run_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'reserved',
    estimated_cost_usd REAL NOT NULL DEFAULT 0,
    response_rows INTEGER NOT NULL DEFAULT 0,
    error_type TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS paid_provider_scan_yield(
    run_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    source_records INTEGER NOT NULL DEFAULT 0,
    canonical_opportunities INTEGER NOT NULL DEFAULT 0,
    new_canonical_opportunities INTEGER NOT NULL DEFAULT 0,
    eligible_opportunities INTEGER NOT NULL DEFAULT 0,
    net_new_eligible_opportunities INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(run_id, candidate_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_paid_requests_provider_time
    ON paid_provider_requests(provider, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_paid_requests_run
    ON paid_provider_requests(run_id, provider);
CREATE INDEX IF NOT EXISTS idx_paid_yield_provider
    ON paid_provider_scan_yield(provider, created_at DESC);
