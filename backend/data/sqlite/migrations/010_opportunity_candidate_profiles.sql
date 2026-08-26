-- Candidate constraints and operational scan state are private, local data.
CREATE TABLE IF NOT EXISTS candidate_opportunity_profiles(
    tenant_id TEXT NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    candidate_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(tenant_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS opportunity_source_health(
    tenant_id TEXT NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    candidate_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    attempted_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(tenant_id, candidate_id, target_id)
);

CREATE TABLE IF NOT EXISTS opportunity_scan_runs(
    run_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    candidate_id TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_candidate_profiles_updated
    ON candidate_opportunity_profiles(tenant_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunity_health_candidate
    ON opportunity_source_health(tenant_id, candidate_id, attempted_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunity_runs_candidate
    ON opportunity_scan_runs(tenant_id, candidate_id, started_at DESC);
