// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Vasudev Siddh and vasu-devs

import React from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const repoUrl = "https://github.com/vasu-devs/JustHireMe";
const coffeeUrl = "https://buymeacoffee.com/vasu.devs";
const releaseNotice = {
  title: "Release assets are publishing.",
  copy: "The newest build is being prepared by GitHub Actions. Download buttons unlock when direct installer assets are available.",
};

const navItems = ["Workflow", "Why local", "Features", "Feedback", "Release"];

const features = [
  {
    title: "Find",
    copy: "Collect better job leads from multiple sources.",
    tone: "blue",
    icon: "layers",
  },
  {
    title: "Filter",
    copy: "Remove stale, thin, and low-signal roles.",
    tone: "yellow",
    icon: "filter",
  },
  {
    title: "Rank",
    copy: "Explain why a role is worth your time.",
    tone: "purple",
    icon: "graph",
  },
  {
    title: "Tailor",
    copy: "Draft resumes, cover letters, and outreach.",
    tone: "green",
    icon: "file",
  },
];


const intelligence = [
  {
    title: "Scrape",
    copy: "Adapters normalize jobs from ATS boards, feeds, communities, and configured sources.",
    icon: "globe",
    tone: "blue",
  },
  {
    title: "Embed",
    copy: "Job descriptions and profile evidence become searchable semantic vectors.",
    icon: "pulse",
    tone: "purple",
  },
  {
    title: "Connect",
    copy: "SQLite, LanceDB, and graph context work together locally.",
    icon: "graph",
    tone: "green",
  },
  {
    title: "Rank",
    copy: "Rules, quality gates, semantic match, and profile signals produce explainable fit.",
    icon: "filter",
    tone: "yellow",
  },
];

const principles = [
  {
    term: "Local-first data",
    copy: "Everything lives on your machine. Nothing you don't choose to share ever leaves it.",
  },
  {
    term: "Explainable scoring",
    copy: "Every match comes with the specific evidence behind the number, not just a score.",
  },
  {
    term: "Human review",
    copy: "Drafts wait for your approval. Nothing gets sent to an employer on its own.",
  },
  {
    term: "Source-available",
    copy: "The code is public under AGPL-3.0. Read it, audit it, or fork it.",
  },
];

const platformOptions = [
  { id: "windows", label: "Windows", hint: "Installer", tone: "blue" },
  { id: "mac", label: "macOS", hint: "DMG / PKG", tone: "purple" },
  { id: "linux", label: "Linux", hint: "AppImage / package", tone: "green" },
];

const tour = [
  {
    id: "profile",
    eyebrow: "Step one",
    title: "Teach it who you are, once.",
    copy: "Drop in a resume and the ingestor extracts your skills, roles, and projects into a real graph — not a keyword bag. Nothing leaves your machine to do it.",
    image: "/assets/screens/profile.webp",
    tone: "pink",
  },
  {
    id: "dashboard",
    eyebrow: "Step two",
    title: "It works while you're doing anything else.",
    copy: "Leads get discovered, scored, and queued in the background. You open the dashboard to a shortlist that already has the noise filtered out, not a firehose to sort through.",
    image: "/assets/screens/dashboard.webp",
    tone: "orange",
  },
  {
    id: "pipeline",
    eyebrow: "Step three",
    title: "Every lead lives in one reviewable queue.",
    copy: "Discovered, tailoring, approved, applied, discarded — filter by source or seniority, see the fit and signal score on every row, and nothing moves forward without your say.",
    image: "/assets/screens/pipeline.webp",
    tone: "blue",
  },
  {
    id: "graph",
    eyebrow: "Step four",
    title: "Every score has a reason behind it.",
    copy: "Match quality comes from your own knowledge graph — the projects and experience that actually prove a skill — so a fit score is never a number you have to just trust.",
    image: "/assets/screens/graph.webp",
    tone: "green",
  },
  {
    id: "activity",
    eyebrow: "Step five",
    title: "Watch it think, don't just wait on it.",
    copy: "Every scrape, score, and draft lands in a live stream as it happens. If a source throttles or a model falls back, you see that too — nothing fails silently.",
    image: "/assets/screens/activity.webp",
    tone: "purple",
  },
];
const BROWSER_CACHE_TTL_MS = 6 * 60 * 60 * 1000;
const VIEW_COUNTED_KEY = "justhireme.views.counted";
const DOWNLOAD_COUNTED_PREFIX = "justhireme.downloads.counted.";

