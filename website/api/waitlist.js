import { createHash } from "node:crypto";
import { json, redis, redisConfigured, send } from "./_counter.js";

// JustHireMe waitlists (the iPhone beta and the older Cloud list).
// POST { email, list?, source?, website? } -> joins a list (idempotent per email + list)
// GET  ?list=ios                           -> { count } for the on-page social-proof line
//
// Storage, in order of preference:
//   1. Supabase (SUPABASE_URL + SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY).
//      Table: public.waitlist_signups, see supabase/waitlist.sql. The key never
//      leaves this function; the table has RLS on and no public policies.
//   2. Upstash Redis sorted set (the original storage). Member = normalized email,
//      score = first-signup timestamp (ZADD NX keeps the original date).
const LISTS = new Set(["ios", "cloud"]);
const DEFAULT_LIST = "cloud"; // older clients post without `list`
const REDIS_KEYS = { cloud: "justhireme:waitlist:cloud", ios: "justhireme:waitlist:ios" };
const SUPABASE_TABLE = "waitlist_signups";

// Deliberately simple validation: an email shape check plus length caps. Storage
// dedupes repeats, the hidden honeypot field absorbs dumb bots, the per-IP limit
// slows scripted signups, and the count is read back from storage.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const RATE_LIMIT_PER_HOUR = 8;

function normalizeEmail(value) {
  return String(value || "").trim().toLowerCase().slice(0, 200);
}

function normalizeList(value) {
  const list = String(value || DEFAULT_LIST).toLowerCase();
  return LISTS.has(list) ? list : null;
}

function normalizeSource(value) {
  const source = String(value || "").toLowerCase().replace(/[^a-z0-9._-]/g, "").slice(0, 64);
  return source || null;
}

function supabaseConfig() {
  const url = (process.env.SUPABASE_URL || "").replace(/\/+$/, "");
  const key = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || "";
  return url && key ? { url, key } : null;
}

function supabaseHeaders(key, extra = {}) {
  // New-style secret keys (sb_secret_...) go in `apikey` only; legacy service-role
  // keys are JWTs and PostgREST also expects them as a bearer token.
  const headers = { apikey: key, ...extra };
  if (key.startsWith("eyJ")) headers.authorization = `Bearer ${key}`;
  return headers;
}

async function supabaseJoin({ url, key }, row) {
  const response = await fetch(`${url}/rest/v1/${SUPABASE_TABLE}?on_conflict=email,list`, {
    method: "POST",
    headers: supabaseHeaders(key, {
      "content-type": "application/json",
      prefer: "resolution=ignore-duplicates,return=representation",
    }),
    body: JSON.stringify(row),
  });
  if (!response.ok) throw new Error(`WAITLIST_SUPABASE_INSERT ${response.status}`);
  const inserted = await response.json();
  // ignore-duplicates returns no rows when the email was already on this list.
  return { already: Array.isArray(inserted) && inserted.length === 0 };
}

async function supabaseCount({ url, key }, list) {
  const response = await fetch(`${url}/rest/v1/${SUPABASE_TABLE}?list=eq.${list}&select=id`, {
    method: "HEAD",
    headers: supabaseHeaders(key, { prefer: "count=exact" }),
  });
  if (!response.ok) throw new Error(`WAITLIST_SUPABASE_COUNT ${response.status}`);
  const total = (response.headers.get("content-range") || "").split("/")[1];
  return Number(total) || 0;
}

async function redisJoin(list, email) {
  const added = await redis(["ZADD", REDIS_KEYS[list], "NX", String(Date.now()), email]);
  return { already: Number(added) === 0 };
}

async function redisCount(list) {
  return Number(await redis(["ZCARD", REDIS_KEYS[list]])) || 0;
}

function clientIp(request) {
  const forwarded = String(request.headers?.["x-forwarded-for"] || "").split(",")[0].trim();
  return forwarded || request.socket?.remoteAddress || "unknown";
}

// Returns true when this IP is over the hourly limit. Skipped when Redis is absent;
// the honeypot and unique constraint still apply.
async function rateLimited(request) {
  if (!redisConfigured()) return false;
  const salt = process.env.COUNTER_HASH_SALT || "justhireme";
  const ipHash = createHash("sha256").update(`${salt}:${clientIp(request)}`).digest("hex").slice(0, 32);
  const key = `justhireme:waitlist:rl:${ipHash}`;
  const hits = Number(await redis(["INCR", key])) || 0;
  if (hits === 1) await redis(["EXPIRE", key, "3600"]);
  return hits > RATE_LIMIT_PER_HOUR;
}

async function countFor(list) {
  const supabase = supabaseConfig();
  if (supabase) return { count: await supabaseCount(supabase, list), configured: true };
  if (redisConfigured()) return { count: await redisCount(list), configured: true };
  return { count: 0, configured: false };
}

export default async function handler(request, response) {
  const list = normalizeList(request.query?.list ?? request.body?.list);
  if (!list) return send(response, json({ error: "Unknown waitlist." }, 400));

  if (request.method === "GET") {
    try {
      const { count, configured } = await countFor(list);
      return send(response, {
        body: { count, configured },
        status: 200,
        cacheControl: "public, max-age=60, s-maxage=120, stale-while-revalidate=600",
      });
    } catch (error) {
      console.error("WAITLIST_COUNT_FAILED", { list, message: error.message });
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
      return send(response, json({ error: "Enter a valid email address, like you@example.com." }, 400));
    }

    if (await rateLimited(request)) {
      return send(response, json({ error: "Too many sign-ups from this network. Try again in an hour." }, 429));
    }

    const supabase = supabaseConfig();
    let result;
    if (supabase) {
      result = await supabaseJoin(supabase, { email, list, source: normalizeSource(body.source) });
    } else if (redisConfigured()) {
      result = await redisJoin(list, email);
    } else {
      // Local dev / missing env: acknowledge without pretending to store.
      return send(response, json({ joined: false, configured: false }, 202));
    }

    const { count } = await countFor(list);
    return send(response, json({ joined: true, already: result.already, count }));
  } catch (error) {
    console.error("WAITLIST_JOIN_FAILED", { list, message: error.message });
    return send(response, json({ error: "Couldn't save your email. Try again in a minute." }, 500));
  }
}
