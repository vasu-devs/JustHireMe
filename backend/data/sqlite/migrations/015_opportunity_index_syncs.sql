-- Provenance for public opportunity-index seed/synchronization operations.
-- Private candidate profiles, decisions, events, and application snapshots are
-- deliberately outside this table and outside the synchronizer.
CREATE TABLE IF NOT EXISTS opportunity_index_syncs(
    sync_id TEXT PRIMARY KEY,
    source_sha256 TEXT NOT NULL,
    source_label TEXT NOT NULL,
    source_size_bytes INTEGER NOT NULL,
    source_latest_observed_at TEXT,
    source_counts_json TEXT NOT NULL,
    inserted_counts_json TEXT NOT NULL,
    backup_label TEXT NOT NULL,
    completed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_opportunity_index_syncs_completed
    ON opportunity_index_syncs(completed_at DESC);