function formatCount(value) {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value || 0);
}

function getVisitorId() {
  const key = "justhireme.visitorId";
  const existing = localStorage.getItem(key);
  if (existing) return existing;

  const next = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  localStorage.setItem(key, next);
  return next;
}

function readBrowserCache(key) {
  try {
    const cached = JSON.parse(localStorage.getItem(key) || "null");
    if (cached && Date.now() - cached.savedAt < BROWSER_CACHE_TTL_MS) {
      return cached.value;
    }
  } catch {
    localStorage.removeItem(key);
  }
  return null;
}

function writeBrowserCache(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify({ savedAt: Date.now(), value }));
  } catch {
    // Storage can be unavailable in hardened browser modes.
  }
}

async function cachedFetchJson(key, url, options) {
  const cached = readBrowserCache(key);
  if (cached) return cached;

  const response = await fetch(url, options);
  const payload = await response.json();
  writeBrowserCache(key, payload);
  return payload;
}

function hasLocalFlag(key) {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function setLocalFlag(key) {
  try {
    localStorage.setItem(key, "1");
  } catch {
    // Storage can be unavailable in hardened browser modes.
  }
}

function useViewCounter() {
  const [views, setViews] = React.useState(0);
  const [configured, setConfigured] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;

    const syncViews = async () => {
      const countedLocally = hasLocalFlag(VIEW_COUNTED_KEY);
      const payload = countedLocally
        ? await cachedFetchJson("justhireme.views", "/api/views", { method: "GET" })
        : await cachedFetchJson("justhireme.views", "/api/views", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ visitorId: getVisitorId() }),
          });
      if (!cancelled && typeof payload.total === "number") {
        setViews(payload.total);
        setConfigured(Boolean(payload.configured));
        if (payload.configured && payload.writable !== false && !payload.error) {
          setLocalFlag(VIEW_COUNTED_KEY);
        }
      }
    };

    syncViews().catch(() => {});

    return () => {
      cancelled = true;
    };
  }, []);

  return { views, configured };
}

function useDownloadCounter() {
  const [downloads, setDownloads] = React.useState({ total: 0, windows: 0, mac: 0, linux: 0 });
  const [configured, setConfigured] = React.useState(false);

  const syncDownloads = React.useCallback(async (method = "GET", platform = null) => {
    const cacheKey = platform ? null : "justhireme.downloads";
    const options = {
      method,
      headers: { "content-type": "application/json" },
      body: method === "POST" ? JSON.stringify({ visitorId: getVisitorId(), platform }) : undefined,
    };
    const payload = cacheKey
      ? await cachedFetchJson(cacheKey, "/api/downloads", options)
      : await fetch("/api/downloads", options).then((response) => response.json());

    if (typeof payload.total === "number") {
      setDownloads({
        total: payload.total,
        windows: payload.windows || 0,
        mac: payload.mac || 0,
        linux: payload.linux || 0,
      });
      setConfigured(Boolean(payload.configured));
      writeBrowserCache("justhireme.downloads", payload);
    }
    return payload;
  }, []);

  React.useEffect(() => {
    syncDownloads("GET").catch(() => {});
  }, [syncDownloads]);

  const trackDownload = React.useCallback(async (platform) => {
    const countedKey = `${DOWNLOAD_COUNTED_PREFIX}${platform}`;
    if (hasLocalFlag(countedKey)) {
      return syncDownloads("GET");
    }

    const payload = await syncDownloads("POST", platform);
    if (payload.configured && payload.writable !== false && !payload.error) {
      setLocalFlag(countedKey);
    }
    return payload;
  }, [syncDownloads]);

  return { downloads, configured, trackDownload };
}

