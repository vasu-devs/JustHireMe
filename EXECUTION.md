# JustHireMe v1.0.0 — Execution Plan

> **Goal:** Ship a stable, self-healing desktop app where scans don't silently break, the UI never freezes on stale state, and every failure is visible, logged, and recoverable.
>
> **Estimated total effort:** 7–10 focused days across 6 phases.
>
> **Current version:** 0.1.55 (alpha) → **Target:** 1.0.0 (stable)

---

## How to Read This Document

Each phase contains numbered items. Every item has:

- **Problem** — what's broken and why it hurts users.
- **Root Cause** — the exact code pattern causing it, with file paths and line numbers.
- **Fix** — what to change, specifically.
- **Acceptance Criteria** — how to verify the fix actually works.
- **Effort** — estimated time for implementation + testing.
- **Files** — every file that needs to be touched.

Phases are ordered by severity. **Phases 1–2 are ship-blockers** — nothing else matters until these are done. Phases 3–4 are high-value stability wins. Phases 5–6 separate "works" from "polished release."

---

## Phase 1: Connection Leaks & Silent Failures

**Why this phase exists:** The two most common user-reported issues — "database is locked" errors and "features just stop working silently" — both trace back to this phase. Every other fix is undermined if the database layer is leaking connections and errors are being swallowed.

**Phase effort:** ~1.5 days

---

### 1.1 SQLite Connections Are Never Pooled

**Problem:**
Every function in `data/sqlite/leads.py` calls `connect()` from `data/sqlite/connection.py`, which creates a brand-new `sqlite3.connect()` call. The connection is used for one operation and then closed in a `finally` block. This means:

- A scan that discovers 200 leads and evaluates them triggers 400+ connect/close cycles.
- Under concurrent `asyncio.to_thread()` calls (scan + WebSocket event recording + lead updates happening simultaneously), multiple threads open separate connections to the same database file.
- Even with WAL mode and `busy_timeout=5000`, the connection churn creates lock contention. The `busy_timeout` causes threads to wait up to 5 seconds, which cascades into WebSocket heartbeat timeouts.

This is the single biggest source of "database is locked" errors.

**Root Cause:**
```
data/sqlite/connection.py:67-73 — connect() creates a new sqlite3.connect() every call
data/sqlite/leads.py — every function (save_lead, get_all_leads, update_lead_score,
                        url_exists, get_lead_by_id, etc.) follows the pattern:
                            conn = connect(db_path)
                            try:
                                ... do work ...
                            finally:
                                conn.close()
```

There are 25+ functions in `leads.py` alone that each open and close their own connection. `events.py` and `settings.py` in the same directory follow the same pattern.

**Fix:**
Replace the per-call connect/close pattern with a thread-local singleton connection pool.

1. In `data/sqlite/connection.py`, add a `ConnectionPool` class:
   - Maintain a `threading.local()` storage with one connection per thread.
   - On first access per thread, create a connection with WAL mode, synchronous=NORMAL, and busy_timeout=5000.
   - Provide a `get_connection(db_path)` function that returns the thread-local connection (creating it if needed).
   - Add a `close_all()` function for shutdown cleanup.
   - Keep the existing `connect()` function for migrations (which need their own isolated connection).

2. In `data/sqlite/leads.py`, `data/sqlite/events.py`, and `data/sqlite/settings.py`:
   - Replace every `conn = connect(db_path)` / `try/finally/conn.close()` block with `conn = get_connection(db_path)`.
   - Remove the `finally: conn.close()` blocks — the pool manages lifecycle.
   - Keep explicit `conn.commit()` calls — autocommit is off by default.

3. In `api/app.py` or `main.py`, call `close_all()` during shutdown.

**Acceptance Criteria:**
- [ ] `grep -r "conn = connect(" backend/data/sqlite/` returns only `connection.py` (for migrations) — no other file creates raw connections.
- [ ] Run a scan with 50+ leads. Zero "database is locked" errors in logs.
- [ ] Run two concurrent API calls (e.g., lead update + event recording). No lock contention errors.
- [ ] New unit test: verify that `get_connection()` returns the same connection object when called twice from the same thread.
- [ ] New unit test: verify that `get_connection()` returns different connection objects from different threads.

**Files:**
- `backend/data/sqlite/connection.py` — add ConnectionPool
- `backend/data/sqlite/leads.py` — replace all connect() calls (~25 functions)
- `backend/data/sqlite/events.py` — replace all connect() calls
- `backend/data/sqlite/settings.py` — replace all connect() calls
- `backend/api/app.py` or `backend/main.py` — add shutdown hook
- `backend/tests/test_sqlite_pool.py` — new test file

**Effort:** 1 day

---

### 1.2 WebSocket Broadcast Swallows All Exceptions

**Problem:**
In `api/websocket.py`, the `broadcast()` method has two silent failure points:

1. **Lines 28–35:** When recording an agent event to SQLite, the entire operation is wrapped in `except Exception: pass`. If the database is locked (see 1.1), or if the repository import fails, or if the event data is malformed — nothing is logged. The event is silently lost.

2. **Lines 43–44:** When sending to an individual WebSocket client, failures cause the connection to be added to the `dead` list — but the actual exception (which could be a serialization error, a memory issue, or a protocol violation) is never logged.

This means when "features just stop working," there's literally no log trail to debug it. The broadcast looks successful from the caller's perspective.

**Root Cause:**
```python
# websocket.py:28-35
try:
    from api.dependencies import get_repository
    repo = get_repository()
    await asyncio.to_thread(repo.events.record_event, ...)
except Exception:
    pass  # ← every failure is invisible

# websocket.py:40-44
async def _send(ws: WebSocket) -> None:
    try:
        await asyncio.wait_for(ws.send_text(text), timeout=2.0)
    except Exception:
        dead.append(ws)  # ← connection removed but error never logged
```

**Fix:**

1. Replace `except Exception: pass` on lines 33–35 with:
   ```python
   except Exception as exc:
       _log.debug("event recording failed during broadcast: %s", exc)
   ```
   Use `debug` level — this is high-frequency and shouldn't spam production logs, but must be visible when debugging.

2. Replace the bare `except Exception` in `_send` (lines 43-44) with:
   ```python
   except Exception as exc:
       _log.debug("ws send failed (will remove dead connection): %s", exc)
       dead.append(ws)
   ```

3. Separate concerns: move the event recording out of the broadcast hot path. Event recording is a side effect — it shouldn't block or affect message delivery. Fire it as a background task:
   ```python
   async def broadcast(self, msg: dict):
       if msg.get("type") == "agent":
           asyncio.create_task(self._record_event(msg))
       # ... rest of broadcast logic unchanged
   ```

