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

  // Profile
  getProfile: () => request("/profile"),
  updateCandidate: (body) => request("/profile/candidate", { method: "PUT", body: JSON.stringify(body) }),
  updateIdentity: (body) => request("/profile/identity", { method: "PUT", body: JSON.stringify(body) }),
  addSkill: (body) => request("/profile/skill", { method: "POST", body: JSON.stringify(body) }),
  updateSkill: (sid, body) => request(`/profile/skill/${sid}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteSkill: (sid) => request(`/profile/skill/${sid}`, { method: "DELETE" }),
  addExperience: (body) => request("/profile/experience", { method: "POST", body: JSON.stringify(body) }),
  updateExperience: (eid, body) => request(`/profile/experience/${eid}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteExperience: (eid) => request(`/profile/experience/${eid}`, { method: "DELETE" }),
  addProject: (body) => request("/profile/project", { method: "POST", body: JSON.stringify(body) }),
  updateProject: (pid, body) => request(`/profile/project/${pid}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteProject: (pid) => request(`/profile/project/${pid}`, { method: "DELETE" }),
  addEducation: (body) => request("/profile/education", { method: "POST", body: JSON.stringify(body) }),
  deleteEducation: (entry) => request(`/profile/education/${encodeURIComponent(entry)}`, { method: "DELETE" }),
  addCertification: (body) => request("/profile/certification", { method: "POST", body: JSON.stringify(body) }),
  deleteCertification: (entry) => request(`/profile/certification/${encodeURIComponent(entry)}`, { method: "DELETE" }),
  addAchievement: (body) => request("/profile/achievement", { method: "POST", body: JSON.stringify(body) }),
  deleteAchievement: (entry) => request(`/profile/achievement/${encodeURIComponent(entry)}`, { method: "DELETE" }),

  // Settings
  getSettings: () => request("/settings"),
  saveSettings: (body) => request("/settings", { method: "POST", body: JSON.stringify(body) }),
  validateSettings: () => request("/settings/validate"),
  getTemplate: () => request("/template"),
  saveTemplate: (body) => request("/template", { method: "POST", body: JSON.stringify(body) }),
  getProviderModels: (provider) => request(`/settings/models/${provider}`),

  // Notifications
  getNotifications: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    if (params.limit) qs.set("limit", params.limit);
    if (params.offset) qs.set("offset", params.offset);
    return request(`/notifications?${qs}`);
  },
  getNotificationStats: () => request("/notifications/stats"),
  retryNotification: (id) => request(`/notifications/${id}/retry`, { method: "POST" }),
};
