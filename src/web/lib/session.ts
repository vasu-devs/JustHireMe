// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Vasudev Siddh and vasu-devs

/**
 * Response-parsing helper for the report screens (Overview/Sources — see
 * src/web/screens/), the two audit-style views with no desktop equivalent.
 *
 * Everything else this file used to hold (a bespoke `createWebApi`,
 * `?token=` URL handling) is gone: those screens now use the same `api`
 * (ApiFetch) the real App.tsx builds for every other screen — see
 * web/shims/api-client.ts and web/shims/useWS.ts for how that fetch reaches
 * the backend without the browser ever seeing a token.
 */
export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

/** Reads a JSON body, turning a non-2xx into a typed error with the server's reason. */
export async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body) => (typeof body?.detail === "string" ? body.detail : ""))
      .catch(() => "");
    throw new ApiError(response.status, detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}
