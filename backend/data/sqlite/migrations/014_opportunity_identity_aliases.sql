-- Stable canonical IDs survive the arrival of additional aggregators. Every
-- exact identity key points to the first canonical opportunity that owned it.
CREATE TABLE IF NOT EXISTS opportunity_identity_aliases(
    identity_key TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO opportunity_identity_aliases(identity_key, opportunity_id)
SELECT identity.value, o.opportunity_id
FROM canonical_opportunities o, json_each(o.payload_json, '$.identity_keys') AS identity
WHERE identity.type='text' AND length(identity.value) > 0;

CREATE INDEX IF NOT EXISTS idx_opportunity_alias_id
    ON opportunity_identity_aliases(opportunity_id);
