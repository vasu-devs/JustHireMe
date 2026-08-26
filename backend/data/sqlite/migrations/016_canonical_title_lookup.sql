-- Bound cross-scan syndication reconciliation to exact case-insensitive titles.
-- This expression matches the historical lookup in save_pipeline_result.
CREATE INDEX IF NOT EXISTS idx_canonical_title_lookup
    ON canonical_opportunities(trim(title) COLLATE NOCASE);
