import type { DemoJob } from "../demoData";
import type { ProductView } from "../DemoApp";
import { DemoIcon } from "../DemoIcon";

const timeline = [
  ["09:42", "Application kit ready", "Linear · 8 assets generated", "lime"],
  ["09:39", "Evidence connected", "7 claims grounded to projects", "blue"],
  ["09:31", "New high-signal role", "Mercury · Staff Frontend", "orange"],
  ["08:58", "Source scan complete", "486 postings · 12 qualified", "muted"],
];

export function ProductOverview({ jobs, onSelect, onNavigate, onRun, agentRunning }: { jobs: DemoJob[]; onSelect: (job: DemoJob) => void; onNavigate: (view: ProductView) => void; onRun: () => void; agentRunning: boolean }) {
  const top = jobs.slice().sort((a, b) => b.score - a.score).slice(0, 4);
  return <div className="overview-view product-enter">
    <section className="overview-hero">
      <div className="overview-intro">
        <div className="product-eyebrow"><span className="product-live" />Wednesday field notes · July 15</div>
        <h2>Your next job is<br /><em>hiding in plain sight.</em></h2>
        <p>JustHireMe watched <strong>486 new roles</strong> while you were away. It filtered the noise, checked the evidence, and found three worth your time.</p>
        <div className="overview-actions"><button onClick={() => onSelect(top[0])}>Review top match <DemoIcon name="arrow" /></button><button onClick={onRun} disabled={agentRunning}><DemoIcon name="radar" />{agentRunning ? "Searching the web…" : "Start a fresh scan"}</button></div>
      </div>
      <div className={`signal-orbit ${agentRunning ? "scanning" : ""}`} aria-label="Opportunity signal visualization">
        <div className="orbit-grid" /><div className="orbit-ring ring-one" /><div className="orbit-ring ring-two" /><div className="orbit-ring ring-three" />
        <div className="orbit-core"><span>94</span><small>top match</small></div>
        <i className="orbit-node node-one"><b>LI</b><small>Linear</small></i><i className="orbit-node node-two"><b>RE</b><small>Replit</small></i><i className="orbit-node node-three"><b>ME</b><small>Mercury</small></i>
        <div className="orbit-scanline" />
        <span className="orbit-caption">Today’s match map · 12 lovely possibilities</span>
      </div>
    </section>

    <section className="overview-stats" aria-label="Search performance">
      <article><div><span>Qualified</span><DemoIcon name="inbox" /></div><strong>12</strong><p><b>+3</b> since yesterday</p><i style={{ "--fill": "78%" } as React.CSSProperties} /></article>
      <article><div><span>Avg. match</span><DemoIcon name="bolt" /></div><strong>84<span>%</span></strong><p><b>+9%</b> above baseline</p><i style={{ "--fill": "84%" } as React.CSSProperties} /></article>
      <article><div><span>Ready to send</span><DemoIcon name="send" /></div><strong>03</strong><p>Evidence verified</p><i style={{ "--fill": "56%" } as React.CSSProperties} /></article>
      <article className="stat-accent"><div><span>Response rate</span><DemoIcon name="activity" /></div><strong>28<span>%</span></strong><p><b>2.4×</b> market average</p><i style={{ "--fill": "68%" } as React.CSSProperties} /></article>
    </section>

    <section className="overview-grid">
      <div className="opportunity-panel product-panel">
        <header><div><span className="product-eyebrow">Priority queue</span><h3>High-conviction opportunities</h3></div><button onClick={() => onNavigate("Pipeline")}>Open pipeline <DemoIcon name="arrow" /></button></header>
        <div className="opportunity-head"><span>Opportunity</span><span>Momentum</span><span>Match</span><span /></div>
        <div className="opportunity-list">{top.map((job, index) => <button key={job.id} className="opportunity-row" onClick={() => onSelect(job)}>
          <span className={`opportunity-logo ${job.accent}`}>{job.company[0]}</span><span className="opportunity-name"><strong>{job.role}</strong><small>{job.company} · {job.location}</small><em>{job.source} · {job.posted}</em></span>
          <span className="opportunity-wave">{[3,6,4,9,7,12,8,14,10,16].map((height, i) => <i key={i} style={{ height: height + (index * 2) }} />)}</span>
          <span className="opportunity-score"><strong>{job.score}</strong><small>{job.signal}</small></span><DemoIcon name="chevron" />
        </button>)}</div>
      </div>

      <aside className="agent-panel product-panel">
        <header><div><span className="product-eyebrow">While you were away</span><h3>Scout’s little notebook</h3></div><span className="panel-live"><i />Live</span></header>
        <div className="agent-timeline">{timeline.map(([time, title, detail, tone]) => <div key={time}><time>{time}</time><i className={tone} /><p><strong>{title}</strong><small>{detail}</small></p></div>)}</div>
        <button onClick={() => onNavigate("Scout")}>Inspect agent reasoning <DemoIcon name="arrow" /></button>
      </aside>

      <div className="focus-panel product-panel">
        <span className="product-eyebrow">This week's focus</span><h3>AI product engineering</h3><p>Your profile has unusual leverage here—agent systems, interface craft, and shipping velocity overlap in <strong>31 open roles.</strong></p>
        <div className="focus-tags"><span>Agent systems <b>92</b></span><span>TypeScript <b>89</b></span><span>0→1 product <b>86</b></span></div>
        <button onClick={() => onNavigate("Scout")}>Tune search direction <DemoIcon name="tune" /></button>
      </div>

      <div className="next-move product-panel"><span className="product-eyebrow">Next best move</span><div><span className="next-number">01</span><p><strong>Send Linear today</strong><small>Your evidence is complete and the role is under 24 hours old.</small></p></div><button onClick={() => onSelect(top[0])}>Prepare application <DemoIcon name="arrow" /></button></div>
    </section>
  </div>;
}
