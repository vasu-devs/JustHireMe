import { createHash, createHmac } from "node:crypto";

export function json(body, status = 200) {
  return { body, status };
}

export function send(response, payload) {
  response.setHeader("cache-control", payload.cacheControl || "no-store");
  response.status(payload.status).json(payload.body);
}

export function envInt(name, fallback) {
  const parsed = Number.parseInt(process.env[name] || "", 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

export function cacheableJson(body, seconds = envInt("COUNTER_CDN_CACHE_SECONDS", 21600), status = 200) {
  return {
    body,
    status,
    cacheControl: `public, max-age=600, s-maxage=${seconds}, stale-while-revalidate=${seconds * 24}`,
  };
}

export function countersWritable() {
  return process.env.COUNTER_WRITES_ENABLED !== "false";
}

export function redisConfigured() {
  return Boolean(process.env.UPSTASH_REDIS_REST_URL && process.env.UPSTASH_REDIS_REST_TOKEN);
}

export async function redis(command) {
  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;

  if (!url || !token) {
    return null;
  }

  const response = await fetch(`${url}/pipeline`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    body: JSON.stringify([command]),
  });

  if (!response.ok) {
    throw new Error(`Redis request failed with ${response.status}`);
  }

  const [payload] = await response.json();
  if (payload?.error) {
    throw new Error(payload.error);
  }
  return payload?.result;
}

export async function redisPipeline(commands) {
  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;

  if (!url || !token) {
    return null;
  }

  const response = await fetch(`${url}/pipeline`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(commands),
  });

  if (!response.ok) {
    throw new Error(`Redis request failed with ${response.status}`);
  }

  const payload = await response.json();
  const error = payload.find((item) => item?.error);
  if (error) {
    throw new Error(error.error);
  }
  return payload.map((item) => item?.result);
}

export async function redisScript(script, keys = [], args = []) {
  return redis(["EVAL", script, keys.length, ...keys, ...args]);
}

export function cleanId(value) {
  return String(value || "").replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 80);
}

export function hashVisitorId(value) {
  const id = cleanId(value);
  if (!id) return "";
  const salt = process.env.COUNTER_HASH_SALT || process.env.UPSTASH_REDIS_REST_TOKEN || "justhireme-public-counter";
  if (salt) {
    return createHmac("sha256", salt).update(id).digest("base64url").slice(0, 48);
  }
  return createHash("sha256").update(id).digest("base64url").slice(0, 48);
}

export function visitorKey(prefix, visitorId, scope = "") {
  const hashed = hashVisitorId(visitorId);
  if (!hashed) return "";
  return `${prefix}${scope ? `${scope}:` : ""}${hashed}`;
}

export function createMemoryCache(ttlMs) {
  let value = null;
  let expiresAt = 0;

  return {
    get() {
      return Date.now() < expiresAt ? value : null;
    },
    set(nextValue) {
      value = nextValue;
      expiresAt = Date.now() + ttlMs;
      return value;
    },
    update(updater) {
      const current = this.get();
      if (!current) return null;
      return this.set(updater(current));
    },
  };
}
