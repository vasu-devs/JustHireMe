import { useEffect, useState } from "react";
import Icon from "../../shared/components/Icon";
import { AutomationSettings } from "./panels/AutomationSettings";
import { DiscoverySettings } from "./panels/DiscoverySettings";
import { GlobalSettings } from "./panels/GlobalSettings";
import { ResumeTemplatesPanel } from "./panels/ResumeTemplatesPanel";
import { StepSettings } from "./panels/StepSettings";
import { openUrl } from "@tauri-apps/plugin-opener";
import { EMPTY, type Cfg } from "./panels/shared";
import { SectionLabel } from "./panels/shared";
import { useTheme, type ThemePref } from "../../shared/lib/theme";
import { settingsApi } from "../../api/settings";
import type { ApiFetch } from "../../types";

const LEGAL_BASE = "https://github.com/vasu-devs/JustHireMe/blob/main/docs/legal";
const LEGAL_LINKS: { label: string; href: string }[] = [
  { label: "Terms of Use", href: `${LEGAL_BASE}/terms-of-use.md` },
  { label: "Privacy Policy", href: `${LEGAL_BASE}/privacy-policy.md` },
];

function LegalSettings() {
  return (
    <div>
      <SectionLabel label="Legal & Privacy" sub="JustHireMe is local-first — your data stays on this device" />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {LEGAL_LINKS.map(l => (
          <button key={l.href} className="btn ghost" onClick={() => openUrl(l.href)}
            style={{ fontSize: 12, padding: "7px 11px" }}>
            <Icon name="external" size={12} /> {l.label}
          </button>
        ))}
      </div>
    </div>
  );
}

interface Props { api: ApiFetch; onClose: () => void; }

const THEME_OPTIONS: { value: ThemePref; label: string; icon: string }[] = [
  { value: "light", label: "Light", icon: "sun" },
  { value: "dark", label: "Dark", icon: "moon" },
  { value: "system", label: "System", icon: "globe" },
];

function AppearanceSettings() {
  const { pref, setPref } = useTheme();
  return (
    <div>
      <SectionLabel label="Appearance" sub="theme used across the app — System follows your OS" />
      <div style={{ display: "flex", gap: 8 }}>
        {THEME_OPTIONS.map(opt => {
          const active = pref === opt.value;
          return (
            <button
              key={opt.value}
              onClick={() => setPref(opt.value)}
              aria-pressed={active}
              style={{
                flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                padding: "11px 12px", borderRadius: 11, fontSize: 13, fontWeight: 600, cursor: "pointer",
                background: active ? "var(--accent-soft)" : "var(--paper-2)",
                color: active ? "var(--accent)" : "var(--ink-2)",
                border: `1px solid ${active ? "var(--accent)" : "var(--line)"}`,
                transition: "background 140ms ease, border-color 140ms ease, color 140ms ease",
              }}
            >
              <Icon name={opt.icon} size={15} /> {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function DangerZone({ api }: { api: ApiFetch }) {
  const [open, setOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [clearSettings, setClearSettings] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const armed = confirmText.trim().toUpperCase() === "DELETE";

  const reset = async () => {
    if (!armed) return;
    setBusy(true);
    setError(null);
    try {
      const response = await settingsApi.resetData(api, { clearSettings });
      if (!response.ok) {
        const detail = await response.json().then(d => d.detail).catch(() => "");
        throw new Error(detail || "Reset failed");
      }
      // Reload so every view re-fetches the now-empty data and returns to a clean
      // first-run state.
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <div>
      <SectionLabel label="Danger zone" sub="Wipe local data to start fresh — this cannot be undone" />
      <div style={{ border: "1px solid var(--bad)", background: "var(--bad-soft, rgba(220,38,38,0.06))", borderRadius: 12, padding: 14 }}>
        {!open ? (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
            <div style={{ fontSize: 12.5, color: "var(--ink-2)", maxWidth: 460 }}>
              Delete all leads, your profile (graph + vectors), and generated documents on this device. Your settings and provider keys are kept.
            </div>
            <button className="btn" onClick={() => setOpen(true)}
              style={{ color: "var(--bad)", borderColor: "var(--bad)", fontSize: 13, padding: "8px 16px", whiteSpace: "nowrap" }}>
              <Icon name="trash" size={13} /> Delete all data
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ fontSize: 12.5, color: "var(--ink-2)" }}>
              <Icon name="alert" size={13} /> This permanently deletes all leads, your profile (graph + vectors), and generated PDFs on this device. Type <b>DELETE</b> to confirm.
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, color: "var(--ink-2)", cursor: "pointer" }}>
              <input type="checkbox" checked={clearSettings} onChange={e => setClearSettings(e.target.checked)} />
              Also reset settings &amp; provider config (full factory reset)
            </label>
            <input type="text" value={confirmText} onChange={e => setConfirmText(e.target.value)}
              placeholder="Type DELETE to confirm" autoFocus className="field-input" style={{ fontSize: 13 }} />
            {error && <div style={{ color: "var(--bad)", fontSize: 12, fontWeight: 700 }}>{error}</div>}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button className="btn" disabled={busy}
                onClick={() => { setOpen(false); setConfirmText(""); setError(null); setClearSettings(false); }}
                style={{ fontSize: 13, padding: "8px 16px" }}>Cancel</button>
              <button className="btn" onClick={reset} disabled={busy || !armed}
                style={{ background: "var(--bad)", color: "#fff", borderColor: "var(--bad)", fontSize: 13, padding: "8px 18px", opacity: (busy || !armed) ? 0.55 : 1 }}>
                <Icon name="trash" size={13} /> {busy ? "Deleting..." : clearSettings ? "Delete everything" : "Delete all data"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

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
          <AppearanceSettings />
          <GlobalSettings cfg={cfg} set={set} onChange={onChange} prov={prov} api={api} />
          <ResumeTemplatesPanel api={api} />
          <StepSettings cfg={cfg} onChange={onChange} api={api} />
          <DiscoverySettings cfg={cfg} set={set} onChange={onChange} />
          <AutomationSettings cfg={cfg} onChange={onChange} />
          <LegalSettings />
          <DangerZone api={api} />
          <div style={{ height: 6 }} />
        </div>

        <div style={{ padding: "14px 24px", borderTop: "1px solid var(--line)", background: "var(--paper-2)", display: "flex", justifyContent: "flex-end", gap: 10 }}>
          {saveError && <div style={{ marginRight: "auto", alignSelf: "center", color: "var(--bad)", fontSize: 12, fontWeight: 700 }}>{saveError}</div>}
          <button className="btn" onClick={onClose} style={{ padding: "9px 20px", fontSize: 13, borderRadius: 10 }}>Cancel</button>
          <button className="btn btn-accent" onClick={save} disabled={saving} style={{ padding: "9px 26px", fontSize: 13, borderRadius: 10, minWidth: 110 }}>
            {saved ? "Saved" : saving ? "Saving..." : "Save settings"}
          </button>
        </div>
      </div>
    </>
  );
}
