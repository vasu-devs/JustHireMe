import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { useWS } from "./useWS";

vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

function HookProbe() {
  const { conn, port, apiToken, sidecarError, logs, progress } = useWS();
  return (
    <output>
      {conn}:{String(port)}:{String(apiToken)}:{String(sidecarError)}:{logs.length}:{String(progress.active)}
    </output>
  );
}

describe("useWS render defaults", () => {
  it("provides a disconnected snapshot before desktop events arrive", () => {
    const html = renderToStaticMarkup(<HookProbe />);
    expect(html).toContain("disconnected:null:null:null:0:false");
  });
});
