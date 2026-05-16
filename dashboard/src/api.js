const API_BASE = "/api/v1";

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`${res.status}: ${err}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  getLeads: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    if (params.page) qs.set("page", params.page);
    if (params.limit) qs.set("limit", params.limit);
    return request(`/leads?${qs}`);
  },
  getLead: (jobId) => request(`/leads/${jobId}`),
  createManualLead: (body) =>
    request("/leads/manual", { method: "POST", body: JSON.stringify(body) }),
  matchProgram: (jobId) =>
    request(`/leads/${jobId}/match-program`, { method: "POST" }),
  approveProgram: (jobId) =>
    request(`/leads/${jobId}/approve-program`, { method: "POST" }),
  generate: (jobId) =>
    request(`/leads/${jobId}/generate`, { method: "POST" }),
  getPdf: (jobId, kind) => `/api/v1/leads/${jobId}/pdf?kind=${kind}`,
};
