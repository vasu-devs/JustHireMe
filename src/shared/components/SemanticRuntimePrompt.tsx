import { useCallback, useEffect, useMemo, useState } from "react";
import type { ApiFetch } from "../../types";

type RuntimePayload = {
  ready?: boolean;
  runtime?: {
    status?: string;
    asset?: string;
    dir?: string;
    url?: string;
  };
  vector?: {
    status?: string;
    error?: string;
  };
  sync?: {
    status?: string;
    synced?: number;
    error?: string;
  };
};

type PromptState = "checking" | "required" | "installing" | "ready" | "error";

function statusMessage(payload: RuntimePayload | null, error: string) {
  if (error) return error;
  const vectorError = payload?.vector?.error;
  if (vectorError) return vectorError;
  const asset = payload?.runtime?.asset || "semantic runtime";
  return `${asset} is required for resume matching and identity graph search.`;
}

export function SemanticRuntimePrompt({ api }: { api: ApiFetch }) {
  const [state, setState] = useState<PromptState>("checking");
  const [payload, setPayload] = useState<RuntimePayload | null>(null);
  const [error, setError] = useState("");

  const loadStatus = useCallback(async () => {
    try {
      const response = await api("/api/v1/runtime/vector", { timeoutMs: 15000 });
      if (!response.ok) throw new Error(`Runtime check failed with HTTP ${response.status}.`);
      const next = await response.json() as RuntimePayload;
      setPayload(next);
      setError("");
      setState(next.ready ? "ready" : "required");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setState("error");
    }
  }, [api]);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      if (cancelled) return;
      await loadStatus();
    };
    void check();
    const timer = window.setInterval(() => {
      if (state !== "installing") void check();
    }, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [loadStatus, state]);

  const install = async () => {
    setState("installing");
    setError("");
    try {
      const response = await api("/api/v1/runtime/vector/install", { method: "POST", timeoutMs: 10 * 60 * 1000 });
      const next = await response.json().catch(() => ({})) as RuntimePayload & { detail?: string };
      if (!response.ok) throw new Error(next.detail || `Runtime install failed with HTTP ${response.status}.`);
      setPayload(next);
      if (!next.ready) {
        throw new Error(next.vector?.error || "The semantic engine installed but did not become ready.");
      }
      setState("ready");
      window.dispatchEvent(new CustomEvent("subsystems-refresh"));
      window.dispatchEvent(new CustomEvent("graph-refresh"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setState("error");
    }
  };

  const message = useMemo(() => statusMessage(payload, error), [payload, error]);
  const isBusy = state === "checking" || state === "installing";

  if (state === "ready") return null;

  return (
    <div className="semantic-runtime-backdrop" role="presentation">
      <section className="semantic-runtime-dialog" role="dialog" aria-modal="true" aria-labelledby="semantic-runtime-title">
        <div className="semantic-runtime-mark" aria-hidden="true">S</div>
        <div>
          <div className="eyebrow">Required semantic engine</div>
          <h2 id="semantic-runtime-title">Install resume matching runtime</h2>
          <p>{message}</p>
          {isBusy && (
            <div className="update-progress is-indeterminate">
              <div />
              <span>{state === "installing" ? "Downloading and installing LanceDB, PyArrow, and vector search support." : "Checking semantic runtime."}</span>
            </div>
          )}
          {payload?.sync?.status === "ok" && (
            <p className="semantic-runtime-note">Identity graph vectors synced: {payload.sync.synced ?? 0}</p>
          )}
        </div>
        <div className="semantic-runtime-actions">
          <button className="btn btn-accent" onClick={install} disabled={isBusy}>
            {state === "installing" ? "Installing..." : "Install now"}
          </button>
          {state === "error" && (
            <button className="btn btn-ghost" onClick={() => void loadStatus()} disabled={isBusy}>
              Retry check
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
