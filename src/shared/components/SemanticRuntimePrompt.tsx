import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { relaunch } from "@tauri-apps/plugin-process";
import type { ApiFetch } from "../../types";
import { runtimeApi } from "../../api";

type RuntimeProgress = {
  status?: string;
  message?: string;
  percent?: number;
  downloaded?: number;
  total?: number;
  error?: string;
  active?: boolean;
  started_at?: number | null;
  updated_at?: number | null;
};

type RuntimePayload = {
  ready?: boolean;
  required?: boolean;
  restart_required?: boolean;
  runtime?: {
    status?: string;
    ready?: boolean;
    asset?: string;
    dir?: string;
    url?: string;
    restart_required?: boolean;
  };
  vector?: {
    status?: string;
    error?: string;
    restart_required?: boolean;
  };
  progress?: RuntimeProgress;
  sync?: {
    status?: string;
    synced?: number;
    error?: string;
  };
  install_error?: string;
};

type PromptState = "checking" | "waiting" | "required" | "installing" | "restart_required" | "restarting" | "ready" | "error";

const ACTIVE_PROGRESS = new Set(["starting", "downloading", "extracting", "copying", "verifying", "syncing"]);
const RUNTIME_STATUS_TIMEOUT_MS = 90000;

function isActiveProgress(progress?: RuntimeProgress) {
  return Boolean(progress?.active || (progress?.status && ACTIVE_PROGRESS.has(progress.status)));
}

function runtimeNeedsRestart(payload: RuntimePayload | null) {
  return Boolean(
    payload?.restart_required ||
    payload?.runtime?.restart_required ||
    payload?.vector?.restart_required,
  );
}

function isBackendConnectivityError(message: string) {
  const normalized = message.toLowerCase();
  return normalized.includes("local backend timed out") || normalized.includes("local backend is unreachable") || normalized.includes("failed to fetch");
}

function bannerMessage(state: PromptState, payload: RuntimePayload | null, error: string) {
  if (state === "waiting") {
    return error
      ? `${error} Retrying automatically.`
      : "Waiting for local backend to start.";
  }
  if (state === "installing") {
    const progress = payload?.progress;
    if (!progress) return "Installing runtime pack…";
    const message = progress.message || "Installing runtime pack…";
    const percent = Number.isFinite(progress.percent) ? Math.min(100, Math.max(0, Math.round(progress.percent || 0))) : null;
    if (percent !== null && percent > 0) return `${message} ${percent}%`;
    return message;
  }
  if (state === "restart_required") {
    return error || payload?.vector?.error || "Runtime pack installed. Restart to finish loading.";
  }
  if (state === "restarting") {
    return "Reopening JustHireMe…";
  }
  if (error) return error;
  return "Runtime pack required for semantic matching.";
}

