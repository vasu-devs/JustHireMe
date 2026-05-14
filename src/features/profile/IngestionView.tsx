import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import Icon from "../../shared/components/Icon";
import type { ApiFetch } from "../../types";

export function IngestionView({ api }: { api: ApiFetch }) {
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [activeTab, setActiveTab] = useState<"resume" | "manual" | "raw" | "template" | "linkedin" | "github" | "portfolio" | "json-import">("resume");

  // Forms
  const [skillForm, setSkillForm] = useState({ n: "", cat: "technical" });
  const [expForm, setExpForm]     = useState({ role: "", co: "", period: "", d: "" });
  const [projForm, setProjForm]   = useState({ title: "", stack: "", repo: "", impact: "" });
  const [identityForm, setIdentityForm] = useState({ email: "", phone: "", linkedin_url: "", github_url: "", website_url: "", city: "" });
  const [eduForm, setEduForm] = useState({ title: "" });
  const [certForm, setCertForm] = useState({ title: "" });
  const [achievementForm, setAchievementForm] = useState({ title: "" });
  const [rawText, setRawText]     = useState("");
  const [template, setTemplate]   = useState("");
  const [templateLoaded, setTemplateLoaded] = useState(false);

  // LinkedIn tab state
  const [linkedinFile, setLinkedinFile] = useState<File | null>(null);
  const [linkedinResult, setLinkedinResult] = useState<any>(null);
  // GitHub tab state
  const [githubUsername, setGithubUsername] = useState("");
  const [githubToken, setGithubToken] = useState("");
  const [githubResult, setGithubResult] = useState<any>(null);
  const [showToken, setShowToken] = useState(false);
  const [githubMaxRepos, setGithubMaxRepos] = useState(100);
  // Portfolio tab state
  const [portfolioUrl, setPortfolioUrl] = useState("");
  const [portfolioResult, setPortfolioResult] = useState<any>(null);
  // JSON import tab state
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [jsonResult, setJsonResult] = useState<any>(null);

  // Load existing template on mount
  useEffect(() => {
    if (activeTab !== "template" || templateLoaded) return;
    api(`/api/v1/template`)
      .then(r => r.json())
      .then(d => { setTemplate(d.template || ""); setTemplateLoaded(true); })
      .catch(() => {});
  }, [activeTab, api, templateLoaded]);

  const saveTemplate = async () => {
    setStatus("loading");
    try {
      const r = await api(`/api/v1/template`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ template }),
      });
      setStatus(r.ok ? "done" : "error");
    } catch { setStatus("error"); }
  };

  const addManual = async (type: string, data: any) => {
    setStatus("loading");
    try {
      const endpointType = type === "exp" ? "experience" : type;
      const r = await api(`/api/v1/profile/${endpointType}`, {
        method: type === "identity" ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
      });
      if (r.ok) {
        setStatus("done");
        if (type === "skill")   setSkillForm({ n: "", cat: "technical" });
        if (type === "exp")     setExpForm({ role: "", co: "", period: "", d: "" });
        if (type === "project") setProjForm({ title: "", stack: "", repo: "", impact: "" });
        if (type === "identity") setIdentityForm({ email: "", phone: "", linkedin_url: "", github_url: "", website_url: "", city: "" });
        if (type === "education") setEduForm({ title: "" });
        if (type === "certification") setCertForm({ title: "" });
        if (type === "achievement") setAchievementForm({ title: "" });
        window.dispatchEvent(new CustomEvent("profile-refresh"));
        window.dispatchEvent(new CustomEvent("graph-refresh"));
      } else { setStatus("error"); }
    } catch { setStatus("error"); }
  };

  const ingestResume = async (file: File) => {
    setStatus("loading");
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api(`/api/v1/ingest`, { method: "POST", body: fd });
      setStatus(r.ok ? "done" : "error");
    } catch { setStatus("error"); }
  };

  const ingestLinkedin = async () => {
    if (!linkedinFile) return;
    setStatus("loading");
    setLinkedinResult(null);
    const fd = new FormData();
    fd.append("file", linkedinFile);
    try {
      const isPdf = linkedinFile.name.toLowerCase().endsWith(".pdf");
      const r = await api(isPdf ? `/api/v1/ingest` : `/api/v1/ingest/linkedin`, { method: "POST", body: fd });
      if (r.ok) {
        const data = await r.json();
        setLinkedinResult(isPdf ? {
          status: "ok",
          source: "pdf",
          stats: {
            skills: data?.skills?.length ?? 0,
            experience: data?.exp?.length ?? data?.experience?.length ?? 0,
            projects: data?.projects?.length ?? 0,
            certifications: data?.certifications?.length ?? 0,
          },
        } : data);
        window.dispatchEvent(new CustomEvent("profile-refresh"));
        window.dispatchEvent(new CustomEvent("graph-refresh"));
        setStatus("idle");
      } else {
        const data = await r.json().catch(() => ({}));
        setLinkedinResult({ errorMsg: data?.detail || `Import failed (${r.status})` });
        setStatus("idle");
      }
    } catch (err: any) {
      setLinkedinResult({ errorMsg: err?.message || "Could not import LinkedIn context." });
      setStatus("idle");
    }
  };

  const ingestGithub = async () => {
    setStatus("loading");
    setGithubResult(null);
    try {
      const r = await api(`/api/v1/ingest/github`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: githubUsername, token: githubToken, max_repos: githubMaxRepos }),
      });
      if (r.ok) {
        const data = await r.json();
        setGithubResult(data);
        setStatus("idle");
      } else {
        const data = await r.json().catch(() => ({}));
        setGithubResult({ errorMsg: data?.detail || `GitHub import failed (${r.status})` });
        setStatus("idle");
      }
    } catch {
      setGithubResult({ errorMsg: "Could not reach the local backend." });
      setStatus("idle");
    }
  };

  const scanPortfolio = async (autoImport = false) => {
    setStatus("loading");
    if (!autoImport) setPortfolioResult(null);
    try {
      const r = await api(`/api/v1/ingest/portfolio`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: portfolioUrl, auto_import: autoImport }),
        timeoutMs: 180000,
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        setPortfolioResult(data);
        setStatus("idle");
      } else {
        setPortfolioResult({ errorMsg: data?.detail || "Could not fetch portfolio." });
        setStatus("idle");
      }
    } catch (err: any) {
      setPortfolioResult({ errorMsg: err?.message || "Could not fetch portfolio." });
      setStatus("idle");
    }
  };

  const importPortfolioResult = async () => {
    if (!portfolioResult || portfolioResult.errorMsg || portfolioResult.error) return;
    setStatus("loading");
    setPortfolioResult({ ...portfolioResult, importError: null });
    const payload = {
      candidate: portfolioResult.candidate,
      identity: portfolioResult.identity,
      skills: portfolioResult.skills || [],
      projects: portfolioResult.projects || [],
      achievements: portfolioResult.achievements || [],
      experience: portfolioResult.experience || [],
      education: portfolioResult.education || [],
      certifications: portfolioResult.certifications || [],
    };
    try {
      const r = await api(`/api/v1/ingest/profile`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        timeoutMs: 120000,
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        setPortfolioResult({ ...portfolioResult, importError: data?.detail || `Import failed (${r.status})` });
        setStatus("idle");
        return;
      }
      setPortfolioResult({ ...portfolioResult, imported: data });
      window.dispatchEvent(new CustomEvent("profile-refresh"));
      window.dispatchEvent(new CustomEvent("graph-refresh"));
      setStatus("idle");
    } catch (err: any) {
      setPortfolioResult({ ...portfolioResult, importError: err?.message || "Could not import portfolio." });
      setStatus("idle");
    }
  };

  const downloadProfileTemplate = async () => {
    try {
      const r = await api(`/api/v1/ingest/profile/template`);
      if (!r.ok) throw new Error(`Template download failed (${r.status})`);
      const data = await r.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "jhm_profile_template.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setJsonError("Could not download template.");
    }
  };

  const importProfileJson = async () => {
    setJsonError(null);
    setJsonResult(null);
    let parsed: any;
    try {
      parsed = JSON.parse(jsonText);
    } catch (err: any) {
      setJsonError(err?.message || "Invalid JSON.");
      return;
    }
    setStatus("loading");
    try {
      const r = await api(`/api/v1/ingest/profile`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        setJsonResult(data);
        setStatus("idle");
      } else {
        setJsonError(data?.detail ? JSON.stringify(data.detail) : `Import failed (${r.status})`);
        setStatus("idle");
      }
    } catch {
      setJsonError("Could not import profile JSON.");
      setStatus("idle");
    }
  };

  const ingestRaw = async () => {
    setStatus("loading");
    const fd = new FormData();
    fd.append("raw", rawText);
    try {
      const r = await api(`/api/v1/ingest`, { method: "POST", body: fd });
      if (r.ok) { setStatus("done"); setRawText(""); } else { setStatus("error"); }
    } catch { setStatus("error"); }
  };

  const TABS = [
    { id: "resume" as const, label: "Resume", description: "PDF parser", icon: "upload", accent: "teal" },
    { id: "manual" as const, label: "Manual", description: "Skills, roles, projects", icon: "plus", accent: "blue" },
    { id: "raw" as const, label: "Raw Text", description: "Paste notes", icon: "file", accent: "yellow" },
    { id: "template" as const, label: "Template", description: "Resume format", icon: "layers", accent: "purple" },
    { id: "linkedin" as const, label: "LinkedIn", description: "Data export", icon: "brief", accent: "blue" },
    { id: "github" as const, label: "GitHub", description: "Repo signals", icon: "external-link", accent: "green" },
    { id: "portfolio" as const, label: "Portfolio", description: "Personal site", icon: "globe", accent: "orange" },
    { id: "json-import" as const, label: "JSON", description: "Structured import", icon: "download", accent: "pink" },
  ];
  const activeTabMeta = TABS.find(t => t.id === activeTab) ?? TABS[0];

  return (
    <div className="ingestion-page scroll">
      <div className="ingestion-shell">
        <div className="ingestion-hero">
          <div className="ingestion-hero-copy">
            <span className="eyebrow">Append-only Pipeline</span>
            <h2>Add Context</h2>
            <p>Merge resumes, repos, portfolio pages, exports, and hand-written notes into one clean Identity Graph.</p>
          </div>
          <div className={`ingestion-active-card ingestion-accent-${activeTabMeta.accent}`}>
            <div className="ingestion-active-icon"><Icon name={activeTabMeta.icon} size={18} /></div>
            <div>
              <span>Current source</span>
              <strong>{activeTabMeta.label}</strong>
            </div>
          </div>
        </div>

        <div className="ingestion-tabs" role="tablist" aria-label="Context source">
          {TABS.map(t => (
            <button key={t.id} onClick={() => { setActiveTab(t.id); setStatus("idle"); }}
              className={`ingestion-tab ingestion-accent-${t.accent} ${activeTab === t.id ? "active" : ""}`}
              role="tab"
              aria-selected={activeTab === t.id}>
              <span className="ingestion-tab-icon"><Icon name={t.icon} size={15} /></span>
              <span className="ingestion-tab-copy">
                <strong>{t.label}</strong>
                <small>{t.description}</small>
              </span>
            </button>
          ))}
        </div>

        {status === "done" && (
          <motion.div initial={{opacity:0,y:-10}} animate={{opacity:1,y:0}} className="ingestion-alert success">
            <Icon name="check" size={18} /><div style={{fontWeight:600}}>Saved successfully!</div>
          </motion.div>
        )}
        {status === "error" && (
          <motion.div initial={{opacity:0,y:-10}} animate={{opacity:1,y:0}} className="ingestion-alert error">
            An error occurred.
          </motion.div>
        )}

        {activeTab === "resume" && (
          <motion.div initial={{opacity:0}} animate={{opacity:1}} className="card col gap-4" style={{ padding: "64px 32px", alignItems: "center", textAlign: "center", border: "2px dashed var(--line)", background: "var(--paper-2)" }}>
            <div style={{ width: 64, height: 64, borderRadius: 16, background: "var(--teal-soft)", color: "var(--teal)", display: "grid", placeItems: "center" }}><Icon name="upload" size={28} /></div>
            <div style={{ fontWeight: 600, fontSize: 18 }}>Drop a fresh Resume PDF</div>
            <div style={{ fontSize: 14, color: "var(--ink-3)", maxWidth: 360, lineHeight: 1.5 }}>Our ingestion agent discovers skills, roles, and projects and maps them into your graph.</div>
            <input type="file" accept=".pdf" onChange={e => e.target.files?.[0] && ingestResume(e.target.files[0])} style={{ display: "none" }} id="pdf-in" />
            <button className="btn btn-primary" style={{ marginTop: 16, padding: "12px 32px", fontSize: 15 }} onClick={() => document.getElementById("pdf-in")?.click()}>Select PDF File</button>
            {status === "loading" && <div className="mono pulse" style={{ fontSize: 12, marginTop: 16 }}>Agent parsing resume...</div>}
          </motion.div>
        )}

        {activeTab === "manual" && (
          <motion.div initial={{opacity:0}} animate={{opacity:1}} className="col gap-8">
            <div className="card col gap-4" style={{ padding: 24 }}>
              <h3 style={{ fontSize: 16, fontWeight: 600, display: "flex", gap: 8, alignItems: "center" }}><Icon name="spark" size={16}/> Add Skill</h3>
              <input className="field-input" placeholder="Skill name" value={skillForm.n} onChange={v => setSkillForm({...skillForm, n: v.target.value})} />
              <select className="field-input" value={skillForm.cat} onChange={v => setSkillForm({...skillForm, cat: v.target.value})}>
                <option value="technical">Technical</option>
                <option value="soft">Soft Skill</option>
                <option value="tool">Tool / Utility</option>
                <option value="language">Language</option>
                <option value="framework">Framework</option>
              </select>
              <button className="btn btn-primary" style={{alignSelf:"flex-start",padding:"10px 24px"}} onClick={() => addManual("skill", skillForm)} disabled={status==="loading" || !skillForm.n.trim()}>Add Skill</button>
            </div>
            <div className="card col gap-4" style={{ padding: 24 }}>
              <h3 style={{ fontSize: 16, fontWeight: 600, display: "flex", gap: 8, alignItems: "center" }}><Icon name="brief" size={16}/> Add Experience</h3>
              <input className="field-input" placeholder="Role Title" value={expForm.role} onChange={v => setExpForm({...expForm, role: v.target.value})} />
              <input className="field-input" placeholder="Company" value={expForm.co} onChange={v => setExpForm({...expForm, co: v.target.value})} />
              <input className="field-input" placeholder="Period (e.g. 2022-2024)" value={expForm.period} onChange={v => setExpForm({...expForm, period: v.target.value})} />
              <textarea className="field-input" placeholder="Description" rows={3} value={expForm.d} onChange={v => setExpForm({...expForm, d: v.target.value})} />
              <button className="btn btn-primary" style={{alignSelf:"flex-start",padding:"10px 24px"}} onClick={() => addManual("exp", expForm)} disabled={status==="loading" || (!expForm.role.trim() && !expForm.co.trim())}>Add Experience</button>
            </div>
            <div className="card col gap-4" style={{ padding: 24 }}>
              <h3 style={{ fontSize: 16, fontWeight: 600, display: "flex", gap: 8, alignItems: "center" }}><Icon name="layers" size={16}/> Add Project</h3>
              <input className="field-input" placeholder="Project Title" value={projForm.title} onChange={v => setProjForm({...projForm, title: v.target.value})} />
              <input className="field-input" placeholder="Stack (comma-separated)" value={projForm.stack} onChange={v => setProjForm({...projForm, stack: v.target.value})} />
              <input className="field-input" placeholder="Repo URL (optional)" value={projForm.repo} onChange={v => setProjForm({...projForm, repo: v.target.value})} />
              <textarea className="field-input" placeholder="Impact / Description" rows={3} value={projForm.impact} onChange={v => setProjForm({...projForm, impact: v.target.value})} />
              <button className="btn btn-primary" style={{alignSelf:"flex-start",padding:"10px 24px"}} onClick={() => addManual("project", projForm)} disabled={status==="loading" || !projForm.title.trim()}>Add Project</button>
            </div>
            <div className="card col gap-4" style={{ padding: 24 }}>
              <h3 style={{ fontSize: 16, fontWeight: 600, display: "flex", gap: 8, alignItems: "center" }}><Icon name="user" size={16}/> Contact & Social Links</h3>
              <div className="grid-2 gap-3">
                <input className="field-input" placeholder="Email address" value={identityForm.email} onChange={v => setIdentityForm({...identityForm, email: v.target.value})} />
                <input className="field-input" placeholder="Phone number" value={identityForm.phone} onChange={v => setIdentityForm({...identityForm, phone: v.target.value})} />
                <input className="field-input" placeholder="LinkedIn URL" value={identityForm.linkedin_url} onChange={v => setIdentityForm({...identityForm, linkedin_url: v.target.value})} />
                <input className="field-input" placeholder="GitHub URL" value={identityForm.github_url} onChange={v => setIdentityForm({...identityForm, github_url: v.target.value})} />
                <input className="field-input" placeholder="Portfolio / website URL" value={identityForm.website_url} onChange={v => setIdentityForm({...identityForm, website_url: v.target.value})} />
                <input className="field-input" placeholder="City / location" value={identityForm.city} onChange={v => setIdentityForm({...identityForm, city: v.target.value})} />
              </div>
              <button className="btn btn-primary" style={{alignSelf:"flex-start",padding:"10px 24px"}} onClick={() => addManual("identity", identityForm)} disabled={status==="loading"}>Save Contact</button>
            </div>
            <div className="grid-2 gap-4">
              <div className="card col gap-4" style={{ padding: 24 }}>
                <h3 style={{ fontSize: 16, fontWeight: 600, display: "flex", gap: 8, alignItems: "center" }}><Icon name="file" size={16}/> Add Education</h3>
                <input className="field-input" placeholder="Degree, school, year" value={eduForm.title} onChange={v => setEduForm({...eduForm, title: v.target.value})} />
                <button className="btn btn-primary" style={{alignSelf:"flex-start",padding:"10px 24px"}} onClick={() => addManual("education", eduForm)} disabled={status==="loading" || !eduForm.title.trim()}>Add Education</button>
              </div>
              <div className="card col gap-4" style={{ padding: 24 }}>
                <h3 style={{ fontSize: 16, fontWeight: 600, display: "flex", gap: 8, alignItems: "center" }}><Icon name="check" size={16}/> Add Certification</h3>
                <input className="field-input" placeholder="Certification, issuer, year" value={certForm.title} onChange={v => setCertForm({...certForm, title: v.target.value})} />
                <button className="btn btn-primary" style={{alignSelf:"flex-start",padding:"10px 24px"}} onClick={() => addManual("certification", certForm)} disabled={status==="loading" || !certForm.title.trim()}>Add Certification</button>
              </div>
            </div>
            <div className="card col gap-4" style={{ padding: 24 }}>
              <h3 style={{ fontSize: 16, fontWeight: 600, display: "flex", gap: 8, alignItems: "center" }}><Icon name="trending" size={16}/> Add Achievement</h3>
              <input className="field-input" placeholder="Award, publication, shipped milestone, competition result" value={achievementForm.title} onChange={v => setAchievementForm({...achievementForm, title: v.target.value})} />
              <button className="btn btn-primary" style={{alignSelf:"flex-start",padding:"10px 24px"}} onClick={() => addManual("achievement", achievementForm)} disabled={status==="loading" || !achievementForm.title.trim()}>Add Achievement</button>
            </div>
          </motion.div>
        )}

        {activeTab === "raw" && (
          <motion.div initial={{opacity:0}} animate={{opacity:1}} className="card col gap-4" style={{ padding: 24 }}>
            <div className="eyebrow">Raw Text Aggregator</div>
            <textarea className="field-input" placeholder="Paste unstructured text from LinkedIn, personal websites, or notes..." rows={16} value={rawText} onChange={v => setRawText(v.target.value)} style={{ fontSize: 14, lineHeight: 1.6 }} />
            <button className="btn btn-primary" style={{ padding: 16, fontSize: 15 }} onClick={ingestRaw} disabled={status==="loading"}>
              {status === "loading" ? "Processing..." : "Sync Raw Context"}
            </button>
          </motion.div>
        )}

        {activeTab === "linkedin" && (
          <motion.div initial={{opacity:0}} animate={{opacity:1}} className="col gap-4">
            <div
              className="card col gap-4"
              style={{ padding: "48px 32px", alignItems: "center", textAlign: "center", border: "2px dashed var(--line)", background: "var(--paper-2)", cursor: "pointer" }}
              onDragOver={e => e.preventDefault()}
              onDrop={e => {
                e.preventDefault();
                const f = e.dataTransfer.files[0];
                const lower = f?.name.toLowerCase() || "";
                if (f && (lower.endsWith(".zip") || lower.endsWith(".pdf"))) { setLinkedinFile(f); setLinkedinResult(null); }
              }}
              onClick={() => document.getElementById("linkedin-zip-in")?.click()}
            >
              <div style={{ width: 64, height: 64, borderRadius: 16, background: "var(--teal-soft)", color: "var(--teal)", display: "grid", placeItems: "center" }}><Icon name="upload" size={28} /></div>
              <div style={{ fontWeight: 600, fontSize: 18 }}>
                {linkedinFile ? linkedinFile.name : "Drop your LinkedIn export (.zip) or profile PDF here"}
              </div>
              <div style={{ fontSize: 14, color: "var(--ink-3)", maxWidth: 400, lineHeight: 1.5 }}>
                {linkedinFile ? "File ready to import." : "or click to browse"}
              </div>
              <div style={{ fontSize: 12, color: "var(--ink-4)", maxWidth: 420, lineHeight: 1.6, marginTop: 4 }}>
                Use a LinkedIn data export ZIP for structured import, or a saved LinkedIn profile PDF for quick profile extraction.
              </div>
              <input type="file" accept=".zip,.pdf,application/zip,application/pdf" id="linkedin-zip-in" style={{ display: "none" }}
                onChange={e => { const f = e.target.files?.[0]; if (f) { setLinkedinFile(f); setLinkedinResult(null); } }} />
            </div>
            <button className="btn btn-primary" style={{ padding: 16, fontSize: 15 }}
              disabled={!linkedinFile || status === "loading"}
              onClick={ingestLinkedin}>
              {status === "loading" ? "Importing..." : linkedinFile?.name.toLowerCase().endsWith(".pdf") ? "Import LinkedIn PDF" : "Import LinkedIn data"}
            </button>
            {linkedinResult?.errorMsg && (
              <div style={{ padding: 16, background: "var(--bad-soft)", color: "var(--bad)", borderRadius: 12, border: "1px solid var(--bad)", fontSize: 14 }}>
                {linkedinResult.errorMsg}
              </div>
            )}
            {linkedinResult && !linkedinResult.errorMsg && (
              <div style={{
                padding: 16,
                background: linkedinResult.status === "ok" ? "var(--green-soft)" : "var(--paper-3)",
                color: linkedinResult.status === "ok" ? "var(--green-ink)" : "var(--ink-2)",
                borderRadius: 12,
                border: `1px solid ${linkedinResult.status === "ok" ? "var(--green)" : "var(--line)"}`,
              }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>
                  Imported: {linkedinResult.stats?.skills ?? 0} skills - {linkedinResult.stats?.experience ?? 0} jobs - {linkedinResult.stats?.projects ?? 0} projects - {linkedinResult.stats?.certifications ?? 0} certifications
                </div>
                {linkedinResult.source === "pdf" && (
                  <div style={{ fontSize: 13, marginTop: 4, color: "var(--ink-3)" }}>Parsed as a profile PDF and synced into your Identity Graph.</div>
                )}
                {linkedinResult.status === "partial" && (
                  <div style={{ fontSize: 13, marginTop: 4, color: "var(--ink-3)" }}>Some items could not be imported.</div>
                )}
              </div>
            )}
          </motion.div>
        )}

        {activeTab === "github" && (
          <motion.div initial={{opacity:0}} animate={{opacity:1}} className="col gap-4">
            <div className="card col gap-4" style={{ padding: 24 }}>
              <h3 style={{ fontSize: 16, fontWeight: 600 }}>GitHub username</h3>
              <input className="field-input" placeholder="e.g. torvalds" value={githubUsername}
                onChange={e => setGithubUsername(e.target.value)} />
              <button className="btn btn-ghost" style={{ alignSelf: "flex-start", fontSize: 13, padding: "6px 12px" }}
                onClick={() => setShowToken(t => !t)}>
                {showToken ? "- Hide token" : "+ Add GitHub token for higher rate limits"}
              </button>
              {showToken && (
                <div className="col gap-2">
                  <input className="field-input" type="password" placeholder="ghp_..." value={githubToken}
                    onChange={e => setGithubToken(e.target.value)} />
                  <div style={{ fontSize: 12, color: "var(--ink-4)", lineHeight: 1.5 }}>
                    Optional: increases API rate limit from 60 to 5,000 req/hr. Never stored remotely.
                  </div>
                </div>
              )}
              <div className="row gap-3" style={{ alignItems: "center" }}>
                <span style={{ fontSize: 14, color: "var(--ink-2)" }}>Max repos to scan:</span>
                <input className="field-input" type="number" min={1} max={500} value={githubMaxRepos}
                  style={{ width: 80 }}
                  onChange={e => setGithubMaxRepos(Math.max(1, Math.min(500, parseInt(e.target.value) || 100)))} />
              </div>
            </div>
            <button className="btn btn-primary" style={{ padding: 16, fontSize: 15 }}
              disabled={!githubUsername.trim() || status === "loading"}
              onClick={ingestGithub}>
              {status === "loading" ? "Fetching repos, READMEs, languages, and manifests..." : "Scan GitHub profile"}
            </button>
            {githubResult && !githubResult.errorMsg && (
              <div className="card col gap-3" style={{ padding: 24 }}>
                <div className="row gap-3" style={{ alignItems: "center" }}>
                  {githubResult.github_user?.avatar
                    ? <img src={githubResult.github_user.avatar} alt="avatar" style={{ width: 48, height: 48, borderRadius: "50%", objectFit: "cover" }} />
                    : <div style={{ width: 48, height: 48, borderRadius: "50%", background: "var(--teal-soft)", color: "var(--teal)", display: "grid", placeItems: "center", fontWeight: 700, fontSize: 18, flexShrink: 0 }}>
                        {(githubResult.github_user?.login?.[0] ?? "?").toUpperCase()}
                      </div>
                  }
                  <div>
                    <div style={{ fontWeight: 600 }}>@{githubResult.github_user?.login}</div>
                    {githubResult.github_user?.bio && (
                      <div style={{ fontSize: 13, color: "var(--ink-3)", marginTop: 2 }}>{githubResult.github_user.bio}</div>
                    )}
                  </div>
                </div>
                <div style={{ fontSize: 14, color: "var(--ink-2)" }}>
                  Found {githubResult.stats?.repos_fetched ?? 0} repos - Enriched {githubResult.stats?.repos_enriched ?? 0} - Extracted {githubResult.stats?.projects_extracted ?? 0} projects - {githubResult.stats?.skills_extracted ?? 0} skills
                </div>
                <div style={{ fontSize: 12, color: "var(--ink-4)", lineHeight: 1.5 }}>
                  Read {githubResult.stats?.readmes_read ?? 0} READMEs, {githubResult.stats?.languages_read ?? 0} language maps, and {githubResult.stats?.manifests_read ?? 0} manifest files.
                </div>
                {githubResult.errors?.length > 0 && (
                  <div style={{ fontSize: 13, color: "var(--ink-4)", lineHeight: 1.5 }}>{githubResult.errors[0]}</div>
                )}
              </div>
            )}
            {githubResult?.errorMsg && (
              <div style={{ padding: 16, background: "var(--bad-soft)", color: "var(--bad)", borderRadius: 12, border: "1px solid var(--bad)", fontSize: 14 }}>
                {githubResult.errorMsg}
              </div>
            )}
          </motion.div>
        )}

        {activeTab === "portfolio" && (
          <motion.div initial={{opacity:0}} animate={{opacity:1}} className="col gap-4">
            <div className="card col gap-4" style={{ padding: 24 }}>
              <h3 style={{ fontSize: 16, fontWeight: 600 }}>Your portfolio / personal site URL</h3>
              <input className="field-input" placeholder="https://yoursite.com" value={portfolioUrl}
                onChange={e => { setPortfolioUrl(e.target.value); setPortfolioResult(null); }} />
              <button className="btn btn-primary" style={{ alignSelf: "flex-start", padding: "10px 24px" }}
                disabled={!portfolioUrl.trim() || status === "loading"}
                onClick={() => scanPortfolio(false)}>
                {status === "loading" ? "Fetching and reading your site..." : "Scan portfolio"}
              </button>
            </div>
            {portfolioResult?.errorMsg && (
              <div style={{ padding: 16, background: "var(--bad-soft)", color: "var(--bad)", borderRadius: 12, border: "1px solid var(--bad)", fontSize: 14 }}>
                {portfolioResult.errorMsg}
              </div>
            )}
            {portfolioResult && !portfolioResult.errorMsg && (
              <div className="card col gap-3" style={{ padding: 24 }}>
                {portfolioResult.screenshot_b64 && (
                  <img src={`data:image/png;base64,${portfolioResult.screenshot_b64}`} alt="Portfolio screenshot" style={{ maxHeight: 160, width: "100%", objectFit: "cover", borderRadius: 8, border: "1px solid var(--line)" }} />
                )}
                {portfolioResult.candidate ? (
                  <>
                    <div style={{ fontSize: 14, color: "var(--ink-2)" }}>
                      Scanned {portfolioResult.stats?.pages_scanned ?? 0} pages - Structured {portfolioResult.stats?.skills ?? 0} skills - {portfolioResult.stats?.projects ?? 0} projects
                    </div>
                    <div style={{ fontSize: 12, color: "var(--ink-4)", lineHeight: 1.5 }}>
                      Read {portfolioResult.stats?.links_seen ?? 0} links and preserved raw evidence{portfolioResult.stats?.llm_used ? " with LLM cleanup." : " with deterministic cleanup."}
                    </div>
                    <div style={{ maxHeight: 360, overflowY: "auto", border: "1px solid var(--line)", borderRadius: 8, padding: 14, background: "var(--paper-2)" }}>
                      {portfolioResult.candidate?.summary && (
                        <div style={{ marginBottom: 14 }}>
                          <div className="eyebrow" style={{ marginBottom: 6 }}>Summary</div>
                          <div style={{ fontSize: 13.5, color: "var(--ink-2)", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{portfolioResult.candidate.summary}</div>
                        </div>
                      )}
                      {(portfolioResult.skills || []).length > 0 && (
                        <div style={{ marginBottom: 14 }}>
                          <div className="eyebrow" style={{ marginBottom: 8 }}>Skills</div>
                          <div className="row gap-1" style={{ flexWrap: "wrap" }}>
                            {portfolioResult.skills.map((skill: any, idx: number) => (
                              <span key={`${skill.name || skill.n}-${idx}`} className="pill" style={{ fontSize: 11 }}>{skill.name || skill.n}</span>
                            ))}
                          </div>
                        </div>
                      )}
                      {(portfolioResult.projects || []).length > 0 && (
                        <div>
                          <div className="eyebrow" style={{ marginBottom: 8 }}>Projects</div>
                          <div className="col gap-2">
                            {portfolioResult.projects.map((project: any, idx: number) => (
                              <div key={`${project.title}-${idx}`} style={{ padding: 12, border: "1px solid var(--line)", borderRadius: 8, background: "var(--paper)" }}>
                                <div style={{ fontWeight: 650, marginBottom: 4 }}>{project.title}</div>
                                {project.stack && <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 6 }}>{project.stack}</div>}
                                {project.impact && <div style={{ fontSize: 13, color: "var(--ink-2)", lineHeight: 1.5 }}>{project.impact}</div>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                    {portfolioResult.imported ? (
                      <div style={{ padding: 12, background: "var(--green-soft)", color: "var(--green-ink)", borderRadius: 8, border: "1px solid var(--green)", fontWeight: 600, lineHeight: 1.5 }}>
                        Imported: {portfolioResult.imported?.stats?.skills ?? 0} skills - {portfolioResult.imported?.stats?.projects ?? 0} projects - {portfolioResult.imported?.stats?.experience ?? 0} experience items
                      </div>
                    ) : (
                      <button className="btn btn-primary" style={{ alignSelf: "flex-start", padding: "10px 24px" }}
                        disabled={status === "loading"}
                        onClick={importPortfolioResult}>
                        {status === "loading" ? "Importing..." : "Import shown items to Profile"}
                      </button>
                    )}
                    {portfolioResult.importError && (
                      <div style={{ padding: 12, background: "var(--bad-soft)", color: "var(--bad)", borderRadius: 8, border: "1px solid var(--bad)", fontSize: 13 }}>
                        {portfolioResult.importError}
                      </div>
                    )}
                  </>
                ) : (
                  <div style={{ fontSize: 13, color: "var(--ink-3)", lineHeight: 1.5 }}>
                    {portfolioResult.error || "No structured data was extracted."}
                  </div>
                )}
              </div>
            )}
          </motion.div>
        )}

        {activeTab === "json-import" && (
          <motion.div initial={{opacity:0}} animate={{opacity:1}} className="col gap-4">
            <div className="card col gap-4" style={{ padding: 24 }}>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                <h3 style={{ fontSize: 16, fontWeight: 600 }}>Paste your profile JSON here</h3>
                <button className="btn btn-ghost" style={{ fontSize: 13, padding: "8px 12px", flexShrink: 0 }}
                  onClick={downloadProfileTemplate}>
                  Download template
                </button>
              </div>
              <textarea className="field-input" value={jsonText}
                onChange={e => { setJsonText(e.target.value); setJsonError(null); setJsonResult(null); }}
                placeholder={`{\n  "candidate": { "name": "..." },\n  "skills": []\n}`}
                style={{ minHeight: 220, fontSize: 13, lineHeight: 1.6, fontFamily: "var(--font-mono)" }} />
              <button className="btn btn-primary" style={{ alignSelf: "flex-start", padding: "10px 24px" }}
                disabled={!jsonText.trim() || status === "loading"}
                onClick={importProfileJson}>
                {status === "loading" ? "Importing..." : "Import profile"}
              </button>
            </div>
            {jsonError && (
              <div style={{ padding: 16, background: "var(--bad-soft)", color: "var(--bad)", borderRadius: 12, border: "1px solid var(--bad)", fontSize: 14 }}>
                {jsonError}
              </div>
            )}
            {jsonResult && (
              <div style={{
                padding: 16,
                background: jsonResult.status === "ok" ? "var(--green-soft)" : "var(--paper-3)",
                color: jsonResult.status === "ok" ? "var(--green-ink)" : "var(--ink-2)",
                borderRadius: 12,
                border: `1px solid ${jsonResult.status === "ok" ? "var(--green)" : "var(--line)"}`,
              }}>
                <div style={{ fontWeight: 600 }}>
                  Imported: {jsonResult.stats?.skills ?? 0} skills - {jsonResult.stats?.experience ?? 0} jobs - {jsonResult.stats?.projects ?? 0} projects - {jsonResult.stats?.certifications ?? 0} certifications
                </div>
                {jsonResult.status === "partial" && (
                  <div style={{ fontSize: 13, marginTop: 4, color: "var(--ink-3)" }}>Some items were skipped.</div>
                )}
              </div>
            )}
          </motion.div>
        )}

        {activeTab === "template" && (
          <motion.div initial={{opacity:0}} animate={{opacity:1}} className="col gap-4">
            <div className="card" style={{ padding: 24, background: "var(--purple-soft)", border: "1px solid var(--purple)" }}>
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>Resume Template</h3>
              <p style={{ fontSize: 13.5, color: "var(--ink-2)", lineHeight: 1.6 }}>
                Paste your preferred resume format here (plain text or Markdown). When the agent generates a tailored resume, it will follow this structure: section order, headings, and layout, and fill it in with your profile and the job requirements.
              </p>
            </div>
            <div className="card col gap-4" style={{ padding: 24 }}>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-2)" }}>Template content</span>
                {template && <span className="pill mono" style={{ fontSize: 10, background: "var(--green-soft)", color: "var(--green-ink)", border: "1px solid var(--green)" }}>Template saved</span>}
              </div>
              <textarea
                className="field-input"
                placeholder={`Paste your resume template here. For example:\n\n# [Name]\n[Contact info]\n\n## Summary\n[2-3 sentence professional summary]\n\n## Experience\n### [Role] - [Company] ([Period])\n- [Bullet points]\n\n## Projects\n### [Project Name]\n- Stack: ...\n- Impact: ...\n\n## Skills\n[Comma-separated list]`}
                rows={24}
                value={template}
                onChange={e => setTemplate(e.target.value)}
                style={{ fontSize: 13, lineHeight: 1.65, fontFamily: "var(--font-mono)" }}
              />
              <div className="row gap-3" style={{ alignItems: "center" }}>
                <button className="btn btn-primary" style={{ padding: "12px 28px", fontSize: 14 }} onClick={saveTemplate} disabled={status==="loading"}>
                  {status === "loading" ? "Saving..." : "Save Template"}
                </button>
                {template && (
                  <button className="btn btn-ghost" style={{ fontSize: 13 }} onClick={() => { setTemplate(""); }}>
                    Clear
                  </button>
                )}
                <span style={{ fontSize: 12, color: "var(--ink-4)" }}>{template.length} chars</span>
              </div>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}
