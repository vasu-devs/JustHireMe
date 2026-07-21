import { json, redis, redisConfigured, send } from "./_counter.js";

// JustHireMe Cloud waitlist.
// POST { email, website? }  -> joins the list (idempotent per email)
// GET                       -> { count } for the on-page social-proof line
//
// Storage: one Upstash sorted set. Member = normalized email, score = first-signup
// timestamp (ZADD NX keeps the original date on repeat signups). This gives dedupe,
// a live count (ZCARD), and a signup-over-time curve (ZRANGEBYSCORE) for free —
// the slope is the number that matters in investor conversations.
const WAITLIST_KEY = "justhireme:waitlist:cloud";

// Deliberately simple validation: an email shape check plus length caps. The sorted
// set dedupes repeats, the hidden honeypot field absorbs dumb bots, and the count is
// read back from storage (never trusted from the client).
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

function normalizeEmail(value) {
  return String(value || "").trim().toLowerCase().slice(0, 200);
}

export default async function handler(request, response) {
  if (request.method === "GET") {
    try {
      const count = redisConfigured() ? await redis(["ZCARD", WAITLIST_KEY]) : null;
      return send(response, {
        body: { count: Number(count) || 0, configured: redisConfigured() },
        status: 200,
        cacheControl: "public, max-age=60, s-maxage=120, stale-while-revalidate=600",
      });
    } catch {
      return send(response, json({ count: 0, configured: false }));
    }
  }

  if (request.method !== "POST") {
    return send(response, json({ error: "Method not allowed" }, 405));
  }

  try {
    const body = typeof request.body === "object" && request.body ? request.body : {};

    // Honeypot: real users never fill the visually-hidden "website" field.
    if (body.website) {
      return send(response, json({ joined: true, ignored: true }));
    }

    const email = normalizeEmail(body.email);
    if (!EMAIL_RE.test(email)) {
      return send(response, json({ error: "That email doesn't look right." }, 400));
    }

    if (!redisConfigured()) {
      // Local dev / missing env: acknowledge without pretending to store.
      return send(response, json({ joined: false, configured: false }, 202));
    }

    // NX preserves the first-signup timestamp when someone re-submits.
    const added = await redis(["ZADD", WAITLIST_KEY, "NX", String(Date.now()), email]);
    const count = await redis(["ZCARD", WAITLIST_KEY]);

    return send(response, json({
      joined: true,
      already: Number(added) === 0,
      count: Number(count) || 0,
    }));
  } catch {
    return send(response, json({ error: "Couldn't save that right now — try again in a minute." }, 500));
  }
}
