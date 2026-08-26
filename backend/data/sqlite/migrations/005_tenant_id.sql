-- Multi-tenancy: every user-owned table gets a tenant_id.
--
-- Existing desktop installs are a single tenant, so the column defaults to the
-- local tenant UUID (core.tenancy.LOCAL_TENANT_ID) and every existing row is
-- adopted by it. That keeps this migration a no-op for the ~2,200 desktop users
-- while giving the hosted build the column and the predicate it needs.
--
-- A real UUID (not 'local') on purpose: the same column type and the same RLS
-- predicate then work in both builds, and a desktop database can be imported
-- into the hosted one without translating anything.
--
-- schema_migrations is deliberately NOT tenant-scoped: schema version is global
-- infrastructure, not user data.
--
-- Indexes are COMPOSITE, always (tenant_id, <the key the query already used>).
-- A bare tenant_id index is worse than useless once a tenant has thousands of
-- rows: every lookup degrades into a scan of that tenant's slice.

ALTER TABLE leads             ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001';
ALTER TABLE events            ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001';
ALTER TABLE settings          ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001';
ALTER TABLE error_log         ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001';
ALTER TABLE metrics           ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001';
ALTER TABLE resume_templates  ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001';

-- leads: the hot paths are "all leads for this tenant, newest first",
-- "this tenant's lead by id", and the status/score filters the Jobs screen uses.
CREATE INDEX IF NOT EXISTS idx_leads_tenant_created  ON leads(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_leads_tenant_job      ON leads(tenant_id, job_id);
CREATE INDEX IF NOT EXISTS idx_leads_tenant_status   ON leads(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_leads_tenant_url      ON leads(tenant_id, url);

-- events: only ever read as "this tenant's activity, newest first", optionally
-- narrowed to one job.
CREATE INDEX IF NOT EXISTS idx_events_tenant_ts      ON events(tenant_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_tenant_job     ON events(tenant_id, job_id);

-- settings: key lookup is per tenant. The old PRIMARY KEY(key) is now wrong in
-- principle (two tenants may hold the same key) but SQLite cannot redefine it
-- in place; the Postgres schema makes it PRIMARY KEY (tenant_id, key). Until
-- then this index carries the lookup.
CREATE INDEX IF NOT EXISTS idx_settings_tenant_key   ON settings(tenant_id, key);

CREATE INDEX IF NOT EXISTS idx_templates_tenant      ON resume_templates(tenant_id, is_default);
CREATE INDEX IF NOT EXISTS idx_error_log_tenant      ON error_log(tenant_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_tenant        ON metrics(tenant_id);
