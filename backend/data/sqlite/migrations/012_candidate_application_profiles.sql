-- Candidate-scoped resume evidence for the local multi-person pilot. These
-- private snapshots never enter canonical public-opportunity storage.
CREATE TABLE IF NOT EXISTS candidate_application_profiles(
    tenant_id TEXT NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    candidate_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'local_profile_snapshot',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(tenant_id,candidate_id)
);

CREATE INDEX IF NOT EXISTS idx_candidate_application_profiles_updated
    ON candidate_application_profiles(tenant_id,updated_at DESC);
