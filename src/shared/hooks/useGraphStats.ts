import { useEffect, useState } from "react";
import { isAbortLikeError } from "../../api/client";
import type { ApiFetch, GraphStats } from "../../types";

export function useGraphStats(api: ApiFetch | null) {
  const [stats, setStats] = useState<GraphStats>({ candidate: 0, skill: 0, project: 0, experience: 0, joblead: 0, loaded: false, loading: false });
  useEffect(() => {
    if (!api) {
      setStats({ candidate: 0, skill: 0, project: 0, experience: 0, joblead: 0, loaded: false, loading: false });
      return;
    }
    const controller = new AbortController();
    let alive = true;
    const load = async (repair = false) => {
      setStats(prev => ({ ...prev, loading: true, request_error: "" }));
      try {
        const response = await api(`/api/v1/graph${repair ? "?repair=true" : ""}`, { signal: controller.signal, timeoutMs: repair ? 45000 : undefined });
        if (!response.ok) {
          const detail = await response.text().catch(() => "");
          throw new Error(`Graph request failed (${response.status})${detail ? `: ${detail.slice(0, 240)}` : ""}`);
        }
        const data = await response.json();
        if (!alive) return;
        setStats({ ...data, loaded: true, loading: false, request_error: "" });
      } catch (error) {
        if (!alive || controller.signal.aborted || isAbortLikeError(error)) return;
        const message = error instanceof Error ? error.message : "Graph request failed";
        setStats(prev => ({ ...prev, loaded: true, loading: false, request_error: message }));
      }
    };
    let debounceTimer: ReturnType<typeof setTimeout> | null = null;
    const refresh = () => {
      // Coalesce bursts — a scan broadcasts one lead-updated per scored lead, and
      // each refetch hits the expensive /api/v1/graph snapshot. Debounce so the
      // graph is fetched once after the burst settles instead of N times.
      if (debounceTimer !== null) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => { debounceTimer = null; load(false); }, 800);
    };
    load();
    window.addEventListener("lead-updated", refresh);
    window.addEventListener("leads-refresh", refresh);
    window.addEventListener("graph-refresh", refresh);
    window.addEventListener("profile-refresh", refresh);
    window.addEventListener("scan-done", refresh);
    window.addEventListener("reevaluate-done", refresh);
    window.addEventListener("cleanup-done", refresh);
    return () => {
      alive = false;
      if (debounceTimer !== null) clearTimeout(debounceTimer);
      controller.abort();
      window.removeEventListener("lead-updated", refresh);
      window.removeEventListener("leads-refresh", refresh);
      window.removeEventListener("graph-refresh", refresh);
      window.removeEventListener("profile-refresh", refresh);
      window.removeEventListener("scan-done", refresh);
      window.removeEventListener("reevaluate-done", refresh);
      window.removeEventListener("cleanup-done", refresh);
    };
  }, [api]);
  return stats;
}
