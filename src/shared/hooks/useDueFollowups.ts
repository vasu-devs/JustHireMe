import { useEffect, useState } from "react";
import type { ApiFetch, Lead } from "../../types";

export function useDueFollowups(api: ApiFetch | null) {
  const [leads, setLeads] = useState<Lead[]>([]);
  useEffect(() => {
    if (!api) return;
    const load = () => api(`/api/v1/followups/due?limit=25`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        // Error bodies are {detail: ...}; storing one as the list would make
        // every consumer's .length/.map blow up.
        if (Array.isArray(data)) setLeads(data);
      })
      .catch(() => {});
    load();
    const interval = setInterval(load, 60000);
    return () => clearInterval(interval);
  }, [api]);
  return leads;
}
