import { openUrl } from "@tauri-apps/plugin-opener";

/**
 * Open a web URL in the user's default browser, but only if it is http(s).
 *
 * Lead URLs come from scraped listings (attacker-controlled), so a crafted
 * `file:`, `javascript:`, or other non-web scheme must never reach the OS
 * opener. Internal `blob:`/`data:` URLs we generate ourselves should use
 * `openUrl` directly, not this guard.
 */
export async function openExternalUrl(url: string | null | undefined): Promise<void> {
  if (!url) return;
  let scheme = "";
  try {
    scheme = new URL(url).protocol;
  } catch {
    console.warn("[openExternal] refusing to open malformed URL:", url);
    return;
  }
  if (scheme !== "http:" && scheme !== "https:") {
    console.warn("[openExternal] refusing to open non-http(s) URL:", url);
    return;
  }
  await openUrl(url);
}