**Acceptance Criteria:**
- [ ] Zero `except Exception: pass` blocks remain in `websocket.py`.
- [ ] Force a database error during broadcast (e.g., delete the DB file temporarily). Verify the error appears in logs at debug level.
- [ ] Verify that a failed event recording does not prevent the WebSocket message from reaching connected clients.
- [ ] Existing WebSocket tests still pass.

**Files:**
- `backend/api/websocket.py` — fix exception handling, add logger, separate event recording

**Effort:** 30 minutes

---

### 1.3 Frontend WebSocket Message Parse Errors Silently Dropped

**Problem:**
In `src/shared/hooks/useWS.ts`, the `ws.onmessage` handler wraps the entire message processing in a `try/catch` that does nothing:

```typescript
// useWS.ts:98
} catch { /* ignore */ }
```

If the backend sends malformed JSON (which happens during sidecar crashes when partial output is flushed), or if the message structure doesn't match the expected `WSMessage` type (which happens when new event types are added to the backend but the frontend type isn't updated), the message is silently dropped.

The user sees the heartbeat counter freeze and has no idea what went wrong. The developer has no console output to debug with.

**Root Cause:**
```
src/shared/hooks/useWS.ts:69-98 — ws.onmessage handler
Line 98: catch { /* ignore */ }
```

**Fix:**
Replace the empty catch with a meaningful handler:

```typescript
} catch (err) {
  console.warn("[WS] Failed to parse message:", err, e.data?.slice?.(0, 200));
  addLog(`Message parse error: ${err}`, "system", "ws");
}
```

This logs to both the browser console (for developer debugging) and the in-app log panel (for user-visible diagnostics).

**Acceptance Criteria:**
- [ ] Send a malformed JSON string to the WebSocket. Verify a warning appears in the browser console.
- [ ] Verify the malformed message appears in the in-app log panel.
- [ ] Valid messages still process normally — no regression.

**Files:**
- `src/shared/hooks/useWS.ts` — replace empty catch block

**Effort:** 15 minutes

---

## Phase 2: Concurrency & Race Conditions

**Why this phase exists:** After fixing the silent failures in Phase 1, the next class of bugs is operations stepping on each other — duplicate scans, graph operations blocking the event loop, and frontend state getting stuck because it lost sync with the backend.

**Phase effort:** ~1.5 days

---

### 2.1 Global SCAN_TASK / REEVALUATE_TASK Lifecycle Is Raceable

**Problem:**
In `api/routers/discovery.py`, scan and reevaluation tasks are managed via global variables (`SCAN_TASK`, `REEVALUATE_TASK`) protected by asyncio locks (`_scan_lock`, `_reevaluate_lock`). The pattern is:

1. Acquire lock → check if task is running → create task → release lock.
2. Task runs to completion.
3. In the `finally` block of `run_scan_task` (line 247): `SCAN_TASK = None`.

The race: between step 1 (lock released after task creation) and step 3 (task finishes and clears the global), there's a window where a rapid second request could see `SCAN_TASK.done()` as `True` (if the task errored immediately) and create a duplicate task before the `finally` block runs and clears the reference.

Additionally, setting a module-level global from inside an async task's `finally` block without holding the lock means the cleanup isn't atomic with respect to the creation check.

**Root Cause:**
```python
# discovery.py:227-248
async def run_scan_task(...) -> None:
    global SCAN_TASK
    try:
        await run_scan(...)
    except Exception as exc:
        ...
    finally:
        SCAN_TASK = None  # ← this runs OUTSIDE the lock

# discovery.py:339-362
@router.post("/scan")
async def scan(...):
    global SCAN_TASK
    async with _scan_lock:                    # lock held here
        if SCAN_TASK and not SCAN_TASK.done():  # check here
            raise HTTPException(409, ...)
        SCAN_TASK = asyncio.create_task(...)   # create here
    return {"status": "scanning"}             # lock released, but SCAN_TASK
                                              # won't be None'd until finally
```

**Fix:**
Replace the global variable pattern with a `TaskRegistry` class that atomically manages task state:

```python
class TaskRegistry:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task] = {}
        self._stops: dict[str, asyncio.Event] = {}

    async def start(self, name: str, coro_factory, *, mutex_with: list[str] | None = None) -> bool:
        async with self._lock:
            # Check this task and any mutually exclusive tasks
            for check_name in [name] + (mutex_with or []):
                task = self._tasks.get(check_name)
                if task and not task.done():
                    return False  # Already running
            stop = asyncio.Event()
            self._stops[name] = stop

            async def _wrapper():
                try:
                    await coro_factory(stop)
                finally:
                    async with self._lock:
                        self._tasks.pop(name, None)
                        self._stops.pop(name, None)

            self._tasks[name] = asyncio.create_task(_wrapper())
            return True

    async def stop(self, name: str) -> bool:
        async with self._lock:
            stop = self._stops.get(name)
            if not stop:
                return False
            stop.set()
            return True

    async def is_running(self, name: str) -> bool:
        async with self._lock:
            task = self._tasks.get(name)
            return task is not None and not task.done()
```

The cleanup now happens inside the lock, atomically. No global variables. The stop events are co-located with the tasks they control.

**Acceptance Criteria:**
- [ ] No global `SCAN_TASK` or `REEVALUATE_TASK` variables remain in `discovery.py`.
- [ ] Rapid double-POST to `/api/v1/scan` returns 409 on the second call, every time. Test with `asyncio.gather(scan(), scan())`.
- [ ] Starting a scan while reevaluation is running returns 409 (mutual exclusion preserved).
- [ ] After a scan completes, the next scan starts cleanly — no stale state.
- [ ] After a scan errors, the next scan starts cleanly — no stale state.
- [ ] Existing tests in `test_api.py` and `test_regressions.py` pass.

**Files:**
- `backend/api/routers/discovery.py` — replace globals with TaskRegistry
- `backend/tests/test_task_registry.py` — new test file

**Effort:** 3 hours

---

### 2.2 Graph Database Operations Block the Async Event Loop

**Problem:**
In `data/graph/connection.py`, every graph operation acquires a `threading.RLock` (`_graph_lock`). This lock is held for the entire duration of each query execution. The `sync_profile_relationships()` function runs hundreds of sequential graph queries — each one acquiring and releasing the lock — and the whole function can take 5–30 seconds depending on profile complexity.

When this runs via `asyncio.to_thread()`, it occupies a thread from the default executor. Other graph operations (like `graph_counts()` for the dashboard, or `graph_snapshot()` for the graph view) also use `asyncio.to_thread()` and need the same lock. If the default thread pool (typically 5–8 threads) has multiple graph operations queued, they all serialize behind the lock.

