import React from "react";
import StatusBadge from "./StatusBadge.jsx";

export default function LeadTable({ leads, onRowClick }) {
  if (!leads || leads.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: "40px", color: "#6b7280" }}>
        No leads found.
      </div>
    );
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "14px" }}>
        <thead>
          <tr style={{ borderBottom: "2px solid #e5e7eb", textAlign: "left" }}>
            <th style={{ padding: "10px 12px", fontWeight: 600, color: "#374151" }}>Title</th>
            <th style={{ padding: "10px 12px", fontWeight: 600, color: "#374151" }}>Company</th>
            <th style={{ padding: "10px 12px", fontWeight: 600, color: "#374151" }}>City</th>
            <th style={{ padding: "10px 12px", fontWeight: 600, color: "#374151" }}>Score</th>
            <th style={{ padding: "10px 12px", fontWeight: 600, color: "#374151" }}>Status</th>
            <th style={{ padding: "10px 12px", fontWeight: 600, color: "#374151" }}>Program</th>
            <th style={{ padding: "10px 12px", fontWeight: 600, color: "#374151" }}>Matched Program</th>
            <th style={{ padding: "10px 12px", fontWeight: 600, color: "#374151" }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {leads.map((lead) => {
            const programStatus = lead?.source_meta?.program_status || lead?.program_status;
            const matchedProgram = lead?.source_meta?.matched_program || lead?.matched_program;
            return (
              <tr
                key={lead.job_id}
                onClick={() => onRowClick?.(lead.job_id)}
                style={{
                  borderBottom: "1px solid #f3f4f6",
                  cursor: "pointer",
                  transition: "background 0.15s",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "#f9fafb")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                <td style={{ padding: "10px 12px", maxWidth: "240px" }}>
                  <div style={{ fontWeight: 600, color: "#111827" }}>{lead.title || "—"}</div>
                </td>
                <td style={{ padding: "10px 12px", color: "#374151" }}>{lead.company || "—"}</td>
                <td style={{ padding: "10px 12px", color: "#6b7280" }}>{lead.location || lead.city || "—"}</td>
                <td style={{ padding: "10px 12px" }}>
                  <span style={{ fontWeight: 700, color: "#2563eb" }}>{lead.score ?? "—"}</span>
                </td>
                <td style={{ padding: "10px 12px" }}>
                  <StatusBadge status={lead.status} />
                </td>
                <td style={{ padding: "10px 12px" }}>
                  {programStatus ? (
                    <span style={{ fontSize: "12px", color: "#6b7280", textTransform: "capitalize" }}>
                      {programStatus}
                    </span>
                  ) : (
                    <span style={{ fontSize: "12px", color: "#9ca3af" }}>—</span>
                  )}
                </td>
                <td style={{ padding: "10px 12px", fontSize: "12px", color: "#6b7280" }}>
                  {matchedProgram?.title || matchedProgram?.name || "—"}
                </td>
                <td style={{ padding: "10px 12px" }}>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onRowClick?.(lead.job_id);
                    }}
                    style={{
                      padding: "4px 10px",
                      borderRadius: "4px",
                      border: "1px solid #d1d5db",
                      background: "#fff",
                      fontSize: "12px",
                      cursor: "pointer",
                    }}
                  >
                    View
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
