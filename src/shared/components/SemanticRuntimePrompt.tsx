import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { relaunch } from "@tauri-apps/plugin-process";
import type { ApiFetch } from "../../types";

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

function formatBytes(value: number) {
  if (!value) return "0 MB";
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDuration(seconds: number) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "a moment";
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))}s`;
  return `${Math.round(seconds / 60)} min`;
}

function isActiveProgress(progress?: RuntimeProgress) {
  return Boolean(progress?.active || (progress?.status && ACTIVE_PROGRESS.has(progress.status)));
}

function isPyo3RestartMessage(message?: string) {
  return Boolean(message?.toLowerCase().includes("initialized once per interpreter"));
}

function runtimeNeedsRestart(payload: RuntimePayload | null) {
  return Boolean(
    payload?.restart_required ||
    payload?.runtime?.restart_required ||
    payload?.vector?.restart_required ||
    isPyo3RestartMessage(payload?.install_error) ||
    isPyo3RestartMessage(payload?.progress?.error),
  );
}

function isBackendConnectivityError(message: string) {
  const normalized = message.toLowerCase();
  return normalized.includes("local backend timed out") || normalized.includes("local backend is unreachable") || normalized.includes("failed to fetch");
}

function statusMessage(state: PromptState, payload: RuntimePayload | null, error: string) {
  if (state === "waiting") {
    return error
      ? `${error} Retrying automatically while the local backend starts.`
      : "Waiting for the local backend to start before installing the required runtime pack.";
  }
  if (state === "installing") {
    return payload?.progress?.message || "Installing LanceDB, PyArrow, embeddings, and Playwright Chromium.";
  }
  if (state === "restart_required") {
    return error || payload?.vector?.error || "The runtime pack installed successfully. Restart JustHireMe to finish loading native vector search.";
  }
  if (state === "restarting") {
    return "Reopening JustHireMe so native vector search can load cleanly.";
  }
  if (error) return error;
  const vectorError = payload?.vector?.error || payload?.install_error;
  if (vectorError) return vectorError;
  const asset = payload?.runtime?.asset || "JustHireMe runtime pack";
  return `${asset} installs LanceDB, vector search support, the local embedder, and Playwright Chromium in one download.`;
}

function progressLabel(state: PromptState, progress: RuntimeProgress | undefined, now: number) {
  if (state === "checking") return "Checking required runtime pack.";
  if (state === "waiting") return "Waiting for the local backend; retrying every few seconds.";
  if (state === "restarting") return "Reopening JustHireMe.";
  if (!progress) return "Preparing JustHireMe runtime pack.";

  const message = progress.message || "Installing JustHireMe runtime pack.";
  const percent = Number.isFinite(progress.percent) ? Math.min(100, Math.max(0, Math.round(progress.percent || 0))) : null;
  const downloaded = progress.downloaded || 0;
  const total = progress.total || 0;
  const startedAt = progress.started_at ? progress.started_at * 1000 : 0;
  const elapsedSeconds = startedAt ? Math.max(1, (now - startedAt) / 1000) : 0;
  const bytesPerSecond = elapsedSeconds > 0 && downloaded > 0 ? downloaded / elapsedSeconds : 0;
  const etaSeconds = total && bytesPerSecond > 0 ? Math.max(0, (total - downloaded) / bytesPerSecond) : null;

  if (total && downloaded) {
    const eta = etaSeconds !== null ? `, about ${formatDuration(etaSeconds)} left` : "";
    return `${message} ${percent ?? 0}% - ${formatBytes(downloaded)} of ${formatBytes(total)}${eta}`;
  }
  if (downloaded) return `${message} ${formatBytes(downloaded)} downloaded - estimating time remaining.`;
  if (percent !== null && percent > 0) return `${message} ${percent}%.`;
  return message;
}

export function SemanticRuntimePrompt({ api }: { api: ApiFetch }) {
  const [state, setState] = useState<PromptState>("checking");
  const [payload, setPayload] = useState<RuntimePayload | null>(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  const stateRef = useRef<PromptState>("checking");
  const installInFlightRef = useRef(false);
  const readyDispatchedRef = useRef(false);
  const statusRequestRef = useRef(0);
  const consecutiveStatusFailuresRef = useRef(0);

  const updateState = useCallback((next: PromptState) => {
    stateRef.current = next;
    setState(next);
  }, []);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    if (state !== "installing") return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
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
      setError(next.progress.error || next.progress.message || next.install_error || "Resume matching runtime install failed.");
      updateState("error");
      return;
    }
    updateState("required");
  }, [markReady, updateState]);

  const loadStatus = useCallback(async () => {
    const requestId = statusRequestRef.current + 1;
    statusRequestRef.current = requestId;
    try {
      const response = await api("/api/v1/runtime/vector", { timeoutMs: 15000 });
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
    setNow(Date.now());
    try {
      const response = await api("/api/v1/runtime/vector/install", { method: "POST", timeoutMs: 30000 });
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

  const message = useMemo(() => statusMessage(state, payload, error), [state, payload, error]);
  const label = useMemo(() => progressLabel(state, payload?.progress, now), [state, payload?.progress, now]);
  const progress = payload?.progress;
  const progressPercent = Number.isFinite(progress?.percent) ? Math.min(100, Math.max(0, Math.round(progress?.percent || 0))) : null;
  const needsRestart = runtimeNeedsRestart(payload);
  const isBusy = state === "checking" || state === "waiting" || state === "installing" || state === "restarting";
  const canInstall = !needsRestart && (state === "required" || (state === "error" && Boolean(payload) && payload?.required !== false));
  const title = state === "waiting" ? "Starting local service" : needsRestart || state === "restarting" ? "Restart JustHireMe" : "Install required runtime pack";

  if (state === "ready") return null;

  return (
    <div className="semantic-runtime-backdrop" role="presentation">
      <section className="semantic-runtime-dialog" role="dialog" aria-modal="true" aria-labelledby="semantic-runtime-title">
        <div className="semantic-runtime-mark" aria-hidden="true">S</div>
        <div>
          <div className="eyebrow">Required runtime pack</div>
          <h2 id="semantic-runtime-title">{title}</h2>
          <p className={state === "error" ? "update-error" : undefined}>{message}</p>
          {isBusy && (
            <div className={`update-progress ${progressPercent === null || state !== "installing" ? "is-indeterminate" : ""}`}>
              <div style={progressPercent !== null && state === "installing" ? { width: `${progressPercent}%` } : undefined} />
              <span>{label}</span>
            </div>
          )}
          {payload?.sync?.status === "ok" && (
            <p className="semantic-runtime-note">Identity graph vectors synced: {payload.sync.synced ?? 0}</p>
          )}
        </div>
        <div className="semantic-runtime-actions">
          {needsRestart && (
            <button className="btn btn-accent" onClick={() => void restartApp()} disabled={state === "restarting"}>
              {state === "restarting" ? "Restarting..." : "Restart"}
            </button>
          )}
          {canInstall && (
            <button className="btn btn-accent" onClick={install} disabled={isBusy}>
              Install now
            </button>
          )}
          {(state === "waiting" || state === "error") && (
            <button className="btn btn-ghost" onClick={() => void loadStatus()}>
              Retry check
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
