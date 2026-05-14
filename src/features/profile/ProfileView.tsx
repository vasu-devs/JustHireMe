import { useCallback, useEffect, useMemo, useState } from "react";
import Icon from "../../shared/components/Icon";
import type { ApiFetch, View } from "../../types";

const stackItems = (stack: any): string[] =>
  (Array.isArray(stack) ? stack : String(stack || "").split(","))
    .map((s: string) => s.trim())
    .filter(Boolean);

const entryTitle = (item: any): string => typeof item === "string" ? item : String(item?.title || "");

export function ProfileView({ api, setView }: { api: ApiFetch; setView: (v: View) => void }) {
  const [profile, setProfile] = useState<any>(null);
  const [profileErr, setProfileErr] = useState<string | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [editData, setEditData] = useState<any>(null);
  const [editingCandidate, setEditingCandidate] = useState(false);
  const [editingIdentity, setEditingIdentity] = useState(false);
  const [candForm, setCandForm] = useState({ n: "", s: "" });
  const [identityForm, setIdentityForm] = useState({ email: "", phone: "", linkedin_url: "", github_url: "", website_url: "", city: "" });
  const [activeProfileTab, setActiveProfileTab] = useState<"skills" | "experience" | "projects" | "education" | "certifications" | "achievements">("skills");
  const [expandedProfileList, setExpandedProfileList] = useState(false);

  const fetchProfile = useCallback(async () => {
    try {
      const r = await api(`/api/v1/profile`);
      if (!r.ok) throw new Error(`Profile load failed (${r.status})`);
      const data = await r.json();
      if (!data || !Array.isArray(data.skills) || !Array.isArray(data.projects) || !Array.isArray(data.exp)) {
        throw new Error("Profile response was not a valid identity graph");
      }
      setProfile(data);
      setProfileErr(null);
    } catch (err: any) {
      console.error("Profile load failed:", err);
      setProfileErr(err?.message || "Profile load failed");
    }
  }, [api]);

  useEffect(() => { fetchProfile(); }, [fetchProfile]);
  useEffect(() => {
    window.addEventListener("profile-refresh", fetchProfile);
    return () => window.removeEventListener("profile-refresh", fetchProfile);
  }, [fetchProfile]);
  useEffect(() => { setExpandedProfileList(false); }, [activeProfileTab]);
  useEffect(() => {
    const exportProfile = () => {
      if (!profile) return;
      const blob = new Blob([JSON.stringify(profile, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${profile.n || "identity-graph"}.json`.replace(/[^\w.-]+/g, "-");
      a.click();
      URL.revokeObjectURL(url);
    };
    window.addEventListener("profile-export", exportProfile);
    return () => window.removeEventListener("profile-export", exportProfile);
  }, [profile]);

  const deleteItem = async (type: string, id: string) => {
    if (!window.confirm("Delete this item?")) return;
    try {
      const res = await api(`/api/v1/profile/${type}/${id}`, { method: "DELETE" });
      if (!res.ok) console.error("Delete failed:", res.status);
    } catch (err) {
      console.error("Delete error:", err);
    }
    await fetchProfile();
    window.dispatchEvent(new CustomEvent("profile-refresh"));
    window.dispatchEvent(new CustomEvent("graph-refresh"));
  };

  const saveEdit = async (type: string, id: string) => {
    await api(`/api/v1/profile/${type}/${id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(editData),
    });
    setEditId(null);
    await fetchProfile();
    window.dispatchEvent(new CustomEvent("profile-refresh"));
    window.dispatchEvent(new CustomEvent("graph-refresh"));
  };

  const saveCandidate = async () => {
    await api(`/api/v1/profile/candidate`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(candForm),
    });
    setEditingCandidate(false);
    await fetchProfile();
    window.dispatchEvent(new CustomEvent("profile-refresh"));
    window.dispatchEvent(new CustomEvent("graph-refresh"));
  };

  const saveIdentity = async () => {
    await api(`/api/v1/profile/identity`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(identityForm),
    });
    setEditingIdentity(false);
    await fetchProfile();
    window.dispatchEvent(new CustomEvent("profile-refresh"));
  };

  const skills = profile?.skills || [];
  const exp = profile?.exp || [];
  const projects = profile?.projects || [];
  const education = profile?.education || [];
  const certifications = profile?.certifications || [];
  const achievements = profile?.achievements || [];
  const identity = profile?.identity || {};
  const identityItems = [
    ["email", identity.email, "mail"],
    ["phone", identity.phone, "phone"],
    ["linkedin_url", identity.linkedin_url, "external-link"],
    ["github_url", identity.github_url, "external-link"],
    ["website_url", identity.website_url, "globe"],
    ["city", identity.city, "globe"],
  ].filter(([, value]) => String(value || "").trim());
  const evidenceCount = skills.length + exp.length + projects.length + education.length + certifications.length + achievements.length + identityItems.length;
  const topStacks = Array.from(new Set<string>(projects.flatMap((p: any) => stackItems(p.stack)))).slice(0, 10);
  const visibleStacks = topStacks.slice(0, 6);
  const summary = String(profile?.s || "").replace(/\s+/g, " ").trim();
  const summaryPreview = summary
    ? summary.length > 265 ? `${summary.slice(0, 262).trim()}...` : summary
    : "Add your name and target role summary above. This becomes the anchor for scoring and document generation.";
  const skillRanks = useMemo(() => {
    const counts = new Map<string, { label: string; count: number; cat: string; id: string }>();
    const bump = (label: string, weight = 1, cat = "general", id = "") => {
      const clean = String(label || "").trim();
      if (!clean) return;
      const key = clean.toLowerCase();
      const prev = counts.get(key);
      counts.set(key, { label: prev?.label || clean, count: (prev?.count || 0) + weight, cat: prev?.cat || cat, id: prev?.id || id });
    };
    skills.forEach((s: any) => bump(s.n, 1, s.cat, s.id));
    projects.forEach((p: any) => stackItems(p.stack).forEach(name => bump(name, 3)));
    exp.forEach((e: any) => (Array.isArray(e.s) ? e.s : stackItems(e.s)).forEach((name: string) => bump(name, 2)));
    return Array.from(counts.values()).sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  }, [skills, projects, exp]);
  const previewSkills = expandedProfileList ? skillRanks : skillRanks.slice(0, 10);
  const previewExp = expandedProfileList ? exp : exp.slice(0, 6);
  const previewProjects = expandedProfileList ? projects : projects.slice(0, 8);
  const previewEducation = expandedProfileList ? education : education.slice(0, 8);
  const previewCertifications = expandedProfileList ? certifications : certifications.slice(0, 8);
  const previewAchievements = expandedProfileList ? achievements : achievements.slice(0, 8);
  const listTotal = activeProfileTab === "skills" ? skillRanks.length : activeProfileTab === "experience" ? exp.length : activeProfileTab === "projects" ? projects.length : activeProfileTab === "education" ? education.length : activeProfileTab === "certifications" ? certifications.length : achievements.length;
  const listShown = activeProfileTab === "skills" ? previewSkills.length : activeProfileTab === "experience" ? previewExp.length : activeProfileTab === "projects" ? previewProjects.length : activeProfileTab === "education" ? previewEducation.length : activeProfileTab === "certifications" ? previewCertifications.length : previewAchievements.length;
  const tabNodes = [
    { id: "skills" as const, label: "Skills", count: skills.length, tone: "blue", icon: "spark" },
    { id: "experience" as const, label: "Experience", count: exp.length, tone: "orange", icon: "brief" },
    { id: "projects" as const, label: "Projects", count: projects.length, tone: "pink", icon: "layers" },
    { id: "education" as const, label: "Education", count: education.length, tone: "green", icon: "file" },
    { id: "certifications" as const, label: "Certs", count: certifications.length, tone: "purple", icon: "check" },
    { id: "achievements" as const, label: "Wins", count: achievements.length, tone: "yellow", icon: "trending" },
  ];

  return (
    <div className="scroll profile-page">
      <div className="profile-shell profile-shell-compact">
        {profileErr && (
          <div style={{ marginBottom: 16, padding: "12px 14px", borderRadius: 8, background: "var(--bad-soft)", border: "1px solid var(--bad)", color: "var(--bad)", fontSize: 13 }}>
            Could not refresh the Identity Graph. Your existing profile was not overwritten.
          </div>
        )}
        <div className="profile-workspace">
          <aside className="profile-left-rail">
            <div className="card profile-identity-card">
              <div className="profile-identity-head">
                <div className="profile-avatar">{(profile?.n || "C").slice(0, 1).toUpperCase()}</div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <span className="eyebrow">Identity Context</span>
                  <h1 className="profile-name">{profile?.n || "Candidate Profile"}</h1>
                </div>
                {!editingCandidate && (
                  <button className="btn profile-edit-btn" onClick={() => { setEditingCandidate(true); setCandForm({ n: profile?.n || "", s: profile?.s || "" }); }}>
                    <Icon name="edit" size={13} /> Edit
                  </button>
                )}
              </div>

          {editingCandidate ? (
            <div className="col gap-3" style={{ marginTop: 18 }}>
              <input className="field-input" placeholder="Your full name" value={candForm.n} onChange={e => setCandForm({ ...candForm, n: e.target.value })} style={{ fontSize: 18, fontWeight: 600 }} />
              <textarea className="field-input" placeholder="Professional summary / target role - agents use this for scoring" rows={4} value={candForm.s} onChange={e => setCandForm({ ...candForm, s: e.target.value })} style={{ fontSize: 14, lineHeight: 1.6 }} />
              <div className="row gap-2">
                <button className="btn btn-primary" style={{ padding: "10px 24px" }} onClick={saveCandidate}>Save Identity</button>
                <button className="btn btn-ghost" onClick={() => setEditingCandidate(false)}>Cancel</button>
              </div>
            </div>
          ) : (
            <>
              <p className="profile-summary">{summaryPreview}</p>
              {identityItems.length > 0 && (
                <div className="profile-contact-list">
                  {identityItems.slice(0, 6).map(([key, value, icon]) => {
                    const text = String(value || "");
                    const isUrl = /^https?:\/\//i.test(text);
                    return (
                      <div key={String(key)} className="profile-contact-item">
                        <Icon name={String(icon)} size={12} />
                        {isUrl ? <a href={text} target="_blank" rel="noreferrer">{text.replace(/^https?:\/\//i, "")}</a> : <span>{text}</span>}
                      </div>
                    );
                  })}
                </div>
              )}
              <div className="profile-pill-row">
                <span className="pill mono">{skills.length} SKILLS</span>
                <span className="pill mono">{exp.length} ROLES</span>
                <span className="pill mono">{projects.length} PROJECTS</span>
              </div>
              {editingIdentity ? (
                <div className="col gap-2" style={{ marginTop: 14 }}>
                  <input className="field-input" placeholder="Email" value={identityForm.email} onChange={e => setIdentityForm({ ...identityForm, email: e.target.value })} />
                  <input className="field-input" placeholder="Phone" value={identityForm.phone} onChange={e => setIdentityForm({ ...identityForm, phone: e.target.value })} />
                  <input className="field-input" placeholder="LinkedIn URL" value={identityForm.linkedin_url} onChange={e => setIdentityForm({ ...identityForm, linkedin_url: e.target.value })} />
                  <input className="field-input" placeholder="GitHub URL" value={identityForm.github_url} onChange={e => setIdentityForm({ ...identityForm, github_url: e.target.value })} />
                  <input className="field-input" placeholder="Website URL" value={identityForm.website_url} onChange={e => setIdentityForm({ ...identityForm, website_url: e.target.value })} />
                  <input className="field-input" placeholder="City / location" value={identityForm.city} onChange={e => setIdentityForm({ ...identityForm, city: e.target.value })} />
                  <div className="row gap-2">
                    <button className="btn btn-primary" onClick={saveIdentity}>Save Contact</button>
                    <button className="btn btn-ghost" onClick={() => setEditingIdentity(false)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <button className="profile-add-context" style={{ marginTop: 12 }} onClick={() => { setEditingIdentity(true); setIdentityForm({ email: identity.email || "", phone: identity.phone || "", linkedin_url: identity.linkedin_url || "", github_url: identity.github_url || "", website_url: identity.website_url || "", city: identity.city || "" }); }}>
                  <Icon name="edit" size={14} /> Contact & Links
                </button>
              )}
              <div className="profile-rail-stats">
                <div>
                  <span>Evidence</span>
                  <strong>{evidenceCount}</strong>
                </div>
                <div>
                  <span>Stack</span>
                  <strong>{topStacks.length}</strong>
                </div>
              </div>
              {visibleStacks.length > 0 && (
                <div className="profile-stack-mini profile-rail-stack">
                  {visibleStacks.map(s => <span key={s} className="pill">{s}</span>)}
                </div>
              )}
              <button className="profile-primary-action" onClick={() => setView("ingestion")}>
                <Icon name="plus" size={14} /> Add Context
              </button>
            </>
          )}
            </div>
          </aside>

          <main className="profile-main-panel">
            <section className="card profile-overview-card">
              <div className="profile-overview-head">
                <div>
                  <span className="eyebrow">Profile Snapshot</span>
                  <h3>Structured Candidate Data</h3>
                </div>
                <button className="btn btn-ghost" onClick={() => setView("ingestion")}>
                  <Icon name="plus" size={14} /> Add Context
                </button>
              </div>
              <div className="profile-overview-grid">
                {tabNodes.map(node => (
                  <button key={node.id} className={`profile-overview-stat profile-overview-stat-${node.tone} ${activeProfileTab === node.id ? "active" : ""}`} onClick={() => { setActiveProfileTab(node.id); setEditId(null); }}>
                    <Icon name={node.icon} size={16} />
                    <span>{node.label}</span>
                    <strong>{node.count}</strong>
                  </button>
                ))}
                <div className="profile-overview-stack">
                  <div>
                    <span className="eyebrow">Stack Tags</span>
                    <strong>{topStacks.length}</strong>
                  </div>
                  <div className="profile-stack-mini">
                    {visibleStacks.length ? visibleStacks.map(s => <span key={s} className="pill">{s}</span>) : <span className="pill">No project stack yet</span>}
                  </div>
                </div>
              </div>
            </section>

            <section className="card profile-tab-card">
              <div className="profile-tabs">
                {tabNodes.map(node => (
                  <button
                    key={node.id}
                    className={activeProfileTab === node.id ? "active" : ""}
                    onClick={() => { setActiveProfileTab(node.id); setEditId(null); }}
                  >
                    <Icon name={node.icon} size={14} />
                    <span>{node.label}</span>
                    <span className="mono">{node.count}</span>
                  </button>
                ))}
              </div>

              <div className="profile-tab-scroll">
                {activeProfileTab === "skills" && (
                  <div className="profile-skill-grid">
                    {skillRanks.length === 0 && <div className="profile-empty">No skills yet.</div>}
                    {previewSkills.map((s, idx) => {
                      const tone = ["blue", "yellow", "purple", "green", "orange", "teal"][idx % 6];
                      return (
                        <div key={`${s.id || s.label}-${idx}`} className={`profile-list-tile profile-list-tile-${tone}`}>
                          <div className="profile-list-leading">
                            <Icon name="check" size={14} />
                            <span>{s.label}</span>
                          </div>
                          <div className="profile-list-trailing">
                            <span className="profile-count-badge">{s.count}</span>
                            {s.id ? (
                              <button className="profile-row-action" onClick={() => deleteItem("skill", s.id)} title="Delete skill">
                                <Icon name="arrow-right" size={14} />
                              </button>
                            ) : (
                              <Icon name="arrow-right" size={14} />
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {activeProfileTab === "experience" && (
                  <div className="profile-timeline">
                    {exp.length === 0 && <div className="profile-empty">No experience recorded.</div>}
                    {previewExp.map((e: any, idx: number) => (
                      <div key={e.id} className="profile-timeline-item">
                        {editId === e.id ? (
                          <div className="col gap-3">
                            <div className="grid-2 gap-3">
                              <input className="field-input" value={editData.role} placeholder="Role" onChange={v => setEditData({ ...editData, role: v.target.value })} />
                              <input className="field-input" value={editData.co} placeholder="Company" onChange={v => setEditData({ ...editData, co: v.target.value })} />
                            </div>
                            <input className="field-input" value={editData.period} placeholder="Period" onChange={v => setEditData({ ...editData, period: v.target.value })} />
                            <textarea className="field-input" value={editData.d} rows={4} placeholder="Description" onChange={v => setEditData({ ...editData, d: v.target.value })} />
                            <div className="row gap-2">
                              <button className="btn btn-primary" onClick={() => saveEdit("experience", e.id)}>Save</button>
                              <button className="btn btn-ghost" onClick={() => setEditId(null)}>Cancel</button>
                            </div>
                          </div>
                        ) : (
                          <div className="col gap-1">
                            <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                              <div className="col">
                                <div className="profile-card-title">{e.role}</div>
                                <div className="row gap-2" style={{ fontSize: 13, color: "var(--ink-2)", marginTop: 3 }}>
                                  <span>{e.co}</span><span style={{ color: "var(--ink-4)" }}>-</span><span className="mono" style={{ fontSize: 11 }}>{e.period}</span>
                                </div>
                              </div>
                              <div className="row gap-2">
                                <span className="profile-count-badge">{idx + 1}</span>
                                <button className="btn-icon profile-mini-action" onClick={() => { setEditId(e.id); setEditData({ ...e }); }}><Icon name="edit" size={14} /></button>
                                <button className="btn-icon profile-mini-action profile-danger" onClick={() => deleteItem("experience", e.id)}><Icon name="trash" size={14} /></button>
                              </div>
                            </div>
                            {e.d && <div style={{ fontSize: 13.5, color: "var(--ink-2)", lineHeight: 1.6, marginTop: 10, whiteSpace: "pre-wrap" }}>{e.d}</div>}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {activeProfileTab === "projects" && (
                  <div className="profile-project-grid">
                    {projects.length === 0 && <div className="profile-empty">No projects mapped.</div>}
                    {previewProjects.map((p: any, idx: number) => (
                      <div key={p.id} className="profile-project-card">
                        {editId === p.id ? (
                          <div className="col gap-3">
                            <input className="field-input" value={editData.title} placeholder="Title" onChange={v => setEditData({ ...editData, title: v.target.value })} />
                            <input className="field-input" value={editData.stack} placeholder="Stack (comma-separated)" onChange={v => setEditData({ ...editData, stack: v.target.value })} />
                            <input className="field-input" value={editData.repo} placeholder="Repo URL" onChange={v => setEditData({ ...editData, repo: v.target.value })} />
                            <textarea className="field-input" value={editData.impact} rows={4} placeholder="Impact" onChange={v => setEditData({ ...editData, impact: v.target.value })} />
                            <div className="row gap-2">
                              <button className="btn btn-primary" onClick={() => saveEdit("project", p.id)}>Save</button>
                              <button className="btn btn-ghost" onClick={() => setEditId(null)}>Cancel</button>
                            </div>
                          </div>
                        ) : (
                          <div className="col gap-1">
                            <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                              <div className="profile-card-title">{p.title}</div>
                              <div className="row gap-2">
                                <span className="profile-count-badge">{idx + 1}</span>
                                <button className="btn-icon profile-mini-action" onClick={() => { setEditId(p.id); setEditData({ ...p, stack: stackItems(p.stack).join(", ") }); }}><Icon name="edit" size={14} /></button>
                                <button className="btn-icon profile-mini-action profile-danger" onClick={() => deleteItem("project", p.id)}><Icon name="trash" size={14} /></button>
                              </div>
                            </div>
                            <div className="row gap-1" style={{ flexWrap: "wrap", margin: "8px 0 10px" }}>
                              {stackItems(p.stack).map((s: string, i: number) => (
                                <span key={i} className="pill" style={{ fontSize: 11, padding: "4px 10px", background: "var(--pink-soft)", color: "var(--pink-ink)", border: "1px solid var(--pink)" }}>{s.trim()}</span>
                              ))}
                            </div>
                            {p.impact && <div style={{ fontSize: 13.5, color: "var(--ink-2)", lineHeight: 1.6 }}>{p.impact}</div>}
                            {p.repo && <div className="row gap-2" style={{ marginTop: 10 }}><Icon name="link" size={12} color="var(--ink-3)" /><a href={p.repo} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: "var(--ink-3)" }}>{p.repo}</a></div>}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                {activeProfileTab === "education" && (
                  <div className="profile-skill-grid">
                    {education.length === 0 && <div className="profile-empty">No education recorded.</div>}
                    {previewEducation.map((item: any, idx: number) => (
                      <div key={`${entryTitle(item)}-${idx}`} className="profile-list-tile profile-list-tile-green">
                        <div className="profile-list-leading">
                          <Icon name="file" size={14} />
                          <span>{entryTitle(item)}</span>
                        </div>
                        <span className="profile-count-badge">{idx + 1}</span>
                      </div>
                    ))}
                  </div>
                )}
                {activeProfileTab === "certifications" && (
                  <div className="profile-skill-grid">
                    {certifications.length === 0 && <div className="profile-empty">No certifications recorded.</div>}
                    {previewCertifications.map((item: any, idx: number) => (
                      <div key={`${entryTitle(item)}-${idx}`} className="profile-list-tile profile-list-tile-purple">
                        <div className="profile-list-leading">
                          <Icon name="check" size={14} />
                          <span>{entryTitle(item)}</span>
                        </div>
                        <span className="profile-count-badge">{idx + 1}</span>
                      </div>
                    ))}
                  </div>
                )}
                {activeProfileTab === "achievements" && (
                  <div className="profile-skill-grid">
                    {achievements.length === 0 && <div className="profile-empty">No achievements recorded.</div>}
                    {previewAchievements.map((item: any, idx: number) => (
                      <div key={`${entryTitle(item)}-${idx}`} className="profile-list-tile profile-list-tile-yellow">
                        <div className="profile-list-leading">
                          <Icon name="trending" size={14} />
                          <span>{entryTitle(item)}</span>
                        </div>
                        <span className="profile-count-badge">{idx + 1}</span>
                      </div>
                    ))}
                  </div>
                )}
                {listTotal > listShown && (
                  <button className="profile-view-all" onClick={() => setExpandedProfileList(true)}>
                    View all {activeProfileTab} <Icon name="arrow-right" size={13} />
                  </button>
                )}
              </div>
            </section>
          </main>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════
   INGESTION VIEW
══════════════════════════════════════ */
