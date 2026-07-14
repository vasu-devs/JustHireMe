import { useState } from "react";
import { DemoIcon } from "../DemoIcon";

const initialSources = [
  ["Hacker News", "Who is hiring threads", true, "128"],
  ["YC Work at a Startup", "High-signal startup roles", true, "84"],
  ["LinkedIn", "Network and recruiter signals", true, "173"],
  ["Wellfound", "Early-stage teams", true, "61"],
  ["Remote OK", "Remote-first opportunities", false, "22"],
  ["Company watchlist", "19 hand-picked teams", true, "18"],
] as const;

export function ProductScout({ running, onRun, notify }: { running: boolean; onRun: () => void; notify: (message: string) => void }) {
  const [sources, setSources] = useState(() => initialSources.map(source => ({ name: source[0], detail: source[1], active: source[2], count: source[3] })));
  const [strict, setStrict] = useState(true);
  return <div className="scout-view product-enter">
    <div className="view-toolbar"><div><span className="product-eyebrow">Search sketchbook</span><h2>Where Scout wanders</h2></div><div className="view-toolbar-actions"><button onClick={() => notify("Search settings saved locally")}><DemoIcon name="check" />Save configuration</button><button className={`toolbar-primary ${running ? "is-running" : ""}`} onClick={onRun} disabled={running}><DemoIcon name="radar" />{running ? "Scanning 6 sources" : "Run scout now"}</button></div></div>
    <div className="scout-grid">
      <section className="scout-radar product-panel">
        <header><div><span className="product-eyebrow">Live discovery field</span><h3>{running ? "Scanning the market…" : "Ready for next scan"}</h3></div><span className="scout-status"><i />{running ? "Live" : "Standby"}</span></header>
        <div className={`radar-field ${running ? "running" : ""}`}><div className="radar-rings" /><div className="radar-beam" />{[[22,30],[68,24],[78,66],[43,74],[31,55]].map(([x,y], i) => <i key={i} style={{ left:`${x}%`, top:`${y}%`, animationDelay:`${i * .3}s` }}><span>{["HN","YC","LI","WF","CO"][i]}</span></i>)}<div className="radar-center"><DemoIcon name="radar" /></div></div>
        <div className="radar-metrics"><div><span>486</span><small>roles watched</small></div><div><span>31</span><small>passed filters</small></div><div><span>12</span><small>profile matches</small></div><div><span>03</span><small>high conviction</small></div></div>
      </section>

      <section className="source-panel product-panel"><header><div><span className="product-eyebrow">Connected sources</span><h3>Where Scout looks</h3></div><button><DemoIcon name="plus" />Add source</button></header><div className="source-list">{sources.map((source, index) => <div key={source.name}><span className="source-mark">{source.name.slice(0,2).toUpperCase()}</span><p><strong>{source.name}</strong><small>{source.detail}</small></p><b>{source.count}</b><button className={`product-switch ${source.active ? "on" : ""}`} onClick={() => setSources(current => current.map((item, i) => i === index ? { ...item, active: !item.active } : item))} aria-label={`${source.active ? "Disable" : "Enable"} ${source.name}`}><i /></button></div>)}</div></section>

      <section className="criteria-panel product-panel"><header><div><span className="product-eyebrow">Search thesis</span><h3>What good looks like</h3></div><button><DemoIcon name="tune" />Edit</button></header><div className="criteria-copy"><p>Senior product engineering roles at ambitious, design-aware teams building <em>AI tools, developer infrastructure, or workflow products.</em></p><div className="criteria-tags"><span>Remote or London <button>×</button></span><span>$150k+ / £95k+ <button>×</button></span><span>TypeScript <button>×</button></span><span>AI product <button>×</button></span><span>Series A–D <button>×</button></span><button><DemoIcon name="plus" />Add signal</button></div></div><div className="strict-row"><div><strong>Strict evidence mode</strong><small>Discard roles that cannot be supported by your profile graph</small></div><button className={`product-switch ${strict ? "on" : ""}`} onClick={() => setStrict(value => !value)} aria-label="Toggle strict evidence mode"><i /></button></div></section>

      <section className="quality-panel product-panel"><span className="product-eyebrow">Signal quality</span><div className="quality-score"><strong>8.7</strong><span>/ 10</span></div><p>Your search is focused enough to reduce noise without hiding adjacent opportunities.</p><div className="quality-bars"><span><i style={{ width:"92%" }} /><b>Role clarity</b></span><span><i style={{ width:"84%" }} /><b>Source quality</b></span><span><i style={{ width:"78%" }} /><b>Market breadth</b></span></div></section>
    </div>
  </div>;
}
