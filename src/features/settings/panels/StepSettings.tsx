import type { Cfg } from "./shared";
import { SectionLabel, STEPS, StepCard } from "./shared";
import type { ApiFetch } from "../../../types";

export function StepSettings({ cfg, onChange, api }: { cfg: Cfg; onChange: (k: keyof Cfg, v: string) => void; api?: ApiFetch | null }) {
  return (
    <>
{/* 2. Per-step */}
          <div>
            <SectionLabel label="Per-Step Configuration" sub="reuse the global key, or give any step its own provider, key & model" />
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {STEPS.map(step => <StepCard key={step.id} step={step} cfg={cfg} onChange={onChange} api={api} />)}
            </div>
          </div>
    </>
  );
}
