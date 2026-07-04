import { cacheableJson, cleanId, countersWritable, createMemoryCache, envInt, json, redisConfigured, redisPipeline, redisScript, send, visitorKey } from "./_counter.js";

const UNIQUE_PREFIX = "justhireme:downloads:visitor:";
const PLATFORM_KEYS = {
  windows: "justhireme:downloads:windows",
  mac: "justhireme:downloads:mac",
  linux: "justhireme:downloads:linux",
};
// Real historical split of installer downloads across all GitHub releases
// (computed from the public release-asset download counts) — used only to
// distribute the one-time DOWNLOAD_COUNT_BASELINE across platforms so the
// per-platform breakdown reconciles with the headline total instead of
// showing e.g. "total: 1907, windows: 959, mac: 0, linux: 0".
const PLATFORM_BASELINE_RATIO = { windows: 0.543, mac: 0.304, linux: 0.153 };
const COUNT_CACHE = createMemoryCache(envInt("COUNTER_SERVER_CACHE_SECONDS", 30 * 60) * 1000);
const VISITOR_TTL_SECONDS = envInt("COUNTER_VISITOR_TTL_DAYS", 400) * 24 * 60 * 60;

// Seeds a platform counter with its share of the baseline on first touch, then
// returns its current value — total is always derived as the sum of the three,
// so the displayed breakdown can never drift from the headline number.
const SEED_IF_MISSING_SCRIPT = `
local key = KEYS[1]
local baseline = tonumber(ARGV[1]) or 0
if redis.call("EXISTS", key) == 0 then
  redis.call("SET", key, baseline)
end
return tonumber(redis.call("GET", key)) or baseline
`;

const COUNT_DOWNLOAD_SCRIPT = `
local platformKey = KEYS[1]
local visitorKey = KEYS[2]
local baseline = tonumber(ARGV[1]) or 0
local ttl = tonumber(ARGV[2]) or 0

if redis.call("EXISTS", platformKey) == 0 then
  redis.call("SET", platformKey, baseline)
end

local wasNew
if ttl > 0 then
  wasNew = redis.call("SET", visitorKey, "1", "EX", ttl, "NX")
else
  wasNew = redis.call("SET", visitorKey, "1", "NX")
end

if wasNew then
  return { 1, redis.call("INCR", platformKey) }
end

return { 0, tonumber(redis.call("GET", platformKey)) or baseline }
`;

function cleanPlatform(value) {
  const platform = String(value || "").toLowerCase();
  return Object.prototype.hasOwnProperty.call(PLATFORM_KEYS, platform) ? platform : null;
}

function platformBaseline(baseline, platform) {
  return Math.round(baseline * PLATFORM_BASELINE_RATIO[platform]);
}

function withTotal(counts) {
  return { ...counts, total: counts.windows + counts.mac + counts.linux };
}

async function getDownloadCounts(configured, baseline) {
  if (!configured) {
    return { configured: false, total: baseline, windows: 0, mac: 0, linux: 0 };
  }

  const cached = COUNT_CACHE.get();
  if (cached) return cached;

  const platforms = Object.keys(PLATFORM_KEYS);
  const results = await redisPipeline(
    platforms.map((platform) => [
      "EVAL", SEED_IF_MISSING_SCRIPT, 1, PLATFORM_KEYS[platform], String(platformBaseline(baseline, platform)),
    ]),
  );
  const counts = Object.fromEntries(
    platforms.map((platform, i) => [platform, Number.parseInt(results?.[i] || "0", 10)]),
  );
  return COUNT_CACHE.set({ configured: true, ...withTotal(counts) });
}

export default async function handler(request, response) {
  try {
    const configured = redisConfigured();
    const baseline = Number.parseInt(process.env.DOWNLOAD_COUNT_BASELINE || "0", 10);

    if (request.method === "GET") {
      return send(response, cacheableJson(await getDownloadCounts(configured, baseline)));
    }

    if (request.method !== "POST") {
      return send(response, json({ error: "Method not allowed" }, 405));
    }

    const body = typeof request.body === "object" && request.body ? request.body : {};
    const visitorId = cleanId(body.visitorId);
    const platform = cleanPlatform(body.platform);

    if (!visitorId) {
      return send(response, json({ error: "Missing visitorId" }, 400));
    }

    if (!platform) {
      return send(response, json({ error: "Missing platform" }, 400));
    }

    if (!configured) {
      return send(response, json({ configured: false, counted: false, total: baseline, windows: 0, mac: 0, linux: 0 }));
    }

    if (!countersWritable()) {
      return send(response, json({ configured: true, writable: false, counted: false, total: baseline, windows: 0, mac: 0, linux: 0 }));
    }

    const key = visitorKey(UNIQUE_PREFIX, visitorId, platform);
    const [wasNew, platformTotal] = await redisScript(
      COUNT_DOWNLOAD_SCRIPT,
      [PLATFORM_KEYS[platform], key],
      [String(platformBaseline(baseline, platform)), String(VISITOR_TTL_SECONDS)],
    );
    const cached = COUNT_CACHE.get();
    const counts = COUNT_CACHE.set({
      configured: true,
      ...withTotal({
        windows: cached?.windows || 0,
        mac: cached?.mac || 0,
        linux: cached?.linux || 0,
        [platform]: Number.parseInt(platformTotal || "0", 10),
      }),
    });

    return send(response, json({
      configured: true,
      counted: Boolean(wasNew),
      platform,
      ...counts,
    }));
  } catch (error) {
    return send(response, json({
      error: "Download counter unavailable",
      total: Number.parseInt(process.env.DOWNLOAD_COUNT_BASELINE || "0", 10),
      windows: 0,
      mac: 0,
      linux: 0,
    }, 500));
  }
}
