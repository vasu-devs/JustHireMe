import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence } from "framer-motion";
import SettingsModal from "./features/settings/SettingsModal";
import "./index.css";
import type { ApiFetch, PipelineTab, View } from "./types";
import { createApiFetch } from "./api/client";
import { useAppShellState } from "./shared/context/AppContext";
import { ONBOARDING_KEY } from "./shared/lib/leadUtils";
import { useWS } from "./shared/hooks/useWS";
import { useLeads } from "./shared/hooks/useLeads";
import { useDueFollowups } from "./shared/hooks/useDueFollowups";
import { useGraphStats } from "./shared/hooks/useGraphStats";
import { useKeyboardShortcuts } from "./shared/hooks/useKeyboardShortcuts";
import { Sidebar } from "./shared/components/Sidebar";
import { Topbar } from "./shared/components/Topbar";
import ErrorBoundary from "./shared/components/ErrorBoundary";
import { DashboardView } from "./features/dashboard/DashboardView";
import { ApplyJobView } from "./features/apply/ApplyJobView";
import { PipelineView } from "./features/pipeline/PipelineView";
import { GraphView } from "./features/graph/GraphView";
import { ActivityView } from "./features/activity/ActivityView";
import { ProfileView } from "./features/profile/ProfileView";
import { IngestionView } from "./features/profile/IngestionView";
import { ApprovalDrawer } from "./features/pipeline/components/ApprovalDrawer";
import { OnboardingWizard } from "./shared/components/OnboardingWizard";
import { HelpChat } from "./shared/components/HelpChat";
import { UpdatePrompt } from "./shared/components/UpdatePrompt";
import { SemanticRuntimePrompt } from "./shared/components/SemanticRuntimePrompt";

const PIPELINE_VIEW_TO_TAB: Partial<Record<View, PipelineTab>> = {
  pipeline: "all",
  "pipeline-hot": "hot",
  "pipeline-found": "found",
  "pipeline-evaluated": "evaluated",
  "pipeline-generated": "generated",
  "pipeline-applied": "applied",
  "pipeline-discarded": "discarded",
};

type SubsystemHealth = Record<string, { status: string; error?: string; reason?: string; [key: string]: unknown }>;

function isActionableSubsystemIssue(name: string, value: SubsystemHealth[string]) {
  if (value.status === "ok") return false;
  const message = String(value.error || value.reason || "").toLowerCase();
  if (name === "llm" && message.includes("api key")) return false;
  if (name === "embeddings" && value.mode === "hashing") return false;
  return true;
}

