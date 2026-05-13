// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Vasudev Siddh and vasu-devs

import React from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const repoUrl = "https://github.com/vasu-devs/JustHireMe";
const coffeeUrl = "https://buymeacoffee.com/vasu.devs";
const releaseNotice = {
  title: "A new JustHireMe version is releasing soon.",
  copy: "The current public build has a few known issues, so I am holding downloads while the next version is polished. Please bookmark this page and come back soon, or leave feedback with your email and I will send a note when the new version drops.",
};

const navItems = ["Workflow", "Why local", "Features", "Feedback", "Release"];

const pipeline = [
  { status: "Leads", count: 128, tone: "blue" },
  { status: "Ranked", count: 42, tone: "yellow" },
  { status: "Drafts", count: 16, tone: "purple" },
];

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

const story = [
  {
    title: "Noise out",
    copy: "Bad roles never make it into the system.",
    tone: "yellow",
  },
  {
    title: "Signal in",
    copy: "Every match is scored with visible reasons.",
    tone: "blue",
  },
  {
    title: "Draft ready",
    copy: "Application material is prepared for review.",
    tone: "green",
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
  "Local-first data",
  "Explainable scoring",
  "Human review",
  "Source-available",
];

const systemSignals = [
  ["JD vectors", "purple"],
  ["Profile graph", "green"],
  ["Quality gate", "yellow"],
  ["CRM memory", "blue"],
];

const platformOptions = [
  { id: "windows", label: "Windows", hint: "Installer", tone: "blue" },
  { id: "mac", label: "macOS", hint: "DMG / PKG", tone: "purple" },
  { id: "linux", label: "Linux", hint: "AppImage / package", tone: "green" },
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

function PlatformDownload({ platform, asset, releaseTag, releaseUrl, onDownload }) {
  const available = Boolean(asset?.url);
  const fallbackUrl = releaseUrl || `${repoUrl}/releases`;
  const href = available ? asset.url : fallbackUrl;
  const title = available ? `Download ${asset.name}` : `Open all JustHireMe releases for ${platform.label}`;
  const content = (
    <>
      <Icon name={available ? "download" : "external"} />
      <span>
        <strong>{platform.label}</strong>
        <small>{available ? (releaseTag || "Latest release") : "View releases"}</small>
      </span>
    </>
  );

  return (
    <a
      className={`platform-button tone-${platform.tone}`}
      href={href}
      onClick={() => available && onDownload(platform.id)}
      title={title}
    >
      {content}
    </a>
  );
}

function ReleaseNoticeBanner({ compact = false }) {
  return (
    <div className={`release-notice ${compact ? "compact" : ""}`} role="status" aria-live="polite">
      <span className="release-notice-icon"><Icon name="pulse" /></span>
      <div>
        <strong>{releaseNotice.title}</strong>
        <p>{releaseNotice.copy}</p>
      </div>
      <a className="button primary" href="#feedback">
        <Icon name="message" />
        Leave feedback
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
      const payload = await cachedFetchJson("justhireme.release", "/api/releases");
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

function WorkflowAsset() {
  const steps = [
    ["Profile", "user", "green"],
    ["Leads", "layers", "blue"],
    ["Score", "graph", "purple"],
    ["Draft", "file", "orange"],
  ];

  return (
    <div className="workflow-asset" aria-label="Animated JustHireMe workflow">
      {steps.map(([label, icon, tone], index) => (
        <React.Fragment key={label}>
          <div className={`flow-chip tone-${tone}`}>
            <Icon name={icon} />
            <span>{label}</span>
          </div>
          {index < steps.length - 1 && <span className="flow-arrow" />}
        </React.Fragment>
      ))}
    </div>
  );
}

function IntelligenceMap() {
  return (
    <div className="intel-map" aria-label="JustHireMe intelligence system">
      <div className="intel-center">
        <Icon name="logo" />
        <strong>Local match engine</strong>
        <span>Profile graph + embeddings + CRM</span>
      </div>
      {intelligence.map((item, index) => (
        <article className={`intel-node intel-node-${index + 1} tone-${item.tone}`} key={item.title}>
          <span className="feature-icon"><Icon name={item.icon} /></span>
          <div>
            <h3>{item.title}</h3>
            <p>{item.copy}</p>
          </div>
        </article>
      ))}
    </div>
  );
}

function MiniApp() {
  return (
    <div className="app-preview" aria-label="JustHireMe product preview">
      <aside className="preview-sidebar">
        <div className="brand-mini"><Icon name="logo" /><span>JustHireMe</span></div>
        {["Customize", "Dashboard", "Leads", "Job Pipeline", "Knowledge"].map((item, index) => (
          <div className={`preview-nav ${index === 3 ? "active" : ""}`} key={item}>
            <span className={`nav-dot tone-${["green", "blue", "orange", "purple", "teal"][index]}`} />
            {item}
          </div>
        ))}
        <div className="preview-status">
          <span className="live-dot" />
          Local agent ready
          <small>release waiting</small>
        </div>
      </aside>
      <main className="preview-main">
        <div className="preview-top">
          <div>
            <span className="eyebrow">Pipeline</span>
            <h3>Signal-first job hunt</h3>
          </div>
          <button className="tiny-button"><Icon name="spark" /> Scan</button>
        </div>
        <div className="score-card">
          <div>
            <span className="eyebrow">Today</span>
            <strong>3 high-fit roles</strong>
            <small>2 drafts ready for review</small>
          </div>
          <span className="score-ring">94</span>
        </div>
        <div className="system-signals" aria-label="Matching signals">
          {systemSignals.map(([label, tone]) => (
            <span className={`tone-${tone}`} key={label}>{label}</span>
          ))}
        </div>
        <div className="preview-grid">
          {pipeline.map((item) => (
            <div className={`metric tone-${item.tone}`} key={item.status}>
              <strong>{item.count}</strong>
              <span>{item.status}</span>
            </div>
          ))}
        </div>
        <div className="job-list">
          {[
            ["Founding Engineer", "Remote - Product infra - 94%"],
            ["AI Tools Engineer", "Hybrid - TypeScript - 88%"],
            ["Full-stack Builder", "Remote - public-build friendly - 82%"],
          ].map(([title, meta], index) => (
            <div className="job-row" key={title}>
              <span className={`job-mark tone-${["green", "purple", "orange"][index]}`}>{title[0]}</span>
              <div>
                <strong>{title}</strong>
                <small>{meta}</small>
              </div>
              <span className="review-pill">review</span>
            </div>
          ))}
        </div>
        <div className="preview-docs">
          <div className="doc-card resume-doc">
            <span className="doc-icon"><Icon name="file" /></span>
            <strong>Tailored resume</strong>
            <small>Projects matched to role evidence</small>
            <div className="doc-lines"><i /><i /><i /></div>
          </div>
          <div className="doc-card outreach-doc">
            <span className="doc-icon"><Icon name="pulse" /></span>
            <strong>Outreach draft</strong>
            <small>Founder note + LinkedIn variant</small>
            <div className="doc-lines"><i /><i /><i /></div>
          </div>
        </div>
      </main>
    </div>
  );
}

function App() {
  const { views, configured } = useViewCounter();
  const { downloads } = useDownloadCounter();
  const github = useGitHubStars();

  return (
    <>
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
              A local-first workbench that turns noisy job hunting into a clear, reviewable pipeline.
            </p>
            <div className="proof-line">
              <span>Semantic matching</span>
              <span>Built in public</span>
              <span>Desktop-first</span>
            </div>
            <div className="hero-actions">
              <a className="button primary" href="#feedback" title="Leave feedback and your email for the next release note">
                <Icon name="message" />
                Notify me
              </a>
              <a className="button secondary" href={repoUrl}>
                <Icon name="star" />
                {github.stars == null ? "GitHub stars" : `${formatCount(github.stars)} stars`}
              </a>
            </div>
            <ReleaseNoticeBanner compact />
            <div className="live-counter" title={configured ? "Backed by the deployed view counter" : "Connect Upstash Redis on Vercel to persist this counter"}>
              <span className="live-dot" />
              <strong>{formatCount(views)}</strong>
              <span>unique launch views tracked live</span>
            </div>
            <div className="metric-strip">
              {[
                [github.stars == null ? "-" : formatCount(github.stars), "GitHub stars"],
                [github.pullRequests == null ? "-" : formatCount(github.pullRequests), "open PRs"],
                [formatCount(downloads.total), "total downloads"],
                [formatCount(views), "unique views"],
              ].map(([value, label]) => (
                <div key={label}>
                  <strong>{value}</strong>
                  <span>{label}</span>
                </div>
              ))}
            </div>
          </div>
          <MiniApp />
        </section>

        <section id="workflow" className="section band paper-2">
          <div className="section-head">
            <span className="eyebrow">Workflow</span>
            <h2>Find the role. Understand the fit. Ship the application.</h2>
          </div>
          <WorkflowAsset />
          <div className="story-grid">
            {story.map((item) => (
              <article className={`story-card tone-${item.tone}`} key={item.title}>
                <h3>{item.title}</h3>
                <p>{item.copy}</p>
              </article>
            ))}
          </div>
          <div className="workflow">
            {["Import profile", "Collect leads", "Quality gate", "Rank fit", "Tailor drafts"].map((step, index) => (
              <div className="workflow-step" key={step}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{step}</strong>
              </div>
            ))}
          </div>
        </section>

        <section id="features" className="section band">
          <div className="section-head">
            <span className="eyebrow">What it does</span>
            <h2>Built for applicants who want signal, control, and speed.</h2>
          </div>
          <div className="feature-grid">
            {features.map((feature) => (
              <article className={`feature tone-${feature.tone}`} key={feature.title}>
                <span className="feature-icon"><Icon name={feature.icon} /></span>
                <h3>{feature.title}</h3>
                <p>{feature.copy}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="section band paper-2">
          <div className="section-head">
            <span className="eyebrow">Intelligence layer</span>
            <h2>Advanced matching, explained without the black box.</h2>
          </div>
          <IntelligenceMap />
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
          <div className="principle-list">
            {principles.map((item) => (
              <div className="principle" key={item}>
                <Icon name="check" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </section>

        <section id="feedback" className="section band paper-2">
          <div className="section-head">
            <span className="eyebrow">Feedback</span>
            <h2>Tell me what to fix, polish, or keep exactly as it is.</h2>
          </div>
          <div className="feedback-grid">
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
          </div>
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
          <span className="eyebrow">Release status</span>
          <h2>New build coming soon.</h2>
          <p>
            The current public version has known issues, so downloads are paused until the next cleaner release is ready.
          </p>
          <ReleaseNoticeBanner />
          <div className="hero-actions centered">
            <a className="button primary" href="#feedback"><Icon name="message" /> Drop feedback</a>
            <a className="button secondary" href={repoUrl}><Icon name="github" /> View source</a>
          </div>
          <div className="creator-links" aria-label="Creator links">
            <a href="https://vasudev.live">vasudev.live</a>
            <a href="https://x.com/vasu_devs">@vasu_devs</a>
            <a href={coffeeUrl}>Buy me a coffee</a>
          </div>
        </section>
      </main>

      <footer>
        <span>JustHireMe</span>
        <span>By Vasudev - vasudev.live - @vasu_devs - buymeacoffee.com/vasu.devs</span>
      </footer>
    </>
  );
}

const root = document.getElementById("root");

if (root) {
  createRoot(root).render(<App />);
}
