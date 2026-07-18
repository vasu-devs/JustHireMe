import { useEffect, useRef, useState } from "react";
import { SectionLabel } from "./shared";
import { settingsApi } from "../../../api/settings";
import type { ApiFetch } from "../../../types";

/** Visual looks for the generated resume PDF (backend STYLE_PRESETS, #90). */
const STYLE_PRESETS = [
  { id: "classic", label: "Classic", sub: "navy · centered" },
  { id: "harvard", label: "Harvard", sub: "serif · traditional" },
  { id: "modern", label: "Modern", sub: "warm · left-aligned" },
] as const;

export interface ResumeTemplate {
  id: string;
  name: string;
  source_filename: string;
  is_default: boolean;
  created_at: string;
  char_count: number;
  preview: string;
}

export function ResumeTemplatesPanel({ api }: { api: ApiFetch }) {
  const [templates, setTemplates] = useState<ResumeTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [stylePreset, setStylePreset] = useState("classic");
  const fileRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    settingsApi.get(api)
      .then(res => res.json())
      .then(body => {
        if (!cancelled && typeof body?.resume_style_preset === "string" && body.resume_style_preset) {
          setStylePreset(body.resume_style_preset);
        }
      })
      .catch(() => { /* keep the classic default when settings can't load */ });
    return () => { cancelled = true; };
  }, [api]);

  const chooseStyle = async (id: string) => {
    const previous = stylePreset;
    setStylePreset(id);
    try {
      const res = await settingsApi.save(api, { resume_style_preset: id });
      if (!res.ok) throw new Error(`Save failed (${res.status})`);
    } catch (err) {
      setStylePreset(previous);
      setError(err instanceof Error ? err.message : "Could not save style");
    }
  };

  const load = async () => {
    setLoading(true);
    try {
      const res = await api("/api/v1/templates");
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Could not load templates");
      setTemplates(body.templates || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load templates");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [api]);

  const upload = async (file: File) => {
    setLoading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("make_default", templates.length === 0 ? "true" : "false");
      const res = await api("/api/v1/templates/upload", { method: "POST", body: form, timeoutMs: 60000 });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `Upload failed (${res.status})`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const act = async (id: string, run: () => Promise<Response>) => {
    setBusyId(id);
    setError(null);
    try {
      const res = await run();
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed (${res.status})`);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusyId("");
    }
  };

  const setDefault = (id: string) => act(id, () => api(`/api/v1/templates/${id}/default`, { method: "POST" }));
  const remove = (id: string) => act(id, () => api(`/api/v1/templates/${id}`, { method: "DELETE" }));

  return (
    <div>
      <SectionLabel label="Visual style" sub="how the generated resume PDF looks — colors, typeface, and alignment" />
      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        {STYLE_PRESETS.map(p => (
          <button
            key={p.id}
            onClick={() => void chooseStyle(p.id)}
            aria-pressed={stylePreset === p.id}
            style={{
              padding: "10px 16px", borderRadius: 12, cursor: "pointer", textAlign: "left",
              border: stylePreset === p.id ? "1.5px solid var(--accent)" : "1px solid var(--line)",
              background: stylePreset === p.id ? "var(--accent-soft)" : "var(--paper)",
            }}
          >
            <div style={{ fontWeight: 700, fontSize: 13 }}>{p.label}</div>
            <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>{p.sub}</div>
          </button>
        ))}
      </div>

      <SectionLabel label="Resume Templates" sub="upload your own resumes (PDF/DOCX) as reusable style guides — the generator mimics the one you pick per job" />

      <input
        ref={fileRef}
        type="file"
        accept=".pdf,.docx,.txt,.md"
        style={{ display: "none" }}
        onChange={e => { const f = e.target.files?.[0]; if (f) void upload(f); }}
      />

      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 12 }}>
        <button className="btn btn-accent" disabled={loading} onClick={() => fileRef.current?.click()} style={{ padding: "8px 18px", fontSize: 13, borderRadius: 10 }}>
          {loading ? "Working…" : "Upload resume template"}
        </button>
        <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{templates.length} saved</span>
      </div>

      {error && <div style={{ color: "var(--bad)", fontSize: 12, fontWeight: 700, marginBottom: 10 }}>{error}</div>}

      {templates.length === 0 && !loading && (
        <div style={{ fontSize: 13, color: "var(--ink-3)", padding: "12px 14px", border: "1px dashed var(--line)", borderRadius: 12 }}>
          No templates yet. Upload a resume you like — it becomes the default style for generated resumes until you add more.
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {templates.map(t => (
          <div key={t.id} style={{ border: "1px solid var(--line)", borderRadius: 12, padding: "12px 14px", background: t.is_default ? "var(--blue-soft)" : "var(--paper)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 14, display: "flex", alignItems: "center", gap: 8 }}>
                  {t.name}
                  {t.is_default && <span className="pill" style={{ fontSize: 10 }}>Default</span>}
                </div>
                <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>
                  {t.source_filename || "pasted text"} · {t.char_count.toLocaleString()} chars
                </div>
              </div>
              <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                {!t.is_default && (
                  <button className="btn" disabled={busyId === t.id} onClick={() => setDefault(t.id)} style={{ padding: "6px 12px", fontSize: 12, borderRadius: 8 }}>
                    Set default
                  </button>
                )}
                <button className="btn" disabled={busyId === t.id} onClick={() => remove(t.id)} style={{ padding: "6px 12px", fontSize: 12, borderRadius: 8, color: "var(--bad)" }}>
                  {busyId === t.id ? "…" : "Delete"}
                </button>
              </div>
            </div>
            {t.preview && (
              <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 8, whiteSpace: "pre-wrap", maxHeight: 48, overflow: "hidden" }}>
                {t.preview}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