export default function App() {
  const { conn, port, apiToken, sidecarError, logs, addLog: wsAddLog, progress, resetProgress } = useWS();
  const api = useMemo<ApiFetch | null>(() => {
    if (!port || !apiToken) return null;
    return createApiFetch(port, apiToken);
  }, [port, apiToken]);
  const { leads, setLeads, loading: leadsLoading, error: leadsError } = useLeads(api, wsAddLog);
  const dueFollowups = useDueFollowups(api);
  const stats  = useGraphStats(api);
  const {
    view, setView, sel, setSel, showSettings, setShowSettings, showOnboarding,
    setShowOnboarding, applyDraft, setApplyDraft, applyAutoFocus, setApplyAutoFocus,
    scanning, setScanning, reevaluating, setReevaluating, cleaning, setCleaning,
    scanErr, setScanErr, closeDrawer, focusApplyView, openSettings,
  } = useAppShellState();
  // Always pass the live version of the selected lead so the drawer reflects real-time updates
  const liveSel = sel ? (leads.find(l => l.job_id === sel.job_id) ?? sel) : null;
  const [startupSeconds, setStartupSeconds] = useState(0);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem("jhm-sidebar-collapsed") === "1");
  const [subsystems, setSubsystems] = useState<SubsystemHealth | null>(null);

  useEffect(() => {
    localStorage.setItem("jhm-sidebar-collapsed", sidebarCollapsed ? "1" : "0");
  }, [sidebarCollapsed]);

  useEffect(() => {
    const h = () => setScanning(false);
    window.addEventListener("scan-done", h);
    return () => window.removeEventListener("scan-done", h);
  }, []);

  useEffect(() => {
    const h = (event: Event) => {
      const detail = (event as CustomEvent<{ scanning?: boolean; reevaluating?: boolean }>).detail || {};
      setScanning(Boolean(detail.scanning));
      setReevaluating(Boolean(detail.reevaluating));
    };
    window.addEventListener("backend-status", h);
    return () => window.removeEventListener("backend-status", h);
  }, []);

  useEffect(() => {
    // Watchdog for ANY long-running op (scan / re-evaluate / cleanup): if a lost
    // terminal WS frame leaves a flag stuck while the socket stays connected, clear
    // it (and the progress bar) after 15 min so the UI isn't wedged.
    if (!scanning && !reevaluating && !cleaning) return;
    const timer = window.setTimeout(() => {
      setScanning(false);
      setReevaluating(false);
      setCleaning(false);
      resetProgress();
      const msg = "Activity indicator cleared after 15 minutes without backend progress.";
      setScanErr(msg);
      wsAddLog(msg, "system", "scan");
    }, 15 * 60 * 1000);
    return () => window.clearTimeout(timer);
  }, [scanning, reevaluating, cleaning, progress.updatedAt, setScanning, setReevaluating, setCleaning, setScanErr, wsAddLog, resetProgress]);

  useEffect(() => {
    if (api) return;
    const started = Date.now();
    const timer = window.setInterval(() => {
      setStartupSeconds(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [api]);

  useEffect(() => {
    if (!api) {
      setSubsystems(null);
      return;
    }
    let stopped = false;
    const load = async () => {
      try {
        const response = await api("/api/v1/health/subsystems", { timeoutMs: 10000 });
        if (!response.ok) return;
        const payload = await response.json();
        if (!stopped) setSubsystems(payload);
      } catch {
        if (!stopped) setSubsystems(null);
      }
    };
    load();
    const timer = window.setInterval(load, 30000);
    window.addEventListener("subsystems-refresh", load);
    return () => {
      stopped = true;
      window.removeEventListener("subsystems-refresh", load);
      window.clearInterval(timer);
    };
  }, [api]);

  useKeyboardShortcuts({
    onEscape: closeDrawer,
    onCmdK: focusApplyView,
    onCmdComma: openSettings,
  });

  useEffect(() => {
    if (view !== "apply" || !applyAutoFocus) return;
    const timer = window.setTimeout(() => setApplyAutoFocus(false), 0);
    return () => window.clearTimeout(timer);
  }, [view, applyAutoFocus]);

  useEffect(() => {
    const h = () => setReevaluating(false);
    window.addEventListener("reevaluate-done", h);
    return () => window.removeEventListener("reevaluate-done", h);
  }, []);

  useEffect(() => {
    const h = () => setCleaning(false);
    window.addEventListener("cleanup-done", h);
    return () => window.removeEventListener("cleanup-done", h);
  }, []);

  const onScan = useCallback(async () => {
    if (!port || !api || scanning) return;
    setScanning(true); setScanErr(null);
    try {
      const r = await api(`/api/v1/scan`, { method: "POST" });
      if (!r.ok) {
        const detail = await r.json().then(d => d.detail).catch(() => "");
        throw new Error(detail || "Backend unreachable");
      }
    } catch (e: any) {
      setScanErr(e.message || "Scan failed"); setScanning(false);
    }
  }, [port, api, scanning]);

  const onStopScan = useCallback(async () => {
    if (!port || !api) return;
    try {
      const r = await api(`/api/v1/scan/stop`, { method: "POST" });
      if (!r.ok) {
        const detail = await r.json().then(d => d.detail).catch(() => "");
        throw new Error(detail || "Stop scan failed");
      }
    } catch (e: any) {
      const msg = e.message || "Stop scan request failed";
      setScanErr(msg);
      wsAddLog(msg, "system", "scan");
    }
  }, [port, api, setScanErr, wsAddLog]);

  const onReevaluateJobs = useCallback(async () => {
    if (!port || !api || reevaluating || scanning) return;
    setReevaluating(true); setScanErr(null);
    try {
      const r = await api(`/api/v1/leads/reevaluate`, { method: "POST" });
      if (!r.ok) {
        const detail = await r.json().then(d => d.detail).catch(() => "");
        throw new Error(detail || "Re-evaluation failed");
      }
    } catch (e: any) {
      const msg = e.message || "Re-evaluation failed";
      setScanErr(msg); setReevaluating(false);
      wsAddLog(msg, "system", "reeval");
    }
  }, [port, api, reevaluating, scanning, wsAddLog]);

  const onStopReevaluate = useCallback(async () => {
    if (!port || !api) return;
    try {
      const r = await api(`/api/v1/leads/reevaluate/stop`, { method: "POST" });
      if (!r.ok) {
        const detail = await r.json().then(d => d.detail).catch(() => "");
        throw new Error(detail || "Stop re-evaluation failed");
      }
    } catch (e: any) {
      const msg = e.message || "Stop re-evaluation request failed";
      setScanErr(msg);
      wsAddLog(msg, "system", "reeval");
    }
  }, [port, api, setScanErr, wsAddLog]);

  const onCleanupLeads = useCallback(async () => {
    if (!port || !api || scanning || reevaluating || cleaning) return;
    const ok = window.confirm("Discard obvious bad rows like HN discussion comments and non-job content? This keeps the rows in Discarded with a cleanup reason.");
    if (!ok) return;
    setCleaning(true); setScanErr(null);
    try {
      const r = await api(`/api/v1/leads/cleanup`, { method: "POST" });
      if (!r.ok) {
        const detail = await r.json().then(d => d.detail).catch(() => "");
        throw new Error(detail || "Cleanup failed");
      }
      const result = await r.json();
      wsAddLog(`Cleanup discarded ${result.candidates ?? 0} bad rows after scanning ${result.scanned ?? 0}`, "system", "cleanup");
      window.dispatchEvent(new CustomEvent("leads-refresh"));
    } catch (e: any) {
      const msg = e.message || "Cleanup failed";
      setScanErr(msg);
      wsAddLog(msg, "system", "cleanup");
    } finally {
      setCleaning(false);
    }
  }, [port, api, scanning, reevaluating, cleaning, wsAddLog]);

  const deleteLead = useCallback(async (jobId: string) => {
    if (!port || !api) return;
    const r = await api(`/api/v1/leads/${jobId}`, { method: "DELETE" });
    // Only remove it locally on a real success — a swallowed HTTP error left the
    // lead deleted in the UI (and broke bulkDelete's failure counting).
    if (!r.ok) throw new Error(`Delete failed (${r.status})`);
    setLeads(prev => prev.filter(l => l.job_id !== jobId));
  }, [port, api, setLeads]);

  const leadCounts = {
    total:        leads.length,
    hot:          leads.filter(l => (l.signal_score || 0) >= 80 || (l.score || 0) >= 85).length,
    discovered:   leads.filter(l=>l.status==="discovered").length,
    evaluated:    leads.filter(l => l.score > 0 || (l.signal_score || 0) > 0).length,
    evaluating:   leads.filter(l=>l.status==="evaluating").length,
    tailoring:    leads.filter(l=>l.status==="tailoring").length,
    approved:     leads.filter(l=>l.status==="approved").length,
    ready:        leads.filter(l=>l.status==="tailoring" || l.status==="approved").length,
    applied:      leads.filter(l=>l.status==="applied").length,
    discarded:    leads.filter(l=>l.status==="discarded").length,
    interviewing: leads.filter(l=>l.status==="interviewing").length,
    accepted:     leads.filter(l=>l.status==="accepted").length,
    rejected:     leads.filter(l=>l.status==="rejected").length,
  };
  const pipelineTab = PIPELINE_VIEW_TO_TAB[view] || "all";
  const isPipelineView = Boolean(PIPELINE_VIEW_TO_TAB[view]);
  const degradedSubsystems = Object.entries(subsystems ?? {}).filter(([name, value]) => isActionableSubsystemIssue(name, value));

  if (!api) {
    return (
      <>
        <StartupScreen conn={conn} port={port} seconds={startupSeconds} sidecarError={sidecarError} />
        <UpdatePrompt />
      </>
    );
  }

  return (
    <>
      <div style={{ display: "flex", height: "100vh", width: "100vw", overflow: "hidden", alignItems: "stretch" }}>
        <Sidebar
          view={view}
          setView={setView}
          leadCounts={leadCounts}
          collapsed={sidebarCollapsed}
          onToggleCollapsed={() => setSidebarCollapsed(value => !value)}
          onSettings={() => setShowSettings(true)}
        />
        <div className="app-main">
          <Topbar view={view} progress={progress} />
          <SubsystemBanner items={degradedSubsystems} />
          <NoticeBanner />
          <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column", background: "var(--paper)" }}>
            {view === "apply"     && <ErrorBoundary label="Apply" api={api ?? undefined}><ApplyJobView port={port} api={api} leads={leads} openDrawer={setSel} initialInput={applyDraft} autoFocus={applyAutoFocus} /></ErrorBoundary>}
            {view === "dashboard" && <ErrorBoundary label="Dashboard" api={api ?? undefined}><DashboardView leads={leads} dueFollowups={dueFollowups} logs={logs} setView={setView} openDrawer={setSel} scanning={scanning} reevaluating={reevaluating} cleaning={cleaning} progress={progress} onScan={onScan} onStopScan={onStopScan} onReevaluate={onReevaluateJobs} onStopReevaluate={onStopReevaluate} onCleanup={onCleanupLeads} scanErr={scanErr} api={api} /></ErrorBoundary>}
            {isPipelineView  && <ErrorBoundary label="Pipeline" api={api ?? undefined}><PipelineView leads={leads} openDrawer={setSel} deleteLead={deleteLead} port={port} api={api} scanning={scanning} reevaluating={reevaluating} cleaning={cleaning} onReevaluate={onReevaluateJobs} onStopReevaluate={onStopReevaluate} onCleanup={onCleanupLeads} loading={leadsLoading || !port || !api} error={leadsError} tab={pipelineTab} /></ErrorBoundary>}
            {view === "graph"     && <ErrorBoundary label="Graph" api={api ?? undefined}><GraphView stats={stats} /></ErrorBoundary>}
            {view === "activity"  && <ErrorBoundary label="Activity" api={api ?? undefined}><ActivityView logs={logs} /></ErrorBoundary>}
            {view === "profile"   && (api ? <ErrorBoundary label="Profile" api={api ?? undefined}><ProfileView api={api} setView={setView} stats={stats} /></ErrorBoundary> : <BackendUnavailable title="Profile" conn={conn} port={port} />)}
            {view === "ingestion" && (api ? <ErrorBoundary label="Ingestion" api={api ?? undefined}><IngestionView api={api} /></ErrorBoundary> : <BackendUnavailable title="Add Context" conn={conn} port={port} />)}
          </div>
        </div>

        {/* The drawer/modal layer renders the richest untyped lead data; a
            render crash here without a boundary would blank the whole app. */}
        <ErrorBoundary label="Lead drawer" api={api ?? undefined}>
          <AnimatePresence>
            {liveSel && api && (
              <ApprovalDrawer key={liveSel.job_id} j={liveSel} api={api} onClose={() => setSel(null)} />
            )}
            {showSettings && api && (
              <SettingsModal key="settings" api={api} onClose={() => setShowSettings(false)} />
            )}
            {showOnboarding && api && (
              <OnboardingWizard
                key="onboarding"
                api={api}
                onOpenSettings={() => setShowSettings(true)}
                onFinish={(draft) => {
                  localStorage.setItem(ONBOARDING_KEY, "done");
                  setApplyDraft(draft);
                  setView("apply");
                  setShowOnboarding(false);
                }}
              />
            )}
          </AnimatePresence>
        </ErrorBoundary>
        {api && (
          <ErrorBoundary label="Help chat" api={api}>
            <HelpChat api={api} />
          </ErrorBoundary>
        )}
      </div>
      <ErrorBoundary label="Prompts" api={api ?? undefined}>
        <SemanticRuntimePrompt api={api} />
        <UpdatePrompt />
      </ErrorBoundary>
    </>
  );
}

function NoticeBanner() {
  // Transient banner for degraded/notable backend outcomes (LLM-fallback scoring,
  // empty scout, feedback re-rank) that would otherwise be buried in the log.
  const [notice, setNotice] = useState<{ level: string; msg: string } | null>(null);
  useEffect(() => {
    let timer = 0;
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ level?: string; msg?: string }>).detail;
      if (!detail?.msg) return;
      setNotice({ level: detail.level || "info", msg: detail.msg });
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setNotice(null), 9000);
    };
    window.addEventListener("backend-notice", handler);
    return () => { window.removeEventListener("backend-notice", handler); window.clearTimeout(timer); };
  }, []);
  if (!notice) return null;
  const warn = notice.level === "warn";
  return (
    <div
      role="status"
      style={{
        display: "flex", alignItems: "center", gap: 10, padding: "8px 14px",
        fontSize: 13, borderBottom: "1px solid var(--line, #e5e7eb)",
        background: warn ? "var(--warn-bg, #fef3c7)" : "var(--info-bg, #e0f2fe)",
        color: warn ? "#92400e" : "#075985",
      }}
    >
      <span style={{ flex: 1 }}>{notice.msg}</span>
      <button
        onClick={() => setNotice(null)}
        aria-label="Dismiss"
        style={{ background: "none", border: "none", cursor: "pointer", fontSize: 16, color: "inherit", lineHeight: 1 }}
      >
        ×
      </button>
    </div>
  );
}


