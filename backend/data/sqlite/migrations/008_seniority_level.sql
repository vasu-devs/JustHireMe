-- Persisted result of gateway.lead_adapters.classify_job_seniority (title/
-- description keyword classifier). NULL means "not yet classified" -- every
-- pre-existing row lands here as NULL and leads.service backfills it lazily,
-- unbounded, on the next GET /api/v1/leads (same pattern as migration 007's
-- geo_band/ai_relevant).
--
-- Without this column, GET /api/v1/leads called classify_job_seniority() for
-- every job lead with no cached seniority_level on EVERY request (~43s for
-- 6,516 leads -- the client's 30s timeout meant the endpoint always failed).
ALTER TABLE leads ADD COLUMN seniority_level TEXT;
