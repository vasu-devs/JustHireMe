// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Vasudev Siddh and vasu-devs

import { useCallback, useEffect, useRef, useState } from "react";
import { discoveryApi } from "../../api";
import { createApiFetch } from "./api-client";
import type { ConnSt, LogLine, OperationProgress } from "../../types";

// Goes through discoveryApi (src/api/discovery.ts), not a raw fetch: every
// backend call has to route through src/api — src/api/api-layer.test.ts
// fails the build otherwise. createApiFetch's own args are unused (see
// api-client.ts) so the placeholders here are never actually sent anywhere.
const api = createApiFetch(0, "");

/**
 * Web replacement for shared/hooks/useWS.ts, aliased in vite.web.config.ts.
 *
 * The desktop hook learns its backend's port + bearer token from Tauri events
 * emitted by the Rust shell (`sidecar-port`/`sidecar-token`), then opens a
 * direct `ws://127.0.0.1:<port>/ws` connection authenticated with that real
 * token. None of that exists in a browser: there's no Tauri event bridge, and
 * putting the real token on the page would defeat the whole point of the dev
 * proxy's server-side token injection (see vite.web.config.ts).
 *
 * So this version:
 *  - returns constant, harmless `port`/`apiToken` placeholders. Real values
 *    would be meaningless here anyway — the aliased api client
 *    (web/shims/api-client.ts) ignores both and fetches paths relative to
 *    the page's own origin, which the dev proxy forwards with the real
 *    token attached server-side.
 *  - has no live WebSocket. `npm run web` already waits for the backend to
 *    report ready before starting Vite, so there's no startup race to gate
 *    on either — the app can render immediately.
 *  - polls discoveryApi.status (the same endpoint the desktop hook reconciles
 *    against on every WS reconnect) to keep `scanning`/`reevaluating`
 *    correct, via the same `backend-status` event App.tsx already listens
 *    for.
 *
 * ponytail: known ceiling — no live agent-event stream, so the scan progress
 * meter and the live field-log don't update mid-scan (only start/finish is
 * inferred, from the status transition). Add a real WS (proxied through
 * vite.web.config.ts with server-side token injection on the upgrade
 * request, mirroring the REST proxy) if that granularity is ever needed in
 * the browser.
 */
const POLL_MS = 3000;

const emptyProgress = (): OperationProgress => ({
  active: false,
  mode: null,
  total: 0,
  completed: 0,
  current: "",
  updatedAt: Date.now(),
});

type TaskStatus = { scanning?: boolean; reevaluating?: boolean };

export function useWS() {
  const [conn, setConn] = useState<ConnSt>("connecting");
  const [sidecarError, setSidecarError] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [beat, setBeat] = useState(0);
  const [progress, setProgress] = useState<OperationProgress>(() => emptyProgress());
  const idRef = useRef(0);
  const prevStatusRef = useRef<TaskStatus | null>(null);
  const failuresRef = useRef(0);

  const addLog = useCallback((msg: string, kind: LogLine["kind"], src = "sys") => {
    setLogs(p => [
      { id: idRef.current++, ts: String(idRef.current).padStart(4, "0"), msg, src, kind },
      ...p.slice(0, 149),
    ]);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const res = await discoveryApi.status(api, { headers: { "Cache-Control": "no-store" } });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const status = (await res.json()) as TaskStatus;
        if (cancelled) return;
        failuresRef.current = 0;
        setConn("connected");
        setSidecarError(null);
        window.dispatchEvent(new CustomEvent("backend-status", { detail: status }));
        if (!status.scanning && !status.reevaluating) setProgress(emptyProgress());

        const prev = prevStatusRef.current;
        if (prev?.scanning && !status.scanning) addLog("Scan finished.", "system", "scan");
        if (!prev?.scanning && status.scanning) addLog("Scan started.", "system", "scan");
        if (prev?.reevaluating && !status.reevaluating) addLog("Re-evaluation finished.", "system", "reeval");
        if (!prev?.reevaluating && status.reevaluating) addLog("Re-evaluation started.", "system", "reeval");
        prevStatusRef.current = status;
        setBeat(b => b + 1);
      } catch (err) {
        if (cancelled) return;
        failuresRef.current += 1;
        if (failuresRef.current >= 3) {
          setConn("disconnected");
          setSidecarError(err instanceof Error ? err.message : String(err));
        }
      }
    };

    void poll();
    const timer = window.setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [addLog]);

  const resetProgress = useCallback(() => setProgress(emptyProgress()), []);

  return {
    conn,
    port: 1,
    apiToken: "web",
    sidecarError,
    logs,
    beat,
    addLog,
    progress,
    resetProgress,
  };
}