function getFirstAvailableDownload(assets) {
  for (const platform of platformOptions) {
    const asset = assets?.[platform.id];
    if (asset?.url) {
      return { platformId: platform.id, asset };
    }
  }
  return null;
}

function PlatformDownload({ platform, asset, releaseTag, onDownload }) {
  const available = Boolean(asset?.url);
  const title = available ? `Download ${asset.name}` : `${platform.label} installer is still publishing`;
  const content = (
    <>
      <Icon name={available ? "download" : "pulse"} />
      <span>
        <strong>{platform.label}</strong>
        <small>{available ? (releaseTag || "Latest release") : "Publishing"}</small>
      </span>
    </>
  );

  if (!available) {
    return (
      <button
        className={`platform-button tone-${platform.tone}`}
        type="button"
        disabled
        title={title}
      >
        {content}
      </button>
    );
  }

  return (
    <a
      className={`platform-button tone-${platform.tone}`}
      href={asset.url}
      download={asset.name}
      onClick={() => onDownload(platform.id)}
      title={title}
    >
      {content}
    </a>
  );
}

function getPreferredPlatformId() {
  const platform = `${navigator.platform || ""} ${navigator.userAgent || ""}`.toLowerCase();
  if (platform.includes("win")) return "windows";
  if (platform.includes("mac")) return "mac";
  if (platform.includes("linux") || platform.includes("x11")) return "linux";
  return "windows";
}

function ReleaseNoticeBanner({ compact = false, release }) {
  const latestText = release?.tag ? `Latest tag: ${release.tag}` : "Latest release assets";

  return (
    <div className={`release-notice ${compact ? "compact" : ""}`} role="status" aria-live="polite">
      <span className="release-notice-icon"><Icon name="pulse" /></span>
      <div>
        <strong>{release?.available ? latestText : releaseNotice.title}</strong>
        <p>{release?.available ? "Pick an available platform below. Missing installers stay disabled until direct download assets publish." : releaseNotice.copy}</p>
      </div>
      <a className="button primary" href={release?.url || `${repoUrl}/releases`}>
        <Icon name="external" />
        Releases
      </a>
    </div>
  );
}

function useGitHubStars() {
  const [github, setGithub] = React.useState({ stars: null, pullRequests: null });

  React.useEffect(() => {
    let cancelled = false;

    const loadStars = async () => {
      const payload = await cachedFetchJson("justhireme.github", "/api/github");
      if (!cancelled) {
        setGithub({
          stars: typeof payload.stars === "number" ? payload.stars : null,
          pullRequests: typeof payload.pullRequests === "number" ? payload.pullRequests : null,
        });
      }
    };

    loadStars().catch(() => {});

    return () => {
      cancelled = true;
    };
  }, []);

  return github;
}

function useLatestRelease() {
  const [release, setRelease] = React.useState({
    available: false,
    tag: null,
    url: `${repoUrl}/releases`,
    tagsUrl: `${repoUrl}/tags`,
    assets: { windows: null, mac: null, linux: null },
  });

  React.useEffect(() => {
    let cancelled = false;

    const loadRelease = async () => {
      try {
        localStorage.removeItem("justhireme.release");
      } catch {
        // Storage can be unavailable in hardened browser modes.
      }

      const response = await fetch(`/api/releases?ts=${Date.now()}`, {
        headers: { "cache-control": "no-cache" },
      });
      const payload = await response.json();
      if (!cancelled) {
        setRelease({
          available: Boolean(payload.available),
          tag: payload.tag || null,
          url: payload.url || `${repoUrl}/releases`,
          tagsUrl: payload.tagsUrl || `${repoUrl}/tags`,
          assets: payload.assets || { windows: null, mac: null, linux: null },
        });
      }
    };

    loadRelease().catch(() => {});

    return () => {
      cancelled = true;
    };
  }, []);

  return release;
}

