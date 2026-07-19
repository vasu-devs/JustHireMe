import { describe, expect, it } from "vitest";
import { __wsTest, nextProgressFromAgentEvent } from "./useWS";

describe("WebSocket progress parsing", () => {
  it("starts scan progress from eval_start totals", () => {
    const next = nextProgressFromAgentEvent(__wsTest.emptyProgress(), "eval_start", "Evaluating 52 leads via ollama", 10);
    expect(next).toMatchObject({ active: true, mode: "scan", total: 52, completed: 0, updatedAt: 10 });
  });

  it("increments scan progress on scored events", () => {
    const start = nextProgressFromAgentEvent(__wsTest.emptyProgress(), "eval_start", "Evaluating 2 leads", 10);
    const next = nextProgressFromAgentEvent(start, "eval_scored", "Scored Backend Engineer = 82/100", 20);
    expect(next.completed).toBe(1);
    expect(next.current).toContain("Backend Engineer");
  });

  it("clears scan progress on eval_done", () => {
    const active = { ...__wsTest.emptyProgress(), active: true, mode: "scan" as const, total: 3, completed: 2 };
    expect(nextProgressFromAgentEvent(active, "eval_done", "done", 30).active).toBe(false);
  });

  it("starts reevaluation progress", () => {
    const next = nextProgressFromAgentEvent(__wsTest.emptyProgress(), "reeval_start", "Re-evaluating 8 job leads", 10);
    expect(next).toMatchObject({ active: true, mode: "reevaluate", total: 8 });
  });

  it("extracts reevaluation totals from bracketed progress", () => {
    const next = nextProgressFromAgentEvent(__wsTest.emptyProgress(), "reeval_scored", "[3/10] Re-scored Engineer = 90/100", 10);
    expect(next.total).toBe(10);
    expect(next.completed).toBe(1);
  });

  it("leaves unrelated agent events unchanged", () => {
    const prev = { ...__wsTest.emptyProgress(), updatedAt: 1 };
    expect(nextProgressFromAgentEvent(prev, "heartbeat", "noop", 99)).toBe(prev);
  });

  // The scan must read as running from its FIRST phase — the topbar stop
  // control and dashboard meter were dead through scouting when only
  // eval_* events activated progress.
  it("activates from the earliest scan phase", () => {
    const next = nextProgressFromAgentEvent(__wsTest.emptyProgress(), "free_scout_start", "Scanning free sources for job leads...", 10);
    expect(next).toMatchObject({ active: true, mode: "scan", unit: "sources" });
  });

  it("reads the search-plan size from scout_start", () => {
    const next = nextProgressFromAgentEvent(__wsTest.emptyProgress(), "scout_start", "Launching scan for 19 targets...", 10);
    expect(next).toMatchObject({ active: true, total: 19, completed: 0, unit: "sources" });
  });

  it("tracks batch completion via scout_progress", () => {
    const start = nextProgressFromAgentEvent(__wsTest.emptyProgress(), "scout_start", "Launching scan for 19 targets...", 10);
    const next = nextProgressFromAgentEvent(start, "scout_progress", "[8/19] sources scanned", 20);
    expect(next).toMatchObject({ active: true, total: 19, completed: 8, unit: "sources" });
  });

  it("stays active through scout_done and hands off to evaluation", () => {
    const scout = nextProgressFromAgentEvent(__wsTest.emptyProgress(), "scout_progress", "[19/19] sources scanned", 10);
    const done = nextProgressFromAgentEvent(scout, "scout_done", "Scout finished - 42 new leads found", 20);
    expect(done.active).toBe(true);
    expect(done.completed).toBe(19);
    const evaluating = nextProgressFromAgentEvent(done, "eval_start", "Evaluating 42 new leads via codex_cli", 30);
    expect(evaluating).toMatchObject({ active: true, total: 42, completed: 0, unit: "leads" });
  });
});
