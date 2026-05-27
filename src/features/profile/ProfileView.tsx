import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import Icon from "../../shared/components/Icon";
import type { ApiFetch, GraphStats, View } from "../../types";
import { applyProfileDeleteMarkers, entryTitle, mergeProfileWithGraphFallback, normalizeProfileResponse, profileDeleteKey, profileDeletePath, profileHasDeleteMarker, removeProfileItem, type ProfileDeleteMarker } from "./profileUtils";

const stackItems = (stack: any): string[] =>
  (Array.isArray(stack) ? stack : String(stack || "").split(","))
    .map((s: string) => s.trim())
    .filter(Boolean);

const EMPTY_PROFILE_LIST: unknown[] = [];
const profileList = (value: unknown): unknown[] => Array.isArray(value) ? value : EMPTY_PROFILE_LIST;

export function ProfileView({ api, setView, stats }: { api: ApiFetch; setView: (v: View) => void; stats?: GraphStats }) {
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
  const [deletingItem, setDeletingItem] = useState<{ key: string; label: string } | null>(null);
  const deleteMarkersRef = useRef<ProfileDeleteMarker[]>([]);
  const deleteInFlightRef = useRef(false);

  const setDeleteMarkerList = useCallback((markers: ProfileDeleteMarker[]) => {
    deleteMarkersRef.current = markers;
  }, []);

  const addDeleteMarker = useCallback((marker: ProfileDeleteMarker) => {
    const exists = deleteMarkersRef.current.some(item => item.type === marker.type && item.id === marker.id);
    if (exists) return deleteMarkersRef.current;
    const next = [...deleteMarkersRef.current, marker];
    setDeleteMarkerList(next);
    return next;
  }, [setDeleteMarkerList]);

  const removeDeleteMarker = useCallback((marker: ProfileDeleteMarker) => {
    const next = deleteMarkersRef.current.filter(item => item.type !== marker.type || item.id !== marker.id);
    setDeleteMarkerList(next);
  }, [setDeleteMarkerList]);

  const applyLocalDeletes = useCallback((nextProfile: unknown, pruneResolved = false) => {
    const markers = deleteMarkersRef.current;
    if (!markers.length) return normalizeProfileResponse(nextProfile);
    const resolved = pruneResolved ? markers.filter(marker => profileHasDeleteMarker(nextProfile, marker)) : markers;
    if (resolved.length !== markers.length) {
      setDeleteMarkerList(resolved);
    }
    return applyProfileDeleteMarkers(nextProfile, resolved);
  }, [setDeleteMarkerList]);

  const fetchProfile = useCallback(async (options?: { errorPrefix?: string; suppressError?: boolean }) => {
    try {
      const r = await api(`/api/v1/profile`);
      if (!r.ok) throw new Error(`Profile load failed (${r.status})`);
      const data = await r.json();
      setProfile(applyLocalDeletes(mergeProfileWithGraphFallback(data, stats), true));
      setProfileErr(null);
      return true;
    } catch (err: any) {
      console.error("Profile load failed:", err);
      const message = err?.message || "Profile load failed";
      if (!options?.suppressError) {
        setProfileErr(options?.errorPrefix ? `${options.errorPrefix}: ${message}` : message);
      }
      return false;
    }
  }, [api, applyLocalDeletes, stats]);

  useEffect(() => { fetchProfile(); }, [fetchProfile]);
  useEffect(() => {
    setProfile((prev: any) => prev ? applyLocalDeletes(mergeProfileWithGraphFallback(prev, stats, { fillEmptyBuckets: false })) : prev);
  }, [applyLocalDeletes, stats]);
  useEffect(() => {
    const onProfileRefresh = () => { void fetchProfile(); };
    window.addEventListener("profile-refresh", onProfileRefresh);
    return () => window.removeEventListener("profile-refresh", onProfileRefresh);
  }, [fetchProfile]);
  useEffect(() => { setExpandedProfileList(false); }, [activeProfileTab]);
  useEffect(() => {
    const exportProfile = async () => {
      if (!profile) return;
      const blob = new Blob([JSON.stringify(profile, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      // WebKitGTK (Tauri's Linux webview) silently ignores programmatic
      // `<a download>` clicks, so the anchor approach never produces a file
      // there — the button looked dead on Linux (issue #92). Inside the Tauri
      // shell, hand the blob to the system opener instead, the same path the
      // resume "Download PDF" button already uses on every desktop platform.
      // Fall back to a real download anchor in a plain browser (dev).
      const inTauri = typeof window !== "undefined"
        && ("__TAURI_INTERNALS__" in window || "__TAURI__" in window);
      if (inTauri) {
        try {
          await openUrl(url);
        } finally {
          setTimeout(() => URL.revokeObjectURL(url), 10_000);
        }
        return;
      }
      const a = document.createElement("a");
      a.href = url;
      a.download = `${profile.n || "identity-graph"}.json`.replace(/[^\w.-]+/g, "-");
      a.click();
      URL.revokeObjectURL(url);
    };
    window.addEventListener("profile-export", exportProfile);
    return () => window.removeEventListener("profile-export", exportProfile);
  }, [profile]);

  const deleteItem = useCallback(async (type: string, id: string) => {
    const key = `${type}:${id}`;
    if (!id || deleteInFlightRef.current) return;
    const marker = { type, id };
    deleteInFlightRef.current = true;
    setDeletingItem({ key, label: id });
    setProfileErr(null);
    try {
      const res = await api(profileDeletePath(type, id), { method: "DELETE", timeoutMs: 120000 });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `Delete failed (${res.status})`);
      const markers = addDeleteMarker(marker);
      setProfile((prev: any) => prev ? applyProfileDeleteMarkers(removeProfileItem(prev, type, id), markers) : prev);
      const refreshed = await fetchProfile({ suppressError: true });
      if (!refreshed) {
        setProfileErr("Deleted, but profile refresh failed. The deleted item is hidden locally and will stay tombstoned.");
      } else {
        setProfileErr(null);
      }
      window.dispatchEvent(new CustomEvent("graph-refresh"));
    } catch (err: any) {
      console.error("Delete error:", err);
      removeDeleteMarker(marker);
      setProfileErr(err?.message || "Delete failed");
    } finally {
      deleteInFlightRef.current = false;
      setDeletingItem(null);
    }
  }, [api, addDeleteMarker, fetchProfile, removeDeleteMarker]);

  const saveEdit = async (type: string, id: string) => {
    if (!id) {
      setProfileErr("This profile row needs a graph id before it can be edited. Delete it or re-import profile context.");
      return;
    }
    try {
      const res = await api(`/api/v1/profile/${type}/${id}`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(editData),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `Save failed (${res.status})`);
      setEditId(null);
      setEditData(null);
      setProfileErr(null);
      await fetchProfile();
      window.dispatchEvent(new CustomEvent("profile-refresh"));
      window.dispatchEvent(new CustomEvent("graph-refresh"));
    } catch (err: any) {
      setProfileErr(err?.message || "Profile save failed");
    }
  };

  const saveCandidate = async () => {
    try {
      const res = await api(`/api/v1/profile/candidate`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(candForm),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `Save failed (${res.status})`);
      setProfile((prev: any) => normalizeProfileResponse({ ...(prev || {}), n: body.n ?? candForm.n, s: body.s ?? candForm.s }));
      setEditingCandidate(false);
      setProfileErr(null);
      await fetchProfile({ errorPrefix: "Identity Context saved, but refresh failed" });
      window.dispatchEvent(new CustomEvent("profile-refresh"));
      window.dispatchEvent(new CustomEvent("graph-refresh"));
    } catch (err: any) {
      setProfileErr(err?.message || "Identity Context save failed");
    }
  };

  const saveIdentity = async () => {
    try {
      const res = await api(`/api/v1/profile/identity`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(identityForm),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `Save failed (${res.status})`);
      setProfile((prev: any) => normalizeProfileResponse({ ...(prev || {}), identity: { ...((prev || {}).identity || {}), ...body } }));
      setEditingIdentity(false);
      setProfileErr(null);
      await fetchProfile({ errorPrefix: "Contact details saved, but refresh failed" });
      window.dispatchEvent(new CustomEvent("profile-refresh"));
      window.dispatchEvent(new CustomEvent("graph-refresh"));
    } catch (err: any) {
      setProfileErr(err?.message || "Contact save failed");
    }
  };

  const skills = useMemo(() => profileList(profile?.skills), [profile?.skills]);
  const exp = useMemo(() => profileList(profile?.exp), [profile?.exp]);
  const projects = useMemo(() => profileList(profile?.projects), [profile?.projects]);
  const education = useMemo(() => profileList(profile?.education), [profile?.education]);
  const certifications = useMemo(() => profileList(profile?.certifications), [profile?.certifications]);
  const achievements = useMemo(() => profileList(profile?.achievements), [profile?.achievements]);
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
  const skillItems = useMemo(() => {
    const seen = new Set<string>();
    return skills
      .map((s: any) => {
        const label = String(s?.n || s?.name || s?.title || "").trim();
        const id = String(s?.id || "").trim();
        const key = (id || label).toLowerCase();
        if (!label || seen.has(key)) return null;
        seen.add(key);
        return { label, cat: String(s?.cat || s?.category || "general"), id };
      })
      .filter(Boolean) as { label: string; cat: string; id: string }[];
  }, [skills]);
  const previewSkills = expandedProfileList ? skillItems : skillItems.slice(0, 10);
  const previewExp = expandedProfileList ? exp : exp.slice(0, 6);
  const previewProjects = expandedProfileList ? projects : projects.slice(0, 8);
  const previewEducation = expandedProfileList ? education : education.slice(0, 8);
  const previewCertifications = expandedProfileList ? certifications : certifications.slice(0, 8);
  const previewAchievements = expandedProfileList ? achievements : achievements.slice(0, 8);
  const listTotal = activeProfileTab === "skills" ? skillItems.length : activeProfileTab === "experience" ? exp.length : activeProfileTab === "projects" ? projects.length : activeProfileTab === "education" ? education.length : activeProfileTab === "certifications" ? certifications.length : achievements.length;
  const listShown = activeProfileTab === "skills" ? previewSkills.length : activeProfileTab === "experience" ? previewExp.length : activeProfileTab === "projects" ? previewProjects.length : activeProfileTab === "education" ? previewEducation.length : activeProfileTab === "certifications" ? previewCertifications.length : previewAchievements.length;
  const deletingKey = deletingItem?.key || "";
  const isDeleting = Boolean(deletingItem);
  const isDeletingKey = (key: string) => deletingKey === key;
  const deleteButtonTitle = (key: string, label: string) =>
    isDeletingKey(key) ? `Deleting ${label}` : isDeleting ? "Wait for the current delete to finish" : `Delete ${label}`;
  const deleteButtonContent = (key: string) =>
    isDeletingKey(key) ? <span className="spinner-sm profile-delete-spinner" aria-hidden="true" /> : <Icon name="trash" size={14} />;
  const deleteStatus = (key: string) => isDeletingKey(key) ? (
    <span className="profile-delete-status"><span className="spinner-sm profile-delete-spinner" aria-hidden="true" /> Deleting...</span>
  ) : null;
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
            {profileErr}
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
                    {skillItems.length === 0 && <div className="profile-empty">No skills yet.</div>}
                    {previewSkills.map((s, idx) => {
                      const tone = ["blue", "yellow", "purple", "green", "orange", "teal"][idx % 6];
                      return (
                        <div key={`${s.id || s.label}-${idx}`} className={`profile-list-tile profile-list-tile-${tone}`}>
                          <div className="profile-list-leading">
                            <Icon name="check" size={14} />
                            <span>{s.label}</span>
                          </div>
                          <div className="profile-list-trailing">
                            <span className="profile-count-badge">{s.cat}</span>
                            {deleteStatus(`skill:${s.id || s.label}`)}
                            <button className="profile-row-action" onClick={() => deleteItem("skill", s.id || s.label)} disabled={isDeleting} title={deleteButtonTitle(`skill:${s.id || s.label}`, s.label)}>
                              {deleteButtonContent(`skill:${s.id || s.label}`)}
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {activeProfileTab === "experience" && (
                  <div className="profile-timeline">
                    {exp.length === 0 && <div className="profile-empty">No experience recorded.</div>}
                    {previewExp.map((e: any, idx: number) => {
                      const rowId = String(e?.id || "");
                      const rowKey = profileDeleteKey(e) || `experience-${idx}`;
                      return (
                      <div key={rowKey} className="profile-timeline-item">
                        {rowId && editId === rowId ? (
                          <div className="col gap-3">
                            <div className="grid-2 gap-3">
                              <input className="field-input" value={editData.role} placeholder="Role" onChange={v => setEditData({ ...editData, role: v.target.value })} />
                              <input className="field-input" value={editData.co} placeholder="Company" onChange={v => setEditData({ ...editData, co: v.target.value })} />
                            </div>
                            <input className="field-input" value={editData.period} placeholder="Period" onChange={v => setEditData({ ...editData, period: v.target.value })} />
                            <textarea className="field-input" value={editData.d} rows={4} placeholder="Description" onChange={v => setEditData({ ...editData, d: v.target.value })} />
                            <div className="row gap-2">
                              <button className="btn btn-primary" onClick={() => saveEdit("experience", rowId)}>Save</button>
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
                                {deleteStatus(`experience:${rowKey}`)}
                                <button className="btn-icon profile-mini-action" onClick={() => { setEditId(rowId); setEditData({ ...e }); }} disabled={!rowId || isDeletingKey(`experience:${rowKey}`)} title={rowId ? "Edit experience" : "Re-import or refresh graph before editing this row"}><Icon name="edit" size={14} /></button>
                                <button className="btn-icon profile-mini-action profile-danger" onClick={() => deleteItem("experience", rowKey)} disabled={isDeleting} title={deleteButtonTitle(`experience:${rowKey}`, entryTitle(e) || "experience")} >{deleteButtonContent(`experience:${rowKey}`)}</button>
                              </div>
                            </div>
                            {e.d && <div style={{ fontSize: 13.5, color: "var(--ink-2)", lineHeight: 1.6, marginTop: 10, whiteSpace: "pre-wrap" }}>{e.d}</div>}
                          </div>
                        )}
                      </div>
                      );
                    })}
                  </div>
                )}

                {activeProfileTab === "projects" && (
                  <div className="profile-project-grid">
                    {projects.length === 0 && <div className="profile-empty">No projects mapped.</div>}
                    {previewProjects.map((p: any, idx: number) => {
                      const rowId = String(p?.id || "");
                      const rowKey = profileDeleteKey(p) || `project-${idx}`;
                      return (
                      <div key={rowKey} className="profile-project-card">
                        {rowId && editId === rowId ? (
                          <div className="col gap-3">
                            <input className="field-input" value={editData.title} placeholder="Title" onChange={v => setEditData({ ...editData, title: v.target.value })} />
                            <input className="field-input" value={editData.stack} placeholder="Stack (comma-separated)" onChange={v => setEditData({ ...editData, stack: v.target.value })} />
                            <input className="field-input" value={editData.repo} placeholder="Repo URL" onChange={v => setEditData({ ...editData, repo: v.target.value })} />
                            <textarea className="field-input" value={editData.impact} rows={4} placeholder="Impact" onChange={v => setEditData({ ...editData, impact: v.target.value })} />
                            <div className="row gap-2">
                              <button className="btn btn-primary" onClick={() => saveEdit("project", rowId)}>Save</button>
                              <button className="btn btn-ghost" onClick={() => setEditId(null)}>Cancel</button>
                            </div>
                          </div>
                        ) : (
                          <div className="col gap-1">
                            <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                              <div className="profile-card-title">{p.title}</div>
                              <div className="row gap-2">
                                <span className="profile-count-badge">{idx + 1}</span>
                                {deleteStatus(`project:${rowKey}`)}
                                <button className="btn-icon profile-mini-action" onClick={() => { setEditId(rowId); setEditData({ ...p, stack: stackItems(p.stack).join(", ") }); }} disabled={!rowId || isDeletingKey(`project:${rowKey}`)} title={rowId ? "Edit project" : "Re-import or refresh graph before editing this row"}><Icon name="edit" size={14} /></button>
                                <button className="btn-icon profile-mini-action profile-danger" onClick={() => deleteItem("project", rowKey)} disabled={isDeleting} title={deleteButtonTitle(`project:${rowKey}`, entryTitle(p) || "project")}>{deleteButtonContent(`project:${rowKey}`)}</button>
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
                      );
                    })}
                  </div>
                )}
                {activeProfileTab === "education" && (
                  <div className="profile-skill-grid">
                    {education.length === 0 && <div className="profile-empty">No education recorded.</div>}
                    {previewEducation.map((item: any, idx: number) => {
                      const rowKey = profileDeleteKey(item);
                      return (
                      <div key={`${entryTitle(item)}-${idx}`} className="profile-list-tile profile-list-tile-green">
                        <div className="profile-list-leading">
                          <Icon name="file" size={14} />
                          <span>{entryTitle(item)}</span>
                        </div>
                        <div className="profile-list-trailing">
                          <span className="profile-count-badge">{idx + 1}</span>
                          {deleteStatus(`education:${rowKey}`)}
                          <button className="profile-row-action" onClick={() => deleteItem("education", rowKey)} disabled={isDeleting} title={deleteButtonTitle(`education:${rowKey}`, entryTitle(item) || "education")}>
                            {deleteButtonContent(`education:${rowKey}`)}
                          </button>
                        </div>
                      </div>
                      );
                    })}
                  </div>
                )}
                {activeProfileTab === "certifications" && (
                  <div className="profile-skill-grid">
                    {certifications.length === 0 && <div className="profile-empty">No certifications recorded.</div>}
                    {previewCertifications.map((item: any, idx: number) => {
                      const rowKey = profileDeleteKey(item);
                      return (
                      <div key={`${entryTitle(item)}-${idx}`} className="profile-list-tile profile-list-tile-purple">
                        <div className="profile-list-leading">
                          <Icon name="check" size={14} />
                          <span>{entryTitle(item)}</span>
                        </div>
                        <div className="profile-list-trailing">
                          <span className="profile-count-badge">{idx + 1}</span>
                          {deleteStatus(`certification:${rowKey}`)}
                          <button className="profile-row-action" onClick={() => deleteItem("certification", rowKey)} disabled={isDeleting} title={deleteButtonTitle(`certification:${rowKey}`, entryTitle(item) || "certification")}>
                            {deleteButtonContent(`certification:${rowKey}`)}
                          </button>
                        </div>
                      </div>
                      );
                    })}
                  </div>
                )}
                {activeProfileTab === "achievements" && (
                  <div className="profile-skill-grid">
                    {achievements.length === 0 && <div className="profile-empty">No achievements recorded.</div>}
                    {previewAchievements.map((item: any, idx: number) => {
                      const rowKey = profileDeleteKey(item);
                      return (
                      <div key={`${entryTitle(item)}-${idx}`} className="profile-list-tile profile-list-tile-yellow">
                        <div className="profile-list-leading">
                          <Icon name="trending" size={14} />
                          <span>{entryTitle(item)}</span>
                        </div>
                        <div className="profile-list-trailing">
                          <span className="profile-count-badge">{idx + 1}</span>
                          {deleteStatus(`achievement:${rowKey}`)}
                          <button className="profile-row-action" onClick={() => deleteItem("achievement", rowKey)} disabled={isDeleting} title={deleteButtonTitle(`achievement:${rowKey}`, entryTitle(item) || "achievement")}>
                            {deleteButtonContent(`achievement:${rowKey}`)}
                          </button>
                        </div>
                      </div>
                      );
                    })}
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
