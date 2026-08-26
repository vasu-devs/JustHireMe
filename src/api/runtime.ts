import { json, withOpts } from "./client";
import type { ApiFetch, ApiFetchOptions } from "./types";

/** Mirrors backend/api/routers/runtime.py — optional local runtimes (vector store,
 *  embedding model) that the app can install on demand. */
export const runtimeApi = {
  vector: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/runtime/vector", opts),
  installVector: (api: ApiFetch, opts?: ApiFetchOptions) =>
    api("/api/v1/runtime/vector/install", withOpts({ method: "POST" }, opts)),
  embeddings: (api: ApiFetch, opts?: ApiFetchOptions) => api("/api/v1/runtime/embeddings", opts),
  setEmbeddingProvider: (api: ApiFetch, provider: string, opts?: ApiFetchOptions) =>
    api("/api/v1/runtime/embeddings/provider", withOpts(json("POST", { provider }), opts)),
  downloadOnnx: (api: ApiFetch, opts?: ApiFetchOptions) =>
    api("/api/v1/runtime/embeddings/onnx/download", withOpts({ method: "POST" }, opts)),
};