export function SemanticRuntimePrompt({ api }: { api: ApiFetch }) {
  const [state, setState] = useState<PromptState>("checking");
  const [payload, setPayload] = useState<RuntimePayload | null>(null);
  const [error, setError] = useState("");
  const [dismissed, setDismissed] = useState(false);
  const stateRef = useRef<PromptState>("checking");
  const installInFlightRef = useRef(false);
  const readyDispatchedRef = useRef(false);
  const statusRequestRef = useRef(0);
  const consecutiveStatusFailuresRef = useRef(0);

  const updateState = useCallback((next: PromptState) => {
    stateRef.current = next;
    setState(next);
    // Un-dismiss when something important happens
    if (next === "restart_required" || next === "error") {
      setDismissed(false);
    }
  }, []);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const markReady = useCallback(() => {
    updateState("ready");
    if (readyDispatchedRef.current) return;
    readyDispatchedRef.current = true;
    window.dispatchEvent(new CustomEvent("subsystems-refresh"));
    window.dispatchEvent(new CustomEvent("graph-refresh"));
  }, [updateState]);

  const applyPayload = useCallback((next: RuntimePayload) => {
    consecutiveStatusFailuresRef.current = 0;
    setPayload(next);
    setError("");

    if (next.ready) {
      markReady();
      return;
    }
    if (isActiveProgress(next.progress)) {
      updateState("installing");
      return;
    }
    if (runtimeNeedsRestart(next)) {
      updateState("restart_required");
      return;
    }
    if (next.required === false || next.runtime?.ready) {
      markReady();
      return;
    }
    if (next.progress?.status === "error") {
      setError(next.progress.error || next.progress.message || next.install_error || "Runtime install failed.");
      updateState("error");
      return;
    }
    updateState("required");
  }, [markReady, updateState]);

  const loadStatus = useCallback(async () => {
    const requestId = statusRequestRef.current + 1;
    statusRequestRef.current = requestId;
    try {
      const response = await runtimeApi.vector(api, { timeoutMs: RUNTIME_STATUS_TIMEOUT_MS });
      if (!response.ok) throw new Error(`Runtime check failed with HTTP ${response.status}.`);
      const next = await response.json() as RuntimePayload;
      if (requestId !== statusRequestRef.current) return;
      applyPayload(next);
    } catch (err) {
      if (requestId !== statusRequestRef.current) return;
      const message = err instanceof Error ? err.message : String(err);
      consecutiveStatusFailuresRef.current += 1;
      setError(message);
      if (stateRef.current === "installing" && consecutiveStatusFailuresRef.current < 4) {
        return;
      }
      updateState(isBackendConnectivityError(message) ? "waiting" : "error");
    }
  }, [api, applyPayload, updateState]);

  useEffect(() => {
    let cancelled = false;
    let timer = 0;

    const tick = async () => {
      await loadStatus();
      if (cancelled) return;
      const current = stateRef.current;
      const delay = current === "installing" ? 1000 : current === "waiting" || current === "checking" ? 2500 : 30000;
      timer = window.setTimeout(tick, delay);
    };

    void tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [loadStatus]);

  const install = async () => {
    if (installInFlightRef.current || stateRef.current === "installing") return;
    installInFlightRef.current = true;
    statusRequestRef.current += 1;
    updateState("installing");
    setError("");
    setDismissed(false);
    try {
      const response = await runtimeApi.installVector(api, { timeoutMs: 30000 });
      const next = await response.json().catch(() => ({})) as RuntimePayload & { detail?: string };
      if (!response.ok) throw new Error(next.detail || `Runtime install failed with HTTP ${response.status}.`);
      applyPayload(next);
      window.setTimeout(() => {
        void loadStatus();
      }, 600);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      updateState(isBackendConnectivityError(message) ? "waiting" : "error");
    } finally {
      installInFlightRef.current = false;
    }
  };

  const restartApp = async () => {
    updateState("restarting");
    setError("");
    try {
      await relaunch();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      updateState("restart_required");
    }
  };

  const message = useMemo(() => bannerMessage(state, payload, error), [state, payload, error]);
  const progress = payload?.progress;
  const progressPercent = Number.isFinite(progress?.percent) ? Math.min(100, Math.max(0, Math.round(progress?.percent || 0))) : null;
  const needsRestart = runtimeNeedsRestart(payload);
  const isBusy = state === "checking" || state === "waiting" || state === "installing" || state === "restarting";
  const canInstall = !needsRestart && (state === "required" || (state === "error" && Boolean(payload) && payload?.required !== false));

  // Don't render when ready, dismissed, or still checking
  if (state === "ready") return null;
  if (dismissed && state !== "restart_required" && state !== "error") return null;
  if (state === "checking") return null;

  return (
    <div className="semantic-runtime-banner" role="status" aria-live="polite">
      <div className="semantic-runtime-banner-content">
        <div className="semantic-runtime-banner-icon" aria-hidden="true">S</div>
        <div className="semantic-runtime-banner-text">
          <span className={state === "error" ? "update-error" : undefined}>{message}</span>
        </div>
        {isBusy && state === "installing" && (
          <div className={`semantic-runtime-banner-progress ${progressPercent === null ? "is-indeterminate" : ""}`}>
            <div style={progressPercent !== null ? { width: `${progressPercent}%` } : undefined} />
          </div>
        )}
        <div className="semantic-runtime-banner-actions">
          {needsRestart && (
            <button className="btn btn-accent btn-sm" onClick={() => void restartApp()} disabled={state === "restarting"}>
              {state === "restarting" ? "Restarting…" : "Restart"}
            </button>
          )}
          {canInstall && (
            <button className="btn btn-accent btn-sm" onClick={install} disabled={isBusy}>
              Install
            </button>
          )}
          {(state === "waiting" || state === "error") && (
            <button className="btn btn-ghost btn-sm" onClick={() => void loadStatus()}>
              Retry
            </button>
          )}
          {!needsRestart && state !== "error" && (
            <button
              className="btn btn-ghost btn-sm semantic-runtime-dismiss"
              onClick={() => setDismissed(true)}
              aria-label="Dismiss"
            >
              ✕
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
