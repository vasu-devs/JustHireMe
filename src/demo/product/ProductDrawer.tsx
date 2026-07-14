import type { DemoJob } from "../demoData";
import { DemoIcon } from "../DemoIcon";

const stageOrder: DemoJob["stage"][] = ["Discovered", "Tailored", "Ready", "Applied"];

export function ProductDrawer({ job, onClose, onMove, notify }: { job: DemoJob; onClose: () => void; onMove: (stage: DemoJob["stage"]) => void; notify: (message: string) => void }) {
  const current = stageOrder.indexOf(job.stage);
  return <div className="drawer-backdrop" onMouseDown={event => { if (event.currentTarget === event.target) onClose(); }}><aside className="product-drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
    <header><span>Opportunity intelligence</span><div><button aria-label="More actions"><DemoIcon name="more" /></button><button onClick={onClose} aria-label="Close opportunity"><DemoIcon name="close" /></button></div></header>
    <div className="drawer-hero"><span className={`drawer-logo ${job.accent}`}>{job.company[0]}</span><p>{job.company}</p><h2 id="drawer-title">{job.role}</h2><div><span>{job.location}</span><span>{job.salary}</span><span>{job.source}</span></div></div>
    <div className="drawer-stage">{stageOrder.map((stage, index) => <button key={stage} className={index <= current ? "done" : ""} onClick={() => onMove(stage)}><i>{index < current ? <DemoIcon name="check" /> : index + 1}</i><span>{stage}</span></button>)}</div>
    <section className="drawer-match"><div className="drawer-score"><strong>{job.score}</strong><span><b>{job.signal} match</b><small>Top {job.score >= 90 ? "2" : "8"}% of roles seen this week</small></span></div><div className="drawer-scorebar"><i style={{width:`${job.score}%`}} /></div></section>
    <section className="drawer-section"><header><div><span>Why this surfaced</span><h3>Match evidence</h3></div><b>3 verified</b></header><div className="drawer-reasons">{job.reasons.map((reason,index) => <div key={reason}><span><DemoIcon name="check" /></span><p><strong>{reason}</strong><small>{["Backed by 2 recent projects","Direct experience in your graph","Strong semantic overlap"][index]}</small></p><b>{[96,91,87][index]}%</b></div>)}</div></section>
    <section className="drawer-section drawer-insight"><span className="product-eyebrow">Agent insight</span><p>“This role values engineers who can move between product judgment and deep implementation. Your JustHireMe work is unusually direct evidence.”</p><div><span>Low competition window</span><span>Posted {job.posted}</span></div></section>
    <section className="drawer-section"><header><div><span>Application assets</span><h3>Grounded package</h3></div><button onClick={() => notify("Preview opened")}>Preview</button></header><div className="drawer-assets"><button><DemoIcon name="file" /><p><strong>Tailored resume</strong><small>7 evidence links · 1 page</small></p><span>Ready</span></button><button><DemoIcon name="file" /><p><strong>Cover letter</strong><small>Company-aware · 312 words</small></p><span>Ready</span></button><button><DemoIcon name="send" /><p><strong>Founder note</strong><small>Concise outreach · 86 words</small></p><span>Draft</span></button></div></section>
    <footer><button onClick={() => notify(`${job.company} saved to your shortlist`)}>Save for later</button><button onClick={() => { onMove("Ready"); notify("Application package ready for final review"); }}><DemoIcon name="tailor" />Build application kit</button></footer>
  </aside></div>;
}
