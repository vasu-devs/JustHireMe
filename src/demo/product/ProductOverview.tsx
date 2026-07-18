import type { DemoJob } from "../demoData";
import type { ProductView } from "../DemoApp";
import { DemoIcon } from "../DemoIcon";

const fieldLog = [
  ["09:42", "Linear kit is ready", "8 grounded assets"],
  ["09:31", "Mercury surfaced", "fresh, high-signal role"],
  ["08:58", "Noise cleared", "486 → 12 qualified"],
];

export function ProductOverview({ jobs, onSelect, onNavigate, onRun, agentRunning }: { jobs: DemoJob[]; onSelect: (job: DemoJob) => void; onNavigate: (view: ProductView) => void; onRun: () => void; agentRunning: boolean }) {
  const top = jobs.slice().sort((a, b) => b.score - a.score).slice(0, 3);

  return <div className="overview-view journal-home product-enter">
    <header className="journal-welcome">
      <div><span>Wednesday, July 15</span><h2>Good morning, Vasudev.</h2></div>
      <p><i /> Scout kept watch overnight. <strong>Three roles</strong> deserve a real look.</p>
    </header>

    <section className="journal-spread" aria-label="Today’s opportunity journal">
      <div className="journal-binding" aria-hidden="true">{Array.from({ length: 8 }, (_, index) => <i key={index} />)}</div>

      <article className="journal-page journal-left">
        <div className="journal-page-meta"><span>Field note · 029</span><b>private / active</b></div>
        <span className="journal-stamp">Today’s page</span>
        <h3>Find work<br />worth <em>caring about.</em></h3>
        <p className="journal-lede">Not more tabs. Not more applications. Just the few opportunities where your work already tells a compelling story.</p>
        <p className="journal-scribble">quality over panic, always.</p>

        <div className="journal-focus">
          <span className="journal-pin" />
          <div><small>One thing before 4 PM</small><strong>Send the Linear application.</strong><p>The evidence is ready and the role is still fresh.</p></div>
          <button onClick={() => onSelect(top[0])}>Do this next <DemoIcon name="arrow" /></button>
        </div>

        <div className="journal-quick-stats">
          <div><strong>12</strong><span>worth a look</span><small>+3 today</small></div>
          <div><strong>84%</strong><span>average fit</span><small>up 9%</small></div>
          <div><strong>03</strong><span>ready to send</span><small>proof checked</small></div>
        </div>
      </article>

      <article className="journal-page journal-right">
        <header><div><span>Today’s strongest signals</span><h3>The roles that made<br />Scout <em>stop scrolling.</em></h3></div><button onClick={() => onNavigate("Pipeline")}>All roles <DemoIcon name="arrow" /></button></header>
        <div className="journal-role-stack">{top.map((job, index) => <button key={job.id} className={`journal-role-card role-card-${index + 1}`} onClick={() => onSelect(job)}>
          <span className="journal-role-number">0{index + 1}</span>
          <span className="journal-role-copy"><small>{job.company} · {job.posted}</small><strong>{job.role}</strong><em>{index === 0 ? "Your clearest evidence match" : index === 1 ? "Fresh role, unusual overlap" : "A credible, exciting stretch"}</em></span>
          <span className="journal-role-fit"><strong>{job.score}</strong><small>fit</small></span>
          <DemoIcon name="arrow" />
        </button>)}</div>
        <div className="journal-proof-note"><span>why these three?</span><p>They reward the exact overlap you already own:</p><strong>agent systems + product judgment + shipping.</strong></div>
        <p className="journal-arrow-note">start here ↑</p>
      </article>
    </section>

    <section className="journal-below">
      <article className="journal-log">
        <header><div><span>Scout’s field log</span><h3>While you were away</h3></div><b><i /> Live</b></header>
        <div>{fieldLog.map(([time, title, detail]) => <button key={time} onClick={() => onNavigate("Scout")}><time>{time}</time><span /><p><strong>{title}</strong><small>{detail}</small></p><DemoIcon name="chevron" /></button>)}</div>
      </article>

      <aside className="journal-scan-card">
        <span className="journal-tape" />
        <DemoIcon name="radar" />
        <div><span>Want a wider view?</span><h3>Let Scout look again.</h3><p>It checks the web, removes duplicates, and only brings back roles with evidence.</p></div>
        <button onClick={onRun} disabled={agentRunning}>{agentRunning ? "Looking…" : "Run a fresh scan"}<DemoIcon name="arrow" /></button>
      </aside>
    </section>
  </div>;
}
