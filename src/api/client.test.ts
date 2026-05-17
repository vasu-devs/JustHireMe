import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createApiFetch, isAbortLikeError } from "./client";

describe("createApiFetch", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { setTimeout, clearTimeout });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("adds the bearer token to every request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("ok"));
    vi.stubGlobal("fetch", fetchMock);
    await createApiFetch(4567, "secret")("/api/v1/leads");
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:4567/api/v1/leads");
    expect(headers.get("Authorization")).toBe("Bearer secret");
  });

  it("preserves caller headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("ok"));
    vi.stubGlobal("fetch", fetchMock);
    await createApiFetch(4567, "secret")("/x", { headers: { "x-request-id": "abc" } });
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("x-request-id")).toBe("abc");
  });

  it("formats backend unreachable errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Failed to fetch")));
    await expect(createApiFetch(4567, "secret")("/x")).rejects.toThrow("Local backend is unreachable");
  });

  it("formats timeout errors", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("window", { setTimeout, clearTimeout });
    vi.stubGlobal("fetch", vi.fn((_url, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener("abort", () => reject((init.signal as AbortSignal).reason));
    })));
    const request = createApiFetch(4567, "secret")("/x", { timeoutMs: 50 });
    vi.advanceTimersByTime(60);
    await expect(request).rejects.toThrow("timed out");
  });

  it("converts caller aborts to AbortError", async () => {
    const controller = new AbortController();
    vi.stubGlobal("fetch", vi.fn((_url, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener("abort", () => reject((init.signal as AbortSignal).reason));
    })));
    const request = createApiFetch(4567, "secret")("/x", { signal: controller.signal });
    controller.abort();
    await expect(request).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("isAbortLikeError", () => {
  it("recognizes DOM aborts", () => {
    expect(isAbortLikeError(new DOMException("Request cancelled", "AbortError"))).toBe(true);
  });

  it("recognizes textual abort errors", () => {
    expect(isAbortLikeError(new Error("signal is aborted"))).toBe(true);
  });
});
