import { useMemo, useState } from "react";

const LANE_PAGE_SIZE = 8;
import { DemoIcon } from "../../demo/DemoIcon";
import type { ApiFetch, Lead, PipelineTab, View } from "../../types";
import { leadDisplayHeading, leadSearchText, leadSignal } from "../../shared/lib/leadUtils";

type BoardLane = "Discovered" | "Tailoring" | "Ready" | "Applied" | "Discarded";

const LANES: Array<{ id: BoardLane; hint: string; next?: string }> = [
  { id: "Discovered", hint: "Needs review", next: "tailoring" },
  { id: "Tailoring", hint: "Assets in progress", next: "approved" },
  { id: "Ready", hint: "Waiting for you", next: "applied" },
  { id: "Applied", hint: "Follow-up tracked" },
];

const PIPELINE_FILTERS: Array<{ label: string; view: View }> = [
  { label: "All", view: "pipeline" },
  { label: "Hot", view: "pipeline-hot" },
  { label: "New", view: "pipeline-found" },
  { label: "Rated", view: "pipeline-evaluated" },
  { label: "Ready", view: "pipeline-generated" },
  { label: "Applied", view: "pipeline-applied" },
  { label: "Discarded", view: "pipeline-discarded" },
];

function laneFor(lead: Lead): BoardLane {
  if (lead.status === "discarded" || lead.status === "rejected") return "Discarded";
  if (["applied", "interviewing", "accepted"].includes(lead.status)) return "Applied";
  if (lead.status === "approved") return "Ready";
  if (lead.status === "tailoring" || lead.score > 0 || (lead.signal_score || 0) > 0) return "Tailoring";
  return "Discovered";
}