function useFeedbackForm(kind) {
  const [state, setState] = React.useState({
    name: "",
    email: "",
    rating: kind === "review" ? "5" : "",
    message: "",
    website: "",
  });
  const [status, setStatus] = React.useState({ type: "idle", message: "" });
  const [submitting, setSubmitting] = React.useState(false);

  const update = React.useCallback((event) => {
    const { name, value } = event.target;
    setState((current) => ({ ...current, [name]: value }));
  }, []);

  const submit = React.useCallback(async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setStatus({ type: "idle", message: "" });

    try {
      const response = await fetch("/api/feedback", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          ...state,
          kind,
          path: window.location.pathname,
          userAgent: navigator.userAgent,
        }),
      });
      const payload = await response.json();

      if (!response.ok) {
        throw new Error(payload.error || "Could not send yet");
      }

      if (payload.delivered) {
        setStatus({ type: "success", message: "Sent. Thank you for making JustHireMe sharper." });
        setState({ name: "", email: "", rating: kind === "review" ? "5" : "", message: "", website: "" });
      } else {
        setStatus({
          type: "warning",
          message: "Form works, but delivery needs GitHub or email environment variables on the deployment.",
        });
      }
    } catch (error) {
      setStatus({ type: "error", message: error.message || "Could not send yet." });
    } finally {
      setSubmitting(false);
    }
  }, [kind, state]);

  return { state, status, submitting, update, submit };
}

function FeedbackCard({ kind, title, copy, tone }) {
  const { state, status, submitting, update, submit } = useFeedbackForm(kind);
  const isReview = kind === "review";

  return (
    <form className={`feedback-card tone-${tone}`} onSubmit={submit}>
      <div className="feedback-card-head">
        <span className="feature-icon"><Icon name={isReview ? "star" : "message"} /></span>
        <div>
          <h3>{title}</h3>
          <p>{copy}</p>
        </div>
      </div>
      <label>
        <span>Name</span>
        <input name="name" value={state.name} onChange={update} placeholder="Your name" autoComplete="name" />
      </label>
      <label>
        <span>Email</span>
        <input name="email" value={state.email} onChange={update} placeholder="you@example.com" type="email" autoComplete="email" />
      </label>
      {isReview && (
        <label>
          <span>Rating</span>
          <select name="rating" value={state.rating} onChange={update}>
            <option value="5">5 - Loved it</option>
            <option value="4">4 - Useful</option>
            <option value="3">3 - Promising</option>
            <option value="2">2 - Needs work</option>
            <option value="1">1 - Not there yet</option>
          </select>
        </label>
      )}
      <label className="span-full">
        <span>{isReview ? "Review" : "Feedback"}</span>
        <textarea
          name="message"
          value={state.message}
          onChange={update}
          placeholder={isReview ? "What worked, what did not, and who should try it?" : "Bug, idea, confusion, feature request, or anything else."}
          required
          rows="5"
        />
      </label>
      <input className="hidden-field" name="website" value={state.website} onChange={update} tabIndex="-1" autoComplete="off" aria-hidden="true" />
      <div className="feedback-actions">
        <button className="button primary" type="submit" disabled={submitting}>
          <Icon name={submitting ? "pulse" : "arrow"} />
          {submitting ? "Sending" : "Send"}
        </button>
        <a className="button secondary" href={`${repoUrl}/issues/new`}>
          <Icon name="github" />
          GitHub issue
        </a>
      </div>
      {status.message && <p className={`form-status ${status.type}`}>{status.message}</p>}
    </form>
  );
}

