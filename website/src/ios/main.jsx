import React from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowRight,
  ArrowUpRight,
  BatteryFull,
  CellSignalFull,
  CheckCircle,
  GithubLogo,
  Plus,
  WifiHigh,
  XLogo,
} from "@phosphor-icons/react";
import "./ios.css";

// The iPhone beta waitlist page. Visual language is lifted from the iOS app
// (ios/JustHireMe/NotebookDesign.swift + Theme.swift): pencil-outline cards,
// crayon strokes, ruled paper, Instrument Serif / Instrument Sans, pastel tints.

const WAITLIST_LIST = "ios";
const SHOW_COUNT_FROM = 25; // below this a public count reads as empty, not as proof
const REPO_URL = "https://github.com/vasu-devs/JustHireMe";
const X_URL = "https://x.com/vasu_devs";
const CONTACT_EMAIL = "pls@justhireme.ai";

const steps = [
  {
    chapter: "01 / Profile",
    tint: "lavender",
    title: "Start with what you already have",
    body: "Drop in your resume, portfolio, notes or Markdown files. It sorts everything into sections, and you can edit any of them.",
    screen: { src: "/ios/import.webp", alt: "The Add content screen sorting a portfolio file into About, Experience, Education, Projects and Skills" },
  },
  {
    chapter: "02 / For you",
    tint: "mint",
    title: "See the jobs that fit you",
    body: "New roles from every field are checked against your profile. You only see the strong matches, with the skills behind each one.",
    screen: { src: "/ios/matches.webp", alt: "The Job matches screen listing a UX Designer role at 100% skill match and a Product Designer role at 75%" },
  },
  {
    chapter: "03 / Apply",
    tint: "sky",
    title: "Tap Apply now",
    body: "It tailors your resume to the role, fills in the form and emails you once it's sent. If a question needs your answer, it asks you first.",
    screen: { src: "/ios/apply.webp", alt: "A Product Designer role with its skills match and the Apply now button" },
  },
  {
    chapter: "04 / Applications",
    tint: "peach",
    title: "Know where every application stands",
    body: "Submitted, interviewing, offer or rejected. Every application and its history, in one place.",
    screen: { tracker: true, alt: "The Applications screen with a count of applications at each stage" },
  },
  {
    chapter: "05 / Grow",
    tint: "butter",
    title: "Learn what to work on next",
    body: "It looks at the skills your matches keep asking for that your profile doesn't have yet, and suggests what to practise.",
    screen: { src: "/ios/grow.webp", alt: "The What to work on screen suggesting Kubernetes, requested by 3 roles" },
  },
];

const plans = [
  { name: "One application", detail: "Pay once for a single application. No subscription.", tint: "card" },
  { name: "Weekly", detail: "A set number of applications each week. Cancel any time.", tint: "card" },
  { name: "Monthly", detail: "A larger allowance, renewed each month. Cancel any time.", tint: "lavender" },
];

const questions = [
  {
    q: "Is the desktop app still free?",
    a: "Yes. The open source desktop app stays free and keeps running on your own machine. The iPhone app is a separate, paid service for people who want the applying done for them.",
  },
  {
    q: "Will it apply to jobs without asking me?",
    a: "Only if you turn on auto-apply, and only within the roles, location and daily limit you set. You can pause it any time. Questions that need a personal answer come back to you.",
  },
  {
    q: "Which job sites can it apply on?",
    a: "At launch it applies through Greenhouse, Lever and Ashby application forms, with more to follow. Roles it can't apply to are marked, so you can apply yourself.",
  },
  {
    q: "When does the beta open?",
    a: "Soon. Everyone on the waitlist gets one email when it opens. No newsletter.",
  },
  {
    q: "What happens to my email?",
    a: "It's used to invite you to the beta and tell you when the app launches. Nothing else, and it's never sold or shared.",
  },
];

/* ---------- notebook primitives (mirroring NotebookDesign.swift) ---------- */