The cascade: WebSocket heartbeats are sent every 2 seconds. If the event loop's thread pool is saturated with graph operations waiting on the lock, heartbeat sends can't be scheduled, the frontend's 2-second receive timeout fires, and the WebSocket appears dead.

**Root Cause:**
```python
# connection.py:36
_graph_lock = threading.RLock()

# connection.py:124-130
def execute_query(query: str, params: dict | None = None):
    if not _ensure_connection() or conn is None:
        return None
    with _graph_lock:  # ← held for every single query
        if params:
            return conn.execute(query, params)
        return conn.execute(query)

# connection.py:166-279
def sync_profile_relationships() -> dict:
    # ... runs 100-300 execute_query() calls sequentially
    # each one acquires and releases _graph_lock
    # total wall time: 5-30 seconds
```

**Fix:**

1. **Dedicated thread executor for graph operations.** Create a single-thread `ThreadPoolExecutor` exclusively for graph work. This ensures graph operations don't compete with SQLite or other I/O for the default pool:

   ```python
   import concurrent.futures
   _graph_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="kuzu")
   ```

   In the services that call graph operations, use:
   ```python
   await asyncio.get_event_loop().run_in_executor(_graph_executor, graph_function)
   ```

2. **Batch lock acquisition in sync_profile_relationships.** Instead of acquiring/releasing the lock per query, acquire it once for each logical batch (e.g., all project-skill links, all experience-skill links). This reduces lock acquisition overhead from 300 to ~10.

3. **Add a lock timeout.** Replace the bare `RLock` with a timeout-aware acquisition so operations fail fast instead of blocking indefinitely:
   ```python
   if not _graph_lock.acquire(timeout=10):
       _log.warning("graph lock acquisition timed out")
       return None
   try:
       return conn.execute(query, params)
   finally:
       _graph_lock.release()
   ```

**Acceptance Criteria:**
- [ ] WebSocket heartbeats never skip during a `sync_profile_relationships` run. Test by triggering a profile sync and monitoring heartbeat counter in the frontend.
- [ ] `graph_counts()` API call returns within 2 seconds even while a profile sync is running.
- [ ] No deadlocks — run profile sync + graph snapshot + graph counts concurrently. All complete.
- [ ] Lock timeout test: simulate a stuck lock. Verify the operation returns `None` after 10 seconds instead of blocking forever.

**Files:**
- `backend/data/graph/connection.py` — dedicated executor, batch locking, lock timeout
- `backend/profile/service.py` — use graph executor for sync calls
- `backend/api/routers/profile.py` — use graph executor for API calls

**Effort:** 3 hours

---

### 2.3 Frontend Scan State Desyncs From Backend After Any Disruption

**Problem:**
`AppContext.tsx` manages `scanning`, `reevaluating`, and `cleaning` as boolean state variables. These are set to `true` by the component that triggers the POST request, and set to `false` only when a specific WebSocket event arrives (`scan-done`, `reevaluate-done`, `cleanup-done`).

If any of these happen, the flag stays stuck at `true` forever:
- The WebSocket disconnects and reconnects (the "done" event was sent while disconnected).
- The sidecar crashes and restarts (the task died with the process; no "done" event ever fires).
- The user navigates away and back (component remounts with stale state from the event listener).

The user sees "Scanning..." permanently with no way to dismiss it except restarting the app.

**Root Cause:**
```
src/App.tsx — sets scanning=true on POST /scan, listens for CustomEvent "scan-done" to set false
src/shared/hooks/useWS.ts — fires CustomEvent "scan-done" only when ws.onmessage receives eval_done
src/shared/context/AppContext.tsx — pure state, no reconciliation logic
```

There is no mechanism for the frontend to ask the backend "are you actually running a scan right now?" and no mechanism to clear stale flags on reconnection.

**Fix:**

1. **Add a backend status endpoint:**
   ```python
   # In api/routers/discovery.py
   @router.get("/status")
   async def task_status():
       return {
           "scanning": SCAN_TASK is not None and not SCAN_TASK.done(),
           "reevaluating": REEVALUATE_TASK is not None and not REEVALUATE_TASK.done(),
       }
   ```
   (Or use the TaskRegistry from fix 2.1: `registry.is_running("scan")`)

2. **Poll status on WebSocket reconnect.** In `useWS.ts`, when the WebSocket `onopen` fires (after a reconnect, not the initial connect), fetch `/api/v1/status` and reconcile the frontend flags:
   ```typescript
   ws.onopen = () => {
     if (wsRef.current !== ws) return;
     setConn("connected");
     if (retryRef.current > 0) {
       // This is a reconnect, not initial connect — reconcile state
       fetch(`http://127.0.0.1:${p}/api/v1/status`, { headers: { Authorization: `Bearer ${token}` } })
         .then(r => r.json())
         .then(status => {
           window.dispatchEvent(new CustomEvent("backend-status", { detail: status }));
         })
         .catch(() => {});
     }
     retryRef.current = 0;
   };
   ```

3. **Listen for reconciliation events in App.tsx:**
   ```typescript
   useEffect(() => {
     const handler = (e: CustomEvent) => {
       setScanning(e.detail.scanning ?? false);
       setReevaluating(e.detail.reevaluating ?? false);
     };
     window.addEventListener("backend-status", handler);
     return () => window.removeEventListener("backend-status", handler);
   }, []);
   ```

4. **Add a safety timeout.** If `scanning` has been `true` for more than 15 minutes without any WebSocket progress event, auto-clear it with a warning log. No scan should ever take that long, so this catches truly stuck states.

**Acceptance Criteria:**
- [ ] Simulate: start a scan → kill the sidecar → restart the sidecar. The "Scanning..." indicator clears within 5 seconds of WebSocket reconnection.
- [ ] Simulate: start a scan → disconnect WiFi for 30 seconds → reconnect. The scanning state matches the backend's actual state.
- [ ] The `/api/v1/status` endpoint returns correct state for: idle, scanning, reevaluating.
- [ ] After 15 minutes of no progress events during a "scan," the UI auto-clears with a warning.

**Files:**
- `backend/api/routers/discovery.py` — add `/status` endpoint
- `src/shared/hooks/useWS.ts` — reconcile on reconnect
- `src/App.tsx` — listen for reconciliation events, add safety timeout
- `src/shared/context/AppContext.tsx` — no changes needed (state is managed by App.tsx)

**Effort:** 2 hours

---

## Phase 3: Error Recovery & Resilience

**Why this phase exists:** After Phases 1–2, the app stops silently breaking and stops getting stuck. Phase 3 makes it self-healing — failures are surfaced to users, the sidecar restarts itself, and degraded modes are clearly communicated.

**Phase effort:** ~1.5 days

---

### 3.1 LLM Evaluator Failures Silently Fall Back With No Signal

**Problem:**
In `ranking/evaluator.py`, the `score()` function (line 307–320) has this pattern:

```python
try:
    return _score_with_llm(jd, candidate_data, baseline)
