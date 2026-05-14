import { useEffect, useMemo, useState } from "react";
import Icon from "../../shared/components/Icon";
import { LeadFilterBar } from "./components/LeadFilterBar";
import { PipelineJobCard, PipelineSkeleton } from "./components/JobCard";
import type { ApiFetch, Lead, LeadSort, PipelineTab, SeniorityFilter } from "../../types";
import { PAGE_SIZE, leadSearchText, sortLeads, seniorityMatches, uniqueLeadValues } from "../../shared/lib/leadUtils";

export function PipelineView({ leads, openDrawer, deleteLead, port, api, scanning, reevaluating, cleaning, onReevaluate, onStopReevaluate, onCleanup, loading, error, tab }: {
  leads: Lead[]; openDrawer: (l: Lead) => void;
  deleteLead: (id: string) => void; port: number | null; api: ApiFetch | null;
  scanning: boolean; reevaluating: boolean; cleaning: boolean; onReevaluate: () => void; onStopReevaluate: () => void; onCleanup: () => void;
  loading: boolean; error: string | null;
  tab: PipelineTab;
}) {
  const [search, setSearch] = useState("");
  const [platform, setPlatform] = useState("");
  const [sort, setSort] = useState<LeadSort>("recommended");
  const [seniority, setSeniority] = useState<SeniorityFilter>("all");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [bulkSelecting, setBulkSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [exporting, setExporting] = useState(false);

  useEffect(() => setVisibleCount(PAGE_SIZE), [tab, search, platform, sort, seniority]);
  useEffect(() => {
    setBulkSelecting(false);
    setSelected(new Set());
  }, [tab]);

  const platforms = useMemo(() => uniqueLeadValues(leads, "platform"), [leads]);

  const tabs = useMemo(() => {
    const q = search.trim().toLowerCase();
    const keep = (lead: Lead) => {
      if (q && !leadSearchText(lead).includes(q)) return false;
      if (platform && lead.platform !== platform) return false;
      if (!seniorityMatches(lead, seniority)) return false;
      return true;
    };
    const apply = (arr: Lead[]) => sortLeads(arr.filter(keep), sort);
    const tabItems: { id: PipelineTab; label: string; tone: string; leads: Lead[] }[] = [
      { id: "all",       label: "All",       tone: "teal",   leads: apply(leads) },
      { id: "hot",       label: "Hot",       tone: "orange", leads: apply(leads.filter(l => (l.signal_score || 0) >= 80 || (l.score || 0) >= 85)) },
      { id: "found",     label: "New",       tone: "blue",   leads: apply(leads.filter(l => l.status === "discovered")) },
      { id: "evaluated", label: "Rated",     tone: "yellow", leads: apply(leads.filter(l => l.score > 0 || (l.signal_score || 0) > 0)) },
      { id: "generated", label: "Ready",     tone: "purple", leads: apply(leads.filter(l => l.status === "tailoring" || l.status === "approved")) },
      { id: "applied",   label: "Applied",   tone: "orange", leads: apply(leads.filter(l => l.status === "applied")) },
      { id: "discarded", label: "Discarded", tone: "bad",    leads: apply(leads.filter(l => l.status === "discarded")) },
    ];
    return tabItems;
  }, [leads, search, platform, sort, seniority]);

  const activeTab = tabs.find(t => t.id === tab) || tabs[0];
  const visibleLeads = activeTab.leads.slice(0, visibleCount);
  const hasFilters = Boolean(search || platform || seniority !== "all" || sort !== "recommended");
  const busyLabel = scanning ? "Scanning for new leads" : reevaluating ? "Re-evaluating fit scores" : cleaning ? "Cleaning bad data" : "";

  const toggleSelect = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const bulkDelete = async () => {
    if (!window.confirm(`Delete ${selected.size} leads?`)) return;
    const count = selected.size;
    const results = await Promise.allSettled([...selected].map(id => Promise.resolve(deleteLead(id))));
    const failed = results.filter(r => r.status === "rejected").length;
    if (failed > 0) alert(`${failed} of ${count} deletions failed. Refreshing list.`);
    setSelected(new Set());
    setBulkSelecting(false);
    window.dispatchEvent(new CustomEvent("leads-refresh"));
  };

  const bulkMarkApplied = async () => {
    if (!api || selected.size === 0) return;
    const ids = [...selected];
    const results = await Promise.allSettled(ids.map(id => api(`/api/v1/leads/${id}/status`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "applied" }),
    })));
    const failed = results.filter(r => r.status === "rejected" || (r.status === "fulfilled" && !r.value.ok)).length;
    if (failed > 0) alert(`${failed} of ${ids.length} jobs could not be marked as applied.`);
    ids.forEach(job_id => window.dispatchEvent(new CustomEvent("lead-updated", { detail: { job_id, status: "applied" } })));
    setSelected(new Set());
    setBulkSelecting(false);
    window.dispatchEvent(new CustomEvent("leads-refresh"));
  };

  const exportCsv = async () => {
    if (!api || exporting) return;
    setExporting(true);
    try {
      const res = await api("/api/v1/leads/export.csv");
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "jhm_pipeline.csv";
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="pipeline-page">
      <div className="pipeline-top">
        {(busyLabel || error) && (
          <div className={`pipeline-notice ${error ? "error" : ""}`}>
            {error ? <Icon name="x" size={13} /> : <span className="dot pulse-soft" />}
            <span>{error || busyLabel}</span>
          </div>
        )}

        <LeadFilterBar
          search={search}
          setSearch={setSearch}
          platform={platform}
          setPlatform={setPlatform}
          sort={sort}
          setSort={setSort}
          seniority={seniority}
          setSeniority={setSeniority}
          platforms={platforms}
          total={activeTab.leads.length}
          shown={Math.min(visibleCount, activeTab.leads.length)}
          label="jobs"
          actions={(
            <>
              <button className="btn" onClick={exportCsv} disabled={!api || exporting || loading}>
                {exporting ? "Exporting..." : "Export"}
              </button>
              {bulkSelecting ? (
                <>
                  <button className="btn" onClick={bulkMarkApplied} disabled={!api || selected.size === 0 || loading}>
                    <Icon name="check" size={13} /> Mark applied {selected.size}
                  </button>
                  <button className="btn" onClick={() => { setBulkSelecting(false); setSelected(new Set()); }}>Cancel</button>
                </>
              ) : (
                <button className="btn" onClick={() => setBulkSelecting(true)} disabled={activeTab.leads.length === 0 || loading}>
                  <Icon name="check" size={13} /> Select
                </button>
              )}
              {reevaluating ? (
                <button className="btn danger" onClick={onStopReevaluate}>
                  <Icon name="x" size={13} /> Stop re-eval
                </button>
              ) : (
                <button className="btn" onClick={onReevaluate} disabled={leads.length === 0 || scanning || cleaning || loading}>
                  <Icon name="pulse" size={13} /> Re-eval
                </button>
              )}
              <button className="btn danger-soft" onClick={onCleanup} disabled={leads.length === 0 || scanning || reevaluating || cleaning || loading}>
                <Icon name="trash" size={13} /> {cleaning ? "Cleaning" : "Clean"}
              </button>
              {tab === "discarded" && (
                bulkSelecting ? (
                  <button className="btn danger" onClick={bulkDelete} disabled={selected.size === 0}>Delete {selected.size}</button>
                ) : (
                  <button className="btn" onClick={() => setBulkSelecting(true)} disabled={activeTab.leads.length === 0}>Bulk delete</button>
                )
              )}
            </>
          )}
        />
      </div>

      <div className="pipeline-content scroll">
        <div className="pipeline-results-head">
          <div>
            <h3>{activeTab.label}</h3>
            <p>{hasFilters ? "Filtered results" : "All matching leads"} - showing {Math.min(visibleCount, activeTab.leads.length)} of {activeTab.leads.length}</p>
          </div>
          {bulkSelecting && (
            <span className={`pipeline-selected mono ${tab === "discarded" ? "danger" : "applied"}`}>
              {selected.size} selected
            </span>
          )}
        </div>
        {loading ? (
          <PipelineSkeleton />
        ) : activeTab.leads.length === 0 ? (
          <div className="pipeline-empty">
            <Icon name={hasFilters ? "filter" : "search"} size={18} />
            <h3>{hasFilters ? "No leads match these filters" : `No ${activeTab.label.toLowerCase()} jobs yet`}</h3>
            <p>{hasFilters ? "Clear filters or lower the score thresholds." : "Run a scan from the dashboard or customize a pasted job to start filling this lane."}</p>
          </div>
        ) : (
          <div className="pipeline-list">
            {visibleLeads.map(lead => (
              <div key={lead.job_id} className="pipeline-list-item">
                {bulkSelecting && (
                  <div
                    className="pipeline-select-box"
                    onClick={() => toggleSelect(lead.job_id)}
                    style={{
                      borderColor: selected.has(lead.job_id) ? (tab === "discarded" ? "var(--bad)" : "var(--orange)") : "var(--line)",
                      background: selected.has(lead.job_id) ? (tab === "discarded" ? "var(--bad)" : "var(--orange)") : "var(--paper)",
                    }}
                  >
                    {selected.has(lead.job_id) && <Icon name="check" size={11} color="#fff" />}
                  </div>
                )}
                <PipelineJobCard
                  lead={lead}
                  onOpen={openDrawer}
                  onDelete={deleteLead}
                  showGenerate={tab === "evaluated"}
                  port={port}
                  api={api}
                />
              </div>
            ))}
          </div>
        )}
        {activeTab.leads.length > visibleCount && (
          <div className="row" style={{ justifyContent: "center", marginTop: 18 }}>
            <button className="btn" onClick={() => setVisibleCount(v => v + PAGE_SIZE)}>
              Show next {Math.min(PAGE_SIZE, activeTab.leads.length - visibleCount)} of {activeTab.leads.length}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════
   PENTAGON GRAPH COMPONENT
══════════════════════════════════════ */
