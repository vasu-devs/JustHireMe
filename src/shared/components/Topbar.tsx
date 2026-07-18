import { DemoIcon } from "../../demo/DemoIcon";
import type { OperationProgress, View } from "../../types";
import { useTheme } from "../lib/theme";

const titleFor = (view: View) => {
  if (view === "dashboard") return "Today";
  if (view === "apply") return "Tailor";
  if (view === "activity") return "Scout";
  if (view === "graph") return "Knowledge";
  if (view === "ingestion") return "Context";
  if (view === "profile") return "Profile";
  return "Pipeline";
};

const subtitleFor = (view: View) => {
  if (view === "dashboard") return "Your opportunity command board";
  if (view === "apply") return "Application workshop";
  if (view === "activity") return "Search sources and field notes";
  if (view === "graph") return "Your connected evidence atlas";
  if (view === "ingestion") return "Add resume, projects, links, and proof";
  if (view === "profile") return "Your connected evidence map";
  return "Every role moving forward";
};

export function Topbar({
  view,
  progress,
  onRun,
  onCommand,
  onNavigate,
}: {
  view: View;
  progress?: OperationProgress;
  onRun?: () => void;
  onCommand?: () => void;
  onNavigate?: (view: View) => void;
}) {
  const { resolved, setPref } = useTheme();
  const running = Boolean(progress?.active);
  const title = titleFor(view);

  return <header className="product-topbar production-product-topbar">
    <div className="product-title">
      <span className="product-title-index">01</span>
      <div><small>Search journal · July sprint</small><h1>{title}</h1><p>{subtitleFor(view)}</p></div>
    </div>
    <button className="product-command-trigger" onClick={onCommand} aria-label="Search or run a command">
      <DemoIcon name="search" /><span>Search or run a command</span><kbd>⌘ K</kbd>
    </button>
    <div className="product-top-actions">
      <button className="product-theme-toggle" onClick={() => setPref(resolved === "dark" ? "light" : "dark")} aria-label={`Switch to ${resolved === "dark" ? "light" : "dark"} mode`}>
        <span><DemoIcon name="sun" /><DemoIcon name="moon" /></span>
      </button>
      <button className="product-notify" aria-label="Notifications" onClick={() => onNavigate?.("activity")}><span>2</span><DemoIcon name="activity" /></button>
      <button className={`product-run ${running ? "running" : ""}`} onClick={onRun} disabled={running || !onRun}>
        <DemoIcon name="radar" />{running ? "Agent running" : "Run agent"}<i />
      </button>
    </div>
  </header>;
}
