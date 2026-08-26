-- Persisted result of leads.shortlist's regex classifier (AI-relevance +
-- geo hireability band A/B/C/D/U). NULL means "not yet classified" -- every
-- pre-existing row lands here as NULL and reporting.service backfills it
-- lazily (bounded per dashboard request) rather than in one big migration
-- pass. Lets the dashboard funnel's "Shortlisted" stage be a SQL COUNT
-- instead of an O(n) Python regex scan over full descriptions on every
-- request (see reporting/service.py::funnel_stages).
ALTER TABLE leads ADD COLUMN ai_relevant INTEGER;
ALTER TABLE leads ADD COLUMN geo_band TEXT;