function Icon({ name }) {
  if (name === "logo") {
    return (
      <svg className="logo-mark" viewBox="0 0 32 32" aria-hidden="true">
        <rect x="1" y="1" width="30" height="30" rx="9" fill="#1F1A14" />
        <path d="M10 21 L10 11 M10 11 L16 11 Q22 11 22 16 Q22 21 16 21 L13 21" stroke="#F4EFE6" strokeWidth="2.2" fill="none" strokeLinecap="round" />
        <circle cx="22" cy="11" r="2" fill="#C96442" />
      </svg>
    );
  }

  const paths = {
    download: "M12 3v12 M7 10l5 5 5-5 M5 21h14",
    spark: "M12 3v4 M12 17v4 M3 12h4 M17 12h4 M5.6 5.6l2.8 2.8 M15.6 15.6l2.8 2.8 M5.6 18.4l2.8-2.8 M15.6 8.4l2.8-2.8",
    graph: "M12 5a2 2 0 1 0 0 .1 M5 18a2 2 0 1 0 0 .1 M19 18a2 2 0 1 0 0 .1 M8.5 11a2 2 0 1 0 0 .1 M15.5 11a2 2 0 1 0 0 .1 M12 7v2 M10 12l-3 4 M14 12l3 4 M10 11h4",
    arrow: "M5 12h14 M13 6l6 6-6 6",
    check: "M5 12l5 5L20 7",
    layers: "M12 3 2 8l10 5 10-5-10-5Z M2 13l10 5 10-5 M2 18l10 5 10-5",
    filter: "M22 3H2l8 9.5V19l4 2v-8.5L22 3z",
    file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6",
    pulse: "M3 12h4l3-8 4 16 3-8h4",
    user: "M12 8a4 4 0 1 0 0 .1 M4 21c0-4 4-7 8-7s8 3 8 7",
    star: "M12 2l3.1 6.3 6.9 1-5 4.9 1.2 6.8-6.2-3.2L5.8 21 7 14.2 2 9.3l6.9-1L12 2z",
    github: "M9 19c-5 1.5-5-2.5-7-3 M15 22v-3.9a3.4 3.4 0 0 0-.9-2.6c3-.3 6.1-1.5 6.1-6.6a5.2 5.2 0 0 0-1.4-3.6 4.8 4.8 0 0 0-.1-3.6s-1.1-.3-3.7 1.4a12.7 12.7 0 0 0-6.7 0C5.7.4 4.6.7 4.6.7a4.8 4.8 0 0 0-.1 3.6A5.2 5.2 0 0 0 3.1 8c0 5.1 3.1 6.3 6.1 6.6a3.4 3.4 0 0 0-.9 2.6V22",
    globe: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M3 12h18 M12 3a14 14 0 0 1 0 18 M12 3a14 14 0 0 0 0 18",
    xlogo: "M4 4l16 16 M20 4L4 20",
    ban: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M5.6 5.6l12.8 12.8",
    external: "M14 3h7v7 M21 3l-9 9 M19 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h6",
    tag: "M20.5 13.5l-7 7a2 2 0 0 1-2.8 0L3 12.8V3h9.8l7.7 7.7a2 2 0 0 1 0 2.8z M7.5 7.5h.1",
    laptop: "M4 5h16v10H4z M2 19h20 M8 19h8",
    message: "M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z",
    coffee: "M4 7h13v6a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V7z M17 9h1.5a2.5 2.5 0 0 1 0 5H17 M6 21h10 M8 3v2 M12 3v2 M16 3v2",
  };

  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name].split(" M").map((d, index) => <path key={index} d={index === 0 ? d : `M${d}`} />)}
    </svg>
  );
}

function useReveal() {
  const ref = React.useRef(null);
  const [visible, setVisible] = React.useState(false);

  React.useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.18, rootMargin: "0px 0px -60px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return [ref, visible];
}

function prefersReducedMotion() {
  return typeof window !== "undefined"
    && window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Animates a displayed number toward `target` whenever it changes, instead of
 * snapping — makes the live counters read as live rather than static text. */
function useCountUp(target, duration = 900) {
  const [display, setDisplay] = React.useState(target ?? 0);
  const fromRef = React.useRef(target ?? 0);
  const frameRef = React.useRef(null);

  React.useEffect(() => {
    if (target == null || Number.isNaN(target)) return undefined;
    if (prefersReducedMotion()) {
      setDisplay(target);
      fromRef.current = target;
      return undefined;
    }

    const from = fromRef.current;
    if (from === target) return undefined;
    const start = performance.now();

    const tick = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(from + (target - from) * eased));
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = target;
      }
    };

    frameRef.current = requestAnimationFrame(tick);
    return () => frameRef.current && cancelAnimationFrame(frameRef.current);
  }, [target, duration]);

  return target == null ? target : display;
}

