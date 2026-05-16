import React, { useState, useEffect, useCallback } from "react";
import { api } from "../api.js";

const MASK = "__JHM_SECRET_SET__";

const inputStyle = {
  padding: "8px 12px",
  borderRadius: "6px",
  border: "1px solid #d1d5db",
  fontSize: "14px",
  width: "100%",
  boxSizing: "border-box",
};

const btnPrimary = {
  padding: "6px 14px",
  borderRadius: "6px",
  border: "none",
  background: "#2563eb",
  color: "#fff",
  fontWeight: 600,
  cursor: "pointer",
  fontSize: "13px",
};

const btnSecondary = {
  padding: "6px 14px",
  borderRadius: "6px",
  border: "1px solid #d1d5db",
  background: "#fff",
  color: "#374151",
  fontWeight: 600,
  cursor: "pointer",
  fontSize: "13px",
};

const btnDanger = {
  padding: "6px 14px",
  borderRadius: "6px",
  border: "none",
  background: "#dc2626",
  color: "#fff",
  fontWeight: 600,
  cursor: "pointer",
  fontSize: "13px",
};

const cardStyle = {
  background: "#fff",
  borderRadius: "10px",
  border: "1px solid #e5e7eb",
  padding: "20px",
  marginBottom: "16px",
};

const sectionTitle = {
  fontSize: "16px",
  fontWeight: 700,
  margin: "0 0 14px",
  color: "#111827",
};

