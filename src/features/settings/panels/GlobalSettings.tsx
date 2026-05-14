import { useEffect, useState } from "react";
import type { Cfg } from "./shared";
import { ApiKeyInput, GLOBAL_MODEL_FIELD, KEY_FIELD, ModelChips, ProviderPills, SectionLabel } from "./shared";
import type { ApiFetch } from "../../../types";

type KeyStatus = "ok" | "invalid_key" | "unreachable" | "not_configured" | "unchecked";
type ValidationResult = Record<string, { status: KeyStatus; latency_ms?: number }>;

export function GlobalSettings({ cfg, set, onChange, prov, api }: { cfg: Cfg; set: (k: keyof Cfg) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void; onChange: (k: keyof Cfg, v: string) => void; prov: string; api: ApiFetch }) {
  const [checking, setChecking] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [results, setResults] = useState<ValidationResult | null>(null);
  const [providerModels, setProviderModels] = useState<Record<string, string[]>>({});
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!results && !err) return;
    const timer = window.setTimeout(() => {
      setResults(null);
      setErr(null);
    }, 30000);
    return () => window.clearTimeout(timer);
  }, [results, err]);

  const checkKeys = async () => {
    setChecking(true);
    setErr(null);
    try {
      const r = await api("/api/v1/settings/validate");
      if (!r.ok) throw new Error(`Server returned ${r.status}`);
      setResults(await r.json());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Key validation failed");
    } finally {
      setChecking(false);
    }
  };
  const loadModels = async () => {
    setLoadingModels(true);
    setErr(null);
    try {
      const save = await api("/api/v1/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cfg),
      });
      if (!save.ok) throw new Error(`Could not save settings (${save.status})`);
      const r = await api(`/api/v1/settings/models/${prov}`);
      const data = await r.json();
      if (!r.ok) throw new Error(`Server returned ${r.status}`);
      if (data.error === "not_configured") {
        setProviderModels(prev => ({ ...prev, [prov]: [] }));
        setErr(`Model list needs a real ${prov} API key. Paste the key, then load again.`);
        return;
      }
      if (data.error) throw new Error(data.error);
      setProviderModels(prev => ({ ...prev, [prov]: Array.isArray(data.models) ? data.models : [] }));
    } catch (e) {
      setErr(e instanceof Error ? `Model list: ${e.message}` : "Model list failed");
    } finally {
      setLoadingModels(false);
    }
  };
  const globalModelField = GLOBAL_MODEL_FIELD[prov];

  const badgeStyle = (status: KeyStatus) => {
    const tone = status === "ok" ? "green" : status === "invalid_key" ? "bad" : status === "unreachable" ? "yellow" : "paper";
    if (tone === "bad") return { background: "var(--bad-soft)", color: "var(--bad)", border: "1px solid var(--bad)" };
    if (tone === "paper") return { background: "var(--paper-3)", color: "var(--ink-3)", border: "1px solid var(--line)" };
    return { background: `var(--${tone}-soft)`, color: `var(--${tone}-ink)`, border: `1px solid var(--${tone})` };
  };

  const label = (status: KeyStatus) => ({
    ok: "ok",
    invalid_key: "invalid key",
    unreachable: "unreachable",
    not_configured: "not set",
    unchecked: "unchecked",
  }[status]);

  return (
    <>
{/* 1. Global default */}
          <div>
            <SectionLabel label="Global Default" sub="fallback for any step not overridden" />
            <div style={{ padding: 16, borderRadius: 14, background: "var(--paper-2)", border: "1px solid var(--line)", display: "flex", flexDirection: "column", gap: 12 }}>
              <ProviderPills value={prov} onChange={v => onChange("llm_provider", v)} />
              {prov !== "ollama" && (
                <ApiKeyInput value={cfg[KEY_FIELD[prov]] as string} onChange={v => onChange(KEY_FIELD[prov], v)} provider={prov} />
              )}
              {prov === "ollama" && (
                <input type="text" placeholder="http://localhost:11434/v1" value={cfg.ollama_url} onChange={set("ollama_url")} className="mono field-input"
                  style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 12 }} />
              )}
              {prov === "custom" && (
                <input type="text" placeholder="https://api.example.com/v1" value={cfg.custom_base_url} onChange={set("custom_base_url")} className="mono field-input"
                  style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 12 }} />
              )}
              {prov === "azure" && (
                <input type="text" placeholder="https://your-resource.openai.azure.com" value={cfg.azure_openai_endpoint} onChange={set("azure_openai_endpoint")} className="mono field-input"
                  style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 12 }} />
              )}
              {globalModelField && (
                <div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 7 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Global Model</div>
                    {prov !== "ollama" && (
                      <button className="btn ghost" onClick={loadModels} disabled={loadingModels} style={{ fontSize: 11, padding: "5px 9px" }}>
                        {loadingModels ? "Loading..." : "Load models"}
                      </button>
                    )}
                  </div>
                  <ModelChips provider={prov} value={cfg[globalModelField] as string} onChange={v => onChange(globalModelField, v)} extraModels={providerModels[prov] || []} />
                </div>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                <button className="btn" onClick={checkKeys} disabled={checking} style={{ alignSelf: "flex-start", fontSize: 12 }}>
                  {checking ? "Checking keys..." : "Check keys"}
                </button>
                {checking && (
                  <div className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>Checking configured providers...</div>
                )}
                {err && <div style={{ fontSize: 12, color: "var(--bad)" }}>{err}</div>}
                {results && (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8 }}>
                    {Object.entries(results).map(([provider, result]) => (
                      <div key={provider} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, padding: "8px 10px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)" }}>
                        <span style={{ fontSize: 12, fontWeight: 700 }}>{provider}</span>
                        <span className="mono" style={{ fontSize: 10.5, padding: "2px 7px", borderRadius: 999, ...badgeStyle(result.status) }}>
                          {label(result.status)}{["ok", "unreachable"].includes(result.status) && result.latency_ms ? ` · ${result.latency_ms}ms` : ""}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
    </>
  );
}