function Reveal({ children, className = "", as: Tag = "div" }) {
  const [ref, visible] = useReveal();
  return (
    <Tag ref={ref} className={`reveal ${visible ? "in-view" : ""} ${className}`}>
      {children}
    </Tag>
  );
}

function DeviceFrame({ src, alt, tone, className = "" }) {
  return (
    <figure className={`device-frame tone-frame-${tone} ${className}`}>
      <div className="device-chrome">
        <span /><span /><span />
      </div>
      <img src={src} alt={alt} loading="lazy" />
    </figure>
  );
}

function ProductTour() {
  return (
    <div className="tour">
      {tour.map((step, index) => {
        const [ref, visible] = useReveal();
        const reversed = index % 2 === 1;
        return (
          <article
            className={`tour-row ${reversed ? "reversed" : ""} ${visible ? "in-view" : ""}`}
            key={step.id}
            ref={ref}
          >
            <div className="tour-copy">
              <span className="eyebrow">{step.eyebrow}</span>
              <h3>{step.title}</h3>
              <p>{step.copy}</p>
            </div>
            <div className="tour-visual">
              <DeviceFrame src={step.image} alt={`JustHireMe ${step.id} view`} tone={step.tone} />
            </div>
          </article>
        );
      })}
    </div>
  );
}

