import React, { useState, useEffect, useCallback } from "react";
import { api } from "../api.js";

const MASK = "__JHM_SECRET_SET__";

const cardStyle = {
  background: "#fff",
  borderRadius: "10px",
  border: "1px solid #e5e7eb",
  padding: "20px",
  marginBottom: "16px",
};

const sectionTitle = {
  fontSize: "16px",
  fontWeight: 700,
  margin: "0 0 14px",
  color: "#111827",
};

const inputStyle = {
  padding: "8px 12px",
  borderRadius: "6px",
  border: "1px solid #d1d5db",
  fontSize: "14px",
  width: "100%",
  boxSizing: "border-box",
};

const btnPrimary = {
  padding: "8px 16px",
  borderRadius: "6px",
  border: "none",
  background: "#2563eb",
  color: "#fff",
  fontWeight: 600,
  cursor: "pointer",
  fontSize: "13px",
};

const btnSecondary = {
  padding: "8px 16px",
  borderRadius: "6px",
  border: "1px solid #d1d5db",
  background: "#fff",
  color: "#374151",
  fontWeight: 600,
  cursor: "pointer",
  fontSize: "13px",
};

const PROVIDERS = [
  { key: "anthropic_key", label: "Anthropic" },
  { key: "openai_key", label: "OpenAI" },
  { key: "groq_key", label: "Groq" },
  { key: "gemini_key", label: "Gemini" },
  { key: "nvidia_key", label: "NVIDIA" },
  { key: "deepseek_key", label: "DeepSeek" },
  { key: "azure_openai_key", label: "Azure OpenAI" },
  { key: "ollama_key", label: "Ollama" },
];