except Exception:
    return baseline
```

When the LLM call fails (rate limit, timeout, invalid API key, network error), the function silently returns the deterministic baseline score. The caller (`run_scan` / `run_reevaluate_jobs`) has no way to know this happened. The user sees a score and assumes "the AI evaluated this" when it was actually the local rubric.

Over a typical scan of 50 leads, if the LLM hits a rate limit after 10 calls, the remaining 40 leads get silently degraded scores. The user has no idea 80% of their results are lower quality.

**Root Cause:**
```python
# evaluator.py:317-320
try:
    return _score_with_llm(jd, candidate_data, baseline)
except Exception:     # ← catches everything
    return baseline   # ← no logging, no signal to caller
```

**Fix:**

1. Add a `scored_by` field to every result:
   ```python
   try:
       result = _score_with_llm(jd, candidate_data, baseline)
       result["scored_by"] = "llm"
       return result
   except Exception as exc:
       _log.warning("LLM evaluator failed, using deterministic fallback: %s", exc)
       baseline["scored_by"] = "deterministic_fallback"
       return baseline
   ```

2. Track fallback counts in the scan loop (`api/routers/discovery.py`). After the evaluation loop, broadcast a summary:
   ```python
   if fallback_count > 0:
       await manager.broadcast({
           "type": "agent",
           "event": "eval_fallback_summary",
           "msg": f"{fallback_count}/{total} leads scored by fallback (LLM unavailable)"
       })
   ```

3. Store `scored_by` in the lead's `source_meta` so it's visible in the UI lead detail.

**Acceptance Criteria:**
- [ ] Set an invalid LLM API key. Run a scan. Verify every lead's result includes `"scored_by": "deterministic_fallback"`.
- [ ] Verify a warning-level log line appears for each LLM failure.
- [ ] Verify a summary broadcast appears: "X/Y leads scored by fallback."
- [ ] Set a valid LLM API key. Run a scan. Verify results include `"scored_by": "llm"`.

**Files:**
- `backend/ranking/evaluator.py` — add scored_by field, log failures
- `backend/api/routers/discovery.py` — track and broadcast fallback counts
- `backend/data/sqlite/leads.py` — persist scored_by in source_meta (optional, via existing source_meta field)

**Effort:** 1 hour

---

### 3.2 Sidecar Crash Recovery Is Fragile on Windows

**Problem:**
The Tauri sidecar management in `src-tauri/src/lib.rs` has several fragility points on Windows:

1. **Stale PID reuse:** `cleanup_stale_sidecar()` reads a PID from `sidecar.pid` and kills it. But on Windows, PIDs are aggressively reused. If the sidecar crashed, the PID might now belong to a completely different process (Chrome, VS Code, etc.). There's no validation that the PID actually belongs to a JustHireMe backend.

2. **PowerShell dependency:** `cleanup_debug_python_sidecars()` uses a PowerShell command with WMI (`Get-CimInstance Win32_Process`). On machines with restrictive execution policies (common in corporate environments), this silently fails, leaving zombie Python processes.

3. **No auto-restart:** When the sidecar terminates (`CommandEvent::Terminated`), the code emits `sidecar-error` and `sidecar-terminated` events. But it never tries to restart the sidecar. The user must manually close and reopen the entire app. For a desktop app that runs continuously, this is a poor experience.

**Root Cause:**
```rust
// lib.rs:417-432 — cleanup_stale_sidecar
// Reads PID from file, kills it without verifying the process name

// lib.rs:361-388 — cleanup_debug_python_sidecars
// Uses PowerShell WMI query that fails silently on restricted systems

// lib.rs:678-713 — CommandEvent::Terminated handler
// Emits error events but never attempts restart
```

**Fix:**

1. **Validate PID before killing:**
   ```rust
   // Before calling taskkill, verify the process name matches
   fn is_jhm_process(pid: u32) -> bool {
       let output = std::process::Command::new("tasklist")
           .args(["/FI", &format!("PID eq {pid}"), "/FO", "CSV", "/NH"])
           .output();
       match output {
           Ok(out) => {
               let text = String::from_utf8_lossy(&out.stdout).to_lowercase();
               text.contains("python") || text.contains("jhm-sidecar")
           }
           Err(_) => false,
       }
   }
   ```

2. **Add a non-PowerShell fallback for process cleanup:** Use `tasklist` + `taskkill` directly instead of WMI queries. These are available on all Windows versions without execution policy restrictions.

3. **Add auto-restart with exponential backoff:**
   ```rust
   // In CommandEvent::Terminated handler:
   if !intentional_shutdown && restart_count < 3 {
       let delay = Duration::from_secs(2u64.pow(restart_count));
       restart_count += 1;
       eprintln!("[tauri] Auto-restarting sidecar in {:?} (attempt {}/3)", delay, restart_count);
       tokio::time::sleep(delay).await;
       // Re-run sidecar spawn logic
   }
   ```

   Only auto-restart on non-zero exit codes. Exit code 0 = clean shutdown, don't restart.

**Acceptance Criteria:**
- [ ] Kill the sidecar process manually (via Task Manager). Verify it auto-restarts within 10 seconds.
- [ ] Kill it 3 times rapidly. After the 3rd restart, verify it gives up and shows a persistent error.
- [ ] On clean shutdown (app close), verify the sidecar does NOT restart.
- [ ] Create a `sidecar.pid` file containing a PID that belongs to a non-JHM process. Verify `cleanup_stale_sidecar` does NOT kill that process.
- [ ] Test on a machine with restricted PowerShell execution policy. Verify process cleanup still works via the fallback.

**Files:**
- `src-tauri/src/lib.rs` — PID validation, auto-restart, non-PowerShell fallback

**Effort:** 3 hours

---

### 3.3 ErrorBoundary Retry Doesn't Re-fetch Data

**Problem:**
The React `ErrorBoundary` in `src/shared/components/ErrorBoundary.tsx` catches render errors and shows a "Retry" button. When clicked, it clears the error state (`this.setState({ error: null })`), which triggers a re-render of the children.

But if the error was caused by stale or missing data (e.g., the selected lead was deleted, or the profile data didn't load), re-rendering with the same stale data will immediately hit the same error. The user clicks "Retry" and sees the error flash back instantly.

**Root Cause:**
```typescript
// ErrorBoundary.tsx:37
<button onClick={() => this.setState({ error: null })}>Retry</button>
```

Clearing the error re-renders the same component tree with the same props and state. No data re-fetch is triggered.

**Fix:**
Use a key-based remount pattern. Track a retry counter and pass it as a key to force React to fully unmount and remount the children (which re-runs all `useEffect` hooks and data fetches):

```typescript
state = { error: null as Error | null, retryCount: 0 };

