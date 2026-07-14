import { useState } from "react";
import type { DemoJob } from "../demoData";
import { DemoIcon } from "../DemoIcon";

const lanes: Array<{ stage: DemoJob["stage"]; label: string; hint: string }> = [
  { stage: "Discovered", label: "Discovered", hint: "Needs review" },
  { stage: "Tailored", label: "Tailoring", hint: "Assets in progress" },
  { stage: "Ready", label: "Ready", hint: "Waiting for you" },
  { stage: "Applied", label: "Applied", hint: "Follow-up tracked" },
];

export function ProductPipeline({ jobs, onSelect, onMove }: { jobs: DemoJob[]; onSelect: (job: DemoJob) => void; onMove: (id: number, stage: DemoJob["stage"]) => void }) {
  const [query, setQuery] = useState("");
  const filtered = jobs.filter(job => `${job.role} ${job.company}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="pipeline-view product-enter">
    <div className="view-toolbar"><div><span className="product-eyebrow">Your application garden</span><h2>Roles in bloom</h2></div><div className="view-toolbar-actions"><label><DemoIcon name="search" /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Filter roles…" /></label><button><DemoIcon name="tune" />Filter</button><button className="toolbar-primary"><DemoIcon name="plus" />Add role</button></div></div>
    <div className="pipeline-summary"><span><i />8 active roles</span><span>3 ready for review</span><span>2 follow-ups due</span><button>Board <kbd>B</kbd></button><button>List <kbd>L</kbd></button></div>
    <div className="kanban-board">{lanes.map((lane, laneIndex) => {
      const laneJobs = filtered.filter(job => job.stage === lane.stage);
      return <section className={`kanban-lane lane-${lane.stage.toLowerCase()}`} key={lane.stage}>
        <header><div><span>{lane.label}</span><b>{laneJobs.length}</b></div><small>{lane.hint}</small><button aria-label={`Add to ${lane.label}`}><DemoIcon name="plus" /></button></header>
        <div className="kanban-cards">{laneJobs.map(job => <article className="kanban-card" key={job.id}>
          <button className="kanban-open" onClick={() => onSelect(job)}><span className={`opportunity-logo ${job.accent}`}>{job.company[0]}</span><DemoIcon name="more" /><strong>{job.role}</strong><small>{job.company} · {job.location}</small></button>
          <div className="kanban-tags"><span>{job.score}% match</span><span>{job.source}</span></div>
          <div className="kanban-foot"><span><i />{job.posted}</span>{laneIndex < lanes.length - 1 && <button onClick={() => onMove(job.id, lanes[laneIndex + 1].stage)} title={`Move to ${lanes[laneIndex + 1].label}`}><DemoIcon name="arrow" /></button>}</div>
        </article>)}
        {laneJobs.length === 0 && <div className="kanban-empty"><span>Drop roles here</span><small>No opportunities in this stage</small></div>}
        </div>
      </section>;
    })}</div>
  </div>;
}
