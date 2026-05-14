import { useState } from "react";
import Icon from "./Icon";
import type { View } from "../../types";

const NAV = [
  { id: "dashboard", label: "Dashboard", icon: "home", tone: "blue" },
  { id: "apply", label: "Customize Job", icon: "spark", tone: "green" },
  { id: "graph", label: "Knowledge", icon: "graph", tone: "green" },
  { id: "activity", label: "Activity", icon: "pulse", tone: "orange" },
  { id: "profile", label: "Profile", icon: "user", tone: "pink" },
  { id: "ingestion", label: "Add Context", icon: "plus", tone: "teal" },
];

const PIPELINE_NAV = [
  { id: "pipeline", label: "All", countKey: "total", tone: "teal" },
  { id: "pipeline-hot", label: "Hot", countKey: "hot", tone: "orange" },
  { id: "pipeline-found", label: "New", countKey: "discovered", tone: "blue" },
  { id: "pipeline-evaluated", label: "Rated", countKey: "evaluated", tone: "yellow" },
  { id: "pipeline-generated", label: "Ready", countKey: "ready", tone: "purple" },
  { id: "pipeline-applied", label: "Applied", countKey: "applied", tone: "orange" },
  { id: "pipeline-discarded", label: "Discarded", countKey: "discarded", tone: "bad" },
];

const isPipelineView = (view: View) => view === "pipeline" || view.startsWith("pipeline-");

export function Sidebar({
  view,
  setView,
  leadCounts,
  collapsed,
  onToggleCollapsed,
  onSettings,
  onSetup,
}: {
  view: View;
  setView: (v: View) => void;
  leadCounts: any;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onSettings: () => void;
  onSetup?: () => void;
}) {
  const [pipelineOpen, setPipelineOpen] = useState(true);
  const pipelineActive = isPipelineView(view);

  return (
    <aside className={"sidebar " + (collapsed ? "collapsed" : "")}>
      <div className="sidebar-brand">
        <div className="row gap-3 sidebar-brand-main">
          <Icon name="logo" size={32} />
          <div className="col sidebar-label" style={{ lineHeight: 1.1 }}>
            <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: "-0.02em" }}>JustHireMe</div>
            <div className="mono" style={{ fontSize: 9.5, color: "var(--ink-3)", letterSpacing: "0.14em", textTransform: "uppercase" }}>v0.1-alpha</div>
          </div>
        </div>
        <button
          className="btn btn-icon sidebar-collapse-btn"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <Icon name="arrow-right" size={14} style={{ transform: collapsed ? "none" : "rotate(180deg)" }} />
        </button>
      </div>

      <div className="eyebrow sidebar-section-label">Workspace</div>
      <div className="col gap-1">
        {NAV.slice(0, 2).map(n => {
          const active = view === n.id;
          return (
            <button
              key={n.id}
              className={"nav-item " + (active ? "active" : "")}
              onClick={() => setView(n.id as View)}
              title={collapsed ? n.label : undefined}
              aria-label={n.label}
            >
              <div
                className="nav-icon"
                style={{
                  background: active ? `var(--${n.tone})` : "var(--paper-3)",
                  color: active ? `var(--${n.tone}-ink)` : "var(--ink-2)",
                }}
              >
                <Icon name={n.icon} size={14} stroke={1.8} />
              </div>
              <span className="nav-label">{n.label}</span>
            </button>
          );
        })}

        <div className={"nav-group " + (pipelineActive ? "active" : "")}>
          <button
            className={"nav-item nav-group-trigger " + (pipelineActive ? "active" : "")}
            onClick={() => {
              if (collapsed) {
                setView("pipeline");
                return;
              }
              setPipelineOpen(value => !value);
              if (!pipelineActive) setView("pipeline");
            }}
            title={collapsed ? "Job Pipeline" : undefined}
            aria-label="Job Pipeline"
            aria-expanded={pipelineOpen && !collapsed}
          >
            <div
              className="nav-icon"
              style={{
                background: pipelineActive ? "var(--purple)" : "var(--paper-3)",
                color: pipelineActive ? "var(--purple-ink)" : "var(--ink-2)",
              }}
            >
              <Icon name="layers" size={14} stroke={1.8} />
            </div>
            <span className="nav-label">Job Pipeline</span>
            <span
              className="mono tabular nav-count"
              style={{
                color: pipelineActive ? "var(--purple-ink)" : "var(--ink-3)",
                background: pipelineActive ? "var(--purple)" : "var(--paper-3)",
              }}
            >
              {leadCounts.total || 0}
            </span>
            <Icon name="arrow-right" size={12} style={{ transform: pipelineOpen ? "rotate(90deg)" : "none" }} />
          </button>

          {pipelineOpen && !collapsed && (
            <div className="pipeline-subnav" aria-label="Pipeline lanes">
              {PIPELINE_NAV.map(item => {
                const active = view === item.id;
                const count = leadCounts[item.countKey] || 0;
                const soft = item.tone === "bad" ? "var(--bad-soft)" : `var(--${item.tone}-soft)`;
                const ink = item.tone === "bad" ? "var(--bad)" : `var(--${item.tone}-ink)`;
                return (
                  <button
                    key={item.id}
                    className={"pipeline-subnav-item " + (active ? "active" : "")}
                    onClick={() => setView(item.id as View)}
                    style={active ? { background: soft, color: ink, borderColor: item.tone === "bad" ? "var(--bad)" : `var(--${item.tone})` } : undefined}
                  >
                    <span>{item.label}</span>
                    <b className="mono tabular">{count}</b>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {NAV.slice(2).map(n => {
          const active = view === n.id;
          return (
            <button
              key={n.id}
              className={"nav-item " + (active ? "active" : "")}
              onClick={() => setView(n.id as View)}
              title={collapsed ? n.label : undefined}
              aria-label={n.label}
            >
              <div
                className="nav-icon"
                style={{
                  background: active ? `var(--${n.tone})` : "var(--paper-3)",
                  color: active ? `var(--${n.tone}-ink)` : "var(--ink-2)",
                }}
              >
                <Icon name={n.icon} size={14} stroke={1.8} />
              </div>
              <span className="nav-label">{n.label}</span>
            </button>
          );
        })}
      </div>

      <div className="eyebrow sidebar-section-label snapshot-label">Snapshot</div>
      <div className="sidebar-snapshot">
        {[
          ["Ready", "green", leadCounts.approved],
          ["Applied", "orange", leadCounts.applied],
          ["Interview", "pink", leadCounts.interviewing],
        ].map(([label, tone, n]) => (
          <div key={label as string} className="sidebar-snapshot-item" title={`${label}: ${n || 0}`}>
            <div className="mono tabular" style={{ fontSize: 15, fontWeight: 800, color: `var(--${tone}-ink)`, lineHeight: 1 }}>{n || 0}</div>
            <div className="sidebar-snapshot-label">{label}</div>
          </div>
        ))}
      </div>

      <div className="grow" />

      <div className="sidebar-utility">
        <button className="profile-add-context sidebar-setup" onClick={onSetup} title={collapsed ? "Setup Guide" : undefined} aria-label="Setup Guide">
          <Icon name="spark" size={14} />
          <span className="sidebar-label">Setup Guide</span>
        </button>

        <button className="btn sidebar-settings-btn" onClick={onSettings} aria-label="Settings" title="Settings">
          <Icon name="settings" size={15} />
          <span className="sidebar-label">Settings</span>
        </button>
      </div>
    </aside>
  );
}
