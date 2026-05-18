import { cacheableJson, cleanId, countersWritable, createMemoryCache, envInt, json, redis, redisConfigured, redisScript, send, visitorKey } from "./_counter.js";

const TOTAL_KEY = "justhireme:views:total";
const UNIQUE_PREFIX = "justhireme:views:visitor:";
const COUNT_CACHE = createMemoryCache(envInt("COUNTER_SERVER_CACHE_SECONDS", 30 * 60) * 1000);
const VISITOR_TTL_SECONDS = envInt("COUNTER_VISITOR_TTL_DAYS", 400) * 24 * 60 * 60;
const COUNT_VIEW_SCRIPT = `
local visitorKey = KEYS[1]
local totalKey = KEYS[2]
local baseline = tonumber(ARGV[1]) or 0
local ttl = tonumber(ARGV[2]) or 0

if redis.call("EXISTS", totalKey) == 0 then
  redis.call("SET", totalKey, baseline)
end

local wasNew
if ttl > 0 then
  wasNew = redis.call("SET", visitorKey, "1", "EX", ttl, "NX")
else
  wasNew = redis.call("SET", visitorKey, "1", "NX")
end

if wasNew then
  return { 1, redis.call("INCR", totalKey) }
end

return { 0, tonumber(redis.call("GET", totalKey)) or baseline }
`;

async function getViewCount(configured, baseline) {
  if (!configured) {
    return { configured: false, total: baseline };
  }

  const cached = COUNT_CACHE.get();
  if (cached) return cached;

  const total = await redis(["GET", TOTAL_KEY]);
  return COUNT_CACHE.set({
    configured: true,
    total: Number.parseInt(total || `${baseline}`, 10),
  });
}

export default async function handler(request, response) {
  try {
    const configured = redisConfigured();
    const baseline = Number.parseInt(process.env.VIEW_COUNT_BASELINE || "0", 10);

    if (request.method === "GET") {
      return send(response, cacheableJson(await getViewCount(configured, baseline)));
    }

    if (request.method !== "POST") {
      return send(response, json({ error: "Method not allowed" }, 405));
    }

    const body = typeof request.body === "object" && request.body ? request.body : {};
    const visitorId = cleanId(body.visitorId);

    if (!visitorId) {
      return send(response, json({ error: "Missing visitorId" }, 400));
    }

    if (!configured) {
      return send(response, json({ configured: false, counted: false, total: baseline }));
    }

    if (!countersWritable()) {
      return send(response, json({ configured: true, writable: false, counted: false, total: baseline }));
    }

    const key = visitorKey(UNIQUE_PREFIX, visitorId);
    const [wasNew, nextTotal] = await redisScript(
      COUNT_VIEW_SCRIPT,
      [key, TOTAL_KEY],
      [String(baseline), String(VISITOR_TTL_SECONDS)],
    );
    const total = Number.parseInt(nextTotal || `${baseline}`, 10);
    COUNT_CACHE.set({ configured: true, total });

    return send(response, json({
      configured: true,
      counted: Boolean(wasNew),
      total,
    }));
  } catch (error) {
    return send(response, json({
      error: "View counter unavailable",
      total: Number.parseInt(process.env.VIEW_COUNT_BASELINE || "0", 10),
    }, 500));
  }
}
