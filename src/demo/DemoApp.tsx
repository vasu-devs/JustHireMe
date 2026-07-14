import { useEffect, useState } from "react";
import type { DemoJob } from "./demoData";
import { demoJobs } from "./demoData";
import { ProductSidebar } from "./product/ProductSidebar";
import { ProductTopbar } from "./product/ProductTopbar";
import { ProductOverview } from "./product/ProductOverview";
import { ProductPipeline } from "./product/ProductPipeline";
import { ProductScout } from "./product/ProductScout";
import { ProductTailor } from "./product/ProductTailor";
import { ProductProfile } from "./product/ProductProfile";
import { ProductCommand } from "./product/ProductCommand";
import { ProductDrawer } from "./product/ProductDrawer";
import { DemoIcon } from "./DemoIcon";
import "./product.css";
import "./handdrawn.css";
import "./polish.css";
import "./diary.css";
import "./board.css";

export type ProductView = "Overview" | "Pipeline" | "Scout" | "Tailor" | "Profile";

export default function DemoApp() {
  const [view, setView] = useState<ProductView>("Overview");
  const [jobs, setJobs] = useState(demoJobs);
  const [selected, setSelected] = useState<DemoJob | null>(null);
  const [palette, setPalette] = useState(false);
  const [menu, setMenu] = useState(false);
  const [agentRunning, setAgentRunning] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); setPalette(value => !value);
      }
      if (event.key === "Escape") { setPalette(false); setSelected(null); setMenu(false); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    document.getElementById("product-content")?.scrollTo({ top: 0, behavior: "auto" });
  }, [view]);

  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 3200);
  };
  const runAgent = () => {
    if (agentRunning) return;
    setAgentRunning(true);
    window.setTimeout(() => { setAgentRunning(false); notify("Scout finished · 3 new roles ranked and deduplicated"); }, 2200);
  };
  const moveJob = (id: number, stage: DemoJob["stage"]) => {
    setJobs(current => current.map(job => job.id === id ? { ...job, stage } : job));
    notify(`Moved to ${stage}`);
  };

  return <div className="product-app">
    <a className="product-skip" href="#product-content">Skip to workspace</a>
    <ProductSidebar view={view} onChange={setView} open={menu} onClose={() => setMenu(false)} />
    {menu && <button className="product-scrim" onClick={() => setMenu(false)} aria-label="Close navigation" />}
    <div className="product-shell">
      <ProductTopbar view={view} agentRunning={agentRunning} onRun={runAgent} onCommand={() => setPalette(true)} onMenu={() => setMenu(true)} />
      <main id="product-content" className="product-content">
        {view === "Overview" && <ProductOverview jobs={jobs} onSelect={setSelected} onNavigate={setView} onRun={runAgent} agentRunning={agentRunning} />}
        {view === "Pipeline" && <ProductPipeline jobs={jobs} onSelect={setSelected} onMove={moveJob} />}
        {view === "Scout" && <ProductScout running={agentRunning} onRun={runAgent} notify={notify} />}
        {view === "Tailor" && <ProductTailor jobs={jobs} notify={notify} />}
        {view === "Profile" && <ProductProfile notify={notify} />}
      </main>
    </div>
    {palette && <ProductCommand jobs={jobs} onClose={() => setPalette(false)} onNavigate={value => { setView(value); setPalette(false); }} onSelect={job => { setSelected(job); setPalette(false); }} />}
    {selected && <ProductDrawer job={selected} onClose={() => setSelected(null)} onMove={stage => { moveJob(selected.id, stage); setSelected({ ...selected, stage }); }} notify={notify} />}
    <div className={`product-toast ${toast ? "show" : ""}`} role="status"><span><DemoIcon name="check" />{toast}</span><button onClick={() => setToast("")} aria-label="Dismiss"><DemoIcon name="close" /></button></div>
  </div>;
}
