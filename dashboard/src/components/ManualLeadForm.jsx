import React, { useState } from "react";
import { api } from "../api.js";

export default function ManualLeadForm({ onCreated }) {
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!text.trim() && !url.trim()) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const lead = await api.createManualLead({ text, url });
      setResult({ type: "created", lead });
      // Auto-trigger match program
      try {
        const matchRes = await api.matchProgram(lead.job_id);
        setResult({ type: "matched", lead, match: matchRes });
        if (matchRes.status === "matched") {
          const updated = await api.getLead(lead.job_id);
          onCreated?.(updated);
        } else {
          onCreated?.(lead);
        }
      } catch (matchErr) {
        setResult({ type: "created", lead, matchError: matchErr.message });
        onCreated?.(lead);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const wrapStyle = {
    border: "1px solid #e5e7eb",
    borderRadius: "10px",
    padding: "18px",
    background: "#fff",
    marginBottom: "18px",
  };

  const inputStyle = {
    width: "100%",
    padding: "10px 12px",
    borderRadius: "6px",
    border: "1px solid #d1d5db",
    fontSize: "14px",
    fontFamily: "inherit",
    marginTop: "4px",
  };

  return (
    <div style={wrapStyle}>
      <h3 style={{ margin: "0 0 14px", fontSize: "15px", fontWeight: 700 }}>
        Create Manual Lead
      </h3>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: "12px" }}>
          <label style={{ fontSize: "13px", fontWeight: 600, color: "#374151" }}>
            Job description / text
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={5}
            style={{ ...inputStyle, resize: "vertical" }}
            placeholder="Paste the full job posting text here…"
          />
        </div>
        <div style={{ marginBottom: "12px" }}>
          <label style={{ fontSize: "13px", fontWeight: 600, color: "#374151" }}>
            URL (optional)
          </label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            style={inputStyle}
            placeholder="https://…"
          />
        </div>
        <button
          type="submit"
          disabled={busy || (!text.trim() && !url.trim())}
          style={{
            padding: "8px 18px",
            borderRadius: "6px",
            border: "none",
            background: "#2563eb",
            color: "#fff",
            fontWeight: 600,
            cursor: "pointer",
            opacity: busy || (!text.trim() && !url.trim()) ? 0.5 : 1,
          }}
        >
          {busy ? "Creating…" : "Create Lead"}
        </button>
        {error && (
          <div style={{ color: "#dc2626", marginTop: "10px", fontSize: "13px" }}>
            {error}
          </div>
        )}
        {result && (
          <div
            style={{
              marginTop: "12px",
              padding: "10px 12px",
              borderRadius: "6px",
              background: result.match?.status === "matched" ? "#ecfdf5" : "#f0fdf4",
              color: "#065f46",
              fontSize: "13px",
            }}
          >
            {result.match?.status === "matched"
              ? `Lead created and program matched: ${result.match?.program?.title || "—"}`
              : result.type === "matched" && result.match?.status === "no_match"
              ? "Lead created, but no matching program found."
              : "Lead created successfully."}
            {result.matchError && (
              <div style={{ color: "#92400e", marginTop: "4px" }}>
                Match error: {result.matchError}
              </div>
            )}
          </div>
        )}
      </form>
    </div>
  );
}