function PencilOutline() {
  // Same wobble as PencilOutline in SwiftUI, expressed in a 100x100 box.
  return (
    <svg className="pencil" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <path
        d="M3 1.2 Q50 -0.6 97 1.6 Q100.6 50 99.2 96.4 Q50 100.8 2.4 99 Q-0.8 50 3 1.2 Z"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function crayonPaths(width) {
  // Seven wavy passes, like CrayonStroke's Canvas loop.
  return Array.from({ length: 7 }, (_, row) => {
    const y = row * 2 + 2;
    let d = `M${(row % 3) * 2} ${y}`;
    for (let x = 0; x <= width; x += 7) {
      d += ` L${x} ${(y + Math.sin((x + row * 9) * 0.08) * 1.5).toFixed(2)}`;
    }
    return d;
  });
}

function CrayonStroke({ tint = "lavender", width = 120, className = "" }) {
  const paths = React.useMemo(() => crayonPaths(width), [width]);
  return (
    <svg
      className={`crayon crayon-${tint} ${className}`}
      viewBox={`0 0 ${width} 18`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {paths.map((d, i) => <path key={i} d={d} pathLength="1" style={{ "--i": i }} />)}
    </svg>
  );
}

function NotebookCard({ tint = "card", ruled = false, className = "", children, ...rest }) {
  return (
    <div className={`nb-card tint-${tint} ${ruled ? "ruled" : ""} ${className}`} {...rest}>
      {children}
      <PencilOutline />
    </div>
  );
}

function Chapter({ label, tint }) {
  return (
    <span className="chapter">
      {label}
      <CrayonStroke tint={tint} width={42} className="chapter-stroke" />
    </span>
  );
}

/* ---------- phone ---------- */

function StatusBar() {
  return (
    <div className="status-bar" aria-hidden="true">
      <span>9:41</span>
      <span className="status-icons">
        <CellSignalFull weight="fill" />
        <WifiHigh weight="bold" />
        <BatteryFull weight="fill" />
      </span>
    </div>
  );
}

function TrackerScreen() {
  // A static rendering of the Applications tab (ApplicationTrackerView) with sample data.
  const rows = [
    { label: "Submitted", count: 14, tint: "sky" },
    { label: "Interviewing", count: 3, tint: "mint" },
    { label: "Offer", count: 1, tint: "butter" },
    { label: "Rejected", count: 5, tint: "peach" },
  ];
  const max = Math.max(...rows.map((row) => row.count));
  return (
    <div className="app-screen">
      <div className="app-nav">Applications</div>
      <div className="app-body">
        <Chapter label="03 / Tracker" tint="peach" />
        <h4 className="app-title">Your applications</h4>
        <p className="app-sub">Track responses, interviews and offers.</p>
        <NotebookCard ruled className="app-chart">
          <strong className="app-total">23 <span>applications</span></strong>
          {rows.map((row) => (
            <div className="app-bar-row" key={row.label}>
              <span>{row.label}</span>
              <i className={`app-bar tint-${row.tint}`} style={{ width: `${(row.count / max) * 100}%` }} />
              <b>{row.count}</b>
            </div>
          ))}
        </NotebookCard>
        {[
          { status: "Interviewing", role: "Product Designer", company: "Northstar", tint: "mint" },
          { status: "Submitted", role: "UX Designer", company: "Moss", tint: "sky" },
          { status: "Rejected", role: "Design Engineer", company: "Fieldnote", tint: "peach" },
        ].map((item) => (
          <NotebookCard key={item.role} tint={item.tint} className="app-item">
            <span className="app-item-status">{item.status}</span>
            <strong>{item.role}</strong>
            <span className="app-item-meta">{item.company}</span>
          </NotebookCard>
        ))}
      </div>
      <div className="app-tabs" aria-hidden="true">
        {["Profile", "For You", "Applications", "Grow", "Plan"].map((tab) => (
          <span key={tab} className={tab === "Applications" ? "active" : ""}>{tab}</span>
        ))}
      </div>
    </div>
  );
}

function Phone({ screen, className = "", eager = false }) {
  return (
    <figure className={`phone ${className}`}>
      <div className="phone-glass">
        <StatusBar />
        {screen.tracker ? (
          <div role="img" aria-label={screen.alt}><TrackerScreen /></div>
        ) : (
          <img src={screen.src} alt={screen.alt} width="603" height="1170" loading={eager ? "eager" : "lazy"} decoding="async" />
        )}
      </div>
    </figure>
  );
}

/* ---------- waitlist ---------- */

function signupSource() {
  try {
    const params = new URLSearchParams(window.location.search);
    const tagged = params.get("ref") || params.get("utm_source");
    if (tagged) return tagged;
    const host = document.referrer ? new URL(document.referrer).hostname : "";
    if (/(^|\.)(t\.co|x\.com|twitter\.com)$/.test(host)) return "x";
    if (host.endsWith("linkedin.com")) return "linkedin";
    if (host && host !== window.location.hostname) return host.replace(/^www\./, "");
  } catch {
    // An unreadable referrer just means we don't know the source.
  }
  return "direct";
}

const WaitlistContext = React.createContext(null);

function WaitlistProvider({ children }) {
  const [count, setCount] = React.useState(null);
  const [joined, setJoined] = React.useState(null); // null | "new" | "already"

  React.useEffect(() => {
    let cancelled = false;
    fetch(`/api/waitlist?list=${WAITLIST_LIST}`)
      .then((response) => response.json())
      .then((payload) => {
        if (!cancelled && typeof payload.count === "number") setCount(payload.count);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const join = React.useCallback(async (email, website) => {
    const response = await fetch("/api/waitlist", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, website, list: WAITLIST_LIST, source: signupSource() }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "Couldn't save your email. Try again in a minute.");
    if (payload.configured === false) throw new Error("Sign-ups aren't switched on yet. Try again soon.");
    if (typeof payload.count === "number") setCount(payload.count);
    setJoined(payload.already ? "already" : "new");
  }, []);

  const value = React.useMemo(() => ({ count, joined, join }), [count, joined, join]);
  return <WaitlistContext.Provider value={value}>{children}</WaitlistContext.Provider>;
}

function WaitlistForm({ id, size = "large" }) {
  const { count, joined, join } = React.useContext(WaitlistContext);
  const [email, setEmail] = React.useState("");
  const [website, setWebsite] = React.useState("");
  const [error, setError] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const inputId = `${id}-email`;
  const errorId = `${id}-error`;

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email.trim())) {
      setError("Enter a valid email address, like you@example.com.");
      return;
    }
    setSubmitting(true);
    try {
      await join(email.trim(), website);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (joined) {
    return (
      <div className={`waitlist-done ${size}`} role="status">
        <CheckCircle weight="fill" aria-hidden="true" />
        <div>
          <strong>{joined === "already" ? "You're already on the list." : "You're on the list."}</strong>
          <span>We'll email you once when the beta opens.</span>
        </div>
      </div>
    );
  }

  return (
    <form className={`waitlist-form ${size}`} onSubmit={submit} noValidate>
      <label htmlFor={inputId}>Email</label>
      <div className="waitlist-row">
        <input
          id={inputId}
          type="email"
          inputMode="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          aria-invalid={error ? "true" : undefined}
          aria-describedby={error ? errorId : undefined}
          required
        />
        <button type="submit" className="nb-button" disabled={submitting}>
          <span>{submitting ? "Joining" : "Join the beta"}</span>
          <ArrowRight weight="bold" aria-hidden="true" />
        </button>
      </div>
      <input
        className="honeypot"
        tabIndex={-1}
        autoComplete="off"
        aria-hidden="true"
        name="website"
        value={website}
        onChange={(event) => setWebsite(event.target.value)}
      />
      {error ? (
        <p className="form-error" id={errorId} role="alert">{error}</p>
      ) : (
        <p className="form-note">
          {count != null && count >= SHOW_COUNT_FROM ? `${count.toLocaleString()} people are on the list. ` : ""}
          One email when it opens. No newsletter.
        </p>
      )}
    </form>
  );
}

/* ---------- sections ---------- */

function Header() {
  return (
    <header className="site-header">
      <a className="brand" href="/ios/" aria-label="JustHireMe for iPhone">
        <img src="/favicon.svg" alt="" width="28" height="28" />
        <span>JustHireMe</span>
      </a>
      <nav className="header-nav" aria-label="Primary">
        <a href="#how">How it works</a>
        <a href="#plans">Pricing</a>
        <a href="/" className="hide-sm">Desktop app</a>
      </nav>
      <a className="header-cta" href="#join">Join the beta</a>
    </header>
  );
}

function Hero() {
  return (
    <section className="hero" aria-labelledby="hero-title">
      <NotebookCard ruled className="hero-sheet">
        <div className="hero-copy">
          <Chapter label="iPhone beta" tint="lavender" />
          <h1 id="hero-title">
            Your job hunt, <em className="underlined">handled.<CrayonStroke tint="lavender" width={160} className="headline-stroke" /></em>
          </h1>
          <p className="hero-sub">
            Upload your resume once. JustHireMe finds roles that fit, tailors your resume and applies for you.
          </p>
          <WaitlistForm id="hero" />
        </div>
      </NotebookCard>
      <div className="hero-phone">
        <Phone screen={steps[1].screen} eager />
      </div>
    </section>
  );
}

function HowItWorks() {
  const [active, setActive] = React.useState(0);
  const stepRefs = React.useRef([]);

  React.useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setActive(Number(entry.target.dataset.index));
        });
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    stepRefs.current.forEach((node) => node && observer.observe(node));
    return () => observer.disconnect();
  }, []);

  return (
    <section className="how" id="how" aria-labelledby="how-title">
      <h2 id="how-title" className="section-title">From a resume to applications, in five screens.</h2>
      <div className="how-grid">
        <div className="how-phone" aria-hidden="true">
          <div className="phone-stack">
            {steps.map((step, index) => (
              <Phone key={step.chapter} screen={step.screen} className={index === active ? "is-active" : ""} />
            ))}
            <p className="sample-note stack-note" data-visible={steps[active].screen.tracker ? "true" : "false"}>Sample data</p>
          </div>
        </div>
        <ol className="how-steps">
          {steps.map((step, index) => (
            <li
              key={step.chapter}
              data-index={index}
              ref={(node) => { stepRefs.current[index] = node; }}
              className={`how-step ${index === active ? "is-active" : ""}`}
            >
              <NotebookCard tint={step.tint}>
                <Chapter label={step.chapter} tint={step.tint} />
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </NotebookCard>
              <Phone screen={step.screen} className="inline-phone" />
              {step.screen.tracker && <p className="sample-note">Sample data</p>}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function AutoApply() {
  const rules = [
    ["Roles", "Product Designer, UX Designer"],
    ["Location", "Remote"],
    ["Minimum skill overlap", "75%"],
    ["Daily limit", "Up to 2 a day"],
  ];
  return (
    <section className="auto" aria-labelledby="auto-title">
      <div className="auto-copy">
        <h2 id="auto-title" className="section-title">Or let it apply while you get on with your day.</h2>
        <p>
          Turn on auto-apply and set the rules: which roles, where, how close a match, and how many a day.
          It stays inside them, skips duplicates and never goes over your allowance. Pause it any time.
        </p>
      </div>
      <NotebookCard tint="butter" className="auto-card">
        <div className="auto-card-head">
          <strong>Auto-apply</strong>
          <span className="toggle" role="img" aria-label="Switched on"><i /></span>
        </div>
        <dl>
          {rules.map(([term, value]) => (
            <div key={term}>
              <dt>{term}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        <p className="auto-card-foot">Only these roles and this location qualify. Turn it off at any time.</p>
      </NotebookCard>
    </section>
  );
}

function Plans() {
  return (
    <section className="plans" id="plans" aria-labelledby="plans-title">
      <div className="plans-copy">
        <h2 id="plans-title" className="section-title">Pay for applications, not features.</h2>
        <p>
          Every plan includes the full app. You only choose how many applications you want.
          One-tap and auto-apply share the same allowance.
        </p>
        <p className="plans-note">Prices will be announced when the beta opens.</p>
      </div>
      <ul className="plan-list">
        {plans.map((plan) => (
          <li key={plan.name}>
            <NotebookCard tint={plan.tint} className="plan">
              <div>
                <strong>{plan.name}</strong>
                <span>{plan.detail}</span>
              </div>
            </NotebookCard>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Questions() {
  return (
    <section className="faq" aria-labelledby="faq-title">
      <NotebookCard ruled className="faq-sheet">
        <h2 id="faq-title" className="section-title">Questions</h2>
        {questions.map((item) => (
          <details key={item.q}>
            <summary>
              <span>{item.q}</span>
              <Plus weight="bold" aria-hidden="true" />
            </summary>
            <p>{item.a}</p>
          </details>
        ))}
      </NotebookCard>
    </section>
  );
}

function FinalCall() {
  return (
    <section className="final" id="join" aria-labelledby="final-title">
      <NotebookCard tint="lavender" className="final-card">
        <h2 id="final-title">Be one of the first to use it.</h2>
        <p>Leave your email and we'll send your invite when the beta opens.</p>
        <WaitlistForm id="final" size="compact" />
      </NotebookCard>
    </section>
  );
}

function Footer() {
  return (
    <footer className="site-footer">
      <span>JustHireMe</span>
      <nav aria-label="Footer">
        <a href="/">Desktop app</a>
        <a href={REPO_URL}><GithubLogo aria-hidden="true" /> GitHub</a>
        <a href={X_URL}><XLogo aria-hidden="true" /> @vasu_devs</a>
        <a href="/legal/privacy-policy.html">Privacy</a>
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL} <ArrowUpRight aria-hidden="true" /></a>
      </nav>
    </footer>
  );
}

function App() {
  return (
    <WaitlistProvider>
      <Header />
      <main>
        <Hero />
        <HowItWorks />
        <AutoApply />
        <Plans />
        <Questions />
        <FinalCall />
      </main>
      <Footer />
    </WaitlistProvider>
  );
}

createRoot(document.getElementById("root")).render(<App />);
