import React, { useState, useEffect, useCallback } from "react";
import { api } from "../api.js";

const STATUS_COLORS = {
  pending: { bg: "#fef3c7", text: "#92400e", label: "Pending" },
  sent: { bg: "#d1fae5", text: "#065f46", label: "Sent" },
  failed: { bg: "#fee2e2", text: "#991b1b", label: "Failed" },
};

function StatusBadge({ status }) {
  const s = status || "pending";
  const config = STATUS_COLORS[s] || STATUS_COLORS.pending;
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 10px",
        borderRadius: "9999px",
        fontSize: "12px",
        fontWeight: 600,
        background: config.bg,
        color: config.text,
        whiteSpace: "nowrap",
      }}
    >
      {config.label}
    </span>
  );
}

const TAB_STYLE = {
  padding: "8px 16px",
  borderRadius: "6px",
  border: "none",
  background: "#fff",
  color: "#374151",
  fontWeight: 600,
  cursor: "pointer",
  fontSize: "13px",
};

const TAB_ACTIVE = {
  ...TAB_STYLE,
  background: "#2563eb",
  color: "#fff",
};

export default function NotificationsPage() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [stats, setStats] = useState({ total: 0, pending: 0, sent: 0, failed: 0 });
  const [retrying, setRetrying] = useState(null);
  const [page, setPage] = useState(1);

  const PAGE_SIZE = 25;

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [listRes, statsRes] = await Promise.all([
        api.getNotifications({
          status: statusFilter === "all" ? undefined : statusFilter,
          limit: PAGE_SIZE,
          offset: (page - 1) * PAGE_SIZE,
        }),
        api.getNotificationStats(),
      ]);
      setItems(listRes.items || []);
      setTotal(listRes.total || 0);
      setStats(statsRes);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, page]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRetry = async (id) => {
    setRetrying(id);
    try {
      await api.retryNotification(id);
      await fetchData();
    } catch (e) {
      setError(e.message);
    } finally {
      setRetrying(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div style={{ maxWidth: "1200px", padding: "24px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
        <h1 style={{ margin: 0, fontSize: "22px", fontWeight: 800 }}>Notifications</h1>
        <button
          onClick={fetchData}
          style={{
            padding: "8px 16px",
            borderRadius: "6px",
            border: "1px solid #d1d5db",
            background: "#fff",
            cursor: "pointer",
            fontWeight: 600,
            fontSize: "13px",
          }}
        >
          Refresh
        </button>
      </div>

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px", marginBottom: "20px" }}>
        {[
          { label: "Total", value: stats.total, color: "#2563eb", bg: "#eff6ff" },
          { label: "Pending", value: stats.pending, color: "#f59e0b", bg: "#fffbeb" },
          { label: "Sent", value: stats.sent, color: "#10b981", bg: "#ecfdf5" },
          { label: "Failed", value: stats.failed, color: "#dc2626", bg: "#fef2f2" },
        ].map((s) => (
          <div key={s.label} style={{ background: s.bg, borderRadius: "10px", padding: "16px", border: "1px solid #e5e7eb" }}>
            <div style={{ fontSize: "12px", fontWeight: 600, color: "#6b7280" }}>{s.label}</div>
            <div style={{ fontSize: "24px", fontWeight: 800, color: s.color, marginTop: "4px" }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
        {["all", "pending", "sent", "failed"].map((tab) => (
          <button
            key={tab}
            onClick={() => { setStatusFilter(tab); setPage(1); }}
            style={statusFilter === tab ? TAB_ACTIVE : TAB_STYLE}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {error && (
        <div style={{ color: "#dc2626", background: "#fef2f2", padding: "12px 16px", borderRadius: "8px", marginBottom: "16px", fontSize: "14px" }}>
          {error}
        </div>
      )}

      <div style={{ background: "#fff", borderRadius: "10px", border: "1px solid #e5e7eb", overflow: "hidden" }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: "50px" }}>Loading…</div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
            <thead>
              <tr style={{ background: "#f9fafb", borderBottom: "1px solid #e5e7eb" }}>
                {["ID", "Channel", "Recipient", "Subject", "Status", "Created", "Sent", "Error", "Action"].map((h) => (
                  <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontWeight: 600, color: "#374151", fontSize: "12px" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: "center", padding: "40px", color: "#6b7280" }}>
                    No notifications found.
                  </td>
                </tr>
              ) : (
                items.map((item) => {
                  let status = "pending";
                  if (item.error) status = "failed";
                  else if (item.sent_at) status = "sent";

                  return (
                    <tr key={item.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                      <td style={{ padding: "10px 14px", color: "#6b7280" }}>{item.id}</td>
                      <td style={{ padding: "10px 14px" }}>{item.channel}</td>
                      <td style={{ padding: "10px 14px" }}>{item.recipient}</td>
                      <td style={{ padding: "10px 14px", maxWidth: "200px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {item.subject || "—"}
                      </td>
                      <td style={{ padding: "10px 14px" }}>
                        <StatusBadge status={status} />
                      </td>
                      <td style={{ padding: "10px 14px", color: "#6b7280", whiteSpace: "nowrap" }}>
                        {item.created_at ? new Date(item.created_at).toLocaleString() : "—"}
                      </td>
                      <td style={{ padding: "10px 14px", color: "#6b7280", whiteSpace: "nowrap" }}>
                        {item.sent_at ? new Date(item.sent_at).toLocaleString() : "—"}
                      </td>
                      <td style={{ padding: "10px 14px", color: "#dc2626", maxWidth: "150px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {item.error || "—"}
                      </td>
                      <td style={{ padding: "10px 14px" }}>
                        {status === "failed" && (
                          <button
                            onClick={() => handleRetry(item.id)}
                            disabled={retrying === item.id}
                            style={{
                              padding: "4px 10px",
                              borderRadius: "4px",
                              border: "none",
                              background: "#2563eb",
                              color: "#fff",
                              fontSize: "12px",
                              fontWeight: 600,
                              cursor: "pointer",
                              opacity: retrying === item.id ? 0.6 : 1,
                            }}
                          >
                            {retrying === item.id ? "Retrying…" : "Retry"}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        )}
      </div>

      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: "8px", marginTop: "18px" }}>
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
          <span style={{ padding: "6px 14px", fontSize: "14px", color: "#374151" }}>
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
    </div>
  );
}
