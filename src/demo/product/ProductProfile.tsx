import { DemoIcon } from "../DemoIcon";

const nodes = [
  ["TypeScript", 24, 22, "skill", 92], ["AI agents", 50, 16, "skill", 96], ["Product craft", 76, 25, "skill", 89],
  ["JustHireMe", 34, 48, "project", 94], ["Local-first", 63, 46, "topic", 86], ["React", 84, 55, "skill", 91],
  ["Python", 17, 69, "skill", 78], ["Tauri", 47, 77, "topic", 82], ["Open source", 73, 78, "topic", 88],
];

export function ProductProfile({ notify }: { notify: (message: string) => void }) {
  return <div className="profile-view product-enter">
    <div className="view-toolbar"><div><span className="product-eyebrow">Your story, mapped</span><h2>Evidence garden</h2></div><div className="view-toolbar-actions"><button><DemoIcon name="plus" />Add evidence</button><button className="toolbar-primary" onClick={() => notify("Profile graph refreshed · 4 new links created")}><DemoIcon name="radar" />Refresh graph</button></div></div>
    <div className="profile-grid">
      <section className="graph-panel product-panel"><header><div><span className="product-eyebrow">Knowledge topology</span><h3>Your professional signal</h3></div><div><button className="active">Graph</button><button>Timeline</button><button><DemoIcon name="tune" /></button></div></header><div className="graph-canvas"><svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path d="M24 22 50 16 76 25M24 22 34 48 17 69M50 16 34 48 63 46 76 25M76 25 84 55 73 78M34 48 47 77 17 69M63 46 47 77 73 78 84 55" /></svg>{nodes.map(([name,x,y,type,score]) => <button key={name} className={`graph-node ${type}`} style={{ left:`${x}%`,top:`${y}%` }}><i>{score}</i><strong>{name}</strong><small>{type}</small></button>)}<span className="graph-legend">9 visible nodes · 28 evidence links</span></div></section>
      <aside className="profile-score product-panel"><span className="product-eyebrow">Profile readiness</span><div className="profile-score-number">96<small>/100</small></div><h3>Exceptionally strong</h3><p>Your profile has enough specific, verified evidence to tailor high-quality applications across 4 role families.</p><div><span><b>Evidence depth</b><i><em style={{width:"96%"}} /></i><small>96</small></span><span><b>Role clarity</b><i><em style={{width:"88%"}} /></i><small>88</small></span><span><b>Recency</b><i><em style={{width:"91%"}} /></i><small>91</small></span></div></aside>
      <section className="profile-assets product-panel"><header><div><span className="product-eyebrow">Evidence library</span><h3>Connected material</h3></div><button>View all <DemoIcon name="arrow" /></button></header><div>{[["Resume · July 2026","18 evidence nodes","file"],["GitHub · vasu-devs","32 repositories indexed","link"],["Portfolio projects","7 case studies","overview"],["Career notes","14 narrative signals","file"]].map(([title,detail,icon]) => <button key={title}><span><DemoIcon name={icon} /></span><p><strong>{title}</strong><small>{detail}</small></p><DemoIcon name="chevron" /></button>)}</div></section>
      <section className="profile-gaps product-panel"><span className="product-eyebrow">Suggested enrichment</span><h3>Make your next match stronger</h3><div><span>01</span><p><strong>Add measurable impact to JustHireMe</strong><small>Quantified outcomes would strengthen 9 target roles.</small></p><button>Add context</button></div><div><span>02</span><p><strong>Connect one leadership example</strong><small>Your seniority signal is strong but lightly evidenced.</small></p><button>Add context</button></div></section>
    </div>
  </div>;
}
