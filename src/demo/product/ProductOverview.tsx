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
      <div className="board-session"><span><i />Focus session 04</span><p><b>Today’s decision:</b> choose one role to ship before 4 PM</p><div className="board-presence"><b>VS</b><b>AI</b><b>+2</b><small>Live on board</small></div></div>
      <div className="overview-intro">
        <div className="product-eyebrow"><span className="product-live" />Active opportunity board · July 15</div>
        <h2>Your next job is<br /><em>hiding in plain sight.</em></h2>
        <p>JustHireMe watched <mark className="diary-highlight blue"><strong>486 new roles</strong></mark> while you were away. It filtered the noise, checked the evidence, and found <mark className="diary-highlight yellow">three worth your time</mark>. <span className="diary-reaction">oh, this is good!</span></p>
        <div className="overview-actions"><button onClick={() => onSelect(top[0])}>Review top match <DemoIcon name="arrow" /></button><button onClick={onRun} disabled={agentRunning}><DemoIcon name="radar" />{agentRunning ? "Searching the web…" : "Start a fresh scan"}</button></div>
      </div>
      <div className={`signal-orbit ${agentRunning ? "scanning" : ""}`} aria-label="Opportunity signal visualization">
        <svg className="board-diagram-links" viewBox="0 0 420 286" aria-hidden="true">
          <defs><marker id="board-arrow-coral" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker></defs>
          <path className="link-linear" d="M206 139 C171 102 126 79 82 67" />
          <path className="link-replit" d="M215 139 C257 112 310 101 350 95" />
          <path className="link-mercury" d="M205 149 C168 181 137 210 105 230" />
          <path className="link-proof" d="M209 153 C229 190 260 214 298 228" />
          <text x="138" y="80">evidence</text><text x="278" y="70">freshness</text><text x="126" y="257">signal</text><text x="270" y="269">decision</text>
        </svg>
        <div className="orbit-grid" /><div className="orbit-ring ring-one" /><div className="orbit-ring ring-two" /><div className="orbit-ring ring-three" />
        <div className="orbit-core"><span>94</span><small>top match</small></div>
        <i className="orbit-node node-one"><b>LI</b><span><small>Linear</small><em>Evidence ready</em></span></i><i className="orbit-node node-two"><b>RE</b><span><small>Replit</small><em>91% fit</em></span></i><i className="orbit-node node-three"><b>ME</b><span><small>Mercury</small><em>High signal</em></span></i>
        <i className="orbit-node node-four"><b>→</b><span><small>Next move</small><em>Review Linear</em></span></i>
        <div className="orbit-scanline" />
        <span className="orbit-caption"><i /><b>evidence</b><i /><b>freshness</b><i /><b>fit</b></span>
      </div>
    </section>

    <section className="overview-stats" aria-label="Search performance">
      <article><span className="stat-note">+3! ✦</span><div><span>Qualified</span><DemoIcon name="inbox" /></div><strong>12</strong><p><b>+3</b> since yesterday</p><i style={{ "--fill": "78%" } as React.CSSProperties} /></article>
      <article><span className="stat-note">looking up ↗</span><div><span>Avg. match</span><DemoIcon name="bolt" /></div><strong>84<span>%</span></strong><p><b>+9%</b> above baseline</p><i style={{ "--fill": "84%" } as React.CSSProperties} /></article>
      <article><span className="stat-note">ready!!</span><div><span>Ready to send</span><DemoIcon name="send" /></div><strong>03</strong><p>Evidence verified</p><i style={{ "--fill": "56%" } as React.CSSProperties} /></article>
      <article className="stat-accent"><span className="stat-note">best yet ♡</span><div><span>Response rate</span><DemoIcon name="activity" /></div><strong>28<span>%</span></strong><p><b>2.4×</b> market average</p><i style={{ "--fill": "68%" } as React.CSSProperties} /></article>
    </section>

    <section className="overview-grid">
      <div className="opportunity-panel product-panel">
        <header><div><span className="product-eyebrow">Pinned shortlist</span><h3><mark className="diary-highlight yellow">High-conviction</mark> opportunities</h3><span className="section-scribble">the good ones ↓</span></div><button onClick={() => onNavigate("Pipeline")}>Open pipeline <DemoIcon name="arrow" /></button></header>
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

      <div className="next-move product-panel"><span className="product-eyebrow">Next best move</span><div><span className="next-number">01</span><p><strong>Send Linear today</strong><small>Your evidence is complete and the role is under 24 hours old.</small></p></div><div className="next-checklist" aria-label="Application readiness"><span><i>✓</i><b>Evidence pack</b><em>Ready</em></span><span><i>✓</i><b>Tailored resume</b><em>Ready</em></span><span className="current"><i>→</i><b>Application</b><em>Next</em></span></div><button onClick={() => onSelect(top[0])}>Prepare application <DemoIcon name="arrow" /></button></div>
    </section>
  </div>;
}
