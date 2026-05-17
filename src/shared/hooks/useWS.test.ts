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
});
