// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Vasudev Siddh and vasu-devs
//
// DEV-ONLY visual preview harness. Mounts the REAL app shell and views with
// seeded data and a mocked API so the interface can be reviewed (and
// screenshot-tested) in a plain browser, where the Tauri sidecar isn't
// available. Never bundled in production: main.tsx only reaches this module
// behind `import.meta.env.DEV`.
//
// URL contract (for humans and Playwright alike):
//   /?preview=1&view=dashboard|pipeline|graph|activity|profile|ingestion|apply
//              &theme=light|dark   &drawer=1   &chrome=0

import { useEffect, useMemo, useState } from "react";
import type { ApiFetch, Lead, LogLine, View, GraphStats, OperationProgress } from "../types";
import { Sidebar } from "../shared/components/Sidebar";
import { Topbar } from "../shared/components/Topbar";
import ErrorBoundary from "../shared/components/ErrorBoundary";
import { DashboardView } from "../features/dashboard/DashboardView";
import { PipelineView } from "../features/pipeline/PipelineView";
import { GraphView } from "../features/graph/GraphView";
import { ActivityView } from "../features/activity/ActivityView";
import { ProfileView } from "../features/profile/ProfileView";
import { IngestionView } from "../features/profile/IngestionView";
import { ApplyJobView } from "../features/apply/ApplyJobView";
import { ApprovalDrawer } from "../features/pipeline/components/ApprovalDrawer";
import { HelpChat } from "../shared/components/HelpChat";

const noop = () => {};
const asyncNoop = async () => {};

/* ── seeded leads: statuses across the whole pipeline, fields across the
      whole market (the product is field-agnostic — the preview should be too) ── */
const LEADS: Lead[] = [
  {
    job_id: "pv-1", title: "Senior Product Engineer", company: "Northbeam Systems",
    url: "https://example.com/jobs/northbeam", platform: "ashby", status: "tailoring", asset: "",
    score: 91, signal_score: 88, reason: "Agent-tooling overlap with three shipped projects",
    description: "Own the workbench surface of a local-first developer tool. TypeScript, Rust bridge, real users.",
    match_points: ["TypeScript", "Tauri", "Local-first architecture"], gaps: ["GraphQL"],
    tech_stack: ["TypeScript", "Rust", "React"], location: "Amsterdam · hybrid",
    seniority_level: "senior", source_meta: { seniority_level: "senior" },
  },
  {
    job_id: "pv-2", title: "Registered Nurse — ICU nights", company: "Halcyon Health Group",
    url: "https://example.com/jobs/halcyon", platform: "workable", status: "approved", asset: "",
    score: 87, signal_score: 82, reason: "Certifications and unit experience match the posting exactly",
    description: "Level-2 ICU, 3x12 shifts, night differential. BLS/ACLS required.",
    match_points: ["ICU experience", "ACLS", "Night shifts"], gaps: [],
    location: "Manchester · onsite", seniority_level: "mid", source_meta: { seniority_level: "mid" },
  },
  {
    job_id: "pv-3", title: "AI Infrastructure Engineer", company: "Fieldstone Labs",
    url: "https://example.com/jobs/fieldstone", platform: "greenhouse", status: "discovered", asset: "",
    score: 0, signal_score: 84, reason: "",
    description: "Inference orchestration for on-device models. ONNX, quantization, embedded vector stores.",
    match_points: [], gaps: [], tech_stack: ["Python", "ONNX"], location: "Remote · EU",
    seniority_level: "mid", source_meta: { seniority_level: "mid" },
  },
  {
    job_id: "pv-4", title: "Pipe Welder — offshore rotation", company: "Meridian Fabrication",
    url: "https://example.com/jobs/meridian", platform: "rss", status: "evaluating", asset: "",
    score: 0, signal_score: 71, reason: "",
    description: "6G certified pipe welding, 4/4 rotation, medical and travel covered.",
    match_points: [], gaps: [], location: "Stavanger · rotation",
    seniority_level: "senior", source_meta: { seniority_level: "senior" },
  },
  {
    job_id: "pv-5", title: "Design Engineer", company: "Quiet Harbor",
    url: "https://example.com/jobs/quietharbor", platform: "lever", status: "applied", asset: "resume.pdf",
    resume_asset: "resume.pdf", cover_letter_asset: "cover.pdf",
    score: 78, signal_score: 74, reason: "Portfolio overlap on editor tooling; weaker on motion work",
    description: "Design-minded engineer for a small analytics product.",
    match_points: ["React", "Design systems"], gaps: ["Motion design"],
    location: "Berlin · hybrid", seniority_level: "mid",
    followup_due_at: new Date(Date.now() + 86400000).toISOString(),
    events: [{ action: "applied", ts: new Date(Date.now() - 3 * 86400000).toISOString() }],
    source_meta: { seniority_level: "mid" },
  },
  {
    job_id: "pv-6", title: "Staff Frontend Engineer", company: "Larkspur",
    url: "https://example.com/jobs/larkspur", platform: "ashby", status: "interviewing", asset: "",
    score: 83, signal_score: 79, reason: "Deep component-system experience; scale story is thinner",
    description: "Own the design-system and editor performance track.",
    match_points: ["React", "Performance"], gaps: ["Team lead experience"],
    location: "Remote · EU", seniority_level: "senior", source_meta: { seniority_level: "senior" },
  },
  {
    job_id: "pv-7", title: "Growth Marketer", company: "Sable & Co",
    url: "https://example.com/jobs/sable", platform: "hn", status: "discarded", asset: "",
    score: 22, signal_score: 31, reason: "Cross-field mismatch: marketing role against an engineering profile",
    description: "Own paid and lifecycle marketing.",
    match_points: [], gaps: ["Paid acquisition", "Lifecycle tooling"],
    location: "Remote", seniority_level: "mid", source_meta: { seniority_level: "mid" },
  },
];

