-- Live-verification results for shortlist_global.py leads (scripts/verify_shortlist.py).
--
-- The shortlist's band (A/B/C) is a deterministic regex guess over scraped
-- text; verify_status is the ground truth from actually fetching the live
-- posting (structured ATS APIs where available, schema.org JobPosting JSON-LD
-- or plain-text regex otherwise). Kept separate from `status` (the apply-
-- pipeline's own lifecycle column) so this never collides with it.

ALTER TABLE leads ADD COLUMN verify_status TEXT DEFAULT '';
ALTER TABLE leads ADD COLUMN verify_evidence TEXT DEFAULT '';
ALTER TABLE leads ADD COLUMN verify_checked_at TEXT DEFAULT '';