// In render:
if (this.state.error) {
  return (
    <div ...>
      <p>{this.props.label} failed to load.</p>
      <button onClick={() => this.setState(prev => ({
        error: null,
        retryCount: prev.retryCount + 1
      }))}>
        Retry
      </button>
    </div>
  );
}
return <React.Fragment key={this.state.retryCount}>{this.props.children}</React.Fragment>;
```

The `key` change forces React to destroy the old component tree and create a new one, re-triggering all effects.

**Acceptance Criteria:**
- [ ] Wrap a component that fetches data on mount in an ErrorBoundary. Make the first fetch fail. Click Retry. Verify the component remounts and fetches again (not just re-renders with stale data).
- [ ] Existing ErrorBoundary behavior is preserved: errors are caught, retry button appears, error reports are sent to backend.

**Files:**
- `src/shared/components/ErrorBoundary.tsx`

**Effort:** 30 minutes

---

### 3.4 No Sidecar Auto-Restart After Crash

**Note:** This item is merged into 3.2 above. The auto-restart logic is part of the sidecar crash recovery fix. Listed separately here for tracking purposes — implementation is in 3.2.

---

## Phase 4: Data Integrity & Validation

**Why this phase exists:** The data layer works but is fragile. Column-index-based row mapping breaks silently on schema changes. Settings accept garbage values. The deprecated compatibility facade adds confusion. These are the bugs that appear after a migration or a settings change and are hard to reproduce.

**Phase effort:** ~1 day

---

### 4.1 lead_row_dict Uses Hardcoded Column Indices

**Problem:**
In `data/sqlite/leads.py`, `lead_row_dict()` (line 59) maps database rows to dictionaries using hardcoded positional indices: `row[0]` is `job_id`, `row[1]` is `title`, ..., `row[38]` is `resume_version`.

This creates a tight coupling between the column order in `LEAD_SELECT_COLUMNS` (line 10) and the index mapping in `lead_row_dict`. If any migration adds a column in the middle, or if `LEAD_SELECT_COLUMNS` is reordered, every field after the change point maps to the wrong value. This produces silent data corruption — scores show up as titles, URLs show up as reasons — with no error.

There are 39 columns. The mapping is maintained by counting positions by hand. One mistake is invisible until a user reports garbled data.

**Root Cause:**
```python
# leads.py:10-17
LEAD_SELECT_COLUMNS = "job_id,title,company,url,platform,status,score,reason,..."
# ↑ 39 columns, comma-separated, order matters

# leads.py:59-101
def lead_row_dict(row) -> dict:
    source_meta = json_dict(row[21] or "{}")  # ← which column is 21? You have to count.
    return {
        "job_id": row[0],     # ← if column order changes, this silently breaks
        "title": row[1],
        "company": row[2],
        ...
        "resume_version": row[38],  # ← 38th position, fragile
    }
