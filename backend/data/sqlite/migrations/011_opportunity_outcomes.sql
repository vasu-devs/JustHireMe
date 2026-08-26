-- Immutable candidate-to-interview funnel events. Public opportunity truth stays
-- separate from private, local candidate outcomes.
CREATE TABLE IF NOT EXISTS candidate_opportunity_events(
    event_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    candidate_id TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    lead_id TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL CHECK(event_type IN (
        'tracked',
        'application_started',
        'application_submitted',
        'outreach_sent',
        'recruiter_reply',
        'screening',
        'technical_assessment',
        'interview',
        'rejected',
        'offer',
        'withdrawn',
        'skipped'
    )),
    occurred_at TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(opportunity_id) REFERENCES canonical_opportunities(opportunity_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_opportunity_events_candidate_time
    ON candidate_opportunity_events(tenant_id, candidate_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunity_events_candidate_opportunity
    ON candidate_opportunity_events(tenant_id, candidate_id, opportunity_id, occurred_at ASC);
CREATE INDEX IF NOT EXISTS idx_opportunity_events_type_time
    ON candidate_opportunity_events(tenant_id, event_type, occurred_at DESC);