function SubsystemBanner({ items }: { items: Array<[string, SubsystemHealth[string]]> }) {
  if (items.length === 0) return null;
  const summary = items.map(([name, value]) => `${name}: ${value.status}`).join(" | ");
  const detail = items
    .map(([name, value]) => {
      const message = value.error || value.reason;
      return message ? `${name}: ${message}` : "";
    })
    .filter(Boolean)
    .join(" | ");
  return (
    <div className="subsystem-banner" role="status">
      <strong>Subsystem degraded</strong>
      <span>{summary}</span>
      {detail && <span className="subsystem-banner-detail">{detail}</span>}
    </div>
  );
}

function StartupScreen({ conn, port, seconds, sidecarError }: { conn: string; port: number | null; seconds: number; sidecarError: string | null }) {
  const isSlow = seconds >= 20;
  return (
    <div style={{
      minHeight: "100vh",
      width: "100vw",
      display: "grid",
      placeItems: "center",
      background: "var(--paper)",
      color: "var(--ink)",
      padding: 24,
    }}>
      <section className="card col gap-4" style={{ width: "min(720px, 100%)", padding: 30 }}>
        <div className="row gap-3">
          <div className="spinner" />
          <div>
            <div className="eyebrow">Starting JustHireMe</div>
            <h1 style={{ fontSize: 30, marginTop: 6 }}>Preparing your local workspace</h1>
          </div>
        </div>
        <p style={{ color: "var(--ink-2)", lineHeight: 1.6, maxWidth: 620 }}>
          The desktop app is launching its bundled backend, opening the local database, and waiting for a private API token.
          The setup guide will appear automatically as soon as the backend is ready.
        </p>
        <div className="row gap-2" style={{ flexWrap: "wrap" }}>
          <span className="pill">Backend: {conn}</span>
          <span className="pill">Port: {port ?? "pending"}</span>
          <span className="pill">Elapsed: {seconds}s</span>
        </div>
        {isSlow && (
          <div style={{
            border: "1px solid var(--line)",
            borderRadius: 8,
            padding: 14,
            background: "var(--paper-3)",
            color: "var(--ink-2)",
            lineHeight: 1.55,
          }}>
            This is taking longer than expected. If it stays here, the bundled backend failed to start.
            On macOS, use Privacy &amp; Security &gt; Open Anyway if the app was blocked, then restart JustHireMe.
          </div>
        )}
        {sidecarError && (
          <div style={{
            border: "1px solid var(--bad)",
            borderRadius: 8,
            padding: 14,
            background: "var(--bad-soft)",
            color: "var(--bad)",
            lineHeight: 1.55,
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            whiteSpace: "pre-wrap",
          }}>
            {sidecarError}
          </div>
        )}
      </section>
    </div>
  );
}

function BackendUnavailable({ title, conn, port }: { title: string; conn: string; port: number | null }) {
  return (
    <div className="ingestion-page scroll">
      <div className="ingestion-shell">
        <div className="card col gap-4" style={{ padding: 28 }}>
          <div className="row gap-3">
            <div className="spinner" />
            <div>
              <div className="eyebrow">Starting local backend</div>
              <h2 style={{ marginTop: 6 }}>{title} will appear automatically</h2>
            </div>
          </div>
          <p style={{ color: "var(--ink-2)", maxWidth: 620, lineHeight: 1.6 }}>
            JustHireMe is waiting for the bundled sidecar to publish its API token and port. This should take a few seconds after launch.
          </p>
          <div className="row gap-2" style={{ flexWrap: "wrap" }}>
            <span className="pill">Connection: {conn}</span>
            <span className="pill">Port: {port ?? "pending"}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
