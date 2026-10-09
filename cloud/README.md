# JustHireMe mobile cloud service

A separate FastAPI service for the iOS SaaS edition. It does not mount, import, or expose the desktop sidecar. All private content is keyed by an authenticated account. Authentication uses Supabase email OTP; the API verifies bearer tokens against Supabase on every authenticated request.

## Run locally

```sh
python -m venv cloud/.venv
# Activate the venv using your shell's command.
pip install -r cloud/requirements.lock.txt
cp cloud/config.example.env cloud/config.env
# Fill in your own Supabase and PostgreSQL configuration.
```

Never use a customer's or production database for tests. From `cloud`:

```sh
python -m pytest -q
# Optional: set TEST_DATABASE_URL to a DISPOSABLE PostgreSQL database, then rerun.
# The PostgreSQL fixture drops and recreates only the mobile tables in that database.
```

SQLite is available only through explicit test injection. Hosted startup requires `postgresql+psycopg://`. Existing tables are initialized once through the management command; API startup does not run migrations.

## Deployment

1. Provision separate staging and production Supabase projects. Configure email OTP templates to include `{{ .Token }}`, custom SMTP, short OTP lifetimes, send/verification limits, and an app-review login path that the reviewer can actually use. Do not create an authentication bypass.
2. Use a dedicated PostgreSQL database and API login that owns these six mobile tables. Require TLS, keep database ingress private, and use a secret manager for the connection string and Supabase service-role key. Prefer a connection pool supported by the provider and configure its limits for your worker count.
3. Copy `config.example.env` to ignored `config.env`. Set public and admin auth keys. Optional AI and Apple values keep their features unavailable until configured. Do not reuse consumer Claude/Codex subscriptions for SaaS inference.
4. Download Apple root `.cer` files from [Apple PKI](https://www.apple.com/certificateauthority/) into ignored `cloud/certificates`. Set `APPLE_ROOT_CERTIFICATES=/app/certificates`, the registered bundle ID, numeric App Store app ID, and environment. Create an In-App Purchase API key in App Store Connect; mount its `.p8` in the same private directory and set `APPLE_API_KEY_PATH`, `APPLE_API_KEY_ID`, and `APPLE_API_ISSUER_ID` so hourly history reconciliation can run. Verification checks the Apple certificate chain, online revocation status, app, environment, ownership, quantity, and account binding. Production may accept sandbox transactions only for the explicit review-account allowlist; use separate staging for normal testing.
5. From `cloud`, run `docker compose build`, then `docker compose run --rm api python -m jhm_cloud.manage init-db`, then `docker compose up -d`. The recovery service refunds abandoned operations after ten minutes, and ignores late results. For managed hosting, deploy the API command and recovery command as separate processes.
6. Put a managed HTTPS ingress in front of localhost port 8000. Set body limit 128 KiB, request timeout over 120 seconds, header/body read timeouts, and rate limits (starting points: 120 authenticated requests/minute/user, 10 purchase verifications/minute/user, 30 webhook requests/minute/IP with Apple retry tolerance). Set Supabase OTP limits independently. The API also bounds streaming JSON bodies and permits one draft in flight per account. Add distributed ingress limits before exposing it publicly; the application is not a complete abuse-prevention system.
7. Configure production and sandbox App Store Server Notifications V2 to `/v1/billing/apple-notifications`. The signed payload selects a verified environment; production sandbox grants are restricted to designated review users. Run Apple's test notification and verify delivery. Return non-2xx on failed processing so Apple can retry.
8. Monitor HTTP failure rates, verification failures, database saturation, stuck operations, refund balance adjustments, and recovery process health without logging tokens, profiles, prompts, drafts, or signed purchase payloads. Access logs are disabled in the shipped Docker command.

The `init-db` command enables PostgreSQL RLS and revokes access from PUBLIC and Supabase `anon`/`authenticated` roles. It creates no client-access policies. The API connects as table owner and enforces ownership through scoped endpoints and locked account rows. This blocks direct Data API access but is not a substitute for server-side account checks. Keep the server database credentials separate from Supabase client credentials.

Schema v1 is managed by SQLAlchemy metadata in `jhm_cloud/models.py`. Once deployed, make future schema changes with versioned migrations; `create_all` does not alter existing columns. Take a backup before changes and rehearse migrations against staging. Do not use `drop_all` outside the test database.

## Wallet rules

| Product ID | Type | Credits per successful transaction |
| --- | --- | ---: |
| `justhireme.focus.weekly` | Auto-renewable, 1 week | 30 |
| `justhireme.pro.monthly` | Auto-renewable, 1 month | 150 |
| `justhireme.credits.50` | Consumable, one-time | 50 |

Each application package costs 5 credits. Saving jobs, tracking status, editing a profile, and reading/exporting existing drafts are free. Purchased credits never expire, including credits delivered by a subscription. Cancelled/expired subscriptions stop future grants while remaining credits can still be used. No free trial or promotional credits are configured. Subscription activity derives from verified expiration dates; grace-period subscribers receive no new credits until a paid renewal arrives, while existing credits remain usable.

The ledger and balance update in one database transaction under an account lock. Apple environment + transaction ID identifies a purchase exactly once; renewals have distinct transaction IDs. Refunded credits are reversed even if this creates a negative balance, so refunds cannot be used to mint future credits. A signed REFUND_REVERSED notification can restore a reversal once. Older deliveries cannot undo a later refund. Do not permit Family Sharing on these products.

Draft generation reserves credits and persists a unique account/request key before invoking AI. A completed retry returns the saved result, an in-flight retry is rejected without a second charge, and a failed operation refunds exactly once. Profile edits do not change the meaning of a retried request; use a new UUID to request a new draft. The recovery process closes operations that outlive the provider timeout and prevents late completion from storing a result after a refund.

## Storage and deletion

PostgreSQL stores profiles, jobs, drafts, purchases, and ledger entries. Configure encrypted disks/backups and point-in-time recovery at your provider. Suggested initial operational targets: daily backups, 30-day backup retention, RPO 15 minutes and RTO 4 hours, subject to the chosen provider tier. These are launch targets, not guarantees implemented by this repo. Perform a restore drill and record actual results.

Deletion removes the profile, jobs, and drafts, clears the balance, marks the account deleted, and deletes its Supabase identity. It is retryable if identity deletion fails after data deletion; the recovery process also retries unfinished identity deletions. The minimal account ID/purchase token and purchase/ledger records remain as a billing tombstone to prevent receipt replay and support required financial records. Set `FINANCIAL_RETENTION_DAYS` to your approved, published retention period: the recovery process purges expired tombstones only after identity deletion succeeds. No legal retention period is assumed by default. Purged purchase tokens cannot attach to a new account. Backups age out under the published policy. An in-flight AI request cannot be recalled, but its result cannot repopulate a deleted account.

This version accepts structured text only. If résumé uploads are added, use a private object bucket, account-scoped object names, short-lived signed URLs, file-size/type validation, malware scanning, and deletion of source files and derived artifacts. Never use a public résumé bucket or put private content in the app bundle.

## Operations still requiring launch validation

Apple signed sandbox lifecycle tests, notification outage/replay testing, history reconciliation using real App Store credentials, a configured retention policy, ingress rate limits, backup/restore drills, deliverable SMTP, and provider cost/quality evaluation are launch gates. With the API key configured, recovery replays each known customer's transaction history and the previous 30 days of app notification history hourly. Notifications recover first purchases that never reached the API. Replays are idempotent and refund reversals use authoritative server history. `python -m jhm_cloud.manage reconcile-purchases` runs a manual catch-up. Failed accounts are reported for alerting; notification pagination is bounded to 1,000 pages. For volume beyond this launch-sized replay or outages over 30 days, add durable incremental cursors/partitioned backfills before expanding. Do not accept public paying customers until live lifecycle tests and operational configuration are completed.

The new deployment is not provisioned automatically. `config.example.env` values are placeholders and there are no real credentials or customer data in this package.