const LOGS: LogLine[] = [
  { id: 1, ts: "09:14", msg: "Scan started — 9 keyless sources", src: "scout", kind: "system" },
  { id: 2, ts: "09:15", msg: "ATS aggregator returned 41 raw postings", src: "scout", kind: "agent" },
  { id: 3, ts: "09:15", msg: "Quality gate rejected 12 (stale: 7, thin: 4, spam: 1)", src: "gate", kind: "agent" },
  { id: 4, ts: "09:16", msg: "Ranked 29 leads against profile graph — 3 above 80", src: "ranker", kind: "agent" },
  { id: 5, ts: "09:18", msg: "Tailored resume v3 generated for Northbeam Systems", src: "customizer", kind: "agent" },
  { id: 6, ts: "09:18", msg: "Scan complete in 3m 41s", src: "scout", kind: "system" },
];

const STATS: GraphStats = {
  candidate: 1, skill: 12, project: 4, experience: 3, joblead: 7,
  available: true, status: "live", loaded: true,
  sync: { status: "ok", synced: 27, refreshed_at: new Date().toISOString() },
  graph: {
    available: true,
    // NOTE: GraphCanvas expects capitalized types (Candidate/Skill/Project/
    // Experience/Credential) and hides JobLead — lowercase renders nothing.
    nodes: [
      { id: "you", label: "You", type: "Candidate" },
      { id: "s1", label: "TypeScript", type: "Skill" }, { id: "s2", label: "Rust", type: "Skill" },
      { id: "s3", label: "Python", type: "Skill" }, { id: "s4", label: "React", type: "Skill" },
      { id: "s5", label: "FastAPI", type: "Skill" }, { id: "s6", label: "Graph databases", type: "Skill" },
      { id: "p1", label: "Realtime collab editor", type: "Project", subtitle: "TypeScript · CRDTs" },
      { id: "p2", label: "GraphRAG inference engine", type: "Project", subtitle: "Python · Kùzu" },
      { id: "p3", label: "Design system at scale", type: "Project", subtitle: "React" },
      { id: "e1", label: "Software Engineer @ Nimbus", type: "Experience" },
      { id: "e2", label: "Full-Stack Engineer @ Beacon", type: "Experience" },
      { id: "c1", label: "BSc Computer Science", type: "Credential", subtitle: "in progress" },
    ],
    edges: [
      { source: "you", target: "s1", type: "HAS_SKILL" }, { source: "you", target: "s2", type: "HAS_SKILL" },
      { source: "you", target: "s3", type: "HAS_SKILL" }, { source: "you", target: "s4", type: "HAS_SKILL" },
      { source: "you", target: "s5", type: "HAS_SKILL" }, { source: "you", target: "s6", type: "HAS_SKILL" },
      { source: "you", target: "p1", type: "BUILT" }, { source: "you", target: "p2", type: "BUILT" },
      { source: "you", target: "p3", type: "BUILT" },
      { source: "you", target: "e1", type: "WORKED" }, { source: "you", target: "e2", type: "WORKED" },
      { source: "you", target: "c1", type: "EARNED" },
      { source: "p1", target: "s1", type: "USES" }, { source: "p2", target: "s3", type: "USES" },
      { source: "p3", target: "s4", type: "USES" },
    ],
  },
  embedding: {
    available: true,
    points: [
      { id: "you", label: "Vasudev Siddh", type: "Candidate", x: 0.02, y: 0.05 },
      { id: "ed1", label: "BSc Computer Science", type: "Education", x: -0.42, y: 0.31 },
      { id: "a1", label: "Shipped a production platform solo", type: "Achievement", x: 0.36, y: -0.22 },
      { id: "a2", label: "10x faster shortlist pipeline", type: "Achievement", x: 0.48, y: 0.12 },
      { id: "a3", label: "7.4s dashboard cold start", type: "Achievement", x: 0.31, y: 0.4 },
      { id: "a4", label: "4-model schema migration", type: "Achievement", x: -0.18, y: -0.45 },
      { id: "x1", label: "Software Engineer @ Nimbus", type: "Experience", x: -0.3, y: -0.12 },
      { id: "x2", label: "Full-Stack Engineer @ Beacon", type: "Experience", x: -0.5, y: 0.05 },
      { id: "pr1", label: "Founder profile", type: "Profile", x: 0.12, y: 0.52 },
      { id: "p1", label: "Realtime collab editor", type: "Project", x: 0.55, y: -0.35 },
      { id: "p2", label: "GraphRAG inference engine", type: "Project", x: -0.08, y: 0.33 },
      { id: "s1", label: "TypeScript", type: "Skill", x: 0.2, y: -0.05 },
      { id: "s2", label: "Rust", type: "Skill", x: 0.14, y: 0.18 },
      { id: "s3", label: "Python", type: "Skill", x: -0.12, y: 0.1 },
      { id: "c1", label: "AWS Cloud Practitioner", type: "Credential", x: -0.35, y: 0.48 },
      { id: "c2", label: "Deep Learning Specialization", type: "Credential", x: 0.42, y: 0.55 },
    ],
  },
};

