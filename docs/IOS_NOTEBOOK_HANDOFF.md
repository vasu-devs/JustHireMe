# Notebook product direction and backend handoff

This replaces the earlier credit-and-draft workspace. The customer sees exactly five main sections: **Profile, For You, Applications, Grow, Plan**. The iOS frontend uses pale lavender, mint, peach, blue, pink, and yellow on ruled paper, with pencil outlines, crayon strokes, serif chapter headings, and editable profile sections inspired by the desktop dossier.

## Customer journey

1. Bring portfolio details, a résumé, Markdown, or other content into the profile notebook. Review organized sections and edit identity, experience, education, projects, skills, and achievements in place.
2. Receive job recommendations from a shared backend discovery service. There are no customer scraper controls or manually maintained job-search pipelines.
3. Tap **Apply now**, or configure auto-apply boundaries. Each application uses one unit of the application allowance.
4. Follow submitted, interviewing, offer, rejected, and needs-attention outcomes in a chart and timeline.
5. Read and practise suggested topics based on profile gaps and application evidence.
6. Choose one application, a weekly allowance, or a monthly allowance. The sample quantities are 1 once, 10/week, and 40/month; they are product proposals, not published App Store offerings.

## Implemented frontend behavior

`NotebookModel` owns this experience independently from the older `AppModel` credit/draft API. Preview actions are guarded and never create accounts, purchases, AI requests, employer submissions, scraper runs, or background jobs.

- File picker accepts regular files up to 10 MB, using security-scoped access. Markdown/text/CSV/JSON and text-based PDFs use local text extraction. Heading recognition organizes known sections. This is a deterministic convenience parser, not an AI agent. Files such as images, scans, and DOCX stay attached in session with an explicit pending-processing state; the UI does not claim extraction succeeded.
- Proposed sections are reviewed before merging. Imports preserve manual edits, and exact repeated blocks are not duplicated. Uploaded text is data, never executable instructions.
- Profile changes and source attachments currently live in memory. A Markdown export lets the user keep a copy. No account sync or durable upload queue is claimed. Sign-out clears the notebook.
- Preview recommendations are fictional, and their displayed score is calculated skill overlap. It is not a prediction of hiring success. Editing skills changes overlap and learning gaps.
- One-tap preview submission creates a tracker entry and deducts one application once per role. A missing profile or exhausted allowance blocks the request. Duplicate taps return the existing application.
- Auto-apply preview requires an explicit toggle, eligible role titles, matching location, a minimum overlap, a daily cap, and remaining allowance. It runs only when the user taps the preview action. It never schedules unattended submissions.
- Preview employer responses update chart counts and the timeline. They are explicitly labelled simulations.
- Learning topics count missing skills in the suggested roles. Rejections without employer feedback are not assigned invented causes. Reading links point to W3C accessibility tutorials, MDN learning material, and Nielsen Norman Group research guidance.
- The new billing screen speaks only in applications, not credits. It does not reuse the legacy StoreKit credit product IDs or pretend those products sell the new application plans.

## Contracts to implement next

These are **proposed contracts**, not existing endpoints:

| Service | Inputs / expected response |
| --- | --- |
| Profile ingestion | Tenant-scoped signed upload, source ID, ingestion status, extracted typed sections, provenance and confidence; explicit merge review |
| Profile editor | Versioned profile document, editable identity and section entries, conflict handling and export/delete support |
| Global recommendations | Shared job inventory, tenant-specific ranking, stable job ID, freshness/closed status, explicit scoring components |
| Apply | Idempotency key, job ID, profile version, allowance reservation; prepared/submitted/needs-attention/failed state plus receipt |
| Auto-apply | Explicit opt-in, allowlisted titles/locations, threshold, daily/period caps, pause/revoke; uses the same idempotent submit service |
| Application outcomes | Append-only events with verified source, timestamps, status, employer feedback when available; tenant-scoped feed |
| Growth | Explainable gaps and recommended resources linked to role requirements or actual feedback; completion state |
| Billing | New StoreKit product catalog, localized price, period entitlement, one-application top-ups, renewal/switch rules and purchase recovery |

Reserve allowance on accepted work and settle against confirmed submission. Define retry/refund/needs-attention behavior so duplicate or failed requests cannot double-charge. Establish period reset/time zone and unused-unit rules before publishing pricing. Do not assume the old non-expiring credit ledger directly implements this new product.

The account, sign-in, purchase-verification, and deletion code from the earlier prototype remains in the repository for reuse, but its contracts do not implement this new product end-to-end. The shared scraper, AI ingestion/OCR, actual submission provider, outcome sync, storage, and new billing entitlements are backend work. Preserve tenant isolation and file provenance when connecting them.
