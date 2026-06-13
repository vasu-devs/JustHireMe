import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { isAbortLikeError } from "../../api/client";
import type { ApiFetch, Lead, LogLine } from "../../types";

export function useLeads(api: ApiFetch | null, addLog?: (msg: string, kind: LogLine["kind"], src?: string) => void) {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const initialLoadDone = useRef(false);
  const knownLeadIds = useRef<Set<string>>(new Set());

  const notifyStrongLead = (lead: Lead) => {
    const topScore = Math.max(lead.score || 0, lead.signal_score ?? 0);
    if (topScore < 80) return;
    invoke("notify_high_score_lead", {
      title: `Strong match: ${lead.title}`,
      body: `${lead.company} · Score ${topScore}`,
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
    const load = async (background = false) => {
      const seq = ++snapshotSeq;
      if (!background) setLoading(true);
      try {
        const r = await api(`/api/v1/leads`, { signal: controller.signal });
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
      } finally {
        if (alive) {
          setLoading(false);
          setLoaded(true);
        }
      }
    };
    load(false);
    const retryTimer = window.setTimeout(() => {
      if (!initialLoadDone.current) load(true);
    }, 900);

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

    api(`/api/v1/events?limit=200`, { signal: controller.signal })
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
      window.clearTimeout(retryTimer);
      if (trailingReload !== null) window.clearTimeout(trailingReload);
      window.removeEventListener("lead-updated", onLeadUpdated);
      window.removeEventListener("leads-refresh", onRefresh);
    };
  }, [api]);
  return { leads, setLeads, loading: loading && !loaded, error };
}