const PROFILE = {
  n: "Vasudev Siddh",
  skills: [
    { n: "TypeScript", cat: "technical" }, { n: "Rust", cat: "technical" },
    { n: "Python", cat: "technical" }, { n: "React", cat: "technical" },
    { n: "FastAPI", cat: "technical" }, { n: "Graph databases", cat: "technical" },
    { n: "Vector search", cat: "technical" }, { n: "Technical writing", cat: "soft" },
  ],
  projects: [
    { n: "Realtime collab editor", desc: "CRDT-based multiplayer editing", stack: ["TypeScript"] },
    { n: "GraphRAG inference engine", desc: "Profile graph retrieval over Kùzu", stack: ["Python"] },
    { n: "Design system at scale", desc: "Tokenized component library", stack: ["React"] },
  ],
  exp: [
    { role: "Software Engineer", company: "Nimbus", years: "2024–2025" },
    { role: "Full-Stack Engineer", company: "Beacon", years: "2023–2024" },
  ],
};

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });

const mockApi: ApiFetch = async (path) => {
  if (path.startsWith("/api/v1/profile")) return json(PROFILE);
  if (path.startsWith("/api/v1/leads")) return json(LEADS);
  if (path.startsWith("/api/v1/followups")) return json([]);
  if (path.startsWith("/api/v1/help/chat")) {
    return json({ answer: "This is the preview harness, so I'm a canned reply — but in the real app I answer from the local docs. Try asking how scanning or tailoring works." });
  }
  return json({});
};

const PROGRESS: OperationProgress = { active: false, mode: null, total: 0, completed: 0, current: "", updatedAt: 0 };

const VIEWS: View[] = ["dashboard", "pipeline", "graph", "activity", "profile", "ingestion", "apply"];