function IntelligenceMap() {
  return (
    <div className="intel-flow" aria-label="JustHireMe intelligence system">
      <div className="intel-hub">
        <span className="intel-hub-icon"><Icon name="logo" /></span>
        <div>
          <strong>Local match engine</strong>
          <span>Profile graph + embeddings + CRM</span>
        </div>
      </div>
      <span className="intel-connector" aria-hidden="true" />
      <div className="ledger ledger-4col">
        {intelligence.map((item) => (
          <article className="ledger-row ledger-row-stacked" key={item.title}>
            <span className={`feature-icon tone-${item.tone}`}><Icon name={item.icon} /></span>
            <div>
              <h3>{item.title}</h3>
              <p>{item.copy}</p>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function App() {
  const { views, configured } = useViewCounter();
  const { downloads, trackDownload } = useDownloadCounter();
  const github = useGitHubStars();
  const release = useLatestRelease();
  const hasReleaseAssets = platformOptions.some((platform) => release.assets?.[platform.id]?.url);
  const preferredPlatformId = React.useMemo(getPreferredPlatformId, []);
  const preferredAsset = release.assets?.[preferredPlatformId];
  const availableDownload = preferredAsset?.url
    ? { platformId: preferredPlatformId, asset: preferredAsset }
    : getFirstAvailableDownload(release.assets);

  const starsCount = useCountUp(github.stars);
  const prCount = useCountUp(github.pullRequests);
  const viewsCount = useCountUp(views);
  const downloadsTotalCount = useCountUp(downloads.total);
  const downloadsByPlatform = {
    windows: useCountUp(downloads.windows),
    mac: useCountUp(downloads.mac),
    linux: useCountUp(downloads.linux),
  };

  return (
    <>
      <div className="grain-overlay" aria-hidden="true" />
      <header className="site-header">
        <a className="brand" href="#top" aria-label="JustHireMe home"><Icon name="logo" /><span>JustHireMe</span></a>
        <nav aria-label="Primary navigation">
          {navItems.map((item) => <a key={item} href={`#${item.toLowerCase().replace(" ", "-")}`}>{item}</a>)}
        </nav>
        <div className="header-actions">
          <a className="header-link hide-mobile" href="https://vasudev.live"><Icon name="globe" /> <span>Portfolio</span></a>
          <a className="header-link hide-mobile" href="https://x.com/vasu_devs"><Icon name="xlogo" /> <span>X</span></a>
          <a className="header-link support-link" href={coffeeUrl}><Icon name="coffee" /> <span>Support</span></a>
          <a className="header-link" href={repoUrl}><Icon name="github" /> <span>GitHub</span></a>
        </div>
      </header>

      <main id="top">
        <section className="hero band">
          <div className="hero-copy">
            <span className="eyebrow">Local-first AI job intelligence workbench</span>
            <h1>JustHireMe</h1>
            <p>
              Job hunting is mostly noise: dead boards, keyword-matched rejections, applications into a void.
              JustHireMe runs the whole search on your machine — it finds the roles, explains why they fit, and
              hands you a reviewable draft instead of another tab to keep track of.
            </p>
            <div className="proof-line">
              <span>Semantic matching</span>
              <span>Built in public</span>
              <span>Desktop-first</span>
            </div>
            <div className="hero-actions">
              {availableDownload ? (
                <a
                  className="button primary"
                  href={availableDownload.asset.url}
                  download={availableDownload.asset.name}
                  onClick={() => trackDownload(availableDownload.platformId)}
                  title={`Download ${availableDownload.asset.name}`}
                >
                  <Icon name="download" />
                  Download
                </a>
              ) : (
                <button
                  className="button primary"
                  type="button"
                  disabled
                  title="Installer assets are still publishing"
                >
                  <Icon name="pulse" />
                  Download pending
                </button>
              )}
              <a className="button secondary" href={repoUrl}>
                <Icon name="star" />
                {github.stars == null ? "GitHub stars" : `${formatCount(starsCount)} stars`}
              </a>
            </div>
            <div className="hero-downloads" aria-label="Latest downloads">
              {platformOptions.map((platform) => (
                <PlatformDownload
                  key={platform.id}
                  platform={platform}
                  asset={release.assets?.[platform.id]}
                  releaseTag={release.tag}
                  onDownload={trackDownload}
                />
              ))}
            </div>
            {!hasReleaseAssets && (
              <div className="wait-note">
                <span className="spinner" />
                Installer assets are still publishing. Download controls will stay disabled until direct assets are ready.
              </div>
            )}
            <div className="live-counter" title={configured ? "Backed by the deployed view counter" : "Connect Upstash Redis on Vercel to persist this counter"}>
              <span className="live-dot" />
              <strong>{formatCount(viewsCount)}</strong>
              <span>unique launch views tracked live</span>
            </div>
            <div className="metric-strip">
              {[
                [github.stars == null ? "-" : formatCount(starsCount), "GitHub stars"],
                [github.pullRequests == null ? "-" : formatCount(prCount), "open PRs"],
                [formatCount(downloadsTotalCount), "total downloads"],
                [formatCount(viewsCount), "unique views"],
              ].map(([value, label]) => (
                <div key={label}>
                  <strong>{value}</strong>
                  <span>{label}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="hero-visual">
            <DeviceFrame src="/assets/screens/graph.webp" alt="JustHireMe knowledge graph view" tone="green" className="hero-visual-back" />
            <DeviceFrame src="/assets/screens/dashboard.webp" alt="JustHireMe dashboard view" tone="orange" className="hero-visual-front" />
          </div>
        </section>

        <section id="workflow" className="section band paper-2">
          <div className="section-head">
            <span className="eyebrow">How it actually works</span>
            <h2>Not a demo. This is the real product, screen by screen.</h2>
          </div>
          <ProductTour />
        </section>

        <section id="features" className="section band">
          <div className="section-head">
            <span className="eyebrow">What it does</span>
            <h2>Built for applicants who want signal, control, and speed.</h2>
          </div>
          <Reveal className="ledger ledger-2col">
            {features.map((feature) => (
              <article className="ledger-row" key={feature.title}>
                <span className={`feature-icon tone-${feature.tone}`}><Icon name={feature.icon} /></span>
                <div>
                  <h3>{feature.title}</h3>
                  <p>{feature.copy}</p>
                </div>
              </article>
            ))}
          </Reveal>
        </section>

        <section className="section band paper-2">
          <div className="section-head">
            <span className="eyebrow">Intelligence layer</span>
            <h2>Advanced matching, explained without the black box.</h2>
          </div>
          <Reveal>
            <IntelligenceMap />
          </Reveal>
          <div className="tech-strip">
            {["Scrapers", "JD embeddings", "Profile embeddings", "LanceDB", "SQLite CRM", "Kuzu graph", "Quality gates", "Semantic ranker"].map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
        </section>

        <section id="why-local" className="section split band paper-3">
          <div>
            <span className="eyebrow">Why local-first</span>
            <h2>Your job search should feel private, legible, and yours.</h2>
          </div>
          <Reveal className="principle-list">
            {principles.map((item) => (
              <div className="principle" key={item.term}>
                <span className="principle-mark"><Icon name="check" /></span>
                <div>
                  <strong>{item.term}</strong>
                  <p>{item.copy}</p>
                </div>
              </div>
            ))}
          </Reveal>
        </section>

        <section id="feedback" className="section band paper-2">
          <div className="section-head">
            <span className="eyebrow">Feedback</span>
            <h2>Tell me what to fix, polish, or keep exactly as it is.</h2>
          </div>
          <Reveal className="feedback-grid">
            <FeedbackCard
              kind="feedback"
              title="Feedback form"
              copy="Share bugs, rough edges, missing sources, installer issues, or workflow ideas."
              tone="blue"
            />
            <FeedbackCard
              kind="review"
              title="Review form"
              copy="Leave a public-product-style review with a rating and practical notes."
              tone="green"
            />
          </Reveal>
          <div className="support-callout">
            <div>
              <span className="eyebrow">Support the build</span>
              <h3>Fuel the open-source roadmap.</h3>
              <p>JustHireMe is built in public. Coffee helps keep releases, adapters, and docs moving.</p>
            </div>
            <a className="button primary" href={coffeeUrl}>
              <Icon name="coffee" />
              Buy me a coffee
            </a>
          </div>
        </section>

        <section id="release" className="section final-cta band">
          <Reveal className="final-cta-inner">
          <span className="eyebrow">Release status</span>
          <h2>{release.tag ? `${release.tag} downloads` : "Latest downloads"}</h2>
          <p>
            Download the latest public build. Stats stay live, and download links update from GitHub Releases automatically.
          </p>
          <div className="hero-downloads release-downloads" aria-label="Latest platform downloads">
            {platformOptions.map((platform) => (
              <PlatformDownload
                key={platform.id}
                platform={platform}
                asset={release.assets?.[platform.id]}
                releaseTag={release.tag}
                onDownload={trackDownload}
              />
            ))}
          </div>
          {!hasReleaseAssets && <ReleaseNoticeBanner release={release} />}
          <div className="download-proof">
            <Icon name="download" />
            <strong>{formatCount(downloadsTotalCount)}</strong>
            <span>tracked downloads</span>
          </div>
          <div className="download-breakdown">
            {platformOptions.map((platform) => (
              <span className={`tone-${platform.tone}`} key={platform.id}>
                {platform.label}
                <strong>{formatCount(downloadsByPlatform[platform.id] || 0)}</strong>
              </span>
            ))}
          </div>
          <div className="hero-actions centered">
            <a className="button primary" href={release.url || `${repoUrl}/releases`}><Icon name="external" /> GitHub release</a>
            <a className="button secondary" href={repoUrl}><Icon name="github" /> View source</a>
          </div>
          <div className="creator-links" aria-label="Creator links">
            <a href="https://vasudev.live">vasudev.live</a>
            <a href="https://x.com/vasu_devs">@vasu_devs</a>
            <a href={coffeeUrl}>Buy me a coffee</a>
          </div>
          </Reveal>
        </section>
      </main>

      <footer>
        <span>JustHireMe</span>
        <span className="footer-legal">
          <a href="/legal/terms-of-use.html">Terms</a>
          <a href="/legal/privacy-policy.html">Privacy</a>
        </span>
        <span>By Vasudev - vasudev.live - @vasu_devs - buymeacoffee.com/vasu.devs</span>
      </footer>
    </>
  );
}

const root = document.getElementById("root");

if (root) {
  createRoot(root).render(<App />);
}
