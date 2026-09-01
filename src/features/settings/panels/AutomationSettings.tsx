import type { Cfg } from "./shared";
import { BigToggle, SectionLabel } from "./shared";

export function AutomationSettings({ cfg, onChange }: { cfg: Cfg; onChange: (k: keyof Cfg, v: string) => void }) {
  return (
    <div style={{ borderTop: "1px dashed var(--line)", paddingTop: 18 }}>
      <SectionLabel label="Browser Automation" sub="candidate-scoped safeguards" />
      <div style={{ fontSize: 12, color: "var(--ink-3)", lineHeight: 1.5, marginBottom: 10 }}>
        Guarded auto-apply is authorized per candidate in Opportunities. It submits only after eligibility, fit, profile, form-safety, duplicate, and daily-limit checks pass.
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <BigToggle active={cfg.ghost_mode === "true"} onToggle={() => onChange("ghost_mode", cfg.ghost_mode === "true" ? "false" : "true")}
          icon="ghost" tone="purple" label="Experimental Ghost Mode" badge={cfg.ghost_mode === "true" ? "lab on" : "off"}
          sub="Contributor lab for background runs; not part of the main OSS workflow" />
        <BigToggle active={cfg.auto_apply === "true"} onToggle={() => onChange("auto_apply", cfg.auto_apply === "true" ? "false" : "true")}
          icon="fire" tone="orange" label="Legacy Pipeline Submit" badge={cfg.auto_apply === "true" ? "enabled" : "off"}
          sub="Controls classic Pipeline Fire actions; candidate campaigns use their own explicit authorization" />
        <BigToggle active={cfg.headed_browser === "true"} onToggle={() => onChange("headed_browser", cfg.headed_browser === "true" ? "false" : "true")}
          icon="globe" tone="blue" label="Headed Browser" badge={cfg.headed_browser === "true" ? "visible" : "headless"}
          sub="Show the browser window while observing or debugging form automation" />
      </div>
    </div>
  );
}
