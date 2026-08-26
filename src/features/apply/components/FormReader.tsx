import { useEffect, useRef, useState } from "react";
import type { ApiFetch, FormField, FormReadResult } from "../../../types";
import { automationApi } from "../../../api";

export function FormReader({
  jobId,
  defaultUrl,
  api,
}: {
  jobId: string;
  defaultUrl: string;
  api: ApiFetch;
}) {
  const [url, setUrl] = useState(defaultUrl || "");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<FormReadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [expandedCl, setExpandedCl] = useState(false);
  const requestRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => () => {
    mountedRef.current = false;
    requestRef.current?.abort();
  }, []);

  const readForm = async () => {
    setLoading(true);
    setError(null);
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    try {
      const r = await automationApi.readForm(api, jobId, url, { signal: controller.signal });
      if (!r.ok) {
        const detail = await r.json().then((d: any) => d.detail).catch(() => "");
        throw new Error(detail || `Server returned ${r.status}`);
      }
      setResult(await r.json());
    } catch (err) {
      if (mountedRef.current) setError(err instanceof Error ? err.message : "Form read failed");
    } finally {
      if (requestRef.current === controller) requestRef.current = null;
      if (mountedRef.current) setLoading(false);
    }
  };

  const copy = (text: string, key: string) => {
    navigator.clipboard?.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 1500);
  };

  const copyAll = () => {
    if (!result) return;
    const found = result.fields.filter(f => f.found_on_page && f.answer);
    const lines = found.map(f =>
      f.type === "cover_letter"
        ? `${f.label}:\n${f.answer}`
        : `${f.label}: ${f.answer}`
    );
    copy(lines.join("\n"), "__all__");
  };

  const foundFields = result?.fields.filter(f => f.found_on_page) ?? [];
  const missingFields = result?.fields.filter(f => !f.found_on_page) ?? [];

  const confidenceDot = (c: FormField["confidence"]) => {
    const color = c === "high" ? "var(--green)" : c === "medium" ? "var(--yellow)" : "var(--ink-4)";
    return (
      <span
        title={`Confidence: ${c}`}
        style={{
          display: "inline-block",
          width: 7,
          height: 7,
          borderRadius: "50%",
          background: color,
          flexShrink: 0,
        }}
      />
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div className="eyebrow">Form Reader</div>

      {/* URL bar */}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input
          type="url"
          value={url}
          onChange={e => setUrl(e.target.value)}
          placeholder="https://boards.greenhouse.io/..."
          style={{
            flex: 1,
            padding: "7px 10px",
            borderRadius: 8,
            border: "1px solid var(--line)",
            background: "var(--paper-3)",
            color: "var(--ink)",
            fontSize: 12,
          }}
        />
        <button
          onClick={readForm}
          disabled={loading || !url.trim()}
          style={{
            padding: "7px 14px",
            borderRadius: 8,
            fontSize: 12,
            fontWeight: 700,
            border: "1px solid var(--blue)",
            background: "var(--blue-soft)",
            color: "var(--blue-ink)",
            cursor: loading || !url.trim() ? "not-allowed" : "pointer",
            opacity: loading || !url.trim() ? 0.6 : 1,
            whiteSpace: "nowrap",
          }}
        >
          {loading ? "Reading form..." : "Read form"}
        </button>
      </div>

      {error && (
        <div style={{ fontSize: 12, color: "var(--bad)", padding: "6px 10px", background: "var(--bad-soft)", border: "1px solid var(--bad)", borderRadius: 8 }}>
          {error}
        </div>
      )}

      {result && (
        <>
          {/* Platform badge */}
          {result.platform && (
            <div>
              <span style={{
                display: "inline-block",
                padding: "3px 10px",
                borderRadius: 999,
                fontSize: 11,
                fontWeight: 700,
                background: "var(--blue-soft)",
                color: "var(--blue-ink)",
                border: "1px solid var(--blue)",
              }}>
                {result.platform_label}
              </span>
            </div>
          )}
          {!result.platform && (
            <div>
              <span style={{
                display: "inline-block",
                padding: "3px 10px",
                borderRadius: 999,
                fontSize: 11,
                fontWeight: 700,
                background: "var(--paper-3)",
                color: "var(--ink-3)",
                border: "1px solid var(--line)",
              }}>
                Generic form
              </span>
            </div>
          )}

          {/* Error from result */}
          {result.error && (
            <div style={{ fontSize: 12, color: "var(--bad)" }}>
              Browser error: {result.error}
            </div>
          )}

          {/* Side-by-side layout */}
          <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
            {/* Screenshot */}
            {result.screenshot_b64 && (
              <div style={{ flex: "0 0 45%", minWidth: 0 }}>
                <img
                  src={`data:image/png;base64,${result.screenshot_b64}`}
                  alt="Form screenshot"
                  style={{ width: "100%", borderRadius: 8, border: "1px solid var(--line)", objectFit: "contain", display: "block" }}
                />
              </div>
            )}

            {/* Field list */}
            <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 6 }}>
              {foundFields.map(field => (
                <div key={field.type} style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 8,
                  padding: "7px 10px",
                  background: "var(--paper-3)",
                  border: "1px solid var(--line)",
                  borderRadius: 8,
                }}>
                  {confidenceDot(field.confidence)}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="mono" style={{ fontSize: 10, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>
                      {field.label}
                    </div>
                    {field.type === "cover_letter" ? (
                      <>
                        <div style={{ fontSize: 12, color: "var(--ink-2)" }}>
                          {expandedCl ? (
                            <div style={{ maxHeight: 120, overflowY: "auto", whiteSpace: "pre-wrap", lineHeight: 1.5, paddingRight: 4 }}>
                              {field.answer}
                            </div>
                          ) : (
                            <span title={field.answer}>
                              {field.answer.slice(0, 80)}{field.answer.length > 80 ? "…" : ""}
                            </span>
                          )}
                        </div>
                        <button
                          onClick={() => setExpandedCl(v => !v)}
                          style={{ marginTop: 3, fontSize: 10.5, color: "var(--ink-3)", background: "none", border: "none", cursor: "pointer", padding: 0 }}
                        >
                          {expandedCl ? "Collapse" : "Preview"}
                        </button>
                      </>
                    ) : (
                      <div style={{ fontSize: 12, color: "var(--ink-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={field.answer}>
                        {field.answer || <span style={{ color: "var(--ink-4)" }}>—</span>}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => copy(field.answer, field.type)}
                    style={{
                      padding: "3px 8px",
                      borderRadius: 6,
                      fontSize: 10.5,
                      fontWeight: 700,
                      border: "1px solid var(--line)",
                      background: copied === field.type ? "var(--green-soft)" : "var(--paper)",
                      color: copied === field.type ? "var(--green-ink)" : "var(--ink-3)",
                      cursor: "pointer",
                      flexShrink: 0,
                    }}
                  >
                    {copied === field.type ? "Copied!" : "Copy"}
                  </button>
                </div>
              ))}

              {missingFields.length > 0 && (
                <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 2 }}>
                  Not found on page: {missingFields.map(f => f.label).join(", ")}
                </div>
              )}

              {result.unmatched_labels.length > 0 && (
                <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>
                  Fields we couldn't match: {result.unmatched_labels.join(", ")}
                </div>
              )}
            </div>
          </div>

          {foundFields.some(f => f.answer) && (
            <button
              onClick={copyAll}
              style={{
                padding: "7px 14px",
                borderRadius: 8,
                fontSize: 12,
                fontWeight: 700,
                border: "1px solid var(--line)",
                background: copied === "__all__" ? "var(--green-soft)" : "var(--paper-3)",
                color: copied === "__all__" ? "var(--green-ink)" : "var(--ink-2)",
                cursor: "pointer",
                alignSelf: "flex-start",
              }}
            >
              {copied === "__all__" ? "Copied all!" : "Copy all answers"}
            </button>
          )}
        </>
      )}
    </div>
  );
}
