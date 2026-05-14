import Icon from "./Icon";
import type { View } from "../../types";

export function Topbar({ view }: { view: View }) {
  const titles: Record<View, string> = {
    apply:     "Customize One Job",
    dashboard: "Command Center",
    pipeline:  "Job Pipeline",
    "pipeline-hot": "Hot Jobs",
    "pipeline-found": "New Jobs",
    "pipeline-evaluated": "Rated Jobs",
    "pipeline-generated": "Ready Jobs",
    "pipeline-applied": "Applied Jobs",
    "pipeline-discarded": "Discarded Jobs",
    graph:     "Knowledge Graph",
    activity:  "Live Activity",
    profile:   "Profile",
    ingestion: "Add Context",
  };
  const subtitles: Record<View, string> = {
    apply: "Tailor resume, cover letter, and outreach for one selected role",
    dashboard: "Scan, review, and move the next best roles forward",
    pipeline: "Track applications and follow-ups",
    "pipeline-hot": "High-fit or high-signal roles worth attention first",
    "pipeline-found": "Freshly discovered roles waiting for evaluation",
    "pipeline-evaluated": "Roles with fit, signal, or quality scoring",
    "pipeline-generated": "Application packages that are ready or being tailored",
    "pipeline-applied": "Roles already marked as sent",
    "pipeline-discarded": "Rejected, cleanup, or low-quality rows",
    graph: "Local profile context used by matching",
    activity: "Backend events and agent logs",
    profile: "Candidate details used for tailoring",
    ingestion: "Add resume, project, portfolio, and GitHub context",
  };
  return (
    <header className="topbar">
      <div style={{ flex: 1, minWidth: 0 }}>
        <h2 style={{ fontSize: 19, fontWeight: 600, letterSpacing: 0 }}>{titles[view]}</h2>
        <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>{subtitles[view]}</div>
      </div>
      {view === "profile" && (
        <button className="btn" onClick={() => window.dispatchEvent(new CustomEvent("profile-export"))}>
          <Icon name="download" size={13} /> Export Graph
        </button>
      )}
    </header>
  );
}

/* ══════════════════════════════════════
   DASHBOARD VIEW
══════════════════════════════════════ */

export const StatCard = ({ tone, label, value, sub, icon }: any) => (
  <div style={{
    background: `var(--${tone}-soft)`,
    border: `1px solid var(--${tone})`,
    borderRadius: 16, padding: 18,
    display: "flex", flexDirection: "column", gap: 12,
    minHeight: 132,
  }}>
    <div style={{
      width: 32, height: 32, borderRadius: 9,
      background: `var(--${tone})`, color: `var(--${tone}-ink)`,
      display: "grid", placeItems: "center",
    }}>
      <Icon name={icon} size={15} />
    </div>
    <div className="col" style={{ gap: 4 }}>
      <div className="display tabular" style={{ fontSize: 40, color: `var(--${tone}-ink)`, lineHeight: 1 }}>{value}</div>
      <div style={{ fontSize: 13, fontWeight: 500, color: "var(--ink)" }}>{label}</div>
      <div className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)", letterSpacing: "0.08em", textTransform: "uppercase" }}>{sub}</div>
    </div>
  </div>
);
