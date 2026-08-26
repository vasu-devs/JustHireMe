-- Canonical public opportunity truth is separate from local candidate state.
CREATE TABLE IF NOT EXISTS opportunity_source_records(
    source_record_id TEXT PRIMARY KEY,
    source_target_id TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL,
    provider_tenant TEXT NOT NULL DEFAULT '',
    provider_requisition_id TEXT NOT NULL DEFAULT '',
    canonical_source_url TEXT NOT NULL,
    description_sha256 TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    active_hint TEXT NOT NULL DEFAULT 'unknown',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS canonical_opportunities(
    opportunity_id TEXT PRIMARY KEY,
    employer_name TEXT NOT NULL,
    title TEXT NOT NULL,
    location_text TEXT NOT NULL DEFAULT '',
    canonical_apply_url TEXT NOT NULL,
    live_status TEXT NOT NULL DEFAULT 'unknown',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS opportunity_observations(
    opportunity_id TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    PRIMARY KEY(opportunity_id, source_record_id)
);

CREATE TABLE IF NOT EXISTS candidate_opportunity_decisions(
    tenant_id TEXT NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    candidate_id TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    eligibility TEXT NOT NULL,
    decision TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(tenant_id, candidate_id, opportunity_id, rule_version)
);

ALTER TABLE leads ADD COLUMN opportunity_id TEXT;

CREATE INDEX IF NOT EXISTS idx_source_records_target_observed
    ON opportunity_source_records(source_target_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_records_requisition
    ON opportunity_source_records(provider, provider_tenant, provider_requisition_id);
CREATE INDEX IF NOT EXISTS idx_canonical_live_status
    ON canonical_opportunities(live_status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_candidate_decisions_queue
    ON candidate_opportunity_decisions(tenant_id, candidate_id, decision, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_leads_opportunity_id ON leads(opportunity_id);
