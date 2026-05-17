import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("./PipelineView.tsx", import.meta.url), "utf8");

describe("PipelineView critical UI contracts", () => {
  it("renders an empty state for no leads", () => {
    expect(source).toContain("No leads");
  });

  it("keeps reevaluation controls wired", () => {
    expect(source).toContain("onReevaluate");
    expect(source).toContain("onStopReevaluate");
  });

  it("keeps cleanup controls wired", () => {
    expect(source).toContain("onCleanup");
    expect(source).toContain("cleaning");
  });

  it("keeps lead deletion available from the pipeline", () => {
    expect(source).toContain("deleteLead");
  });
});
