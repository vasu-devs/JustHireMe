import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createProfileItemDelete, ProfileView } from "./ProfileView";
import type { ApiFetch, GraphStats } from "../../types";

const okResponse = (body: unknown = {}) => ({
  ok: true,
  status: 200,
  json: async () => body,
}) as Response;

// Node test environment has no DOM: stub the window surface the delete
// handler touches (confirm guard + graph-refresh dispatch).
class StubCustomEvent {
  type: string;
  constructor(type: string) { this.type = type; }
}

const stubWindow = (confirmResult = true) => {
  const confirm = vi.fn(() => confirmResult);
  const dispatchEvent = vi.fn();
  vi.stubGlobal("window", { confirm, dispatchEvent });
  vi.stubGlobal("CustomEvent", StubCustomEvent);
  return { confirm, dispatchEvent };
};

const makeDeps = (api: ApiFetch) => {
  const state = { deleting: null as string | null };
  const deps = {
    api,
    isBusy: () => state.deleting !== null,
    setBusy: (marker: string | null) => { state.deleting = marker; },
    reload: vi.fn(async () => {}),
    setError: vi.fn(),
  };
  return { state, deps };
};

afterEach(() => { vi.unstubAllGlobals(); });

describe("profile item deletion contract", () => {
  it("DELETEs graph-id types by id after the confirm names the entry", async () => {
    const { confirm, dispatchEvent } = stubWindow();
    const api: ApiFetch = vi.fn(async () => okResponse());
    const { state, deps } = makeDeps(api);

    await createProfileItemDelete(deps)("skill", { id: "skill-7", n: "Python" });

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("Python"));
    expect(api).toHaveBeenCalledWith("/api/v1/profile/skill/skill-7", { method: "DELETE" });
    expect(deps.reload).toHaveBeenCalledTimes(1);
    expect(dispatchEvent).toHaveBeenCalledWith(expect.objectContaining({ type: "graph-refresh" }));
    expect(state.deleting).toBeNull();
  });

  it("DELETEs title-keyed types via the URL-encoded entry title", async () => {
    stubWindow();
    const api: ApiFetch = vi.fn(async () => okResponse());
    const { deps } = makeDeps(api);

    await createProfileItemDelete(deps)("certification", "AWS Certified Developer");

    expect(api).toHaveBeenCalledWith("/api/v1/profile/certification/AWS%20Certified%20Developer", { method: "DELETE" });
  });

  it("does nothing when the confirm is declined", async () => {
    stubWindow(false);
    const api: ApiFetch = vi.fn(async () => okResponse());
    const { deps } = makeDeps(api);

    await createProfileItemDelete(deps)("skill", { id: "skill-7", n: "Python" });

    expect(api).not.toHaveBeenCalled();
    expect(deps.reload).not.toHaveBeenCalled();
  });

  it("single-flight: blocks a second delete while one is in flight", async () => {
    const { confirm } = stubWindow();
    let release!: (response: Response) => void;
    const api: ApiFetch = vi.fn(() => new Promise<Response>(resolve => { release = resolve; }));
    const { state, deps } = makeDeps(api);
    const deleteItem = createProfileItemDelete(deps);

    const first = deleteItem("skill", { id: "skill-1", n: "Python" });
    await deleteItem("skill", { id: "skill-2", n: "Rust" });

    // The second call returns before even prompting: one confirm, one DELETE.
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(api).toHaveBeenCalledTimes(1);

    release(okResponse());
    await first;
    expect(state.deleting).toBeNull();
    expect(deps.setError).not.toHaveBeenCalled();
  });

  it("surfaces failed deletes through the error state and clears the flight", async () => {
    stubWindow();
    const api: ApiFetch = vi.fn(async () => ({ ok: false, status: 500 }) as Response);
    const { state, deps } = makeDeps(api);

    await createProfileItemDelete(deps)("project", { id: "proj-1", title: "Graph Engine" });

    expect(deps.setError).toHaveBeenCalledWith("Delete failed (500)");
    expect(deps.reload).not.toHaveBeenCalled();
    expect(state.deleting).toBeNull();
  });
});

describe("ProfileView delete affordances", () => {
  it("renders per-item delete buttons and the credibility markers section", () => {
    const api: ApiFetch = vi.fn(async () => okResponse({}));
    const stats = {
      candidate: 1, skill: 1, project: 1, experience: 1, joblead: 0,
      profile: {
        n: "Ada Lovelace",
        skills: [{ id: "skill-1", n: "Python" }],
        projects: [{ id: "proj-1", title: "Graph Engine" }],
        exp: [{ id: "exp-1", role: "Engineer", co: "Acme" }],
        education: ["BSc Mathematics"],
        certifications: ["AWS Certified Developer"],
        achievements: ["Hackathon Winner"],
      },
    } as GraphStats;

    const html = renderToStaticMarkup(<ProfileView api={api} setView={vi.fn()} stats={stats} />);

    expect(html).toContain('aria-label="Remove skill Python"');
    expect(html).toContain('aria-label="Remove Graph Engine"');
    expect(html).toContain('aria-label="Remove Engineer at Acme"');
    expect(html).toContain("Credibility markers");
    expect(html).toContain('aria-label="Remove education BSc Mathematics"');
    expect(html).toContain('aria-label="Remove certification AWS Certified Developer"');
    expect(html).toContain('aria-label="Remove achievement Hackathon Winner"');
  });
});
