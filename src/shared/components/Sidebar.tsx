import { DemoIcon } from "../../demo/DemoIcon";
import brandMark from "../../assets/brand/justhireme-mark.svg";
import type { LeadCounts, View } from "../../types";

type RailItem = {
  label: string;
  hint: string;
  icon: string;
  tone: string;
  view: View;
  badge?: keyof LeadCounts;
  active: (view: View) => boolean;
};

const ITEMS: RailItem[] = [
  { label: "Overview", hint: "Home board", icon: "overview", tone: "peach", view: "dashboard", active: view => view === "dashboard" },
  { label: "Opportunities", hint: "Verified early-career roles", icon: "radar", tone: "mint", view: "opportunities", active: view => view === "opportunities" },
  { label: "Pipeline", hint: "Application flow", icon: "inbox", tone: "blue", view: "pipeline", badge: "total", active: view => view === "pipeline" || view.startsWith("pipeline-") },
  { label: "Scout", hint: "Agent journal", icon: "radar", tone: "mint", view: "activity", badge: "hot", active: view => view === "activity" },
  { label: "Tailor", hint: "Asset workshop", icon: "tailor", tone: "pink", view: "apply", active: view => view === "apply" },
  { label: "Knowledge", hint: "Evidence atlas", icon: "graph", tone: "blue", view: "graph", active: view => view === "graph" },
  { label: "Learn", hint: "Skill intelligence", icon: "tune", tone: "mint", view: "learn", active: view => view === "learn" },
  { label: "Profile", hint: "Evidence garden", icon: "profile", tone: "lilac", view: "profile", active: view => view === "profile" },
  { label: "Context", hint: "Add evidence", icon: "context", tone: "peach", view: "ingestion", active: view => view === "ingestion" },
];

// No desktop equivalent — the audit-report screen (leads funnel, per-source
// confirm rate) only App's web entry opts into via `showReport`.
const REPORT_ITEM: RailItem = { label: "Report", hint: "Audit numbers", icon: "file", tone: "lilac", view: "report", active: view => view === "report" };

export function Sidebar({
  view,
  setView,
  leadCounts,
  onSettings,
  showReport = false,
}: {
  view: View;
  setView: (v: View) => void;
  leadCounts: LeadCounts;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onSettings: () => void;
  showReport?: boolean;
}) {
  const items = showReport ? [...ITEMS, REPORT_ITEM] : ITEMS;
  return <aside className="product-sidebar production-product-sidebar">
    <div className="product-logo">
      <span className="product-brand-mark"><img src={brandMark} alt="JustHireMe" /></span>
      <div className="product-wordmark"><strong>JustHireMe</strong><small>opportunity studio</small></div>
    </div>

    <nav aria-label="Product navigation">
      <p><span>Workspace</span><i>9 rooms</i></p>
      {items.map(item => {
        const selected = item.active(view);
        const badge = item.badge ? Number(leadCounts[item.badge] || 0) : 0;
        return <button
          key={item.label}
          className={selected ? "active" : ""}
          aria-current={selected ? "page" : undefined}
          aria-label={badge ? `${item.label} ${badge}` : item.label}
          title={item.hint}
          onClick={() => setView(item.view)}
        >
          <span className={`nav-stamp ${item.tone}`}><DemoIcon name={item.icon} /></span>
          <span className="nav-copy"><strong>{item.label}</strong><small>{item.hint}</small></span>
          {badge > 0 && <b>{badge}</b>}
        </button>;
      })}
    </nav>

    <div className="product-sidebar-spacer" />
    <button className="product-settings" onClick={onSettings} aria-label="Settings" title="Settings">
      <DemoIcon name="settings" /><span>Settings</span><kbd>⌘,</kbd>
    </button>
  </aside>;
}
