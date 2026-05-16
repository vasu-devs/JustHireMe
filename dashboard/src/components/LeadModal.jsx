import React, { useState, useEffect } from "react";
import { api } from "../api.js";
import StatusBadge from "./StatusBadge.jsx";

export default function LeadModal({ leadId, onClose, onUpdate }) {
  const [lead, setLead] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionBusy, setActionBusy] = useState("");

  useEffect(() => {
    if (!leadId) return;
    setLoading(true);
    setError("");
    api
      .getLead(leadId)
      .then((data) => {
        setLead(data);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [leadId]);

  if (!leadId) return null;

  const handleApprove = async () => {
    setActionBusy("approve");
    try {
      await api.approveProgram(leadId);
      const updated = await api.getLead(leadId);
      setLead(updated);
      onUpdate?.(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setActionBusy("");
    }
  };

  const handleGenerate = async () => {
    setActionBusy("generate");
    try {
      await api.generate(leadId);
      const updated = await api.getLead(leadId);
      setLead(updated);
      onUpdate?.(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setActionBusy("");
    }
  };

  const program = lead?.source_meta?.matched_program || lead?.matched_program;
  const programStatus =
    lead?.source_meta?.program_status || lead?.program_status;

  const overlayStyle = {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,0.45)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1000,
    padding: "20px",
  };

  const boxStyle = {
    background: "#fff",
    borderRadius: "12px",
    width: "100%",
    maxWidth: "720px",
    maxHeight: "90vh",
    overflow: "auto",
    padding: "28px",
    position: "relative",
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={boxStyle} onClick={(e) => e.stopPropagation()}>
        {loading ? (
          <div style={{ textAlign: "center", padding: "40px" }}>Loading…</div>
        ) : error ? (
          <div style={{ color: "#dc2626", padding: "20px" }}>Error: {error}</div>
        ) : (
          <>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                marginBottom: "20px",
              }}
            >
              <div>
                <h2 style={{ margin: 0, fontSize: "20px", fontWeight: 700 }}>
                  {lead.title || "Untitled Lead"}
                </h2>
                <div style={{ color: "#6b7280", marginTop: "4px" }}>
                  {lead.company || "—"} · {lead.location || "—"}
                </div>
              </div>
              <button
                onClick={onClose}
                style={{
                  border: "none",
                  background: "none",
                  fontSize: "22px",
                  cursor: "pointer",
                  lineHeight: 1,
                }}
              >
                ×
              </button>
            </div>

            <div
              style={{
                display: "flex",
                gap: "12px",
                flexWrap: "wrap",
                marginBottom: "20px",
              }}
            >
              <StatusBadge status={lead.status} />
              <span
                style={{
                  fontSize: "13px",
                  color: "#374151",
                  background: "#f3f4f6",
                  padding: "2px 10px",
                  borderRadius: "9999px",
                }}
              >
                Score: {lead.score ?? "—"}
              </span>
              {lead.seniority_level && (
                <span
                  style={{
                    fontSize: "13px",
                    color: "#374151",
                    background: "#f3f4f6",
                    padding: "2px 10px",
                    borderRadius: "9999px",
                  }}
                >
                  {lead.seniority_level}
                </span>
              )}
            </div>

            {lead.reason && (
              <div
                style={{
                  background: "#f9fafb",
                  padding: "14px",
                  borderRadius: "8px",
                  marginBottom: "18px",
                  fontSize: "14px",
                  lineHeight: 1.6,
                }}
              >
                <strong>Reason:</strong> {lead.reason}
              </div>
            )}

            {lead.description && (
              <div
                style={{
                  marginBottom: "18px",
                  fontSize: "14px",
                  lineHeight: 1.6,
                  color: "#374151",
                  maxHeight: "200px",
                  overflow: "auto",
                }}
              >
                <strong>Description:</strong>
                <p style={{ margin: "6px 0 0", whiteSpace: "pre-wrap" }}>
                  {lead.description}
                </p>
              </div>
            )}

            {program && (
              <div
                style={{
                  border: "1px solid #e5e7eb",
                  borderRadius: "10px",
                  padding: "16px",
                  marginBottom: "18px",
                }}
              >
                <h3
                  style={{
                    margin: "0 0 12px",
                    fontSize: "15px",
                    fontWeight: 700,
                    color: "#111827",
                  }}
                >
                  Matched Program
                </h3>
                <div style={{ fontSize: "14px", lineHeight: 1.6 }}>
                  <div>
                    <strong>{program.title || program.name || "—"}</strong>
                  </div>
                  <div style={{ color: "#6b7280" }}>
                    {program.university || program.institution || "—"} ·{" "}
                    {program.city || program.location || "—"}
                  </div>
                  {program.modalities && (
                    <div style={{ marginTop: "4px", color: "#6b7280" }}>
                      Modalities:{" "}
                      {Array.isArray(program.modalities)
                        ? program.modalities.join(", ")
                        : program.modalities}
                    </div>
                  )}
                  {program.match_score !== undefined && (
                    <div style={{ marginTop: "4px" }}>
                      Match Score: {" "}
                      <strong>{program.match_score}%</strong>
                    </div>
                  )}
                </div>

                <div style={{ marginTop: "14px", display: "flex", gap: "10px" }}>
                  {programStatus === "matched" && (
                    <button
                      onClick={handleApprove}
                      disabled={actionBusy === "approve"}
                      style={{
                        padding: "8px 16px",
                        borderRadius: "6px",
                        border: "none",
                        background: "#f59e0b",
                        color: "#fff",
                        fontWeight: 600,
                        cursor: "pointer",
                        opacity: actionBusy === "approve" ? 0.6 : 1,
                      }}
                    >
                      {actionBusy === "approve"
                        ? "Approving…"
                        : "Approve Program"}
                    </button>
                  )}
                  {(programStatus === "approved" ||
                    lead.status === "tailoring") && (
                    <button
                      onClick={handleGenerate}
                      disabled={actionBusy === "generate"}
                      style={{
                        padding: "8px 16px",
                        borderRadius: "6px",
                        border: "none",
                        background: "#10b981",
                        color: "#fff",
                        fontWeight: 600,
                        cursor: "pointer",
                        opacity: actionBusy === "generate" ? 0.6 : 1,
                      }}
                    >
                      {actionBusy === "generate"
                        ? "Generating…"
                        : "Generate Application Package"}
                    </button>
                  )}
                </div>
              </div>
            )}

            {lead.resume_asset || lead.asset ? (
              <div
                style={{
                  display: "flex",
                  gap: "10px",
                  flexWrap: "wrap",
                  marginTop: "8px",
                }}
              >
                <a
                  href={api.getPdf(leadId, "resume")}
                  download
                  style={{
                    padding: "8px 14px",
                    borderRadius: "6px",
                    background: "#2563eb",
                    color: "#fff",
                    textDecoration: "none",
                    fontSize: "13px",
                    fontWeight: 600,
                  }}
                >
                  Download Resume PDF
                </a>
                <a
                  href={api.getPdf(leadId, "cover")}
                  download
                  style={{
                    padding: "8px 14px",
                    borderRadius: "6px",
                    background: "#7c3aed",
                    color: "#fff",
                    textDecoration: "none",
                    fontSize: "13px",
                    fontWeight: 600,
                  }}
                >
                  Download Cover Letter PDF
                </a>
              </div>
            ) : null}

            {lead.url && (
              <div style={{ marginTop: "18px", fontSize: "13px" }}>
                <a
                  href={lead.url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: "#2563eb" }}
                >
                  Open original listing →
                </a>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
