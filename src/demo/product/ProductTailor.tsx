import { useState } from "react";
import type { DemoJob } from "../demoData";
import { DemoIcon } from "../DemoIcon";

export function ProductTailor({ jobs, notify }: { jobs: DemoJob[]; notify: (message: string) => void }) {
  const [activeJob, setActiveJob] = useState(jobs[0]);
  const [tab, setTab] = useState("Resume");
  const [generating, setGenerating] = useState(false);
  const generate = () => { setGenerating(true); window.setTimeout(() => { setGenerating(false); notify(`${tab} regenerated from 7 verified evidence nodes`); }, 1500); };
  return <div className="tailor-view product-enter">
    <div className="view-toolbar"><div><span className="product-eyebrow">Grounded document studio</span><h2>Application tailor</h2></div><div className="view-toolbar-actions"><button><DemoIcon name="eye" />Preview package</button><button className="toolbar-primary" onClick={() => notify("Application package exported to your local workspace")}><DemoIcon name="send" />Export package</button></div></div>
    <div className="tailor-layout">
      <aside className="tailor-jobs product-panel"><header><span className="product-eyebrow">Selected role</span><button><DemoIcon name="search" /></button></header><div className="tailor-role"><span className={`opportunity-logo ${activeJob.accent}`}>{activeJob.company[0]}</span><p><strong>{activeJob.role}</strong><small>{activeJob.company}</small></p><b>{activeJob.score}</b></div><span className="tailor-label">Other high-fit roles</span>{jobs.slice(1,6).map(job => <button className={activeJob.id === job.id ? "active" : ""} key={job.id} onClick={() => setActiveJob(job)}><span className={`opportunity-logo ${job.accent}`}>{job.company[0]}</span><p><strong>{job.role}</strong><small>{job.company}</small></p><b>{job.score}</b></button>)}</aside>
      <section className="document-studio product-panel">
        <header><div className="document-tabs">{["Resume","Cover letter","Founder note"].map(item => <button className={tab === item ? "active" : ""} onClick={() => setTab(item)} key={item}>{item}</button>)}</div><div><span><i />Auto-saved</span><button><DemoIcon name="more" /></button></div></header>
        <div className={`document-page ${generating ? "generating" : ""}`}>
          <div className="document-head"><div><h3>Vasudev Siddh</h3><p>Product Engineer · AI Systems · Developer Tools</p></div><span>{tab}</span></div>
          <div className="document-rule" />
          <section><span>PROFILE</span><p>Product-minded engineer building AI-native tools that turn complex systems into clear, dependable experiences. Strong across <mark>agent architecture</mark>, TypeScript, and high-craft interfaces.</p></section>
          <section><span>SELECTED IMPACT</span><h4>JustHireMe · Creator &amp; Product Engineer</h4><p>Designed and shipped a local-first job intelligence workbench that discovers, ranks, and tailors applications across multiple live sources.</p><ul><li>Built an evidence-grounded generation pipeline with <mark>structured scoring and provenance</mark>.</li><li>Orchestrated autonomous discovery agents across 6 sources while keeping candidate data private.</li><li>Created a reusable design system spanning desktop, web, and generated documents.</li></ul></section>
          <div className="evidence-note"><DemoIcon name="link" /><p><strong>7 claims linked to source evidence</strong><small>No unsupported claims detected in this draft</small></p><span>Verified</span></div>
          {generating && <div className="document-loader"><i /><span>Rewriting with grounded evidence…</span></div>}
        </div>
        <footer><span><DemoIcon name="check" />All claims grounded</span><p>418 words · 1 page</p><button onClick={generate} disabled={generating}><DemoIcon name="tailor" />{generating ? "Generating…" : `Regenerate ${tab.toLowerCase()}`}</button></footer>
      </section>
      <aside className="evidence-panel product-panel"><header><div><span className="product-eyebrow">Match evidence</span><h3>Why you fit</h3></div><strong>{activeJob.score}%</strong></header><div className="evidence-ring"><span style={{ "--score": `${activeJob.score * 3.6}deg` } as React.CSSProperties}><b>{activeJob.score}</b><small>match</small></span></div><div className="evidence-list">{activeJob.reasons.map((reason, index) => <div key={reason}><span>{index + 1}</span><p><strong>{reason}</strong><small>{["Strong project evidence","3 verified examples","Direct role overlap"][index]}</small></p><DemoIcon name="check" /></div>)}</div><button><DemoIcon name="profile" />Open evidence graph</button></aside>
    </div>
  </div>;
}
