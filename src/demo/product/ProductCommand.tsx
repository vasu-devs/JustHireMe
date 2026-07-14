import { useMemo, useState } from "react";
import type { DemoJob } from "../demoData";
import type { ProductView } from "../DemoApp";
import { DemoIcon } from "../DemoIcon";

export function ProductCommand({ jobs, onClose, onNavigate, onSelect }: { jobs: DemoJob[]; onClose: () => void; onNavigate: (view: ProductView) => void; onSelect: (job: DemoJob) => void }) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => jobs.filter(job => `${job.role} ${job.company}`.toLowerCase().includes(query.toLowerCase())).slice(0,4), [jobs, query]);
  return <div className="command-backdrop" onMouseDown={event => { if (event.currentTarget === event.target) onClose(); }}><section className="command-modal" role="dialog" aria-modal="true" aria-label="Command menu"><label><DemoIcon name="search" /><input autoFocus value={query} onChange={event => setQuery(event.target.value)} placeholder="Search roles or type a command…" /><kbd>ESC</kbd></label><div className="command-body">
    {!query && <><span className="command-label">Go to</span><div className="command-grid">{(["Overview","Pipeline","Scout","Tailor","Profile"] as ProductView[]).map((view, i) => <button key={view} onClick={() => onNavigate(view)}><DemoIcon name={["overview","inbox","radar","tailor","profile"][i]} /><span>{view}</span><kbd>G {i+1}</kbd></button>)}</div><span className="command-label">Quick actions</span><button className="command-action"><span><DemoIcon name="radar" /></span><p><strong>Run a fresh scan</strong><small>Search all configured sources</small></p><kbd>↵</kbd></button><button className="command-action"><span><DemoIcon name="plus" /></span><p><strong>Add an opportunity</strong><small>Paste a job URL or description</small></p></button></>}
    {query && <><span className="command-label">Matching opportunities</span>{filtered.map(job => <button className="command-result" key={job.id} onClick={() => onSelect(job)}><span className={`opportunity-logo ${job.accent}`}>{job.company[0]}</span><p><strong>{job.role}</strong><small>{job.company} · {job.location}</small></p><b>{job.score}</b></button>)}{filtered.length === 0 && <div className="command-empty"><DemoIcon name="search" /><strong>No matching command</strong><small>Try a company, role, or workspace name.</small></div>}</>}
  </div><footer><span><kbd>↑↓</kbd> Navigate</span><span><kbd>↵</kbd> Select</span><span>JustHireMe command system</span></footer></section></div>;
}
