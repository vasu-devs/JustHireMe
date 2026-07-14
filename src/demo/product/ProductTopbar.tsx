import { DemoIcon } from "../DemoIcon";
import type { ProductView } from "../DemoApp";

const subtitles: Record<ProductView, string> = {
  Overview: "Your opportunity intelligence, distilled",
  Pipeline: "Every role, decision, and next move",
  Scout: "Tune where and how your agent searches",
  Tailor: "Build grounded application assets",
  Profile: "The evidence graph behind every match",
};

export function ProductTopbar({ view, agentRunning, onRun, onCommand, onMenu }: { view: ProductView; agentRunning: boolean; onRun: () => void; onCommand: () => void; onMenu: () => void }) {
  return <header className="product-topbar">
    <button className="product-menu" onClick={onMenu} aria-label="Open navigation"><DemoIcon name="menu" /></button>
    <div className="product-title"><h1>{view}</h1><p>{subtitles[view]}</p></div>
    <button className="product-command-trigger" onClick={onCommand}><DemoIcon name="search" /><span>Search or run a command</span><kbd>⌘ K</kbd></button>
    <div className="product-top-actions"><button className="product-notify" aria-label="Notifications"><span>2</span><DemoIcon name="activity" /></button><button className={`product-run ${agentRunning ? "running" : ""}`} onClick={onRun} disabled={agentRunning}><DemoIcon name="radar" />{agentRunning ? "Agent running" : "Run agent"}<i /></button></div>
  </header>;
}
