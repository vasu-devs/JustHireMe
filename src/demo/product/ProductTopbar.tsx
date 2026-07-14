import { DemoIcon } from "../DemoIcon";
import type { ProductView } from "../DemoApp";

const subtitles: Record<ProductView, string> = {
  Overview: "Your opportunity command board",
  Pipeline: "Every role moving forward",
  Scout: "Search sources and territory",
  Tailor: "Application workshop",
  Profile: "Your connected evidence map",
};

const indexes: Record<ProductView, string> = { Overview: "01", Pipeline: "02", Scout: "03", Tailor: "04", Profile: "05" };

export function ProductTopbar({ view, agentRunning, onRun, onCommand, onMenu }: { view: ProductView; agentRunning: boolean; onRun: () => void; onCommand: () => void; onMenu: () => void }) {
  return <header className="product-topbar">
    <button className="product-menu" onClick={onMenu} aria-label="Open navigation"><DemoIcon name="menu" /></button>
    <div className="product-title"><span className="product-title-index">{indexes[view]}</span><div><small>Opportunity board · July sprint</small><h1>{view}</h1><p>{subtitles[view]}</p></div></div>
    <button className="product-command-trigger" onClick={onCommand}><DemoIcon name="search" /><span>Search or run a command</span><kbd>⌘ K</kbd></button>
    <div className="product-top-actions"><button className="product-notify" aria-label="Notifications"><span>2</span><DemoIcon name="activity" /></button><button className={`product-run ${agentRunning ? "running" : ""}`} onClick={onRun} disabled={agentRunning}><DemoIcon name="radar" />{agentRunning ? "Agent running" : "Run agent"}<i /></button></div>
  </header>;
}