export default function PreviewHarness() {
  const params = new URLSearchParams(window.location.search);
  const [view, setView] = useState<View>((params.get("view") as View) || "dashboard");
  const [theme, setTheme] = useState(params.get("theme") === "dark" ? "dark" : "light");
  const [drawerOpen, setDrawerOpen] = useState(params.get("drawer") === "1");
  const [sel, setSel] = useState<Lead | null>(null);
  const showChrome = params.get("chrome") !== "0";

  useEffect(() => {
    // Go through the same channel the app uses (localStorage + attributes +
    // broadcast) so real components like Topbar agree on the current theme.
    try { localStorage.setItem("jhm-theme", theme); } catch { /* private mode */ }
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.dispatchEvent(new CustomEvent("jhm-theme", { detail: theme }));
  }, [theme]);

  // Keep the harness shell in sync when the REAL Topbar toggle fires (it goes
  // through useTheme/applyTheme, which broadcasts "jhm-theme").
  useEffect(() => {
    const onTheme = (event: Event) => {
      const next = (event as CustomEvent<"light" | "dark">).detail;
      setTheme(next);
    };
    window.addEventListener("jhm-theme", onTheme);
    return () => window.removeEventListener("jhm-theme", onTheme);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setSel(null); setDrawerOpen(false); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const leadCounts = useMemo(() => ({
    total:        LEADS.length,
    hot:          LEADS.filter(l => (l.signal_score || 0) >= 80 || (l.score || 0) >= 85).length,
    discovered:   LEADS.filter(l => l.status === "discovered").length,
    evaluated:    LEADS.filter(l => l.score > 0 || (l.signal_score || 0) > 0).length,
    evaluating:   LEADS.filter(l => l.status === "evaluating").length,
    tailoring:    LEADS.filter(l => l.status === "tailoring").length,
    approved:     LEADS.filter(l => l.status === "approved").length,
    ready:        LEADS.filter(l => l.status === "tailoring" || l.status === "approved").length,
    applied:      LEADS.filter(l => l.status === "applied").length,
    discarded:    LEADS.filter(l => l.status === "discarded").length,
    interviewing: LEADS.filter(l => l.status === "interviewing").length,
    accepted:     0,
    rejected:     0,
  }), []);

  const drawerLead = sel ?? (drawerOpen ? LEADS[0] : null);

  return (
    <div className="product-app app-production" data-theme={theme}>
      <Sidebar
        view={view} setView={setView} leadCounts={leadCounts}
        collapsed={false} onToggleCollapsed={noop} onSettings={noop}
      />
      <div className="product-shell app-main">
        <Topbar view={view} progress={PROGRESS} onRun={noop} onCommand={noop} onNavigate={setView} />
        <main id="product-content" className="product-content production-live-content">
          {view === "dashboard" && (
            <ErrorBoundary label="Dashboard">
              <DashboardView
                leads={LEADS} dueFollowups={[LEADS[4]]} logs={LOGS} setView={setView} openDrawer={setSel}
                scanning={false} reevaluating={false} cleaning={false} progress={PROGRESS}
                onScan={asyncNoop} onStopScan={asyncNoop} onReevaluate={asyncNoop} onStopReevaluate={asyncNoop}
                onCleanup={asyncNoop} scanErr={null} api={mockApi}
              />
            </ErrorBoundary>
          )}
          {view === "pipeline" && (
            <ErrorBoundary label="Pipeline">
              <PipelineView
                leads={LEADS} openDrawer={setSel} deleteLead={asyncNoop} port={1420} api={mockApi}
                scanning={false} reevaluating={false} cleaning={false}
                onReevaluate={asyncNoop} onStopReevaluate={asyncNoop} onCleanup={asyncNoop}
                loading={false} error={null} tab="all" setView={setView}
              />
            </ErrorBoundary>
          )}
          {view === "graph"     && <ErrorBoundary label="Graph"><GraphView stats={STATS} /></ErrorBoundary>}
          {view === "activity"  && <ErrorBoundary label="Activity"><ActivityView logs={LOGS} /></ErrorBoundary>}
          {view === "profile"   && <ErrorBoundary label="Profile"><ProfileView api={mockApi} setView={setView} stats={STATS} /></ErrorBoundary>}
          {view === "ingestion" && <ErrorBoundary label="Ingestion"><IngestionView api={mockApi} /></ErrorBoundary>}
          {view === "apply" && (
            <ErrorBoundary label="Apply">
              <ApplyJobView port={1420} api={mockApi} leads={LEADS} openDrawer={setSel} initialInput="" />
            </ErrorBoundary>
          )}
        </main>
      </div>

      <ErrorBoundary label="Lead drawer">
        {drawerLead && <ApprovalDrawer j={drawerLead} api={mockApi} onClose={() => { setSel(null); setDrawerOpen(false); }} />}
      </ErrorBoundary>

      <ErrorBoundary label="Help chat">
        <HelpChat api={mockApi} />
      </ErrorBoundary>

      {showChrome && (
        <div style={{
          position: "fixed", left: 14, bottom: 14, zIndex: 9000, display: "flex", gap: 6,
          padding: "7px 10px", borderRadius: 999, background: "rgba(31,26,20,.92)", color: "#F4EFE6",
          fontFamily: "var(--font-mono)", fontSize: 10.5, letterSpacing: ".04em", alignItems: "center",
        }}>
          <span style={{ opacity: .55, marginRight: 2 }}>preview</span>
          {VIEWS.map(v => (
            <button key={v} onClick={() => setView(v)} style={{
              background: v === view ? "#C96442" : "transparent", color: "inherit", border: "none",
              borderRadius: 999, padding: "3px 8px", cursor: "pointer", font: "inherit",
            }}>{v}</button>
          ))}
          <button onClick={() => setTheme(t => (t === "dark" ? "light" : "dark"))} style={{
            background: "transparent", color: "inherit", border: "1px solid rgba(244,239,230,.35)",
            borderRadius: 999, padding: "3px 8px", cursor: "pointer", font: "inherit",
          }}>{theme}</button>
        </div>
      )}
    </div>
  );
}
