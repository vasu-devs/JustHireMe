import React from "react";
import { Link, useLocation } from "react-router-dom";

const NAV = [
  { path: "/leads", label: "Leads" },
  { path: "/profile", label: "Profile" },
  { path: "/notifications", label: "Notifications" },
  { path: "/settings", label: "Settings" },
];

export default function Sidebar() {
  const location = useLocation();
  const current = location.pathname;

  return (
    <aside
      style={{
        width: "220px",
        minHeight: "100vh",
        background: "#111827",
        color: "#f9fafb",
        padding: "24px 16px",
        flexShrink: 0,
      }}
    >
      <div
        style={{
          fontSize: "18px",
          fontWeight: 800,
          marginBottom: "32px",
          letterSpacing: "-0.5px",
        }}
      >
        JustHireMe
      </div>
      <nav style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {NAV.map((item) => {
          const active = current === item.path || current.startsWith(item.path + "/");
          return (
            <Link
              key={item.path}
              to={item.path}
              style={{
                padding: "10px 14px",
                borderRadius: "8px",
                fontSize: "14px",
                fontWeight: 600,
                textDecoration: "none",
                color: active ? "#fff" : "#9ca3af",
                background: active ? "#2563eb" : "transparent",
                transition: "background 0.15s",
              }}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
