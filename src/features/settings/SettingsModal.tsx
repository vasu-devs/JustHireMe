import { useEffect, useState } from "react";
import Icon from "../../shared/components/Icon";
import { AutomationSettings } from "./panels/AutomationSettings";
import { DiscoverySettings } from "./panels/DiscoverySettings";
import { GlobalSettings } from "./panels/GlobalSettings";
import { StepSettings } from "./panels/StepSettings";
import { EMPTY, type Cfg } from "./panels/shared";
import type { ApiFetch } from "../../types";

interface Props { api: ApiFetch; onClose: () => void; }

export default function SettingsModal({ api, onClose }: Props) {
  const [cfg, setCfg]       = useState<Cfg>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved]   = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    api("/api/v1/settings")
      .then(r => r.json())
      .then(d => setCfg(c => ({ ...c, ...d })))
      .catch(() => {});
  }, [api]);

  const set = (k: keyof Cfg) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setCfg(c => ({ ...c, [k]: e.target.value }));

  const onChange = (k: keyof Cfg, v: string) => setCfg(c => ({ ...c, [k]: v }));

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const response = await api("/api/v1/settings", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cfg),
      });
      if (!response.ok) {
        const detail = await response.json().then(data => data.detail).catch(() => "");
        throw new Error(detail || "Settings could not be saved");
      }
      if (cfg.x_enable_notifications === "true" && "Notification" in window && Notification.permission === "default") {
        Notification.requestPermission().catch(() => {});
      }
      setSaved(true); setTimeout(() => setSaved(false), 2000);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : String(error));
    } finally { setSaving(false); }
  };

  const prov = cfg.llm_provider || "ollama";

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} style={{ zIndex: 100 }} />
      <div style={{ position: "fixed", top: "50%", left: "50%", transform: "translate(-50%, -50%)", width: "min(720px, 94vw)", maxHeight: "90vh", background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 22, boxShadow: "var(--shadow-lg)", zIndex: 101, overflow: "hidden", display: "flex", flexDirection: "column", animation: "slide-up .3s ease" }}>
        <div style={{ padding: "18px 24px", borderBottom: "1px solid var(--line)", background: "var(--blue-soft)", display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
          <div>
            <div className="eyebrow">Configuration</div>
            <h2 style={{ fontSize: 26, marginTop: 2 }}>Settings</h2>
            <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 3 }}>Configure local keys, scraper thresholds, ranker behavior, and customization models</div>
          </div>
          <button className="btn btn-icon" onClick={onClose}><Icon name="x" size={15} /></button>
        </div>

        <div className="scroll" style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 22 }}>
          <GlobalSettings cfg={cfg} set={set} onChange={onChange} prov={prov} api={api} />
          <StepSettings cfg={cfg} onChange={onChange} />
          <DiscoverySettings cfg={cfg} set={set} onChange={onChange} />
          <AutomationSettings cfg={cfg} onChange={onChange} />
          <div style={{ height: 6 }} />
        </div>

        <div style={{ padding: "14px 24px", borderTop: "1px solid var(--line)", background: "var(--paper-2)", display: "flex", justifyContent: "flex-end", gap: 10 }}>
          {saveError && <div style={{ marginRight: "auto", alignSelf: "center", color: "var(--bad)", fontSize: 12, fontWeight: 700 }}>{saveError}</div>}
          <button className="btn" onClick={onClose} style={{ padding: "9px 20px", fontSize: 13, borderRadius: 10 }}>Cancel</button>
          <button className="btn btn-accent" onClick={save} disabled={saving} style={{ padding: "9px 26px", fontSize: 13, borderRadius: 10, minWidth: 110 }}>
            {saved ? "? Saved" : saving ? "Saving?" : "Save settings"}
          </button>
        </div>
      </div>
    </>
  );
}