export default function ProfilePage() {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState("");

  const fetchProfile = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.getProfile();
      setProfile(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  const handleSaveCandidate = async (n, s) => {
    setSaving("candidate");
    try {
      await api.updateCandidate({ n, s });
      await fetchProfile();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving("");
    }
  };

  const handleSaveIdentity = async (identity) => {
    setSaving("identity");
    try {
      await api.updateIdentity(identity);
      await fetchProfile();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving("");
    }
  };

  if (loading) return <div style={{ padding: "40px", textAlign: "center" }}>Loading…</div>;
  if (error) return <div style={{ color: "#dc2626", padding: "20px" }}>Error: {error}</div>;
  if (!profile) return <div style={{ padding: "20px" }}>No profile found.</div>;

  return (
    <div style={{ maxWidth: "900px", padding: "24px" }}>
      <h1 style={{ margin: "0 0 20px", fontSize: "22px", fontWeight: 800 }}>Profile</h1>

      {error && (
        <div style={{ color: "#dc2626", background: "#fef2f2", padding: "12px 16px", borderRadius: "8px", marginBottom: "16px", fontSize: "14px" }}>
          {error}
        </div>
      )}

      <IdentitySection identity={profile.identity || {}} onSave={handleSaveIdentity} saving={saving === "identity"} />
      <CandidateSection n={profile.n || ""} s={profile.s || ""} onSave={handleSaveCandidate} saving={saving === "candidate"} />
      <SkillsSection skills={profile.skills || []} onRefresh={fetchProfile} />
      <ExperienceSection exp={profile.exp || []} onRefresh={fetchProfile} />
      <ProjectsSection projects={profile.projects || []} onRefresh={fetchProfile} />
      <SimpleListSection title="Education" items={profile.education || []} addApi={api.addEducation} deleteApi={api.deleteEducation} onRefresh={fetchProfile} />
      <SimpleListSection title="Certifications" items={profile.certifications || []} addApi={api.addCertification} deleteApi={api.deleteCertification} onRefresh={fetchProfile} />
      <SimpleListSection title="Achievements" items={profile.achievements || []} addApi={api.addAchievement} deleteApi={api.deleteAchievement} onRefresh={fetchProfile} />
    </div>
  );
}

function IdentitySection({ identity, onSave, saving }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(identity);

  useEffect(() => {
    setForm(identity);
  }, [identity]);

  const fields = [
    { key: "email", label: "Email" },
    { key: "phone", label: "Phone" },
    { key: "city", label: "City" },
    { key: "linkedin_url", label: "LinkedIn" },
    { key: "github_url", label: "GitHub" },
    { key: "website_url", label: "Website" },
  ];

  if (!editing) {
    return (
      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <h2 style={sectionTitle}>Identity</h2>
          <button onClick={() => setEditing(true)} style={btnSecondary}>Edit</button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          {fields.map((f) => (
            <div key={f.key}>
              <div style={{ fontSize: "12px", color: "#6b7280", fontWeight: 600, marginBottom: "2px" }}>{f.label}</div>
              <div style={{ fontSize: "14px", color: "#111827" }}>{form[f.key] || "—"}</div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div style={cardStyle}>
      <h2 style={sectionTitle}>Identity</h2>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
        {fields.map((f) => (
          <div key={f.key}>
            <label style={{ fontSize: "12px", color: "#6b7280", fontWeight: 600 }}>{f.label}</label>
            <input
              style={inputStyle}
              value={form[f.key] || ""}
              onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
            />
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: "10px", marginTop: "14px" }}>
        <button
          onClick={() => onSave(form)}
          disabled={saving}
          style={{ ...btnPrimary, opacity: saving ? 0.6 : 1 }}
        >
          {saving ? "Saving…" : "Save"}
        </button>
        <button onClick={() => { setForm(identity); setEditing(false); }} style={btnSecondary}>Cancel</button>
      </div>
    </div>
  );
}

function CandidateSection({ n, s, onSave, saving }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(n);
  const [summary, setSummary] = useState(s);

  useEffect(() => { setName(n); setSummary(s); }, [n, s]);

  if (!editing) {
    return (
      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <h2 style={sectionTitle}>Summary</h2>
          <button onClick={() => setEditing(true)} style={btnSecondary}>Edit</button>
        </div>
        <div style={{ fontSize: "14px", fontWeight: 700, marginBottom: "6px" }}>{n || "—"}</div>
        <div style={{ fontSize: "14px", color: "#374151", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{s || "—"}</div>
      </div>
    );
  }

  return (
    <div style={cardStyle}>
      <h2 style={sectionTitle}>Summary</h2>
      <label style={{ fontSize: "12px", color: "#6b7280", fontWeight: 600 }}>Name</label>
      <input style={{ ...inputStyle, marginBottom: "12px" }} value={name} onChange={(e) => setName(e.target.value)} />
      <label style={{ fontSize: "12px", color: "#6b7280", fontWeight: 600 }}>Summary</label>
      <textarea
        style={{ ...inputStyle, minHeight: "100px", resize: "vertical" }}
        value={summary}
        onChange={(e) => setSummary(e.target.value)}
      />
      <div style={{ display: "flex", gap: "10px", marginTop: "14px" }}>
        <button onClick={() => onSave(name, summary)} disabled={saving} style={{ ...btnPrimary, opacity: saving ? 0.6 : 1 }}>
          {saving ? "Saving…" : "Save"}
        </button>
        <button onClick={() => { setName(n); setSummary(s); setEditing(false); }} style={btnSecondary}>Cancel</button>
      </div>
    </div>
  );
}

function SkillsSection({ skills, onRefresh }) {
  const [adding, setAdding] = useState(false);
  const [newSkill, setNewSkill] = useState({ n: "", cat: "frontend" });
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({ n: "", cat: "" });
  const [busy, setBusy] = useState(false);

  const handleAdd = async () => {
    if (!newSkill.n.trim()) return;
    setBusy(true);
    try {
      await api.addSkill(newSkill);
      setNewSkill({ n: "", cat: "frontend" });
      setAdding(false);
      await onRefresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleUpdate = async (sid) => {
    if (!editForm.n.trim()) return;
    setBusy(true);
    try {
      await api.updateSkill(sid, editForm);
      setEditingId(null);
      await onRefresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (sid) => {
    if (!confirm("Delete this skill?")) return;
    setBusy(true);
    try {
      await api.deleteSkill(sid);
      await onRefresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  };

  const cats = ["frontend", "backend", "database", "devops", "tools", "ai", "other"];

  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
        <h2 style={sectionTitle}>Skills ({skills.length})</h2>
        <button onClick={() => setAdding((v) => !v)} style={btnPrimary}>+ Add</button>
      </div>

      {adding && (
        <div style={{ display: "flex", gap: "10px", marginBottom: "14px", alignItems: "center" }}>
          <input
            style={{ ...inputStyle, maxWidth: "200px" }}
            placeholder="Skill name"
            value={newSkill.n}
            onChange={(e) => setNewSkill((p) => ({ ...p, n: e.target.value }))}
          />
          <select
            style={{ ...inputStyle, maxWidth: "140px" }}
            value={newSkill.cat}
            onChange={(e) => setNewSkill((p) => ({ ...p, cat: e.target.value }))}
          >
            {cats.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <button onClick={handleAdd} disabled={busy} style={{ ...btnPrimary, opacity: busy ? 0.6 : 1 }}>Save</button>
          <button onClick={() => setAdding(false)} style={btnSecondary}>Cancel</button>
        </div>
      )}

      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
        {skills.map((skill, idx) => {
          const sid = skill.n || idx;
          if (editingId === sid) {
            return (
              <div key={sid} style={{ display: "flex", gap: "6px", alignItems: "center", background: "#f3f4f6", padding: "6px 10px", borderRadius: "6px" }}>
                <input
                  style={{ ...inputStyle, width: "140px", padding: "4px 8px" }}
                  value={editForm.n}
                  onChange={(e) => setEditForm((p) => ({ ...p, n: e.target.value }))}
                />
                <select
                  style={{ ...inputStyle, width: "100px", padding: "4px 8px" }}
                  value={editForm.cat}
                  onChange={(e) => setEditForm((p) => ({ ...p, cat: e.target.value }))}
                >
                  {cats.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
                <button onClick={() => handleUpdate(sid)} disabled={busy} style={{ ...btnPrimary, padding: "4px 10px", fontSize: "12px" }}>✓</button>
                <button onClick={() => setEditingId(null)} style={{ ...btnSecondary, padding: "4px 10px", fontSize: "12px" }}>✕</button>
              </div>
            );
          }
          return (
            <div
              key={sid}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                background: "#f3f4f6",
                padding: "6px 12px",
                borderRadius: "6px",
                fontSize: "13px",
              }}
            >
              <span style={{ fontWeight: 600 }}>{skill.n}</span>
              <span style={{ color: "#6b7280", fontSize: "11px" }}>{skill.cat}</span>
              <button
                onClick={() => { setEditingId(sid); setEditForm({ n: skill.n, cat: skill.cat || "other" }); }}
                style={{ border: "none", background: "none", cursor: "pointer", fontSize: "12px", color: "#2563eb" }}
              >
                ✎
              </button>
              <button
                onClick={() => handleDelete(sid)}
                style={{ border: "none", background: "none", cursor: "pointer", fontSize: "12px", color: "#dc2626" }}
              >
                ×
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ExperienceSection({ exp, onRefresh }) {
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ role: "", co: "", period: "", d: "" });
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({ role: "", co: "", period: "", d: "" });
  const [busy, setBusy] = useState(false);

  const reset = () => { setForm({ role: "", co: "", period: "", d: "" }); };

  const handleAdd = async () => {
    if (!form.role.trim() && !form.co.trim()) return;
    setBusy(true);
    try {
      await api.addExperience(form);
      reset();
      setAdding(false);
      await onRefresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleUpdate = async (eid) => {
    if (!editForm.role.trim() && !editForm.co.trim()) return;
    setBusy(true);
    try {
      await api.updateExperience(eid, editForm);
      setEditingId(null);
      await onRefresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (eid) => {
    if (!confirm("Delete this experience?")) return;
    setBusy(true);
    try {
      await api.deleteExperience(eid);
      await onRefresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
        <h2 style={sectionTitle}>Experience ({exp.length})</h2>
        <button onClick={() => setAdding((v) => !v)} style={btnPrimary}>+ Add</button>
      </div>

      {adding && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "14px" }}>
          <input style={inputStyle} placeholder="Role" value={form.role} onChange={(e) => setForm((p) => ({ ...p, role: e.target.value }))} />
          <input style={inputStyle} placeholder="Company" value={form.co} onChange={(e) => setForm((p) => ({ ...p, co: e.target.value }))} />
          <input style={inputStyle} placeholder="Period" value={form.period} onChange={(e) => setForm((p) => ({ ...p, period: e.target.value }))} />
          <input style={inputStyle} placeholder="Description" value={form.d} onChange={(e) => setForm((p) => ({ ...p, d: e.target.value }))} />
          <div style={{ display: "flex", gap: "10px", gridColumn: "1 / -1" }}>
            <button onClick={handleAdd} disabled={busy} style={btnPrimary}>{busy ? "Saving…" : "Save"}</button>
            <button onClick={() => { reset(); setAdding(false); }} style={btnSecondary}>Cancel</button>
          </div>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {exp.map((item) => {
          const eid = item.role + "::" + item.co;
          if (editingId === eid) {
            return (
              <div key={eid} style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", background: "#f9fafb", padding: "12px", borderRadius: "8px" }}>
                <input style={inputStyle} value={editForm.role} onChange={(e) => setEditForm((p) => ({ ...p, role: e.target.value }))} />
                <input style={inputStyle} value={editForm.co} onChange={(e) => setEditForm((p) => ({ ...p, co: e.target.value }))} />
                <input style={inputStyle} value={editForm.period} onChange={(e) => setEditForm((p) => ({ ...p, period: e.target.value }))} />
                <input style={inputStyle} value={editForm.d} onChange={(e) => setEditForm((p) => ({ ...p, d: e.target.value }))} />
                <div style={{ display: "flex", gap: "10px", gridColumn: "1 / -1" }}>
                  <button onClick={() => handleUpdate(eid)} disabled={busy} style={btnPrimary}>{busy ? "Saving…" : "Save"}</button>
                  <button onClick={() => setEditingId(null)} style={btnSecondary}>Cancel</button>
                </div>
              </div>
            );
          }
          return (
            <div key={eid} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", background: "#f9fafb", padding: "12px", borderRadius: "8px" }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: "14px" }}>{item.role} <span style={{ color: "#6b7280", fontWeight: 400 }}>@ {item.co}</span></div>
                <div style={{ fontSize: "12px", color: "#6b7280", marginTop: "2px" }}>{item.period}</div>
                <div style={{ fontSize: "13px", color: "#374151", marginTop: "4px" }}>{item.d}</div>
              </div>
              <div style={{ display: "flex", gap: "6px", flexShrink: 0 }}>
                <button onClick={() => { setEditingId(eid); setEditForm({ role: item.role, co: item.co, period: item.period || "", d: item.d || "" }); }} style={{ ...btnSecondary, padding: "4px 10px", fontSize: "12px" }}>Edit</button>
                <button onClick={() => handleDelete(eid)} style={{ ...btnDanger, padding: "4px 10px", fontSize: "12px" }}>Delete</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ProjectsSection({ projects, onRefresh }) {
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ title: "", stack: "", repo: "", impact: "" });
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({ title: "", stack: "", repo: "", impact: "" });
  const [busy, setBusy] = useState(false);

  const reset = () => { setForm({ title: "", stack: "", repo: "", impact: "" }); };

  const handleAdd = async () => {
    if (!form.title.trim()) return;
    const body = { ...form, stack: form.stack.split(",").map((s) => s.trim()).filter(Boolean) };
    setBusy(true);
    try {
      await api.addProject(body);
      reset();
      setAdding(false);
      await onRefresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleUpdate = async (pid) => {
    if (!editForm.title.trim()) return;
    const body = { ...editForm, stack: editForm.stack.split(",").map((s) => s.trim()).filter(Boolean) };
    setBusy(true);
    try {
      await api.updateProject(pid, body);
      setEditingId(null);
      await onRefresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (pid) => {
    if (!confirm("Delete this project?")) return;
    setBusy(true);
    try {
      await api.deleteProject(pid);
      await onRefresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
        <h2 style={sectionTitle}>Projects ({projects.length})</h2>
        <button onClick={() => setAdding((v) => !v)} style={btnPrimary}>+ Add</button>
      </div>

      {adding && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "14px" }}>
          <input style={inputStyle} placeholder="Title" value={form.title} onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))} />
          <input style={inputStyle} placeholder="Stack (comma separated)" value={form.stack} onChange={(e) => setForm((p) => ({ ...p, stack: e.target.value }))} />
          <input style={inputStyle} placeholder="Repo URL" value={form.repo} onChange={(e) => setForm((p) => ({ ...p, repo: e.target.value }))} />
          <input style={inputStyle} placeholder="Impact" value={form.impact} onChange={(e) => setForm((p) => ({ ...p, impact: e.target.value }))} />
          <div style={{ display: "flex", gap: "10px", gridColumn: "1 / -1" }}>
            <button onClick={handleAdd} disabled={busy} style={btnPrimary}>{busy ? "Saving…" : "Save"}</button>
            <button onClick={() => { reset(); setAdding(false); }} style={btnSecondary}>Cancel</button>
          </div>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {projects.map((item) => {
          const pid = item.title;
          if (editingId === pid) {
            return (
              <div key={pid} style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", background: "#f9fafb", padding: "12px", borderRadius: "8px" }}>
                <input style={inputStyle} value={editForm.title} onChange={(e) => setEditForm((p) => ({ ...p, title: e.target.value }))} />
                <input style={inputStyle} placeholder="Stack (comma separated)" value={editForm.stack} onChange={(e) => setEditForm((p) => ({ ...p, stack: e.target.value }))} />
                <input style={inputStyle} value={editForm.repo} onChange={(e) => setEditForm((p) => ({ ...p, repo: e.target.value }))} />
                <input style={inputStyle} value={editForm.impact} onChange={(e) => setEditForm((p) => ({ ...p, impact: e.target.value }))} />
                <div style={{ display: "flex", gap: "10px", gridColumn: "1 / -1" }}>
                  <button onClick={() => handleUpdate(pid)} disabled={busy} style={btnPrimary}>{busy ? "Saving…" : "Save"}</button>
                  <button onClick={() => setEditingId(null)} style={btnSecondary}>Cancel</button>
                </div>
              </div>
            );
          }
          return (
            <div key={pid} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", background: "#f9fafb", padding: "12px", borderRadius: "8px" }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: "14px" }}>{item.title}</div>
                <div style={{ fontSize: "12px", color: "#6b7280", marginTop: "2px" }}>
                  {Array.isArray(item.stack) ? item.stack.join(", ") : item.stack}
                </div>
                {item.repo && <div style={{ fontSize: "12px", marginTop: "2px" }}><a href={item.repo} target="_blank" rel="noreferrer" style={{ color: "#2563eb" }}>{item.repo}</a></div>}
                <div style={{ fontSize: "13px", color: "#374151", marginTop: "4px" }}>{item.impact}</div>
              </div>
              <div style={{ display: "flex", gap: "6px", flexShrink: 0 }}>
                <button onClick={() => { setEditingId(pid); setEditForm({ title: item.title, stack: Array.isArray(item.stack) ? item.stack.join(", ") : item.stack || "", repo: item.repo || "", impact: item.impact || "" }); }} style={{ ...btnSecondary, padding: "4px 10px", fontSize: "12px" }}>Edit</button>
                <button onClick={() => handleDelete(pid)} style={{ ...btnDanger, padding: "4px 10px", fontSize: "12px" }}>Delete</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SimpleListSection({ title, items, addApi, deleteApi, onRefresh }) {
  const [adding, setAdding] = useState(false);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);

  const handleAdd = async () => {
    if (!value.trim()) return;
    setBusy(true);
    try {
      await addApi({ title: value.trim() });
      setValue("");
      setAdding(false);
      await onRefresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (entry) => {
    if (!confirm(`Delete "${entry}"?`)) return;
    setBusy(true);
    try {
      await deleteApi(entry);
      await onRefresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
        <h2 style={sectionTitle}>{title} ({items.length})</h2>
        <button onClick={() => setAdding((v) => !v)} style={btnPrimary}>+ Add</button>
      </div>

      {adding && (
        <div style={{ display: "flex", gap: "10px", marginBottom: "14px", alignItems: "center" }}>
          <input
            style={{ ...inputStyle, maxWidth: "400px" }}
            placeholder={`New ${title.toLowerCase()} entry`}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleAdd(); }}
          />
          <button onClick={handleAdd} disabled={busy} style={btnPrimary}>{busy ? "Saving…" : "Save"}</button>
          <button onClick={() => { setValue(""); setAdding(false); }} style={btnSecondary}>Cancel</button>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {items.map((item, idx) => {
          const text = typeof item === "string" ? item : item.title || JSON.stringify(item);
          return (
            <div key={idx} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "#f9fafb", padding: "10px 12px", borderRadius: "6px" }}>
              <span style={{ fontSize: "14px" }}>{text}</span>
              <button onClick={() => handleDelete(text)} style={{ border: "none", background: "none", cursor: "pointer", fontSize: "14px", color: "#dc2626" }}>×</button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
