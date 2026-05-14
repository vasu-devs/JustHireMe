import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { openUrl } from "@tauri-apps/plugin-opener";
import Icon from "../../../shared/components/Icon";
import type { ApiFetch, KeywordCoverage, Lead } from "../../../types";
import { isAbortLikeError } from "../../../api/client";
import { GENERATION_TIMEOUT_MS } from "../../../api/generation";
import { cleanLeadText, getTone, leadDisplayHeading } from "../../../shared/lib/leadUtils";
import { FormReader } from "../../apply/components/FormReader";

export function ApprovalDrawer({ j: initialLead, api, onClose }: {
  j: Lead; api: ApiFetch; onClose: () => void;
}) {
  type DocKind = "resume" | "cover";
  type VersionEntry = { version: number; resume?: string; cover_letter?: string };
  const [generating, setGenerating] = useState(false);
  const [activeDoc, setActiveDoc] = useState<DocKind>("resume");
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [pdfLoadErr, setPdfLoadErr] = useState<string | null>(null);
  const [pdfPreviewAttempt, setPdfPreviewAttempt] = useState(0);
  const [generateErr, setGenerateErr] = useState<string | null>(null);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineMsg, setPipelineMsg] = useState<string | null>(null);
  const [statusBusy, setStatusBusy] = useState<string | null>(null);
  const [statusErr, setStatusErr] = useState<string | null>(null);
  const [feedbackBusy, setFeedbackBusy] = useState<string | null>(null);
  const [feedbackErr, setFeedbackErr] = useState<string | null>(null);
  const [followupBusy, setFollowupBusy] = useState<number | null>(null);
  const [versions, setVersions] = useState<VersionEntry[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [versionErr, setVersionErr] = useState<string | null>(null);
  const [generatedLead, setGeneratedLead] = useState<Lead | null>(null);
  const generateControllerRef = useRef<AbortController | null>(null);
  const pipelineControllerRef = useRef<AbortController | null>(null);
  const j = generatedLead ? { ...initialLead, ...generatedLead } : initialLead;

  useEffect(() => () => {
    generateControllerRef.current?.abort();
    pipelineControllerRef.current?.abort();
  }, []);

  const resumeReady = Boolean(j.resume_asset || j.asset);
  const coverReady = Boolean(j.cover_letter_asset);
  const currentVersion = versions[0]?.version ?? j.resume_version ?? null;
  const selectedVersionRecord = selectedVersion
    ? versions.find(v => v.version === selectedVersion)
    : null;
  const activeReady = selectedVersionRecord
    ? Boolean(activeDoc === "resume" ? selectedVersionRecord.resume : selectedVersionRecord.cover_letter)
    : activeDoc === "resume" ? resumeReady : coverReady;
  const activeDocPath = activeReady
    ? `/api/v1/leads/${j.job_id}/pdf?kind=${activeDoc === "resume" ? "resume" : "cover_letter"}${selectedVersionRecord ? `&version=${selectedVersionRecord.version}` : ""}`
    : null;
  const selectedProjects = j.selected_projects || [];
  const coverage = (j.keyword_coverage || j.source_meta?.keyword_coverage || {}) as KeywordCoverage;
  const missingTerms: string[] = Array.isArray(coverage.missing_terms) ? coverage.missing_terms : [];
  const incorporatedTerms: string[] = Array.isArray(coverage.incorporated_terms) ? coverage.incorporated_terms : [];
  const coveredTerms: string[] = Array.isArray(coverage.covered_terms) ? coverage.covered_terms : [];
  const coveragePct = typeof coverage.coverage_pct === "number" ? coverage.coverage_pct : null;
  const hasCoverage = missingTerms.length > 0 || incorporatedTerms.length > 0 || coveredTerms.length > 0;
  const qualityScore = Number(j.lead_quality_score || j.source_meta?.lead_quality_score || 0);
  const qualityReason = String(j.lead_quality_reason || j.source_meta?.lead_quality_reason || "");
  const visibleGenerateErr = generateErr && !/request\s+cancel(?:led|ed)|abort/i.test(generateErr)
    ? generateErr
    : null;
  const display = leadDisplayHeading(j);
  const originalTitle = cleanLeadText(j.title);
  const descriptionText = cleanLeadText(j.description);
  const jobDescription = [
    originalTitle && originalTitle !== display.role ? `Original listing title:\n${originalTitle}` : "",
    descriptionText ? `Description:\n${descriptionText}` : "",
  ].filter(Boolean).join("\n\n") || "No job description extracted yet.";

  const loadVersions = useCallback(async (signal?: AbortSignal) => {
    setVersionErr(null);
    try {
      const r = await api(`/api/v1/leads/${j.job_id}/versions`, { signal });
      if (!r.ok) throw new Error(`Server returned ${r.status}`);
      const items = await r.json() as VersionEntry[];
      setVersions(items);
      setSelectedVersion(prev => {
        if (prev && items.some(item => item.version === prev)) return prev;
        return items[0]?.version ?? null;
      });
    } catch (err) {
      setVersionErr(err instanceof Error ? err.message : "Version history failed to load");
    }
  }, [api, j.job_id]);

  const refreshLead = useCallback(async (signal?: AbortSignal) => {
    const r = await api(`/api/v1/leads/${initialLead.job_id}`, { signal });
    if (!r.ok) throw new Error(`Lead refresh returned ${r.status}`);
    const lead = await r.json() as Lead;
    setGeneratedLead(lead);
    return lead;
  }, [api, initialLead.job_id]);

  useEffect(() => {
    const controller = new AbortController();
    loadVersions(controller.signal);
    return () => controller.abort();
  }, [loadVersions, j.resume_asset, j.cover_letter_asset, j.resume_version]);

  // Tauri WebView blocks <iframe src="http://..."> for localhost � fetch as blob instead
  useEffect(() => {
    if (!activeDocPath) { setPdfBlobUrl(null); setPdfLoadErr(null); return; }
    let revoke: string | null = null;
    let alive = true;
    const controller = new AbortController();
    const previewTimer = window.setTimeout(() => {
      if (!alive) return;
      controller.abort();
      setPdfLoadErr("PDF preview timed out. The package exists, but the embedded preview did not respond.");
      setPdfBlobUrl(null);
    }, 12000);
    setPdfLoadErr(null);
    setPdfBlobUrl(null);
    api(activeDocPath, { signal: controller.signal, timeoutMs: 12000 })
      .then(r => { if (!r.ok) throw new Error(`Server returned ${r.status}`); return r.blob(); })
      .then(blob => {
        if (!alive) return;
        if (!blob.size) throw new Error("Generated PDF was empty");
        window.clearTimeout(previewTimer);
        const url = URL.createObjectURL(blob);
        revoke = url;
        setPdfBlobUrl(url);
      })
      .catch(err => {
        if (!alive) return;
        if (isAbortLikeError(err)) return;
        setPdfLoadErr(String(err));
        setPdfBlobUrl(null);
      });
    return () => {
      alive = false;
      window.clearTimeout(previewTimer);
      controller.abort();
      if (revoke) URL.revokeObjectURL(revoke);
    };
  }, [activeDocPath, api, pdfPreviewAttempt]);

  // Clear generating flag when the lead actually receives its generated documents.
  useEffect(() => {
    if (generating && resumeReady && coverReady) setGenerating(false);
  }, [resumeReady, coverReady, generating]);

  const generatePdf = async () => {
    if (generating || pipelineRunning) return;
    setGenerating(true);
    setGenerateErr(null);
    setPdfBlobUrl(null);
    setPdfLoadErr(null);
    setActiveDoc("resume");
    generateControllerRef.current?.abort();
    const controller = new AbortController();
    generateControllerRef.current = controller;
    try {
      const r = await api(`/api/v1/leads/${j.job_id}/generate`, { method: "POST", signal: controller.signal, timeoutMs: GENERATION_TIMEOUT_MS });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || `Server returned ${r.status}`);
      if (body.lead) setGeneratedLead(body.lead as Lead);
      await refreshLead(controller.signal).catch(() => null);
      window.dispatchEvent(new CustomEvent("leads-refresh"));
      await loadVersions();
      setPdfPreviewAttempt(n => n + 1);
    } catch (err) {
      if (controller.signal.aborted || isAbortLikeError(err)) {
        setGenerating(false);
        return;
      }
      setGenerateErr(err instanceof Error ? err.message : String(err));
      setGenerating(false);
    } finally {
      if (generateControllerRef.current === controller) generateControllerRef.current = null;
    }
  };

  const runPipeline = async () => {
    if (pipelineRunning || generating) return;
    setPipelineRunning(true);
    setPipelineMsg(null);
    pipelineControllerRef.current?.abort();
    const controller = new AbortController();
    pipelineControllerRef.current = controller;
    try {
      const r = await api(`/api/v1/leads/${j.job_id}/pipeline/run`, { method: "POST", signal: controller.signal, timeoutMs: 15000 });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || `Server returned ${r.status}`);
      setPipelineMsg("Pipeline started. You can keep working while it finishes.");
      window.setTimeout(() => {
        setPipelineRunning(false);
        setPipelineMsg(null);
        refreshLead().catch(() => null);
        window.dispatchEvent(new CustomEvent("leads-refresh"));
      }, 3000);
    } catch (err) {
      if (controller.signal.aborted || isAbortLikeError(err)) {
        setPipelineRunning(false);
        return;
      }
      setPipelineMsg(err instanceof Error ? err.message : "Pipeline failed to start");
      setPipelineRunning(false);
    } finally {
      if (pipelineControllerRef.current === controller) pipelineControllerRef.current = null;
    }
  };

  const openPdf = () => { if (pdfBlobUrl) openUrl(pdfBlobUrl); };

  const submitFeedback = async (feedback: string) => {
    setFeedbackBusy(feedback);
    setFeedbackErr(null);
    try {
      const r = await api(`/api/v1/leads/${j.job_id}/feedback`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback }),
      });
      if (!r.ok) {
        const detail = await r.json().then(d => d.detail).catch(() => "");
        throw new Error(detail || `Server returned ${r.status}`);
      }
    } catch (err) {
      setFeedbackErr(err instanceof Error ? err.message : "Feedback failed");
    } finally {
      setFeedbackBusy(null);
    }
  };

  const updateLeadStatus = async (status: string) => {
    setStatusBusy(status);
    setStatusErr(null);
    try {
      const r = await api(`/api/v1/leads/${j.job_id}/status`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!r.ok) {
        const detail = await r.json().then(d => d.detail).catch(() => "");
        throw new Error(detail || `Server returned ${r.status}`);
      }
      window.dispatchEvent(new CustomEvent("lead-updated", { detail: { job_id: j.job_id, status } }));
      window.dispatchEvent(new CustomEvent("leads-refresh"));
    } catch (err) {
      setStatusErr(err instanceof Error ? err.message : "Status update failed");
    } finally {
      setStatusBusy(null);
    }
  };

  const scheduleFollowup = async (days: number) => {
    setFollowupBusy(days);
    setFeedbackErr(null);
    try {
      const r = await api(`/api/v1/leads/${j.job_id}/followup`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ days }),
      });
      if (!r.ok) {
        const detail = await r.json().then(d => d.detail).catch(() => "");
        throw new Error(detail || `Server returned ${r.status}`);
      }
    } catch (err) {
      setFeedbackErr(err instanceof Error ? err.message : "Follow-up save failed");
    } finally {
      setFollowupBusy(null);
    }
  };

  const extractedDetails = [
    ["Tech stack", (j.tech_stack || []).join(", ")],
    ["Location", j.location || ""],
    ["Urgency", j.urgency || ""],
    ["Budget", j.budget || ""],
  ].filter(([, value]) => value);

  const draftBlock = (label: string, value?: string) => value ? (
    <div key={label} style={{ background: "var(--paper-3)", border: "1px solid var(--line)", borderRadius: 10, padding: "10px 12px" }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span className="mono" style={{ fontSize: 10, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</span>
        <button className="btn btn-ghost" style={{ fontSize: 11, padding: "3px 8px" }} onClick={() => navigator.clipboard?.writeText(value)}>Copy</button>
      </div>
      <div style={{ fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{value}</div>
    </div>
  ) : null;

  return (
    <div className="drawer-backdrop" onClick={onClose} style={{ zIndex: 100, display: "grid", placeItems: "center", padding: 12, overflow: "hidden" }}>
      <motion.div className="card"
        initial={{ opacity: 0, y: 24, scale: 0.985 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 18, scale: 0.985 }}
        transition={{ type: "spring", damping: 28, stiffness: 260 }}
        onClick={e => e.stopPropagation()}
        style={{ width: "min(1480px, calc(100vw - 24px))", height: "calc(100dvh - 24px)", maxHeight: "calc(100dvh - 24px)", display: "flex", flexDirection: "column", background: "var(--paper)", zIndex: 101, overflow: "hidden", borderRadius: 18 }}>

        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", padding: "18px 22px 16px", borderBottom: "1px solid var(--line)", flexShrink: 0, gap: 16, background: "var(--paper)", flexWrap: "wrap" }}>
          <div style={{ minWidth: 0 }}>
            <div className="row gap-2" style={{ marginBottom: 7, flexWrap: "wrap" }}>
              <span className="pill" style={{ background: `var(--${getTone(j.status)})`, color: `var(--${getTone(j.status)}-ink)` }}>{j.status}</span>
              <span className="pill mono" style={{ background: "var(--paper-3)", color: "var(--ink-3)" }}>{j.platform}</span>
              {j.budget && <span className="pill mono" style={{ background: "var(--green-soft)", color: "var(--green-ink)", border: "1px solid var(--green)" }}>{j.budget}</span>}
              {(j.signal_score || 0) > 0 && <span className="pill mono" style={{ background: (j.signal_score || 0) >= 80 ? "var(--orange-soft)" : "var(--yellow-soft)", color: (j.signal_score || 0) >= 80 ? "var(--orange-ink)" : "var(--yellow-ink)", border: `1px solid ${(j.signal_score || 0) >= 80 ? "var(--orange)" : "var(--yellow)"}` }}>Lead signal {j.signal_score}</span>}
              {!!j.learning_delta && <span className="pill mono" style={{ background: j.learning_delta > 0 ? "var(--green-soft)" : "var(--bad-soft)", color: j.learning_delta > 0 ? "var(--green-ink)" : "var(--bad)", border: `1px solid ${j.learning_delta > 0 ? "var(--green)" : "var(--bad)"}` }}>Learning {j.learning_delta > 0 ? "+" : ""}{j.learning_delta}</span>}
              {j.feedback && <span className="pill mono" style={{ background: "var(--blue-soft)", color: "var(--blue-ink)", border: "1px solid var(--blue)" }}>{j.feedback.replace(/_/g, " ")}</span>}
              {j.score > 0 && <span className="pill mono" style={{ background: j.score >= 85 ? "var(--green-soft)" : j.score >= 60 ? "var(--yellow-soft)" : "var(--bad-soft)", color: j.score >= 85 ? "var(--green-ink)" : j.score >= 60 ? "var(--yellow-ink)" : "var(--bad)" }}>{j.score}/100 match</span>}
            </div>
            <h2 style={{ fontSize: 26, fontWeight: 600, overflowWrap: "anywhere" }}>
              {display.role} <span style={{ color: "var(--ink-3)", fontWeight: 700 }}>||</span> {display.company}
            </h2>
            <p style={{ color: "var(--ink-3)", fontSize: 13, marginTop: 2 }}>{j.platform}</p>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
            <button
              onClick={() => openUrl(j.url)}
              title="Open original job posting"
              className="btn"
              style={{ fontSize: 12, borderColor: "var(--teal)", background: "var(--teal-soft)", color: "var(--teal)" }}
            >
              <Icon name="external-link" size={12} color="var(--teal)" /> View Posting
            </button>
            <button className="btn btn-icon" onClick={onClose}><Icon name="x" size={15} /></button>
          </div>
        </div>

        <div className="approval-modal-grid" style={{ flex: 1, overflow: "hidden", display: "grid", minHeight: 0 }}>
          {/* Left: PDF */}
          <div className="approval-doc-pane" style={{ padding: 18, borderRight: "1px solid var(--line)", display: "flex", flexDirection: "column", gap: 12, minHeight: 0, overflowY: "auto", overflowX: "hidden" }}>
            <div className="row" style={{ justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <div>
                <div className="eyebrow">Application Package</div>
                <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 3 }}>Resume and cover letter are generated separately for this role.</div>
              </div>
              <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                {pdfBlobUrl && (
                  <button onClick={openPdf} title="Open PDF in system viewer" style={{
                    display: "flex", alignItems: "center", gap: 5,
                    padding: "5px 12px", borderRadius: 8, fontSize: 11, fontWeight: 700,
                    border: "1px solid var(--teal)", background: "var(--teal-soft)", color: "var(--teal)", cursor: "pointer",
                  }}>
                    <Icon name="download" size={12} color="var(--teal)" /> Open PDF
                  </button>
                )}
                <button onClick={generatePdf} disabled={generating || pipelineRunning} style={{
                  padding: "5px 12px", borderRadius: 8, fontSize: 11, fontWeight: 700,
                  border: "1px solid var(--purple)", background: "var(--purple-soft)", color: "var(--purple-ink)", cursor: generating ? "wait" : pipelineRunning ? "not-allowed" : "pointer",
                }}>{generating ? "Generating..." : resumeReady || coverReady ? "Regenerate Package" : "Generate Package"}</button>
                <button onClick={runPipeline} disabled={pipelineRunning || generating} style={{
                  padding: "5px 12px", borderRadius: 8, fontSize: 11, fontWeight: 700,
                  border: "1px solid var(--blue)", background: "var(--blue-soft)", color: "var(--blue-ink)", cursor: pipelineRunning ? "wait" : generating ? "not-allowed" : "pointer",
                }}>{pipelineRunning ? "Pipeline running..." : "Run full pipeline"}</button>
              </div>
            </div>
            {pipelineMsg && <div style={{ color: pipelineMsg.includes("failed") || pipelineMsg.includes("Server") ? "var(--bad)" : "var(--blue-ink)", fontSize: 12 }}>{pipelineMsg}</div>}
            <div className="row gap-2" style={{ background: "var(--paper-3)", padding: 5, borderRadius: 10, flexShrink: 0 }}>
              {[
                ["resume", "Resume", resumeReady],
                ["cover", "Cover Letter", coverReady],
              ].map(([kind, label, ready]) => (
                <button key={kind as string} onClick={() => setActiveDoc(kind as DocKind)} style={{
                  flex: 1, padding: "8px 10px", borderRadius: 7, border: "none", cursor: "pointer",
                  background: activeDoc === kind ? "var(--card)" : "transparent",
                  color: activeDoc === kind ? "var(--ink)" : "var(--ink-3)",
                  fontSize: 12, fontWeight: 700, boxShadow: activeDoc === kind ? "var(--shadow-xs)" : "none",
                  display: "flex", justifyContent: "center", alignItems: "center", gap: 7,
                }}>
                  {label}
                  <span className="dot" style={{ color: ready ? "var(--ok)" : "var(--ink-4)" }} />
                </button>
              ))}
            </div>
            {versions.length > 1 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                <div className="eyebrow">Version history</div>
                <select
                  className="field-input"
                  value={selectedVersion ?? ""}
                  onChange={e => setSelectedVersion(Number(e.target.value))}
                  style={{ fontSize: 12, padding: "8px 10px" }}
                >
                  {versions.map(version => (
                    <option key={version.version} value={version.version}>
                      v{version.version}{version.version === currentVersion ? " (current)" : ""}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {versionErr && <div style={{ color: "var(--bad)", fontSize: 12 }}>{versionErr}</div>}
            {selectedProjects.length > 0 && (
              <div className="row gap-2" style={{ flexWrap: "wrap" }}>
                <span className="eyebrow" style={{ marginRight: 2 }}>Projects used</span>
                {selectedProjects.map((p, i) => (
                  <span key={i} className="pill" style={{ background: "var(--green-soft)", color: "var(--green-ink)", border: "1px solid var(--green)" }}>{p}</span>
                ))}
              </div>
            )}
            {hasCoverage && (
              <div style={{ background: "var(--blue-soft)", border: "1px solid var(--blue)", borderRadius: 10, padding: "10px 12px" }}>
                <div className="row" style={{ justifyContent: "space-between", gap: 10, alignItems: "center", marginBottom: 7 }}>
                  <span className="eyebrow" style={{ color: "var(--blue-ink)" }}>Coverage</span>
                  {coveragePct !== null && <span className="mono" style={{ fontSize: 11, fontWeight: 800, color: "var(--blue-ink)" }}>{coveragePct}% JD keywords</span>}
                </div>
                <div style={{ fontSize: 12.3, color: "var(--ink-2)", lineHeight: 1.5 }}>
                  {missingTerms.length > 0
                    ? <>You're missing these terms from the JD: <b>{missingTerms.slice(0, 6).join(", ")}</b>. We've incorporated the supported matches where applicable.</>
                    : <>Strong keyword coverage. We've incorporated supported JD terms where they fit the profile.</>
                  }
                </div>
                {incorporatedTerms.length > 0 && (
                  <div className="row gap-2" style={{ flexWrap: "wrap", marginTop: 8 }}>
                    <span className="eyebrow" style={{ marginRight: 2 }}>In resume</span>
                    {incorporatedTerms.slice(0, 8).map((term, i) => (
                      <span key={i} className="pill" style={{ background: "var(--paper)", color: "var(--blue-ink)", border: "1px solid var(--blue)" }}>{term}</span>
                    ))}
                  </div>
                )}
              </div>
            )}
            {visibleGenerateErr && <div style={{ color: "var(--bad)", fontSize: 12, padding: "8px 10px", background: "var(--bad-soft)", border: "1px solid var(--bad)", borderRadius: 8 }}>{visibleGenerateErr}</div>}
            <div style={{ flex: "0 0 clamp(680px, 82vh, 980px)", minHeight: 560, background: "var(--card)", border: "1px solid var(--line)", borderRadius: 12, overflow: "hidden" }}>
              {activeReady && pdfBlobUrl && (
                <iframe
                  key={pdfBlobUrl}
                  src={pdfBlobUrl}
                  title={activeDoc === "resume" ? "Resume" : "Cover Letter"}
                  width="100%"
                  style={{ height: "100%", border: "none", display: "block" }}
                />
              )}
              {generating && !pdfBlobUrl && (
                <div style={{ height: "100%", minHeight: 420, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, color: "var(--ink-3)", fontSize: 12, padding: 24, textAlign: "center" }}>
                  <div className="mono pulse">Tailoring resume and cover letter for {j.company}...</div>
                  <div style={{ maxWidth: 360, lineHeight: 1.5 }}>The generator is choosing the strongest profile projects for this job description.</div>
                </div>
              )}
              {!generating && activeReady && !pdfBlobUrl && (
                <div style={{ height: "100%", minHeight: 420, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, color: "var(--ink-3)", fontSize: 12, padding: 24, textAlign: "center" }}>
                  {pdfLoadErr ? (
                    <>
                      <div style={{ color: "var(--bad)", maxWidth: 460, lineHeight: 1.5 }}>Failed to load PDF preview: {pdfLoadErr}</div>
                      <button
                        onClick={() => setPdfPreviewAttempt(n => n + 1)}
                        style={{ padding: "8px 18px", borderRadius: 8, fontSize: 12, fontWeight: 700, border: "1px solid var(--blue)", background: "var(--blue-soft)", color: "var(--blue-ink)", cursor: "pointer" }}
                      >
                        Retry preview
                      </button>
                    </>
                  ) : (
                    <>
                      <div>Loading {activeDoc === "resume" ? "resume" : "cover letter"}...</div>
                      <div className="mono" style={{ fontSize: 10.5, color: "var(--ink-4)" }}>Preview will time out automatically if the backend does not respond.</div>
                    </>
                  )}
                </div>
              )}
              {!generating && !activeReady && (
                <div style={{ height: "100%", minHeight: 420, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, color: "var(--ink-3)", fontSize: 12, padding: 24, textAlign: "center" }}>
                  <Icon name="file" size={26} color="var(--ink-4)" />
                  <div style={{ fontWeight: 700, color: "var(--ink-2)" }}>
                    No tailored {activeDoc === "resume" ? "resume" : "cover letter"} yet.
                  </div>
                  <div style={{ maxWidth: 380, lineHeight: 1.5 }}>
                    Generate the application package to create separate PDFs using the job description, company context, and best-matching projects.
                  </div>
                  <button onClick={generatePdf} disabled={generating || pipelineRunning} style={{ padding: "8px 18px", borderRadius: 8, fontSize: 12, fontWeight: 700, border: "1px solid var(--purple)", background: "var(--purple-soft)", color: "var(--purple-ink)", cursor: generating ? "wait" : pipelineRunning ? "not-allowed" : "pointer" }}>
                    Generate Package
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Right: Score + actions */}
          <div className="approval-detail-pane" style={{ display: "flex", flexDirection: "column", minHeight: 0, background: "var(--paper)" }}>
            <div style={{ padding: 22, display: "flex", flexDirection: "column", gap: 14, overflowY: "auto", minHeight: 0, flex: 1 }}>
            <div>
              <div className="eyebrow" style={{ marginBottom: 6 }}>Job Description</div>
              <div style={{ fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.6, background: "var(--paper-3)", borderRadius: 8, padding: "10px 12px", border: "1px solid var(--line)", whiteSpace: "pre-wrap" }}>
                {jobDescription}
              </div>
            </div>

            {extractedDetails.length > 0 && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Extracted Details</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 8 }}>
                  {extractedDetails.map(([label, value]) => (
                    <div key={label} style={{ background: "var(--paper-3)", border: "1px solid var(--line)", borderRadius: 9, padding: "9px 10px", minWidth: 0 }}>
                      <div className="mono" style={{ fontSize: 9.5, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>{label}</div>
                      <div style={{ fontSize: 12.5, color: "var(--ink-2)", overflowWrap: "anywhere" }}>{value}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="eyebrow">Match Reasoning</div>

            {(j.signal_score || j.signal_reason || (j.signal_tags?.length ?? 0) > 0) && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Lead Signal</div>
                <div style={{ background: "var(--orange-soft)", border: "1px solid var(--orange)", borderRadius: 10, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
                  <div className="row" style={{ justifyContent: "space-between", alignItems: "center", gap: 10 }}>
                    <span style={{ fontSize: 12.5, color: "var(--orange-ink)", fontWeight: 700 }}>Signal score</span>
                    <span className="mono" style={{ fontSize: 13, fontWeight: 800, color: "var(--orange-ink)" }}>{j.signal_score || 0}/100</span>
                  </div>
                  {!!j.learning_delta && (
                    <div style={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 8, padding: "8px 10px" }}>
                      <div className="row" style={{ justifyContent: "space-between", gap: 10, alignItems: "center" }}>
                        <span className="mono" style={{ fontSize: 10, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Feedback learning</span>
                        <span className="mono" style={{ fontSize: 12, fontWeight: 800, color: j.learning_delta > 0 ? "var(--green-ink)" : "var(--bad)" }}>
                          {(j.base_signal_score ?? 0) || ((j.signal_score || 0) - j.learning_delta)} {j.learning_delta > 0 ? "+" : ""}{j.learning_delta}
                        </span>
                      </div>
                      {j.learning_reason && <div style={{ marginTop: 5, fontSize: 12.2, color: "var(--ink-2)", lineHeight: 1.45 }}>{j.learning_reason}</div>}
                    </div>
                  )}
                  {j.signal_reason && <div style={{ fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.55 }}>{j.signal_reason}</div>}
                  {(j.signal_tags?.length ?? 0) > 0 && (
                    <div className="row gap-2" style={{ flexWrap: "wrap" }}>
                      {j.signal_tags!.slice(0, 8).map(tag => (
                        <span key={tag} className="pill mono" style={{ fontSize: 9, background: "var(--paper)", color: "var(--ink-3)", border: "1px solid var(--line)" }}>{tag}</span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {((j.fit_bullets?.length ?? 0) > 0 || j.proof_snippet) && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Proof Pack</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {(j.fit_bullets?.length ?? 0) > 0 && (
                    <div style={{ background: "var(--green-soft)", border: "1px solid var(--green)", borderRadius: 10, padding: "10px 12px" }}>
                      <div className="mono" style={{ fontSize: 10, color: "var(--green-ink)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Why I fit</div>
                      <div className="col gap-1">
                        {j.fit_bullets!.map((bullet, idx) => (
                          <div key={idx} style={{ fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.45 }}>{bullet}</div>
                        ))}
                      </div>
                    </div>
                  )}
                  {j.proof_snippet && draftBlock("Proof snippet", j.proof_snippet)}
                </div>
              </div>
            )}

            {(j.outreach_reply || j.outreach_dm || j.outreach_email || j.proposal_draft) && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Outreach Messages</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {j.outreach_reply && (
                    <div style={{ background: "var(--purple-soft)", border: "1px solid var(--purple)", borderRadius: 10, padding: "10px 12px" }}>
                      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                        <span className="mono" style={{ fontSize: 10, color: "var(--purple-ink)", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700 }}>3-Line Founder Message</span>
                        <button className="btn btn-ghost" style={{ fontSize: 11, padding: "3px 8px" }} onClick={() => navigator.clipboard?.writeText(j.outreach_reply!)}>Copy</button>
                      </div>
                      <div style={{ fontSize: 13, color: "var(--ink)", lineHeight: 1.65, whiteSpace: "pre-wrap", fontWeight: 500 }}>{j.outreach_reply}</div>
                    </div>
                  )}
                  {draftBlock("LinkedIn Note", j.outreach_dm)}
                  {draftBlock("Cold Email", j.outreach_email)}
                  {draftBlock("Proposal", j.proposal_draft)}
                </div>
              </div>
            )}

            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Lead Feedback</div>
              <div className="row gap-2" style={{ flexWrap: "wrap" }}>
                {[
                  ["relevant", "Relevant"],
                  ["not_relevant", "Not Relevant"],
                  ["duplicate", "Duplicate"],
                  ["low_quality", "Low Quality"],
                  ["incorrect_category", "Incorrect Category"],
                  ["already_contacted", "Contacted"],
                ].map(([id, label]) => {
                  const active = j.feedback === id;
                  return (
                    <button key={id} onClick={() => submitFeedback(id)} disabled={feedbackBusy === id} style={{
                      padding: "5px 10px", borderRadius: 8, fontSize: 11.5, fontWeight: 700, cursor: feedbackBusy === id ? "wait" : "pointer",
                      border: `1px solid ${active ? "var(--blue)" : "var(--line)"}`,
                      background: active ? "var(--blue-soft)" : "var(--paper-3)",
                      color: active ? "var(--blue-ink)" : "var(--ink-2)",
                    }}>{feedbackBusy === id ? "Saving..." : label}</button>
                  );
                })}
              </div>
              {feedbackErr && <div style={{ marginTop: 6, color: "var(--bad)", fontSize: 11.5 }}>{feedbackErr}</div>}
            </div>

            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Follow-up</div>
              <div className="row gap-2" style={{ flexWrap: "wrap" }}>
                {[2, 5, 10].map(days => (
                  <button key={days} onClick={() => scheduleFollowup(days)} disabled={followupBusy === days} style={{
                    padding: "5px 10px", borderRadius: 8, fontSize: 11.5, fontWeight: 700, cursor: followupBusy === days ? "wait" : "pointer",
                    border: "1px solid var(--green)", background: "var(--green-soft)", color: "var(--green-ink)",
                  }}>{followupBusy === days ? "Saving..." : `${days} days`}</button>
                ))}
              </div>
              {j.followup_due_at && <div className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)", marginTop: 6 }}>Due {j.followup_due_at}</div>}
              {(j.followup_sequence?.length ?? 0) > 0 && (
                <div style={{ marginTop: 8, background: "var(--paper-3)", border: "1px solid var(--line)", borderRadius: 10, padding: "9px 11px" }}>
                  <div className="mono" style={{ fontSize: 10, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Suggested sequence</div>
                  <div className="col gap-1">
                    {j.followup_sequence!.map((step, idx) => (
                      <div key={idx} style={{ fontSize: 12.2, color: "var(--ink-2)", lineHeight: 1.45 }}>{step}</div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Score bar */}
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Match Score</span>
                <span style={{
                  fontSize: 13, fontWeight: 700,
                  color:       j.score >= 85 ? "var(--green-ink)" : j.score >= 60 ? "var(--yellow-ink)" : "var(--bad)",
                  background:  j.score >= 85 ? "var(--green-soft)" : j.score >= 60 ? "var(--yellow-soft)" : "var(--bad-soft)",
                  padding: "2px 10px", borderRadius: 999,
                }}>{j.score ?? 0}/100</span>
              </div>
              <div style={{ height: 6, background: "var(--paper-3)", borderRadius: 999, marginBottom: 16 }}>
                <div style={{ height: "100%", borderRadius: 999, width: `${Math.min(100, j.score ?? 0)}%`, background: j.score >= 85 ? "var(--green)" : j.score >= 60 ? "var(--yellow)" : "var(--bad)", transition: "width 0.4s ease" }} />
              </div>
            </div>

            {j.reason && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Evaluator Reasoning</div>
                <div style={{ fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.6, background: "var(--paper)", borderRadius: 10, padding: "10px 12px", border: "1px solid var(--line)" }}>{j.reason}</div>
              </div>
            )}

            {qualityReason && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Why This Lead Was Shown</div>
                <div style={{ fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.6, background: "var(--blue-soft)", borderRadius: 10, padding: "10px 12px", border: "1px solid var(--blue)" }}>
                  {qualityScore ? `Quality ${qualityScore}: ` : ""}{qualityReason}
                </div>
              </div>
            )}

            {j.match_points?.length > 0 && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Match Points</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {j.match_points.map((pt, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12, color: "var(--ink-2)" }}>
                      <Icon name="check" size={13} color="var(--ok)" style={{ flexShrink: 0, marginTop: 2 }} />
                      <span style={{ lineHeight: 1.5 }}>{pt}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {j.gaps && j.gaps.length > 0 && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Skill Gaps</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {j.gaps.map((g, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12, color: "var(--ink-2)" }}>
                      <Icon name="alert-circle" size={13} color="var(--bad)" style={{ flexShrink: 0, marginTop: 2 }} />
                      <span style={{ lineHeight: 1.5 }}>{g}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <FormReader
              jobId={j.job_id}
              defaultUrl={j.url}
              api={api}
            />

            </div>
            <div style={{ textAlign: "center", padding: 16, borderTop: "1px solid var(--line)", background: "var(--paper)", flexShrink: 0 }}>
              <button
                className={`btn ${j.status === "applied" ? "btn-applied-done" : "btn-apply-action"}`}
                onClick={() => updateLeadStatus("applied")}
                disabled={statusBusy === "applied" || j.status === "applied"}
                style={{
                  fontSize: 15,
                  padding: "12px 24px",
                  width: "100%",
                  cursor: statusBusy === "applied" ? "wait" : j.status === "applied" ? "default" : "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                }}
              >
                <Icon name="check" size={15} color="#fff" />
                {statusBusy === "applied" ? "Saving..." : j.status === "applied" ? "Marked as applied" : "Mark as applied"}
              </button>
              {statusErr ? (
                <div style={{ marginTop: 8, fontSize: 11.5, color: "var(--bad)", lineHeight: 1.45 }}>
                  {statusErr}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
