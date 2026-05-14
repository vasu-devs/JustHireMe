import { useEffect, useRef, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import Icon from "../../../shared/components/Icon";
import type { ApiFetch, Lead } from "../../../types";
import { GENERATION_TIMEOUT_MS } from "../../../api/generation";
import { getMark, getTone, leadDisplayHeading, leadSeniority, seniorityLabel, seniorityTone } from "../../../shared/lib/leadUtils";

export function JobCard({ lead, onOpen, onDelete, showScore = false, showGenerate = false, port, api }: {
  lead: Lead;
  onOpen: (l: Lead) => void;
  onDelete: (id: string) => void;
  showScore?: boolean;
  showGenerate?: boolean;
  port?: number | null;
  api?: ApiFetch | null;
}) {
  const [generating, setGenerating] = useState(false);
  const requestRef = useRef<AbortController | null>(null);
  const desc = lead.description?.trim();
  const signalScore = lead.signal_score || 0;
  const qualityReason = String(lead.lead_quality_reason || lead.source_meta?.lead_quality_reason || "");
  const qualityScore = Number(lead.lead_quality_score || lead.source_meta?.lead_quality_score || 0);
  const isHotX = lead.platform === "x" && signalScore >= 80;
  const level = leadSeniority(lead);
  const levelTone = seniorityTone(level);

  const handleGenerate = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!port || !api) return;
    setGenerating(true);
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    try {
      const response = await api(`/api/v1/leads/${lead.job_id}/generate`, { method: "POST", signal: controller.signal, timeoutMs: GENERATION_TIMEOUT_MS });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || `Generation returned ${response.status}`);
      if (body.lead) window.dispatchEvent(new CustomEvent("lead-updated", { detail: body.lead }));
      window.dispatchEvent(new CustomEvent("leads-refresh"));
    } catch (error) {
      console.error("Package generation failed", error);
    } finally {
      if (requestRef.current === controller) requestRef.current = null;
      setGenerating(false);
    }
  };

  useEffect(() => () => requestRef.current?.abort(), []);

  return (
    <div className="card lift" style={{
      padding: 16, cursor: "pointer", border: "1px solid var(--line)",
      background: "var(--card)", display: "flex", flexDirection: "column", gap: 10,
    }} onClick={() => onOpen(lead)}>
      {/* Header row */}
      <div className="row gap-3" style={{ alignItems: "flex-start" }}>
        <div style={{
          width: 36, height: 36, borderRadius: 10, flexShrink: 0,
          background: `var(--${getTone(lead.status)})`, color: `var(--${getTone(lead.status)}-ink)`,
          display: "grid", placeItems: "center",
          fontFamily: "var(--font-display)", fontSize: 17, fontWeight: 500,
          border: `1px solid var(--${getTone(lead.status)}-ink)`,
        }}>{getMark(lead.company)}</div>
        <div className="col" style={{ flex: 1, minWidth: 0, gap: 2 }}>
          <div style={{ fontSize: 13.5, fontWeight: 600, lineHeight: 1.25, color: "var(--ink)" }}>{lead.title}</div>
          <div className="row gap-2" style={{ alignItems: "center" }}>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em" }}>{lead.company}</span>
            <span style={{ color: "var(--ink-4)", fontSize: 10 }}>·</span>
            <span className="pill mono" style={{ fontSize: 8.5, padding: "1px 6px" }}>{lead.platform}</span>
            <span className="pill mono" style={{ fontSize: 8.5, padding: "1px 6px", background: `var(--${levelTone}-soft)`, color: `var(--${levelTone}-ink)`, border: `1px solid var(--${levelTone})` }}>{seniorityLabel(level)}</span>
            {isHotX && <span className="pill mono" style={{ fontSize: 8.5, padding: "1px 6px", background: "var(--orange-soft)", color: "var(--orange-ink)", border: "1px solid var(--orange)" }}>HOT X</span>}
            {lead.budget && <span className="pill mono" style={{ fontSize: 8.5, padding: "1px 6px", background: "var(--green-soft)", color: "var(--green-ink)" }}>{lead.budget}</span>}
          </div>
        </div>
        {signalScore > 0 && (
          <span style={{
            flexShrink: 0, fontSize: 11.5, fontWeight: 800, padding: "3px 9px", borderRadius: 999,
            background: signalScore >= 80 ? "var(--orange-soft)" : signalScore >= 60 ? "var(--yellow-soft)" : "var(--paper-3)",
            color: signalScore >= 80 ? "var(--orange-ink)" : signalScore >= 60 ? "var(--yellow-ink)" : "var(--ink-3)",
            border: `1px solid ${signalScore >= 80 ? "var(--orange)" : "var(--line)"}`,
          }}>{signalScore}</span>
        )}
        {/* Score badge */}
        {showScore && lead.score > 0 && (
          <span style={{
            flexShrink: 0, fontSize: 12, fontWeight: 700, padding: "3px 10px", borderRadius: 999,
            background: lead.score >= 85 ? "var(--green)" : lead.score >= 50 ? "var(--yellow)" : "var(--bad-soft)",
            color:      lead.score >= 85 ? "var(--green-ink)" : lead.score >= 50 ? "var(--yellow-ink)" : "var(--bad)",
          }}>{lead.score}%</span>
        )}
        {/* Delete button */}
        <button
          onClick={e => { e.stopPropagation(); onDelete(lead.job_id); }}
          title="Remove"
          style={{
            flexShrink: 0, width: 26, height: 26, borderRadius: 7,
            border: "1px solid var(--line)", background: "var(--paper)",
            color: "var(--bad)", cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 14, lineHeight: 1, padding: 0, opacity: 0.7,
            transition: "opacity 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.opacity = "1")}
          onMouseLeave={e => (e.currentTarget.style.opacity = "0.7")}
        >×</button>
      </div>

      {/* Description */}
      {desc ? (
        <div style={{
          fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.55,
          display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical",
          overflow: "hidden",
          background: "var(--paper-3)", borderRadius: 8, padding: "8px 10px",
          border: "1px solid var(--line)",
        }}>{desc}</div>
      ) : (
        <div style={{ fontSize: 11.5, color: "var(--ink-4)", fontStyle: "italic" }}>No description extracted.</div>
      )}

      {/* Evaluator reason (for Evaluated tab) */}
      {showScore && lead.reason && (
        <div style={{ fontSize: 11.5, color: "var(--ink-3)", lineHeight: 1.5, borderLeft: "2px solid var(--line)", paddingLeft: 8 }}>
          {lead.reason.slice(0, 160)}{lead.reason.length > 160 ? "…" : ""}
        </div>
      )}

      {lead.signal_reason && (
        <div style={{ fontSize: 11.5, color: "var(--ink-3)", lineHeight: 1.5, borderLeft: "2px solid var(--orange)", paddingLeft: 8 }}>
          {lead.signal_reason.slice(0, 150)}{lead.signal_reason.length > 150 ? "..." : ""}
        </div>
      )}

      {qualityReason && (
        <div style={{ fontSize: 11.5, color: "var(--ink-3)", lineHeight: 1.5, borderLeft: "2px solid var(--blue)", paddingLeft: 8 }}>
          Shown by quality gate{qualityScore ? ` (${qualityScore})` : ""}: {qualityReason.slice(0, 150)}{qualityReason.length > 150 ? "..." : ""}
        </div>
      )}

      {/* Footer */}
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginTop: 2 }}>
        <button
          onClick={e => { e.stopPropagation(); openUrl(lead.url); }}
          title={lead.url}
          style={{ fontSize: 11, color: "var(--teal)", background: "none", border: "none", padding: 0, cursor: "pointer", display: "flex", alignItems: "center", gap: 4, maxWidth: "60%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
        >
          <Icon name="external-link" size={11} color="var(--teal)" />
          {lead.url.replace(/^https?:\/\//, "").slice(0, 50)}
        </button>
        <div className="row gap-2">
          {showGenerate && (
            <button
              onClick={handleGenerate}
              disabled={generating}
              style={{
                padding: "4px 10px", borderRadius: 7, fontSize: 11, fontWeight: 600,
                border: "1px solid var(--purple)", background: "var(--purple-soft)",
                color: "var(--purple-ink)", cursor: generating ? "wait" : "pointer",
              }}
            >{generating ? "Queued..." : "Generate Package"}</button>
          )}
          <button
            onClick={e => { e.stopPropagation(); onOpen(lead); }}
            style={{
              padding: "4px 10px", borderRadius: 7, fontSize: 11, fontWeight: 600,
              border: "1px solid var(--line)", background: "var(--paper)",
              color: "var(--ink-2)", cursor: "pointer",
            }}
          >Details →</button>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════
   PIPELINE VIEW (tabbed)
══════════════════════════════════════ */

export function PipelineJobCard({ lead, onOpen, onDelete, showGenerate = false, port, api }: {
  lead: Lead;
  onOpen: (l: Lead) => void;
  onDelete: (id: string) => void;
  showGenerate?: boolean;
  port?: number | null;
  api?: ApiFetch | null;
}) {
  const [generating, setGenerating] = useState(false);
  const requestRef = useRef<AbortController | null>(null);
  const signalScore = lead.signal_score || 0;
  const matchScore = lead.score || 0;
  const qualityScore = Number(lead.lead_quality_score || lead.source_meta?.lead_quality_score || 0);
  const isHotX = lead.platform === "x" && signalScore >= 80;
  const level = leadSeniority(lead);
  const levelTone = seniorityTone(level);
  const statusTone = getTone(lead.status);
  const display = leadDisplayHeading(lead);
  const urlLabel = lead.url ? lead.url.replace(/^https?:\/\//, "").slice(0, 42) : "No source URL";

  const handleGenerate = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!port || !api) return;
    setGenerating(true);
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    try {
      const response = await api(`/api/v1/leads/${lead.job_id}/generate`, { method: "POST", signal: controller.signal, timeoutMs: GENERATION_TIMEOUT_MS });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || `Generation returned ${response.status}`);
      if (body.lead) window.dispatchEvent(new CustomEvent("lead-updated", { detail: body.lead }));
      window.dispatchEvent(new CustomEvent("leads-refresh"));
    } catch (error) {
      console.error("Package generation failed", error);
    } finally {
      if (requestRef.current === controller) requestRef.current = null;
      setGenerating(false);
    }
  };

  useEffect(() => () => requestRef.current?.abort(), []);

  return (
    <div className="pipeline-job-card lift" data-status={lead.status || "discovered"} onClick={() => onOpen(lead)}>
      <div className="pipeline-job-mark" style={{ background: `var(--${statusTone}-soft)`, color: `var(--${statusTone}-ink)`, borderColor: `var(--${statusTone})` }}>
        {getMark(lead.company)}
      </div>
      <div className="pipeline-job-main">
        <div className="pipeline-job-title-row">
          <div className="pipeline-job-title">
            <span>{display.role}</span>
            <b>||</b>
            <span className="company">{display.company}</span>
          </div>
          <span className="pipeline-status-pill" style={{ background: `var(--${statusTone}-soft)`, color: `var(--${statusTone}-ink)`, borderColor: `var(--${statusTone})` }}>
            {lead.status || "discovered"}
          </span>
        </div>
        <div className="pipeline-job-meta">
          <span>{lead.platform || "source"}</span>
          <span style={{ color: `var(--${levelTone}-ink)` }}>{seniorityLabel(level)}</span>
          {isHotX && <span style={{ color: "var(--orange-ink)" }}>Hot X</span>}
          {lead.budget && <span style={{ color: "var(--green-ink)" }}>{lead.budget}</span>}
        </div>
      </div>
      <div className="pipeline-job-side">
        <div className="pipeline-score-stack">
          {matchScore > 0 && <span className={`pipeline-score ${matchScore >= 76 ? "good" : matchScore >= 50 ? "warn" : "bad"}`}>Fit {matchScore}</span>}
          {signalScore > 0 && <span className={`pipeline-score ${signalScore >= 80 ? "hot" : signalScore >= 60 ? "warn" : ""}`}>Signal {signalScore}</span>}
          {qualityScore > 0 && <span className={`pipeline-score ${qualityScore >= 80 ? "hot" : qualityScore >= 60 ? "warn" : ""}`}>Quality {qualityScore}</span>}
        </div>
        <div className="pipeline-job-actions">
          {showGenerate && (
            <button className="btn" onClick={handleGenerate} disabled={generating}>
              <Icon name="file" size={12} /> {generating ? "Queued" : "Generate"}
            </button>
          )}
          <button className="btn btn-icon" onClick={e => { e.stopPropagation(); if (lead.url) openUrl(lead.url); }} title={lead.url} disabled={!lead.url}>
            <Icon name="external-link" size={13} />
          </button>
          <button className="btn" onClick={e => { e.stopPropagation(); onOpen(lead); }}>Details</button>
          <button className="btn btn-icon danger" onClick={e => { e.stopPropagation(); onDelete(lead.job_id); }} title="Delete lead">
            <Icon name="trash" size={13} />
          </button>
        </div>
        <div className="pipeline-source mono" title={lead.url}>{urlLabel}</div>
      </div>
    </div>
  );
}

export function PipelineSkeleton() {
  return (
    <div className="pipeline-skeleton">
      <div className="pipeline-skeleton-bar" />
      {[0, 1, 2, 3].map(i => (
        <div key={i} className="pipeline-skeleton-card">
          <span />
          <div>
            <i />
            <b />
            <em />
          </div>
          <strong />
        </div>
      ))}
    </div>
  );
}
