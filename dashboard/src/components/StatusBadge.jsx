const STATUS_COLORS = {
  discovered: { bg: "#e5e7eb", text: "#374151", label: "Discovered" },
  evaluating: { bg: "#dbeafe", text: "#1e40af", label: "Evaluating" },
  program_matched: { bg: "#fef3c7", text: "#92400e", label: "Needs Approval" },
  program_approved: { bg: "#d1fae5", text: "#065f46", label: "Approved" },
  tailoring: { bg: "#d1fae5", text: "#065f46", label: "Ready to Generate" },
  applied: { bg: "#ede9fe", text: "#5b21b6", label: "Applied" },
  discarded: { bg: "#fee2e2", text: "#991b1b", label: "Discarded" },
};

export default function StatusBadge({ status }) {
  const s = (status || "discovered").toLowerCase();
  const config = STATUS_COLORS[s] || STATUS_COLORS.discovered;
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
