# JustHireMe Website

Vercel project root: `website/`

## View Counter

The live unique-view counter is implemented in `api/views.js`.

For persistent counting on Vercel, add these environment variables:

```txt
UPSTASH_REDIS_REST_URL=...
UPSTASH_REDIS_REST_TOKEN=...
VIEW_COUNT_BASELINE=0
DOWNLOAD_COUNT_BASELINE=0
```

Each browser gets a local visitor id and the API counts it once with Redis `SET NX`. Counter reads are cached by the API and CDN, and the frontend keeps a six-hour browser cache for visible counters. This keeps the public page from burning through Upstash read commands.

The browser also stores a persistent `justhireme.views.counted` flag, so returning visitors do not keep spending Redis write commands after opening a new tab or browser session. Server-side count reads are cached for 30 minutes by default and CDN responses are cacheable for six hours by default.

Useful safety knobs:

```txt
COUNTER_WRITES_ENABLED=false
COUNTER_SERVER_CACHE_SECONDS=1800
COUNTER_CDN_CACHE_SECONDS=21600
COUNTER_VISITOR_TTL_DAYS=400
COUNTER_HASH_SALT=...
```

Set `COUNTER_WRITES_ENABLED=false` as an emergency brake if the Upstash command count starts rising too fast. The page will keep showing the configured baseline or cached count while new writes are paused.

Visitor ids are hashed before they are used in Redis keys. Set `COUNTER_HASH_SALT` to a stable secret to preserve deduplication across deployments without storing raw browser ids server-side.

## Download Counter

The download counter is implemented in `api/downloads.js`. It uses the same visitor id and Redis `SET NX` pattern so one browser is counted once per platform when a real installer asset is clicked. It tracks total downloads plus individual Windows, macOS, and Linux counts. Set `DOWNLOAD_COUNT_BASELINE=0` for a fresh public launch.

When moving to a new Upstash database, set `VIEW_COUNT_BASELINE` and `DOWNLOAD_COUNT_BASELINE` to the totals you want to preserve before deploying. You can also seed Redis directly with:

```txt
SET justhireme:views:total <view-total>
SET justhireme:downloads:total <download-total>
SET justhireme:downloads:windows <windows-total>
SET justhireme:downloads:mac <mac-total>
SET justhireme:downloads:linux <linux-total>
```

## Release Downloads

The platform download buttons are powered by `api/releases.js`, which reads the latest GitHub release from `vasu-devs/JustHireMe` and maps release assets to:

- Windows: `.exe`, `.msi`, `.msix`, or asset names containing `windows`, `win32`, `win64`
- macOS: `.dmg`, `.pkg`, or asset names containing `mac`, `darwin`, `apple`
- Linux: `.AppImage`, `.deb`, `.rpm`, or asset names containing `linux`

If an asset is missing, that platform button stays disabled and says `Available soon`.

## Feedback And Reviews

The feedback and review forms post to `api/feedback.js`.

To create GitHub issues from submissions, add:

```txt
GITHUB_FEEDBACK_TOKEN=...
GITHUB_FEEDBACK_REPO=vasu-devs/JustHireMe
```

The token needs permission to create issues on the target repository. `GITHUB_FEEDBACK_REPO` is optional and defaults to `vasu-devs/JustHireMe`.

Create these labels in the repository for a cleaner feedback inbox:

```txt
website-feedback
feedback
review
```

Then use filtered issue pages:

- Feedback inbox: `https://github.com/vasu-devs/JustHireMe/issues?q=is%3Aissue%20label%3Awebsite-feedback`
- Reviews only: `https://github.com/vasu-devs/JustHireMe/issues?q=is%3Aissue%20label%3Areview`

Feedback and review submissions are delivered through GitHub issues only. If GitHub issue delivery is not configured, the endpoint returns `202` and the page tells the visitor that delivery setup is still needed.

Because GitHub issues are public, the API redacts the separate name/email fields and scrubs email addresses, phone numbers, bearer tokens, and common API-key formats from the message before creating an issue. Ask users not to paste private resumes, account credentials, or secrets into the public feedback form.
