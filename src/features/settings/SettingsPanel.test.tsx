import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

const modal = readFileSync(new URL("./SettingsModal.tsx", import.meta.url), "utf8");
const globalPanel = readFileSync(new URL("./panels/GlobalSettings.tsx", import.meta.url), "utf8");
const discoveryPanel = readFileSync(new URL("./panels/DiscoverySettings.tsx", import.meta.url), "utf8");

describe("Settings UI contracts", () => {
  it("surfaces backend validation errors", () => {
    expect(modal).toContain("saveError");
    expect(modal).toContain("Settings could not be saved");
  });

  it("submits settings through the API client", () => {
    expect(modal).toContain("/api/v1/settings");
    expect(modal).toContain("method: \"POST\"");
  });

  it("keeps LLM provider fields in the global panel", () => {
    expect(globalPanel).toContain("llm_provider");
    expect(globalPanel).toContain("openai");
  });

  it("keeps discovery scan limit fields visible", () => {
    expect(discoveryPanel).toContain("x_max_requests_per_scan");
    expect(discoveryPanel).toContain("free_source_max_requests");
  });
});