export function PipelineView({
  leads,
  openDrawer,
  deleteLead,
  api,
  scanning,
  reevaluating,
  cleaning,
  onReevaluate,
  onStopReevaluate,
  loading,
  error,
  tab,
  setView,
}: {
  leads: Lead[];
  openDrawer: (lead: Lead) => void;
  deleteLead: (id: string) => void;
  port: number | null;
  api: ApiFetch | null;
  scanning: boolean;
  reevaluating: boolean;
  cleaning: boolean;
  onReevaluate: () => void;
  onStopReevaluate: () => void;
  onCleanup: () => void;
  loading: boolean;
  error: string | null;
  tab: PipelineTab;
  setView: (view: View) => void;
}) {
  const [query, setQuery] = useState("");
  const [moving, setMoving] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  // Per-lane visible-card windows so a 40-card lane doesn't become an
  // unreadable infinite scroll; "Show more" reveals a page at a time.
  const [laneLimits, setLaneLimits] = useState<Record<string, number>>({});

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    let rows = needle ? leads.filter(lead => leadSearchText(lead).includes(needle)) : leads;
    if (tab === "hot") rows = rows.filter(lead => leadSignal(lead) >= 80);
    if (tab === "found") rows = rows.filter(lead => laneFor(lead) === "Discovered");
    if (tab === "evaluated") rows = rows.filter(lead => lead.score > 0 || (lead.signal_score || 0) > 0);
    if (tab === "generated") rows = rows.filter(lead => ["Tailoring", "Ready"].includes(laneFor(lead)));
    if (tab === "applied") rows = rows.filter(lead => laneFor(lead) === "Applied");
    if (tab === "discarded") rows = rows.filter(lead => laneFor(lead) === "Discarded");
    return [...rows].sort((a, b) => leadSignal(b) - leadSignal(a));
  }, [leads, query, tab]);

  const moveLead = async (lead: Lead, nextStatus: string) => {
    if (!api || moving) return;
    setMoving(lead.job_id);
    setActionError(null);
    try {
      const response = await api(`/api/v1/leads/${lead.job_id}/status`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      if (!response.ok) throw new Error(`Move failed (${response.status})`);
      window.dispatchEvent(new CustomEvent("lead-updated", { detail: { ...lead, status: nextStatus } }));
      window.dispatchEvent(new CustomEvent("leads-refresh"));
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Could not move this role");
    } finally {
      setMoving(null);
    }
  };

  const active = filtered.filter(lead => laneFor(lead) !== "Discarded");
  const boardRows = tab === "discarded" ? filtered : active;
  const boardLanes: Array<{ id: BoardLane; hint: string; next?: string }> = tab === "discarded"
    ? [{ id: "Discarded", hint: "Set aside for a reason" }]
    : LANES;
  const readyCount = active.filter(lead => laneFor(lead) === "Ready").length;
  const discardedCount = filtered.filter(lead => laneFor(lead) === "Discarded").length;
  const busy = scanning || reevaluating || cleaning;

  return <div className="pipeline-view product-enter production-pipeline-exact scroll">
    <div className="view-toolbar">
      <div><span className="product-eyebrow">Your application board</span><h2>Roles in <em>motion</em></h2><span className="toolbar-scribble">keep these close ✦</span></div>
      <div className="view-toolbar-actions">
        <label><DemoIcon name="search" /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Filter roles…" /></label>
        <button onClick={reevaluating ? onStopReevaluate : onReevaluate} disabled={busy && !reevaluating}><DemoIcon name="tune" />{reevaluating ? "Stop review" : "Re-score"}</button>
        <button className="toolbar-primary" onClick={() => setView("apply")}><DemoIcon name="plus" />Add role</button>
      </div>
    </div>

    <div className="pipeline-summary">
      <span><i />{active.length} active roles</span>
      <span><mark className="diary-highlight pink">{readyCount} ready for review</mark></span>
      <span>{discardedCount} set aside</span>
      <div className="board-presence"><b>VS</b><b>AI</b><small>Live review session</small></div>
      <button className="active">Board <kbd>B</kbd></button><button onClick={() => setView(tab === "all" ? "pipeline-hot" : "pipeline")}>Focus <kbd>F</kbd></button>
    </div>

    <nav className="production-pipeline-lanes" aria-label="Pipeline views">
      {PIPELINE_FILTERS.map(item => {
        const selected = item.view === "pipeline" ? tab === "all" : item.view.endsWith(tab);
        return <button key={item.view} className={selected ? "active" : ""} onClick={() => setView(item.view)}>{item.label}</button>;
      })}
    </nav>

    {(error || actionError) && <div className="pipeline-notice error"><DemoIcon name="close" /><span>{error || actionError}</span></div>}
    {loading ? <div className="kanban-loading">Opening your live application board…</div> : <div className={`kanban-board ${tab === "discarded" ? "is-single" : ""}`}>
      {boardLanes.map((lane, laneIndex) => {
        const laneLeads = boardRows.filter(lead => laneFor(lead) === lane.id);
        // Lanes with dozens of cards were an unreadable infinite scroll — show
        // a page at a time, with an explicit reveal for the rest.
        const laneLimit = laneLimits[lane.id] ?? LANE_PAGE_SIZE;
        const visibleLeads = laneLeads.slice(0, laneLimit);
        const hiddenCount = laneLeads.length - visibleLeads.length;
        return <section className={`kanban-lane lane-${lane.id.toLowerCase()}`} key={lane.id}>
          <header><div><span>{lane.id}</span><b>{laneLeads.length}</b></div><small>{lane.hint}</small><button aria-label={`Add to ${lane.id}`} onClick={() => setView("apply")}><DemoIcon name="plus" /></button></header>
          <div className="kanban-cards">
            {visibleLeads.map(lead => {
              const { role, company } = leadDisplayHeading(lead);
              return <article className="kanban-card" key={lead.job_id}>
                <button className="kanban-open" onClick={() => openDrawer(lead)}>
                  <span className={`opportunity-logo ${["coral", "blue", "violet", "green"][laneIndex]}`}>{company.slice(0, 1).toUpperCase()}</span>
                  <DemoIcon name="more" /><strong>{role}</strong><small>{company} · {lead.location || lead.platform || "Remote"}</small>
                </button>
                <div className="kanban-tags"><span>{leadSignal(lead)}% match</span><span>{lead.platform || "direct"}</span></div>
                <div className="kanban-foot"><span><i />{lead.status}</span><div>
                  <button onClick={() => { if (window.confirm(`Remove ${role}?`)) Promise.resolve(deleteLead(lead.job_id)).catch(cause => setActionError(String(cause))); }} title="Remove role"><DemoIcon name="close" /></button>
                  {lane.next && <button onClick={() => moveLead(lead, lane.next!)} disabled={moving === lead.job_id} title={`Move to ${LANES[laneIndex + 1]?.id}`}><DemoIcon name="arrow" /></button>}
                </div></div>
              </article>;
            })}
            {laneLeads.length === 0 && <div className="kanban-empty"><span>Drop roles here</span><small>No opportunities in this stage</small></div>}
            {hiddenCount > 0 && (
              <button
                className="kanban-more"
                onClick={() => setLaneLimits(prev => ({ ...prev, [lane.id]: laneLimit + LANE_PAGE_SIZE }))}
              >
                Show {Math.min(LANE_PAGE_SIZE, hiddenCount)} more · {hiddenCount} hidden
              </button>
            )}
            {hiddenCount === 0 && laneLeads.length > LANE_PAGE_SIZE && (
              <button
                className="kanban-more"
                onClick={() => setLaneLimits(prev => ({ ...prev, [lane.id]: LANE_PAGE_SIZE }))}
              >
                Show less
              </button>
            )}
          </div>
        </section>;
      })}
    </div>}
  </div>;
}
