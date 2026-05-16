import React, { useState, useEffect, useCallback } from "react";
import { api } from "../api.js";
import LeadTable from "../components/LeadTable.jsx";
import LeadModal from "../components/LeadModal.jsx";
import ManualLeadForm from "../components/ManualLeadForm.jsx";

const PAGE_SIZE = 25;

export default function LeadsPage() {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [selectedLeadId, setSelectedLeadId] = useState(null);
  const [showForm, setShowForm] = useState(false);

  const fetchLeads = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.getLeads({
        page,
        limit: PAGE_SIZE,
        status: statusFilter || undefined,
      });
      let items = [];
      let totalCount = 0;
      if (Array.isArray(res)) {
        items = res;
        totalCount = res.length;
      } else {
        items = res.items || [];
        totalCount = res.total || 0;
      }
      // Sort by score descending
      items.sort((a, b) => (b.score || 0) - (a.score || 0));
      setLeads(items);
      setTotal(totalCount);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    fetchLeads();
  }, [fetchLeads]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const handleLeadUpdate = (updated) => {
    setLeads((prev) =>
      prev.map((l) => (l.job_id === updated.job_id ? updated : l))
    );
  };

  const handleCreated = (lead) => {
    setLeads((prev) => [lead, ...prev]);
    setShowForm(false);
  };

  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "24px" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "20px",
        }}
      >
        <h1 style={{ margin: 0, fontSize: "22px", fontWeight: 800 }}>
          JustHireMe — Leads
        </h1>
        <button
          onClick={() => setShowForm((s) => !s)}
          style={{
            padding: "8px 16px",
            borderRadius: "6px",
            border: "none",
            background: "#2563eb",
            color: "#fff",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          {showForm ? "Close Form" : "+ Create Manual Lead"}
        </button>
      </div>

      {showForm && (
        <ManualLeadForm onCreated={handleCreated} />
      )}

      <div
        style={{
          display: "flex",
          gap: "12px",
          alignItems: "center",
          marginBottom: "16px",
          flexWrap: "wrap",
        }}
      >
        <div>
          <label
            style={{
              fontSize: "13px",
              fontWeight: 600,
              color: "#374151",
              marginRight: "8px",
            }}
          >
            Filter by status:
          </label>
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            style={{
              padding: "6px 12px",
              borderRadius: "6px",
              border: "1px solid #d1d5db",
              fontSize: "14px",
            }}
          >
            <option value="">All</option>
            <option value="discovered">Discovered</option>
            <option value="evaluating">Evaluating</option>
            <option value="program_matched">Program Matched</option>
            <option value="program_approved">Program Approved</option>
            <option value="tailoring">Tailoring</option>
            <option value="applied">Applied</option>
            <option value="discarded">Discarded</option>
          </select>
        </div>
        <div style={{ fontSize: "13px", color: "#6b7280" }}>
          {total} total · Page {page} of {totalPages}
        </div>
      </div>

      {error && (
        <div
          style={{
            color: "#dc2626",
            background: "#fef2f2",
            padding: "12px 16px",
            borderRadius: "8px",
            marginBottom: "16px",
            fontSize: "14px",
          }}
        >
          {error}
        </div>
      )}

      <div
        style={{
          background: "#fff",
          borderRadius: "10px",
          border: "1px solid #e5e7eb",
          overflow: "hidden",
        }}
      >
        {loading ? (
          <div style={{ textAlign: "center", padding: "50px" }}>Loading…</div>
        ) : (
          <LeadTable leads={leads} onRowClick={setSelectedLeadId} />
        )}
      </div>

      {totalPages > 1 && (
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            gap: "8px",
            marginTop: "18px",
          }}
        >
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            style={{
              padding: "6px 14px",
              borderRadius: "6px",
              border: "1px solid #d1d5db",
              background: "#fff",
              cursor: page <= 1 ? "not-allowed" : "pointer",
              opacity: page <= 1 ? 0.5 : 1,
              fontSize: "14px",
            }}
          >
            ← Prev
          </button>
          <span
            style={{
              padding: "6px 14px",
              fontSize: "14px",
              color: "#374151",
            }}
          >
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            style={{
              padding: "6px 14px",
              borderRadius: "6px",
              border: "1px solid #d1d5db",
              background: "#fff",
              cursor: page >= totalPages ? "not-allowed" : "pointer",
              opacity: page >= totalPages ? 0.5 : 1,
              fontSize: "14px",
            }}
          >
            Next →
          </button>
        </div>
      )}

      <LeadModal
        leadId={selectedLeadId}
        onClose={() => setSelectedLeadId(null)}
        onUpdate={handleLeadUpdate}
      />
    </div>
  );
}
