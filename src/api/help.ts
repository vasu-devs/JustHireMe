import { json, withOpts } from "./client";
import type { ApiFetch, ApiFetchOptions } from "./types";

export type HelpTurn = { role: string; content: string };

/** Mirrors backend/api/routers/help.py — the in-app help assistant. */
export const helpApi = {
  chat: (api: ApiFetch, question: string, history: HelpTurn[] = [], opts?: ApiFetchOptions) =>
    api("/api/v1/help/chat", withOpts(json("POST", { question, history }), opts)),
};
