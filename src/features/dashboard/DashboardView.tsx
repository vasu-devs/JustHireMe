import { DemoIcon } from "../../demo/DemoIcon";
import type { ApiFetch, Lead, LogLine, OperationProgress, View } from "../../types";
import { leadDisplayHeading, leadSignal } from "../../shared/lib/leadUtils";

function JournalRole({ lead, index, openDrawer }: { lead: Lead; index: number; openDrawer: (lead: Lead) => void }) {
  const { role, company } = leadDisplayHeading(lead);
  return <button className={`journal-role-card role-card-${index + 1}`} onClick={() => openDrawer(lead)}>
    <span className="journal-role-number">0{index + 1}</span>
    <span className="journal-role-copy">
      <small>{company} · {lead.platform || "source"}</small>
      <strong>{role}</strong>
      <em>{lead.status === "approved" ? "Your evidence package is ready" : lead.status === "applied" ? "Application already moving" : "Open the evidence and decide"}</em>
    </span>
    <span className="journal-role-fit"><strong>{leadSignal(lead)}</strong><small>fit</small></span>
    <DemoIcon name="arrow" />
  </button>;
}

export function DashboardView(props: {
  leads: Lead[];
  dueFollowups: Lead[];
  logs: LogLine[];
  setView: (view: View) => void;
  openDrawer: (lead: Lead) => void;
  scanning: boolean;
  reevaluating: boolean;
  cleaning: boolean;
  progress?: OperationProgress;
  onScan: () => void;
  onStopScan: () => void;
  onReevaluate: () => void;
  onStopReevaluate: () => void;
  onCleanup: () => void;
  scanErr: string | null;
  api?: ApiFetch | null;
}) {
  const { leads, dueFollowups, logs, setView, openDrawer, scanning, reevaluating, cleaning, progress, onScan, onStopScan, scanErr } = props;
  const active = leads.filter(lead => lead.status !== "discarded");
  const queue = [...active].sort((a, b) => leadSignal(b) - leadSignal(a) || (b.score || 0) - (a.score || 0)).slice(0, 3);
  const ready = active.filter(lead => lead.status === "approved" || lead.status === "tailoring").length;
  const scores = active.map(lead => leadSignal(lead)).filter(Boolean);
  const average = scores.length ? Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length) : 0;
  const busy = scanning || reevaluating || cleaning;
  const date = new Intl.DateTimeFormat("en", { weekday: "long", month: "long", day: "numeric" }).format(new Date());
  const current = queue[0];

  return <div className="overview-view journal-home product-enter production-dashboard-exact scroll">
    <header className="journal-welcome">
      <div><span>{date}</span><h2>Good morning, Vasudev.</h2></div>
      <p><i /> Scout kept watch overnight. <strong>{queue.length || "No"} roles</strong> deserve a real look.</p>
    </header>

    <section className="journal-spread" aria-label="Today’s opportunity journal">
      <div className="journal-binding" aria-hidden="true">{Array.from({ length: 8 }, (_, index) => <i key={index} />)}</div>

      <article className="journal-page journal-left">
        <div className="journal-page-meta"><span>Field note · live</span><b>private / active</b></div>
        <span className="journal-stamp">Today’s page</span>
        <h3>Find work<br />worth <em>caring about.</em></h3>
        <p className="journal-lede">Not more tabs. Not more applications. Just the few opportunities where your work already tells a compelling story.</p>
        <p className="journal-scribble">quality over panic, always.</p>

        <div className="journal-focus">
          <span className="journal-pin" />
          <div>
            <small>{busy ? "Scout is working" : "One thing before 4 PM"}</small>
            <strong>{busy ? progress?.current || "Checking the evidence" : current ? `Review the ${leadDisplayHeading(current).company} role.` : "Run one focused scan."}</strong>
            {busy && (progress?.total ?? 0) > 0 ? (
              <div className="journal-scan-meter" role="progressbar" aria-valuemin={0} aria-valuemax={progress!.total} aria-valuenow={progress!.completed}>
                <div className="journal-scan-track"><i style={{ width: `${Math.min(100, Math.round((progress!.completed / Math.max(1, progress!.total)) * 100))}%` }} /></div>
                <span>{progress!.completed}/{progress!.total} {progress!.mode === "reevaluate" ? "leads re-scored" : progress!.unit === "leads" ? "leads scored" : "sources scanned"}</span>
              </div>
            ) : (
              <p>{current ? "The evidence is ready and the role is still fresh." : "Scout will bring back only roles with a credible match."}</p>
            )}
          </div>
          {scanning
            ? <button onClick={onStopScan}><DemoIcon name="close" />Stop scan</button>
            : current
              ? <button onClick={() => openDrawer(current)}>Do this next <DemoIcon name="arrow" /></button>
              : <button onClick={onScan} disabled={busy}><DemoIcon name="radar" />Run agent</button>}
        </div>
        {scanErr && <p className="production-scan-error" role="alert">{scanErr}</p>}

        <div className="journal-quick-stats">
          <div><strong>{active.length}</strong><span>worth a look</span><small>live shortlist</small></div>
          <div><strong>{average}%</strong><span>average fit</span><small>evidence ranked</small></div>
          <div><strong>{String(ready).padStart(2, "0")}</strong><span>ready to send</span><small>{dueFollowups.length} follow-ups</small></div>
        </div>
      </article>

      <article className="journal-page journal-right">
        <header>
          <div><span>Today’s strongest signals</span><h3>The roles that made<br />Scout <em>stop scrolling.</em></h3></div>
          <button onClick={() => setView("pipeline")}>All roles <DemoIcon name="arrow" /></button>
        </header>
        <div className="journal-role-stack">
          {queue.length ? queue.map((lead, index) => <JournalRole key={lead.job_id} lead={lead} index={index} openDrawer={openDrawer} />) : <div className="production-empty-note"><DemoIcon name="radar" /><strong>Your shortlist starts here.</strong><p>Run the agent and the strongest evidence-backed roles will be pinned here.</p></div>}
        </div>
        <aside className="journal-proof-note"><span>why these three?</span><p>They reward the exact overlap your evidence already supports.</p><strong>specific proof + role fit + real momentum.</strong></aside>
        <p className="journal-arrow-note">start here ↑</p>
      </article>
    </section>

    <section className="journal-below">
      <article className="journal-log">
        <header><div><span>Scout’s field log</span><h3>While you were away</h3></div><b><i /> Live</b></header>
        <div>{logs.slice(0, 3).map((line, index) => <button key={`${line.ts}-${index}`} onClick={() => setView("activity")}><time>{line.ts}</time><span /><p><strong>{line.src || line.kind}</strong><small>{line.msg}</small></p><DemoIcon name="arrow" /></button>)}{logs.length === 0 && <p className="production-log-empty">Scout’s next meaningful action will appear here.</p>}</div>
      </article>
      <aside className="journal-scan-card">
        <span className="journal-tape" />
        <DemoIcon name="radar" />
        <div><span>Want a wider view?</span><h3>Let Scout look again.</h3><p>It checks the web, removes duplicates, and only brings back roles with evidence.</p></div>
        <button onClick={scanning ? onStopScan : onScan}>{scanning ? <><DemoIcon name="close" />Stop the scan</> : <><DemoIcon name="radar" />Run a fresh scan</>}</button>
      </aside>
    </section>
  </div>;
}