```

**Fix:**
Use `sqlite3.Row` as the row factory so columns are accessed by name:

1. In `connection.py`, update the connection setup:
   ```python
   def connect(db_path: str | None = None):
       db_path = _resolve_db_path(db_path)
       conn = sqlite3.connect(db_path)
       conn.row_factory = sqlite3.Row  # ← add this
       conn.execute("PRAGMA journal_mode=WAL")
       conn.execute("PRAGMA synchronous=NORMAL")
       conn.execute("PRAGMA busy_timeout=5000")
       return conn
   ```

2. Rewrite `lead_row_dict` to use named access:
   ```python
   def lead_row_dict(row) -> dict:
       source_meta = json_dict(row["source_meta"] or "{}")
       return {
           "job_id": row["job_id"],
           "title": row["title"],
           "company": row["company"],
           ...
       }
   ```

3. Update any other functions that access rows by index (search for `row[` in `leads.py`, `events.py`, `settings.py`).

**Acceptance Criteria:**
- [ ] Zero instances of `row[<integer>]` remain in `data/sqlite/leads.py`.
- [ ] All existing lead-related tests pass.
- [ ] Add a test: reorder two columns in `LEAD_SELECT_COLUMNS`. Verify `lead_row_dict` still returns correct values (because it uses names, not positions).
- [ ] Verify `get_all_leads()`, `get_lead_by_id()`, `get_feedback_training_examples()`, and `get_leads_for_learning()` all return correctly structured data.

**Files:**
- `backend/data/sqlite/connection.py` — add row_factory
- `backend/data/sqlite/leads.py` — rewrite all row[n] access to row["name"]
- `backend/data/sqlite/events.py` — update if it uses row indices
- `backend/data/sqlite/settings.py` — update if it uses row indices

**Effort:** 2 hours

---

### 4.2 No Input Validation on Settings Values

**Problem:**
Settings are stored as key-value text pairs in SQLite (`settings` table: `key TEXT PRIMARY KEY, val TEXT`). The values are only validated at read time via helper functions like `int_cfg()` which silently clamp out-of-range values to defaults. This means:

- A user can set `x_max_requests_per_scan` to `"banana"` — it saves successfully, and every read silently falls back to the default value of 5.
- A user can set `free_source_min_signal_score` to `"-999"` — it saves and gets clamped to 0 on every read.
- No error is ever shown. The user thinks they configured something but their setting is being ignored.

**Root Cause:**
Settings are stored as raw text with no schema:
```python
# settings.py (save)
conn.execute("INSERT OR REPLACE INTO settings(key, val) VALUES(?, ?)", (key, val))
# ← val is whatever string the user sent, no validation

# gateway/discovery_config.py (read)
def int_cfg(cfg, key, default, lo, hi):
    try:
        return max(lo, min(hi, int(cfg.get(key, default))))
    except (ValueError, TypeError):
        return default
# ← silently returns default on bad input, no error
```

**Fix:**

1. Define a settings schema (can be a simple dict):
   ```python
   SETTINGS_SCHEMA = {
       "x_max_requests_per_scan": {"type": "int", "min": 1, "max": 50, "default": 5},
       "x_max_results_per_query": {"type": "int", "min": 10, "max": 100, "default": 50},
       "free_source_min_signal_score": {"type": "int", "min": 0, "max": 100, "default": 60},
       "free_source_max_requests": {"type": "int", "min": 1, "max": 80, "default": 20},
       "board_scan_batch_size": {"type": "int", "min": 1, "max": 12, "default": 4},
       "x_hot_lead_threshold": {"type": "int", "min": 1, "max": 100, "default": 80},
       "llm_provider": {"type": "str", "allowed": ["ollama", "openai", "anthropic", ""], "default": ""},
       "x_bearer_token": {"type": "str", "default": ""},
       # ... etc
   }
   ```

2. Add a validation function:
   ```python
   def validate_setting(key: str, value: str) -> tuple[bool, str]:
       schema = SETTINGS_SCHEMA.get(key)
       if not schema:
           return True, ""  # Unknown keys pass through (forward compat)
       if schema["type"] == "int":
           try:
               v = int(value)
               if v < schema["min"] or v > schema["max"]:
                   return False, f"{key} must be between {schema['min']} and {schema['max']}"
           except ValueError:
               return False, f"{key} must be a number"
       elif schema["type"] == "str" and "allowed" in schema:
           if value not in schema["allowed"]:
               return False, f"{key} must be one of: {schema['allowed']}"
       return True, ""
   ```

3. Call validation in the settings save endpoint. Return 400 with a clear error message on invalid values.

**Acceptance Criteria:**
- [ ] POST a setting with `x_max_requests_per_scan = "banana"`. Verify 400 response with error message.
- [ ] POST a setting with `x_max_requests_per_scan = "999"`. Verify 400 response with range error.
- [ ] POST a setting with `x_max_requests_per_scan = "10"`. Verify 200 response.
- [ ] Unknown setting keys still save successfully (forward compatibility).

**Files:**
- `backend/data/sqlite/settings.py` or `backend/api/routers/settings.py` — add schema and validation
- `backend/tests/test_settings_validation.py` — new test file

**Effort:** 3 hours

---

### 4.3 Remove the db/client.py Compatibility Facade

**Problem:**
`backend/db/client.py` is a 387-line compatibility shim that re-exports everything from the modularized data layer (`data.sqlite.*`, `data.graph.*`, `data.vector.*`). It was created during the modularization to avoid breaking old import paths. It prints a deprecation warning on import.

But code paths still import from `db.client` or `db.*`. This creates confusion about which import path is canonical, masks circular import issues, and makes it unclear which module "owns" a function. The deprecation warning fires on every app start but nothing is actually being migrated.

**Root Cause:**
```python
# db/client.py
import warnings
warnings.warn("db.client is deprecated — import from data.sqlite / data.graph / data.vector", DeprecationWarning, stacklevel=2)

from data.sqlite.leads import *
from data.sqlite.events import *
from data.sqlite.settings import *
from data.graph.connection import conn, db, ...
from data.vector.connection import vec, ...
# ← 387 lines of re-exports
```

**Fix:**

1. `grep -r "from db" backend/ --include="*.py"` and `grep -r "import db" backend/ --include="*.py"` to find all import sites.
2. Rewrite each import to use the canonical path:
   - `from db.client import save_lead` → `from data.sqlite.leads import save_lead`
   - `from db.client import conn` → `from data.graph.connection import conn`
   - etc.
3. After all imports are updated, delete `backend/db/client.py` and `backend/db/__init__.py`.
4. Run the import boundary tests (`test_import_boundaries.py`) to verify no circular imports.

**Acceptance Criteria:**
- [ ] `grep -r "from db" backend/ --include="*.py"` returns zero results (excluding `test_*` files that may need updating).
- [ ] `grep -r "import db" backend/ --include="*.py"` returns zero results (excluding `test_*` files).
- [ ] `backend/db/` directory is deleted.
- [ ] All existing tests pass.
- [ ] `test_import_boundaries.py` passes.

**Files:**
- `backend/db/client.py` — DELETE
- `backend/db/__init__.py` — DELETE
- Every file that imports from `db.*` — update imports

**Effort:** 2 hours

---

## Phase 5: Frontend Stability

**Why this phase exists:** The backend is now solid. Phase 5 ensures the frontend doesn't introduce regressions. With only 2 test files covering the entire UI, every frontend change is a gamble. This phase adds the tests that catch problems before users do, and fixes the UX gaps that make the app feel unfinished.

**Phase effort:** ~2–3 days

---

### 5.1 Frontend Test Coverage Is Nearly Zero

**Problem:**
The entire frontend has exactly 2 test files:
- `src/shared/lib/leadUtils.test.ts` — utility function tests
- `src/features/profile/profileUtils.test.ts` — profile utility tests

There are zero component tests, zero hook tests, and zero integration tests. The `PRODUCTION_READINESS_ROADMAP.md` called for 20+ frontend tests in Sprint 5 — this was never implemented.

Every frontend change is deployed without automated verification. UI regressions (broken lead list rendering, settings not saving, WebSocket reconnection failures) are only caught when users report them.

**Fix:**
Add test coverage for the critical paths. Priority order:

1. **useWS hook tests** (highest value — most complex frontend logic):
   - Test initial connection lifecycle (disconnected → connecting → connected).
   - Test reconnection with exponential backoff after disconnect.
   - Test message parsing for each message type (heartbeat, agent, LEAD_UPDATED, HOT_X_LEAD).
   - Test malformed message handling (the fix from 1.3).
   - Test sidecar-terminated event handling.
   - Test max retry exhaustion.

2. **API client tests:**
   - Test timeout handling (30s default, custom timeout).
   - Test abort/cancel behavior.
   - Test error message formatting ("backend unreachable," "timed out").
   - Test auth header injection.

3. **Pipeline/Lead list tests:**
   - Test lead rendering with all status types.
   - Test status transitions (discovered → evaluating → tailoring → approved).
   - Test empty state rendering.
   - Test lead selection and drawer opening.

4. **Settings panel tests:**
   - Test form field rendering with current values.
   - Test save with validation feedback.
   - Test API key masking.

5. **AppContext tests:**
   - Test state transitions for scanning/reevaluating/cleaning.
   - Test the reconciliation logic (from fix 2.3).

**Acceptance Criteria:**
- [ ] At least 20 new test cases across 5+ test files.
- [ ] `npx vitest run` passes with zero failures.
- [ ] Critical path coverage: useWS, API client, lead list rendering, settings save.
- [ ] Tests run in under 10 seconds (no real network calls, all mocked).

**Files:**
- `src/shared/hooks/useWS.test.ts` — new
- `src/api/client.test.ts` — new
- `src/features/pipeline/PipelineView.test.tsx` — new
- `src/features/settings/SettingsPanel.test.tsx` — new
- `src/shared/context/AppContext.test.tsx` — new

**Effort:** 2–3 days

---

### 5.2 No Progress Indicators for Long Operations

**Problem:**
When the user triggers a scan, reevaluation, or document generation, the UI shows a simple spinner based on the `scanning`/`reevaluating` boolean. There's no progress indicator — a scan of 200 leads takes 5–10 minutes with no feedback beyond the log panel (which most users don't open).

Users think the app froze. They click the scan button again (which returns 409), or they restart the app (which kills the in-progress scan).

The backend already broadcasts progress events (`eval_scored` with lead titles and scores, scout progress, etc.) — the frontend just doesn't surface them.

**Root Cause:**
The information is available. The WebSocket already delivers `eval_scored`, `eval_start` (with total count), `scout_done`, `free_scout_done` events. The frontend processes these events in `useWS.ts` but only writes them to the log panel (`addLog`). The main UI doesn't show any of this.

**Fix:**

1. **Track scan progress in state.** In the scan event handler, parse the progress from broadcast messages:
   - On `eval_start`: extract total count from message (e.g., "Evaluating 52 leads...") → set `scanTotal = 52`.
   - On `eval_scored`: increment `scanProgress += 1`.
   - On `eval_done`: clear both.

2. **Show a progress bar or counter** in the Dashboard/Topbar area:
   ```
   Scanning... 14/52 leads evaluated
   [████████░░░░░░░░░░░░] 27%
   ```

3. **Show the current lead being evaluated** as a subtitle:
   ```
   Scoring: Senior Backend Engineer at Stripe
   ```

**Acceptance Criteria:**
- [ ] During a scan, the UI shows "Evaluating X/Y leads" with a progress counter.
- [ ] Progress updates in real-time as each lead is scored.
- [ ] When the scan completes, the progress indicator disappears cleanly.
- [ ] When the scan is stopped by the user, the progress indicator disappears.

**Files:**
- `src/App.tsx` — parse progress from WebSocket events
- `src/shared/components/Topbar.tsx` (or wherever the scan status is shown) — render progress bar
- `src/shared/hooks/useWS.ts` — expose progress state

**Effort:** 3 hours

---

### 5.3 AppContext useMemo Dependency Array Is Fragile

**Problem:**
In `AppContext.tsx`, the context value is created via `useMemo` with a manually maintained dependency array listing 14 values. If a new state variable is added but forgotten in the dependency array, consumers of the context won't re-render when that value changes — causing stale UI bugs that are extremely hard to debug.

This is a maintenance hazard. It's already bitten once (from the git history pattern of "add state, forget to add to deps, fix in a later commit").

**Root Cause:**
```typescript
// AppContext.tsx:28-57
return useMemo(() => ({
  view, setView, sel, setSel, showSettings, setShowSettings,
  // ... 20+ fields
}), [
  view, sel, showSettings, showOnboarding, applyDraft, applyAutoFocus,
  scanning, reevaluating, cleaning, scanErr, closeDrawer, focusApplyView,
  openSettings, openSetupGuide,
  // ← if you add a new field above but forget to add it here, stale renders
]);
```

**Fix:**
Three options (pick one):

**Option A (simplest):** Remove the `useMemo` entirely. The context value is a shallow object of primitives and callbacks — the memoization overhead is negligible for this app. React's context comparison will handle re-renders correctly.

**Option B (cleanest):** Use `useReducer` with a single state object. The dependency is always `[state]`, and it's impossible to forget a field:
```typescript
const [state, dispatch] = useReducer(appReducer, initialState);
const value = useMemo(() => ({ ...state, dispatch }), [state]);
```

**Option C (if keeping useMemo):** Add an ESLint rule or a test that verifies the dependency array matches the object keys:
```typescript
// In a test file:
const objectKeys = Object.keys(useAppShellState());
const depsCount = /* extract from source */;
expect(objectKeys.length).toBe(depsCount + setterCount);
```

**Recommendation:** Option A. It's 2 lines of change, zero risk, and the performance difference is immeasurable for an app with one context consumer tree.

**Acceptance Criteria:**
- [ ] Adding a new state field to AppContext does NOT require updating a dependency array.
- [ ] All existing context consumers re-render correctly when any state field changes.
- [ ] No stale closure bugs in the dashboard, pipeline, or settings views.

**Files:**
- `src/shared/context/AppContext.tsx`

**Effort:** 1 hour

---

## Phase 6: Release Engineering

**Why this phase exists:** The code is now stable. Phase 6 is about making sure it stays stable across releases and that you can diagnose problems when they happen in the wild. This is what separates "works on my machine" from "shippable product."

**Phase effort:** ~1 day

---

### 6.1 Adopt Semantic Versioning

**Problem:**
The version has been incrementing the patch number for every build (currently 0.1.55). There's no distinction between breaking changes, features, and fixes. The auto-updater can't tell users whether an update is safe to apply immediately or requires attention.

**Fix:**

1. Set the next release version to `1.0.0` in all three manifest files:
   - `package.json`: `"version": "1.0.0"`
   - `src-tauri/tauri.conf.json`: `"version": "1.0.0"`
   - `backend/pyproject.toml`: `version = "1.0.0"`

2. Create `CHANGELOG.md` with the v1.0.0 entry summarizing all stability improvements from this execution plan.

3. Adopt semver going forward:
   - **Major** (2.0.0): breaking changes to settings format, database schema without migration, or API contract.
   - **Minor** (1.1.0): new features (new source adapters, new UI views, new generation types).
   - **Patch** (1.0.1): bug fixes, performance improvements, dependency updates.

4. Add a version check to the CI pipeline: fail the build if the version number wasn't bumped.

**Acceptance Criteria:**
- [ ] All three manifest files show `1.0.0`.
- [ ] `CHANGELOG.md` exists with a v1.0.0 entry.
- [ ] The about/settings screen in the app shows `1.0.0`.

**Files:**
- `package.json`
- `src-tauri/tauri.conf.json`
- `backend/pyproject.toml`
- `CHANGELOG.md` — new file

**Effort:** 1 hour

---

### 6.2 Add a Smoke Test for the Built Binary

**Problem:**
The release process builds with PyInstaller (backend) + Tauri (frontend shell) and ships the result. But there's no automated test that verifies the built binary actually works. Platform-specific bugs — missing DLLs, incorrect path resolution in the frozen PyInstaller bundle, permission errors on first-run — only appear when users run the installer.

This is why "it works in dev but breaks in production" keeps happening. The dev environment has Python on PATH, has all dependencies available, and runs from source. The built binary runs from a frozen bundle in a completely different filesystem layout.

**Fix:**
Add a CI smoke test step that runs after the build:

```yaml
# In GitHub Actions workflow (or equivalent)
smoke-test:
  needs: build
  runs-on: windows-latest
  steps:
    - name: Download build artifact
      uses: actions/download-artifact@v4

    - name: Start the sidecar binary directly
      run: |
        Start-Process -FilePath "./jhm-sidecar-next.exe" -ArgumentList "--no-services" -PassThru
        Start-Sleep -Seconds 10

    - name: Health check
      run: |
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/health"
        if ($response.status -ne "ok") { exit 1 }

    - name: Basic API smoke test
      run: |
        # Test settings endpoint
        Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/api/v1/settings" -Headers @{Authorization="Bearer $TOKEN"}
        # Test leads endpoint
        Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/api/v1/leads" -Headers @{Authorization="Bearer $TOKEN"}
        # Test profile endpoint
        Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/api/v1/profile" -Headers @{Authorization="Bearer $TOKEN"}

    - name: Shutdown
      run: |
        Stop-Process -Name "jhm-sidecar-next" -Force
```

This catches 90% of packaging bugs: missing DLLs, import errors in the frozen bundle, database initialization failures, and path resolution issues.

**Acceptance Criteria:**
- [ ] CI pipeline includes a smoke test step after building.
- [ ] The smoke test starts the backend binary, hits `/health`, `/api/v1/settings`, `/api/v1/leads`, and `/api/v1/profile`.
- [ ] A build with a missing dependency fails the smoke test (verify by intentionally removing a dependency).
- [ ] The smoke test completes in under 30 seconds.

**Files:**
- `.github/workflows/release.yml` (or equivalent CI config) — add smoke test step
- `backend/tests/smoke_test.py` — optional standalone smoke test script

**Effort:** 4 hours

---

### 6.3 Add Structured Error Telemetry

**Problem:**
Errors are logged to stderr and to the `events` table as free-text strings. There's no way to aggregate patterns. You can't answer questions like:
- "What's the most common error this week?"
- "Did the latest release reduce LLM timeout failures?"
- "Which source adapter fails most often?"

When users report bugs, they send screenshots of error messages. You have no structured data to correlate across users or releases.

**Fix:**

1. Create an error aggregation table in SQLite:
   ```sql
   CREATE TABLE IF NOT EXISTS error_log(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       error_type TEXT NOT NULL,      -- e.g., "llm_timeout", "database_locked", "source_fetch_failed"
       error_message TEXT,
       source TEXT,                    -- e.g., "ranking.evaluator", "discovery.sources.hn"
       count INTEGER DEFAULT 1,
       first_seen TEXT DEFAULT (datetime('now')),
       last_seen TEXT DEFAULT (datetime('now'))
   );
   ```

2. Add a `record_error(error_type, message, source)` function to `core/telemetry.py` that upserts into this table:
   - If an error with the same `error_type` and `source` was seen in the last hour, increment `count` and update `last_seen`.
   - Otherwise, insert a new row.

3. Add a `/api/v1/diagnostics` endpoint:
   ```python
   @router.get("/diagnostics")
   async def diagnostics():
       return {
           "top_errors": get_top_errors(limit=10),  # last 7 days
           "error_count_24h": get_error_count(hours=24),
           "version": "1.0.0",
           "uptime_seconds": time.monotonic() - started_at,
       }
   ```

4. Call `record_error()` from the key failure points identified in this execution plan:
   - LLM evaluator failures (Phase 3.1)
   - Source adapter fetch failures (discovery service)
   - Database lock errors (Phase 1.1)
   - WebSocket broadcast failures (Phase 1.2)

**Acceptance Criteria:**
- [ ] After running a scan with some intentional failures, `/api/v1/diagnostics` returns a non-empty `top_errors` list.
- [ ] Each error entry includes: `error_type`, `count`, `source`, `first_seen`, `last_seen`.
- [ ] Duplicate errors within 1 hour are aggregated (count increments) instead of creating new rows.
- [ ] The diagnostics endpoint responds in under 100ms.

**Files:**
- `backend/data/sqlite/connection.py` — add error_log table to migrations
- `backend/core/telemetry.py` — add record_error function
- `backend/api/routers/diagnostics.py` — new router file
- `backend/api/app.py` — register diagnostics router
- `backend/ranking/evaluator.py` — call record_error on LLM failure
- `backend/discovery/service.py` — call record_error on source failures

**Effort:** 3 hours

---

## Summary

| Phase | Items | Effort | Priority |
|-------|-------|--------|----------|
| **1. Connection Leaks & Silent Failures** | 3 items | 1.5 days | Ship-blocker |
| **2. Concurrency & Race Conditions** | 3 items | 1.5 days | Ship-blocker |
| **3. Error Recovery & Resilience** | 4 items | 1.5 days | High |
| **4. Data Integrity & Validation** | 3 items | 1 day | Medium |
| **5. Frontend Stability** | 3 items | 2–3 days | Medium |
| **6. Release Engineering** | 3 items | 1 day | Polish |
| **Total** | **19 items** | **~8–10 days** | |

### The v1.0.0 Definition of Done

All of the following must be true before tagging v1.0.0:

- [ ] **Phase 1 complete:** Zero silent exception swallowing. Connection pooling in place.
- [ ] **Phase 2 complete:** No race conditions in task lifecycle. Frontend state reconciles with backend on reconnect.
- [ ] **Phase 3 complete:** LLM fallback is visible to users. Sidecar auto-restarts. ErrorBoundary triggers data re-fetch.
- [ ] **Phase 4 complete:** Row mapping uses column names. Settings validate on save. db/client.py deleted.
- [ ] **Phase 5 complete:** 20+ frontend tests. Progress indicators for long operations. AppContext dependency bug fixed.
- [ ] **Phase 6 complete:** Version is 1.0.0 with semver. CI smoke test passes. Error telemetry active.
- [ ] **All existing tests pass:** 154+ backend tests, 20+ new frontend tests.
- [ ] **Manual smoke test:** Install from built binary on a clean Windows machine. Complete: profile upload → scan → evaluate → generate resume → apply. Zero errors.
- [ ] **48-hour soak test:** Run the app continuously for 48 hours with periodic scans. Zero crashes, zero memory leaks, zero stuck states.

### Why Things Kept Breaking — Root Cause Summary

The codebase architecture is sound. The modularization was done well. The recurring breakage came from three engineering gaps that compound on each other:

1. **No connection pooling** — SQLite was treated like a stateless HTTP API instead of an embedded database. Every concurrent operation created lock contention.

2. **Silent failure at every boundary** — WebSocket broadcasts, LLM calls, message parsing — all wrapped in `except: pass` or empty `catch {}`. When things broke, they broke invisibly, making diagnosis impossible.

3. **No state reconciliation** — Frontend and backend had no way to agree on "what's actually happening right now." Any disruption (WebSocket drop, sidecar restart) left the UI in a permanent stale state.

These three patterns created a feedback loop: silent failures caused phantom bugs, lack of telemetry made them impossible to diagnose, and state desync made them impossible to recover from. Users experienced "the app just stops working" because that's exactly what happened — features failed silently and nothing recovered.

The fixes in this plan break all three legs of that feedback loop.
