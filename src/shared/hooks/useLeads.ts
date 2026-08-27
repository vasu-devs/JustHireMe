import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { eventsApi, isAbortLikeError, leadsApi } from "../../api";
import type { ApiFetch, Lead, LogLine } from "../../types";

export function useLeads(api: ApiFetch | null, addLog?: (msg: string, kind: LogLine["kind"], src?: string) => void) {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const initialLoadDone = useRef(false);
  const knownLeadIds = useRef<Set<string>>(new Set());

  const notifyStrongLead = (lead: Lead) => {
    const fitScore = lead.score || 0;
    if (fitScore < 80) return;
    invoke("notify_high_score_lead", {
      title: `Strong match: ${lead.title}`,
      body: `${lead.company} · Fit ${fitScore}`,
    }).catch(() => {});
  };

  useEffect(() => {
    if (!api) {
      setLoading(true);
      setLoaded(false);
      setError(null);
      initialLoadDone.current = false;
      return;
    }
    let alive = true;
    const controller = new AbortController();
    // Stamp every snapshot fetch; WS lead updates bump the stamp too, so a
    // fetch that resolves with a pre-update snapshot is discarded instead of
    // reverting fresher WS-driven state. A discarded snapshot schedules one
    // trailing reload so the list still converges after an update burst.
    let snapshotSeq = 0;
    let trailingReload: number | null = null;
    // A fetch of the full lead set is multi-second (tens of MB of JSON), so the
    // 900ms initial-retry and 500ms trailing-reload timers below fire WHILE the
    // previous load() is still legitimately in flight far more often than not.
    // Without this guard, each one starts a brand-new full fetch AND bumps
    // snapshotSeq, which makes the one already in flight look "stale" the
    // moment it finally resolves -- scheduling yet another reload 500ms later,
    // before that one can resolve either. Confirmed live: this became an
    // unbounded pile of concurrent full-dataset fetches that never actually
    // committed real data to state (every resolution found itself stale), so
    // the UI stayed on its loading/zero state indefinitely even though every
    // individual request eventually succeeded. Skipping a call while one is
    // already running lets the in-flight request resolve normally instead of
    // being raced by its own retry.
    let loadInFlight = false;
    // Retry-after-failure, not retry-on-a-fixed-timer: a genuinely failed/timed-out
    // load() (see the catch branch below) gets ONE retry a few seconds later, so a
    // transient failure (the client's own 30s timeout under heavy concurrent load,
    // a dropped connection) doesn't leave the screen on an empty/zero state forever
    // with no error banner either (an aborted fetch is deliberately silent -- see
    // the isAbortLikeError check below). Not scheduled unconditionally at mount:
    // that used to race a slow-but-healthy load() (see loadInFlight's comment).
    let retryTimer: number | null = null;
    const load = async (background = false) => {
      if (loadInFlight) return;
      loadInFlight = true;
      const seq = ++snapshotSeq;
      if (!background) setLoading(true);
      let failed = false;
      try {
        // Longer than the client's 30s default: this is the full dataset (tens of
        // MB), and the sidecar is single-worker (see leads/service.py's module
        // docstring) -- a burst of OTHER requests on initial mount (profile, graph,
        // dashboard) can push this one past 30s under real concurrent load even
        // though it resolves in single-digit seconds alone. Confirmed live: without
        // the extra room, this fetch got aborted by its own timeout mid-flight.
        const r = await leadsApi.listRaw(api, { signal: controller.signal, timeoutMs: 60000 });
        if (!r.ok) throw new Error(`Lead load failed (${r.status})`);
        const data = await r.json();
        if (!alive) return;
        if (seq !== snapshotSeq) {
          if (trailingReload !== null) window.clearTimeout(trailingReload);
          trailingReload = window.setTimeout(() => load(true), 500);
          return;
        }
        const items = Array.isArray(data) ? data : data.items;
        const jobLeads = (items as Lead[]).filter(l => (l.kind || "job") !== "freelance");
        setLeads(jobLeads);
        jobLeads.forEach(lead => knownLeadIds.current.add(lead.job_id));
        if (!background) initialLoadDone.current = true;
        setError(null);
      } catch (e) {
        if (!alive) return;
        if (controller.signal.aborted || isAbortLikeError(e)) return;
        setError(e instanceof Error ? e.message : "Lead load failed");
        failed = true;
      } finally {
        loadInFlight = false;
        if (alive) {
          setLoading(false);
          setLoaded(true);
        }
      }
      if (failed && alive && !initialLoadDone.current) {
        retryTimer = window.setTimeout(() => load(true), 4000);
      }
    };
    load(false);

    // Keep leads fresh when backend broadcasts LEAD_UPDATED over WS
    const onLeadUpdated = (e: Event) => {
      const updated = (e as CustomEvent<Lead>).detail;
      snapshotSeq++;
      setLoaded(true);
      setLoading(false);
      setLeads(prev => {
        const idx = prev.findIndex(l => l.job_id === updated.job_id);
        if (idx === -1) {
          // Some producers dispatch partial payloads ({job_id, status});
          // inserting one as a full lead renders an "Untitled role" ghost row.
          if (!updated.title) return prev;
          const isNew = !knownLeadIds.current.has(updated.job_id);
          knownLeadIds.current.add(updated.job_id);
          if (initialLoadDone.current && isNew) notifyStrongLead(updated);
          return [updated, ...prev];
        }
        const next = [...prev];
        next[idx] = { ...next[idx], ...updated };
        return next;
      });
    };
    window.addEventListener("lead-updated", onLeadUpdated);
    const onRefresh = () => load(true);
    window.addEventListener("leads-refresh", onRefresh);

    eventsApi.list(api, 200, { signal: controller.signal })
      .then(r => r.json())
      .then((evts: {job_id: string; action: string; ts: string}[]) => {
        evts.forEach(ev => {
          const isSystem = !ev.job_id || ev.job_id === "__system__";
          const src = isSystem ? "system" : ev.job_id.slice(0, 8);
          addLog?.(`[${src}] ${ev.action}`, isSystem ? "system" : "agent", src);
        });
      })
      .catch(() => {});
    return () => {
      alive = false;
      controller.abort();
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      if (trailingReload !== null) window.clearTimeout(trailingReload);
      window.removeEventListener("lead-updated", onLeadUpdated);
      window.removeEventListener("leads-refresh", onRefresh);
    };
  }, [api]);
  return { leads, setLeads, loading: loading && !loaded, error };
}
