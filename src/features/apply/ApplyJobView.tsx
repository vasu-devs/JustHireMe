import { useEffect, useRef, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import Icon from "../../shared/components/Icon";
import type { ApiFetch, ContactLookup, KeywordCoverage, Lead } from "../../types";
import { roleFromLead } from "../../shared/lib/leadUtils";

const CUSTOMIZE_START_TIMEOUT_MS = 10000;
const CUSTOMIZE_WATCHDOG_MS = 12000;

function withDeadline<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeoutId = window.setTimeout(() => reject(new Error(message)), timeoutMs);
    promise.then(
      value => {
        window.clearTimeout(timeoutId);
        resolve(value);
      },
      error => {
        window.clearTimeout(timeoutId);
        reject(error);
      },
    );
  });
}

export function ApplyJobView({ port, api, leads, openDrawer, initialInput, autoFocus }: { port: number | null; api: ApiFetch | null; leads: Lead[]; openDrawer: (l: Lead) => void; initialInput?: string; autoFocus?: boolean }) {
  const [input, setInput] = useState("");
  const initialApplied = useRef(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const submitControllerRef = useRef<AbortController | null>(null);
  const submitRunRef = useRef(0);
  const mountedRef = useRef(true);
  const [lead, setLead] = useState<Lead | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [resumeBlobUrl, setResumeBlobUrl] = useState<string | null>(null);
  const [coverBlobUrl, setCoverBlobUrl] = useState<string | null>(null);
  const [resumeLoadErr, setResumeLoadErr] = useState<string | null>(null);
  const [coverLoadErr, setCoverLoadErr] = useState<string | null>(null);

  const liveLead = lead ? (leads.find(l => l.job_id === lead.job_id) || lead) : null;
  const resumeReady = Boolean(liveLead?.resume_asset || liveLead?.asset);
  const coverReady = Boolean(liveLead?.cover_letter_asset);
  const generating = Boolean(liveLead && (!resumeReady || !coverReady) && (liveLead.status === "tailoring" || liveLead.status === "approved"));
  const resumeDocPath = liveLead && resumeReady ? `/api/v1/leads/${liveLead.job_id}/pdf?kind=resume` : null;
  const coverDocPath = liveLead && coverReady ? `/api/v1/leads/${liveLead.job_id}/pdf?kind=cover_letter` : null;
  const coverage = (liveLead?.keyword_coverage || liveLead?.source_meta?.keyword_coverage || {}) as KeywordCoverage;
  const contactLookup = (liveLead?.contact_lookup || liveLead?.source_meta?.contact_lookup || {}) as ContactLookup;
  const primaryContact = contactLookup.primary_contact;
  const missingTerms: string[] = Array.isArray(coverage.missing_terms) ? coverage.missing_terms : [];
  const incorporatedTerms: string[] = Array.isArray(coverage.incorporated_terms) ? coverage.incorporated_terms : [];
  const coveragePct = typeof coverage.coverage_pct === "number" ? coverage.coverage_pct : null;

  useEffect(() => {
    if (initialInput && !initialApplied.current) {
      initialApplied.current = true;
      setInput(initialInput);
    }
  }, [initialInput]);

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus();
  }, [autoFocus]);

  useEffect(() => () => {
    mountedRef.current = false;
    submitControllerRef.current?.abort();
  }, []);

  useEffect(() => {
    if (!lead?.job_id) return;
    const onLeadUpdated = (event: Event) => {
      const updated = (event as CustomEvent<Lead>).detail;
      if (updated?.job_id === lead.job_id) setLead(updated);
    };
    window.addEventListener("lead-updated", onLeadUpdated);
    return () => window.removeEventListener("lead-updated", onLeadUpdated);
  }, [lead?.job_id]);

  useEffect(() => {
    if (!resumeDocPath || !api) { setResumeBlobUrl(null); setResumeLoadErr(null); return; }
    let revoke: string | null = null;
    let alive = true;
    const controller = new AbortController();
    setResumeLoadErr(null);
    setResumeBlobUrl(null);
    api(resumeDocPath, { signal: controller.signal })
      .then(r => {
        if (!r.ok) throw new Error("Resume PDF not ready");
        return r.blob();
      })
      .then(blob => {
        if (!alive) return;
        revoke = URL.createObjectURL(blob);
        setResumeBlobUrl(revoke);
      })
      .catch(e => alive && setResumeLoadErr(e instanceof Error ? e.message : "Resume failed to load"));
    return () => {
      alive = false;
      controller.abort();
      if (revoke) URL.revokeObjectURL(revoke);
    };
  }, [resumeDocPath, api]);

  useEffect(() => {
    if (!coverDocPath || !api) { setCoverBlobUrl(null); setCoverLoadErr(null); return; }
    let revoke: string | null = null;
    let alive = true;
    const controller = new AbortController();
    setCoverLoadErr(null);
    setCoverBlobUrl(null);
    api(coverDocPath, { signal: controller.signal })
      .then(r => {
        if (!r.ok) throw new Error("Cover letter PDF not ready");
        return r.blob();
      })
      .then(blob => {
        if (!alive) return;
        revoke = URL.createObjectURL(blob);
        setCoverBlobUrl(revoke);
      })
      .catch(e => alive && setCoverLoadErr(e instanceof Error ? e.message : "Cover letter failed to load"));
    return () => {
      alive = false;
      controller.abort();
      if (revoke) URL.revokeObjectURL(revoke);
    };
  }, [coverDocPath, api]);

  useEffect(() => {
    if (busy && resumeReady && coverReady) setBusy(false);
  }, [busy, resumeReady, coverReady]);

  useEffect(() => {
    if (!api || !lead?.job_id || !generating || (resumeReady && coverReady)) return;
    let alive = true;
    const timer = window.setInterval(async () => {
      try {
        const res = await api(`/api/v1/leads/${lead.job_id}`, { timeoutMs: 10000 });
        if (!res.ok) return;
        const latest = await res.json();
        if (alive && latest?.job_id === lead.job_id) setLead(latest);
      } catch {
        // Live websocket updates are preferred; polling is only a fallback.
      }
    }, 5000);
    const guard = window.setTimeout(() => {
      if (!alive || resumeReady || coverReady) return;
      setErr("Generation is still running in the background. Open the job from Ready shortly, or press Analyse & Generate again to retry if it does not finish.");
    }, 120000);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.clearTimeout(guard);
    };
  }, [api, lead?.job_id, generating, resumeReady, coverReady]);

  const submit = async () => {
    if (!port || !api || busy || !input.trim()) return;
    setBusy(true);
    setErr(null);
    setResumeBlobUrl(null);
    setCoverBlobUrl(null);
    const controller = new AbortController();
    submitControllerRef.current?.abort();
    submitControllerRef.current = controller;
    const runId = ++submitRunRef.current;
    const watchdogId = window.setTimeout(() => {
      if (!mountedRef.current || submitRunRef.current !== runId) return;
      setBusy(false);
      setErr("Customize is taking too long to respond. I stopped waiting here; check Activity/Ready shortly or retry.");
      controller.abort();
    }, CUSTOMIZE_WATCHDOG_MS);
    try {
      const trimmed = input.trim();
      const url = trimmed.match(/https?:\/\/\S+/)?.[0] || "";
      const r = await withDeadline(
        api(`/api/v1/leads/manual/generate/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind: "job", url, text: trimmed }),
          signal: controller.signal,
          timeoutMs: CUSTOMIZE_START_TIMEOUT_MS,
        }),
        CUSTOMIZE_START_TIMEOUT_MS + 1000,
        "Customize did not accept the job quickly enough.",
      );
      if (!r.ok) {
        const detail = await r.json().then(d => d.detail).catch(() => "");
        throw new Error(detail || `Server returned ${r.status}`);
      }
      const started = await r.json();
      if (submitRunRef.current !== runId) return;
      setLead(started.lead || null);
      setBusy(false);
      window.dispatchEvent(new CustomEvent("leads-refresh"));
    } catch (e) {
      if (mountedRef.current) {
        const message = e instanceof Error ? e.message : "Application package failed";
        setErr(message === "Request cancelled" ? "Stopped waiting. If generation already started, it may still finish in the background." : message);
        setBusy(false);
      }
    } finally {
      window.clearTimeout(watchdogId);
      if (submitControllerRef.current === controller) submitControllerRef.current = null;
    }
  };

  const copyText = (value: string) => navigator.clipboard?.writeText(value);
  const stepTone = (done: boolean, active: boolean) => done ? "green" : active ? "purple" : "blue";
  const stepPill = (label: string, done: boolean, active: boolean) => {
    const tone = stepTone(done, active);
    return (
      <div className="pill mono" style={{ background: `var(--${tone}-soft)`, color: `var(--${tone}-ink)`, border: `1px solid var(--${tone})`, fontSize: 10 }}>
        {done ? "Done" : active ? "Working" : "Waiting"} - {label}
      </div>
    );
  };

  return (
    <div style={{ height: "100%", overflow: "auto", padding: 24 }}>
      <div style={{ maxWidth: 1180, margin: "0 auto", display: "grid", gridTemplateColumns: liveLead ? "420px minmax(0, 1fr)" : "minmax(0, 880px)", gap: 18, alignItems: "start", justifyContent: "center" }}>
        <section className="card" style={{ padding: 22, display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <div className="eyebrow">Customize for this job</div>
            <h2 style={{ fontSize: 24, fontWeight: 700, marginTop: 5, marginBottom: 6 }}>Paste a job URL.</h2>
            <div style={{ fontSize: 13, color: "var(--ink-3)", lineHeight: 1.55 }}>Analyse fit, generate the resume and cover letter, then copy outreach drafts from one page.</div>
          </div>
          <textarea
            ref={inputRef}
            className="field-input"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Paste job URL or full job description"
            rows={liveLead ? 8 : 12}
            style={{ fontSize: 14, lineHeight: 1.55, resize: "vertical" }}
          />
          <button className="btn btn-accent" onClick={submit} disabled={!port || !api || busy || !input.trim()} style={{ justifyContent: "center", padding: "12px 16px", fontSize: 14 }}>
            <Icon name="spark" size={15} color="#fff" /> {busy ? "Analysing and generating..." : "Analyse & Generate"}
          </button>
          {busy && (
            <button className="btn" onClick={() => { submitControllerRef.current?.abort(); setBusy(false); setErr("Stopped waiting. If generation already started, it may still finish in the background."); }} style={{ justifyContent: "center" }}>
              <Icon name="x" size={13} /> Stop waiting
            </button>
          )}
          {err && <div style={{ color: "var(--bad)", background: "var(--bad-soft)", border: "1px solid var(--bad)", borderRadius: 8, padding: "9px 11px", fontSize: 12 }}>{err}</div>}
          {liveLead && (
            <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
              {stepPill("Job captured", true, false)}
              {stepPill("Resume generated", resumeReady, generating && !resumeReady)}
              {stepPill("Cover letter generated", coverReady, generating && resumeReady && !coverReady)}
              <button className="btn" onClick={() => openDrawer(liveLead)} style={{ justifyContent: "center" }}>Open full details</button>
            </div>
          )}
        </section>

        {liveLead && (
          <section style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
            <div className="card" style={{ padding: 18, display: "flex", justifyContent: "space-between", gap: 14, alignItems: "flex-start", flexWrap: "wrap" }}>
              <div style={{ minWidth: 0 }}>
              <div className="eyebrow">Customization Package</div>
                <h3 style={{ fontSize: 18, fontWeight: 700, marginTop: 5 }}>{roleFromLead(liveLead)}</h3>
                <div style={{ fontSize: 13, color: "var(--ink-2)", marginTop: 3 }}>{liveLead.company || "Unknown company"}</div>
              </div>
              <div className="row gap-2" style={{ flexWrap: "wrap" }}>
                {coveragePct !== null && <span className="pill mono" style={{ background: "var(--blue-soft)", color: "var(--blue-ink)", border: "1px solid var(--blue)" }}>{coveragePct}% coverage</span>}
                <span className="pill mono" style={{ background: resumeReady && coverReady ? "var(--green-soft)" : "var(--purple-soft)", color: resumeReady && coverReady ? "var(--green-ink)" : "var(--purple-ink)", border: `1px solid ${resumeReady && coverReady ? "var(--green)" : "var(--purple)"}` }}>
                  {resumeReady && coverReady ? "Ready" : "Generating"}
                </span>
              </div>
            </div>

            {(missingTerms.length > 0 || incorporatedTerms.length > 0) && (
              <div className="card" style={{ padding: 16, borderColor: "var(--blue)", background: "var(--blue-soft)" }}>
                <div className="row" style={{ justifyContent: "space-between", gap: 10, alignItems: "center", marginBottom: 8 }}>
                  <span className="eyebrow" style={{ color: "var(--blue-ink)" }}>Coverage</span>
                  {coveragePct !== null && <span className="mono" style={{ fontSize: 11, fontWeight: 800, color: "var(--blue-ink)" }}>{coveragePct}% JD keywords</span>}
                </div>
                <div style={{ fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.55 }}>
                  {missingTerms.length
                    ? <>You're missing these terms from the JD: <b>{missingTerms.slice(0, 8).join(", ")}</b>. We've incorporated supported matches where applicable.</>
                    : <>Strong keyword coverage. Supported JD terms were incorporated where they fit.</>
                  }
                </div>
                {incorporatedTerms.length > 0 && (
                  <div className="row gap-2" style={{ flexWrap: "wrap", marginTop: 10 }}>
                    {incorporatedTerms.slice(0, 10).map(term => (
                      <span key={term} className="pill" style={{ background: "var(--paper)", color: "var(--blue-ink)", border: "1px solid var(--blue)" }}>{term}</span>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="card" style={{ padding: 16, borderColor: primaryContact ? "var(--green)" : "var(--line)", background: primaryContact ? "var(--green-soft)" : "var(--paper)" }}>
              <div className="row" style={{ justifyContent: "space-between", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
                <div style={{ minWidth: 0 }}>
                  <div className="eyebrow" style={{ color: primaryContact ? "var(--green-ink)" : "var(--ink-3)" }}>Who to contact</div>
                  {primaryContact ? (
                    <>
                      <h3 style={{ fontSize: 17, fontWeight: 800, marginTop: 5 }}>{primaryContact.name || "Company contact"}</h3>
                      <div style={{ fontSize: 12.5, color: "var(--ink-2)", marginTop: 3 }}>{primaryContact.title || "Hiring contact"}{contactLookup.domain ? ` at ${contactLookup.domain}` : ""}</div>
                    </>
                  ) : (
                    <>
                      <h3 style={{ fontSize: 17, fontWeight: 800, marginTop: 5 }}>Contact lookup</h3>
                      <div style={{ fontSize: 12.5, color: "var(--ink-2)", marginTop: 3 }}>
                        {contactLookup.message || (resumeReady && coverReady ? "Add a Hunter.io API key in Settings to find recruiter and founder emails." : "Contact lookup runs after the package is generated.")}
                      </div>
                    </>
                  )}
                </div>
                {contactLookup.status && (
                  <span className="pill mono" style={{ background: primaryContact ? "var(--paper)" : "var(--paper-3)", color: primaryContact ? "var(--green-ink)" : "var(--ink-3)", border: `1px solid ${primaryContact ? "var(--green)" : "var(--line)"}` }}>
                    {contactLookup.status.replace(/_/g, " ")}
                  </span>
                )}
              </div>
              {primaryContact && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10, marginTop: 12 }}>
                  <div style={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 8, padding: 12 }}>
                    <div className="eyebrow">Direct line</div>
                    <div className="col gap-2" style={{ marginTop: 8, fontSize: 12.5, color: "var(--ink-2)" }}>
                      {primaryContact.email && (
                        <button className="btn btn-ghost" style={{ justifyContent: "space-between" }} onClick={() => copyText(primaryContact.email || "")}>
                          <span className="mono" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{primaryContact.email}</span>
                          <span>Copy</span>
                        </button>
                      )}
                      {primaryContact.linkedin_url && (
                        <button className="btn btn-ghost" style={{ justifyContent: "space-between" }} onClick={() => copyText(primaryContact.linkedin_url || "")}>
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>LinkedIn profile</span>
                          <span>Copy</span>
                        </button>
                      )}
                      {typeof primaryContact.confidence === "number" && primaryContact.confidence > 0 && (
                        <div className="mono" style={{ color: "var(--green-ink)", fontSize: 11 }}>{primaryContact.confidence}% Hunter confidence</div>
                      )}
                    </div>
                  </div>
                  {primaryContact.personalized_email && (
                    <div style={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 8, padding: 12 }}>
                      <div className="row" style={{ justifyContent: "space-between", gap: 8, marginBottom: 8 }}>
                        <span className="eyebrow">Cold email</span>
                        <button className="btn btn-ghost" style={{ fontSize: 11, padding: "3px 8px" }} onClick={() => copyText(primaryContact.personalized_email || "")}>Copy</button>
                      </div>
                      <div style={{ fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{primaryContact.personalized_email}</div>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 14 }}>
              {[
                { label: "Resume", ready: resumeReady, blob: resumeBlobUrl, error: resumeLoadErr },
                { label: "Cover Letter", ready: coverReady, blob: coverBlobUrl, error: coverLoadErr },
              ].map(doc => (
                <div key={doc.label} className="card" style={{ minHeight: 600, overflow: "hidden", display: "flex", flexDirection: "column" }}>
                  <div className="row" style={{ padding: 11, borderBottom: "1px solid var(--line)", background: "var(--paper-3)", justifyContent: "space-between", gap: 10 }}>
                    <div className="row gap-2">
                      <span style={{ fontSize: 13, fontWeight: 800 }}>{doc.label}</span>
                      <span className="dot" style={{ color: doc.ready ? "var(--ok)" : "var(--ink-4)" }} />
                    </div>
                    <button className="btn btn-ghost" disabled={!doc.blob} onClick={() => doc.blob && openUrl(doc.blob)} style={{ fontSize: 11, padding: "4px 9px" }}>
                      <Icon name="download" size={12} /> Download PDF
                    </button>
                  </div>
                  <div style={{ flex: 1, minHeight: 0 }}>
                    {doc.ready && doc.blob && (
                      <iframe key={doc.blob} src={doc.blob} title={doc.label} width="100%" style={{ height: "100%", minHeight: 548, border: "none", display: "block" }} />
                    )}
                    {doc.ready && !doc.blob && !doc.error && (
                      <div style={{ minHeight: 548, display: "grid", placeItems: "center", color: "var(--ink-3)", fontSize: 12 }}>Loading PDF...</div>
                    )}
                    {doc.error && (
                      <div style={{ minHeight: 548, display: "grid", placeItems: "center", color: "var(--bad)", fontSize: 12 }}>{doc.error}</div>
                    )}
                    {!doc.ready && (
                      <div style={{ minHeight: 548, display: "grid", placeItems: "center", color: "var(--ink-3)", fontSize: 12, textAlign: "center", padding: 24 }}>
                        {generating ? `Generating ${doc.label.toLowerCase()}...` : `${doc.label} will appear here.`}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {(liveLead.outreach_reply || liveLead.outreach_dm || liveLead.outreach_email || (liveLead.fit_bullets?.length ?? 0) > 0) && (
              <div className="card" style={{ padding: 16, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10 }}>
                {[
                  ["3-line pitch", liveLead.outreach_reply],
                  ["Cold email", liveLead.outreach_email],
                  ["LinkedIn note", liveLead.outreach_dm],
                  ["Fit bullets", (liveLead.fit_bullets || []).join("\n")],
                ].filter(([, value]) => Boolean(value)).map(([label, value]) => (
                  <div key={label} style={{ background: "var(--paper-3)", border: "1px solid var(--line)", borderRadius: 8, padding: "10px 12px" }}>
                    <div className="row" style={{ justifyContent: "space-between", gap: 8, marginBottom: 7 }}>
                      <span className="eyebrow">{label}</span>
                      <button className="btn btn-ghost" style={{ fontSize: 11, padding: "3px 8px" }} onClick={() => copyText(String(value))}>Copy</button>
                    </div>
                    <div style={{ fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{value}</div>
                  </div>
                ))}
              </div>
            )}

            <div className="card" style={{ padding: 16, display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <div style={{ fontSize: 12.5, color: "var(--ink-2)" }}>Ready package: use the generated documents and outreach drafts wherever you apply.</div>
              <button className="btn" onClick={() => liveLead && openDrawer(liveLead)} disabled={!liveLead} style={{ minWidth: 170, justifyContent: "center" }}>
                <Icon name="file" size={14} /> Review Package
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