export default function SettingsPage() {
  const [settings, setSettings] = useState({});
  const [template, setTemplate] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [validation, setValidation] = useState(null);
  const [validating, setValidating] = useState(false);
  const [modelsMap, setModelsMap] = useState({});
  const [loadingModels, setLoadingModels] = useState({});

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [cfg, tpl] = await Promise.all([api.getSettings(), api.getTemplate()]);
      setSettings(cfg);
      setTemplate(tpl.template || "");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSaveSettings = async () => {
    const payload = {};
    for (const [key, value] of Object.entries(settings)) {
      if (value !== MASK) {
        payload[key] = value;
      }
    }
    setSaving(true);
    try {
      await api.saveSettings(payload);
      await fetchData();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveTemplate = async () => {
    setSavingTemplate(true);
    try {
      await api.saveTemplate({ template });
    } catch (e) {
      setError(e.message);
    } finally {
      setSavingTemplate(false);
    }
  };

  const handleValidate = async () => {
    setValidating(true);
    setValidation(null);
    try {
      const res = await api.validateSettings();
      setValidation(res);
    } catch (e) {
      setError(e.message);
    } finally {
      setValidating(false);
    }
  };

  const handleListModels = async (provider) => {
    setLoadingModels((prev) => ({ ...prev, [provider]: true }));
    try {
      const res = await api.getProviderModels(provider);
      setModelsMap((prev) => ({ ...prev, [provider]: res.models || [] }));
    } catch (e) {
      setModelsMap((prev) => ({ ...prev, [provider]: [] }));
    } finally {
      setLoadingModels((prev) => ({ ...prev, [provider]: false }));
    }
  };

  const updateField = (key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  if (loading) return <div style={{ padding: "40px", textAlign: "center" }}>Loading…</div>;

  return (
    <div style={{ maxWidth: "900px", padding: "24px" }}>
      <h1 style={{ margin: "0 0 20px", fontSize: "22px", fontWeight: 800 }}>Settings</h1>

      {error && (
        <div style={{ color: "#dc2626", background: "#fef2f2", padding: "12px 16px", borderRadius: "8px", marginBottom: "16px", fontSize: "14px" }}>
          {error}
        </div>
      )}

      {/* LLM Provider Keys */}
      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
          <h2 style={sectionTitle}>LLM Provider Keys</h2>
          <div style={{ display: "flex", gap: "8px" }}>
            <button onClick={handleValidate} disabled={validating} style={{ ...btnSecondary, opacity: validating ? 0.6 : 1 }}>
              {validating ? "Validating…" : "Validate Keys"}
            </button>
            <button onClick={handleSaveSettings} disabled={saving} style={{ ...btnPrimary, opacity: saving ? 0.6 : 1 }}>
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>

        {validation && (
          <div style={{ marginBottom: "14px", display: "flex", flexWrap: "wrap", gap: "8px" }}>
            {Object.entries(validation).map(([provider, result]) => {
              const color =
                result.status === "ok"
                  ? "#10b981"
                  : result.status === "not_configured"
                  ? "#6b7280"
                  : result.status === "invalid_key"
                  ? "#dc2626"
                  : "#f59e0b";
              return (
                <div key={provider} style={{ padding: "6px 12px", borderRadius: "6px", background: "#f9fafb", border: "1px solid #e5e7eb", fontSize: "13px" }}>
                  <strong style={{ textTransform: "capitalize" }}>{provider}</strong>{" "}
                  <span style={{ color, fontWeight: 600 }}>{result.status}</span>
                  {result.latency_ms > 0 && <span style={{ color: "#6b7280" }}> ({result.latency_ms}ms)</span>}
                </div>
              );
            })}
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {PROVIDERS.map((p) => {
            const value = settings[p.key] || "";
            const isMasked = value === MASK;
            return (
              <div key={p.key} style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <label style={{ fontSize: "13px", fontWeight: 600, color: "#374151" }}>{p.label}</label>
                  <button
                    onClick={() => handleListModels(p.label.toLowerCase().replace(" ", "_").replace("azure_", ""))}
                    disabled={loadingModels[p.label] || (!value && !isMasked)}
                    style={{ ...btnSecondary, padding: "4px 10px", fontSize: "12px" }}
                  >
                    {loadingModels[p.label] ? "Loading…" : "List Models"}
                  </button>
                </div>
                <input
                  style={inputStyle}
                  type="password"
                  value={isMasked ? "••••••••••••••••••••" : value}
                  placeholder={isMasked ? "Key is set (leave blank to keep)" : "Enter API key"}
                  onChange={(e) => updateField(p.key, e.target.value)}
                />
                {modelsMap[p.label] && (
                  <div style={{ fontSize: "12px", color: "#6b7280", background: "#f9fafb", padding: "8px", borderRadius: "6px", maxHeight: "120px", overflow: "auto" }}>
                    {modelsMap[p.label].length > 0 ? modelsMap[p.label].join(", ") : "No models found."}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* General Settings */}
      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
          <h2 style={sectionTitle}>General</h2>
          <button onClick={handleSaveSettings} disabled={saving} style={{ ...btnPrimary, opacity: saving ? 0.6 : 1 }}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          {Object.entries(settings)
            .filter(([key]) => !PROVIDERS.some((p) => p.key === key) && !key.includes("_key") && !key.includes("_token") && key !== "resume_template")
            .map(([key, value]) => (
              <div key={key}>
                <label style={{ fontSize: "12px", color: "#6b7280", fontWeight: 600, display: "block", marginBottom: "4px" }}>{key}</label>
                {typeof value === "boolean" || value === "true" || value === "false" ? (
                  <select style={inputStyle} value={String(value)} onChange={(e) => updateField(key, e.target.value === "true")}>
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                ) : (
                  <input style={inputStyle} value={String(value || "")} onChange={(e) => updateField(key, e.target.value)} />
                )}
              </div>
            ))}
        </div>
      </div>

      {/* Resume Template */}
      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
          <h2 style={sectionTitle}>Resume Template</h2>
          <button onClick={handleSaveTemplate} disabled={savingTemplate} style={{ ...btnPrimary, opacity: savingTemplate ? 0.6 : 1 }}>
            {savingTemplate ? "Saving…" : "Save Template"}
          </button>
        </div>
        <textarea
          style={{ ...inputStyle, minHeight: "300px", fontFamily: "monospace", fontSize: "13px", resize: "vertical" }}
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
        />
      </div>
    </div>
  );
}
