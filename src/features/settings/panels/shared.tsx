import { useCallback, useEffect, useMemo, useState } from "react";
import Icon from "../../../shared/components/Icon";
import { settingsApi } from "../../../api/settings";
import type { ApiFetch } from "../../../types";

export interface Cfg {
  llm_provider: string;
  anthropic_key: string; anthropic_model: string; openai_api_key: string; openai_model: string;
  deepseek_api_key: string; deepseek_model: string; gemini_api_key: string; gemini_model: string;
  groq_api_key: string; groq_model: string; nvidia_api_key: string;
  nvidia_model: string; xai_api_key: string; xai_model: string; kimi_api_key: string; kimi_model: string;
  mistral_api_key: string; mistral_model: string; openrouter_api_key: string; openrouter_model: string;
  together_api_key: string; together_model: string; fireworks_api_key: string; fireworks_model: string;
  cerebras_api_key: string; cerebras_model: string; perplexity_api_key: string; perplexity_model: string;
  huggingface_api_key: string; huggingface_model: string; cohere_api_key: string; cohere_model: string;
  sambanova_api_key: string; sambanova_model: string; qwen_api_key: string; qwen_model: string;
  azure_openai_api_key: string; azure_model: string; azure_openai_endpoint: string;
  custom_api_key: string; custom_model: string; custom_base_url: string;
  ollama_url: string;
  claude_cli_model: string; codex_cli_model: string; gemini_cli_model: string; copilot_cli_model: string;
  scout_provider: string;     scout_api_key: string;     scout_model: string;
  evaluator_provider: string; evaluator_api_key: string; evaluator_model: string;
  generator_provider: string; generator_api_key: string; generator_model: string;
  ingestor_provider: string;  ingestor_api_key: string;  ingestor_model: string;
  actuator_provider: string;  actuator_api_key: string;  actuator_model: string;
  apify_token: string; apify_actor: string; linkedin_cookie: string; x_bearer_token: string; x_search_queries: string; x_watchlist: string;
  hunter_api_key: string; proxycurl_api_key: string; contact_lookup_enabled: string;
  x_max_requests_per_scan: string; x_max_results_per_query: string; x_min_signal_score: string; x_hot_lead_threshold: string; x_enable_notifications: string;
  free_sources_enabled: string; free_source_targets: string; company_watchlist: string; free_source_max_requests: string; free_source_min_signal_score: string;
  custom_connectors_enabled: string; custom_connectors: string; custom_connector_headers: string;
  desired_position: string; onboarding_target_role: string; job_boards: string; job_market_focus: string;
  ghost_mode: string; auto_apply: string; headed_browser: string;
}

export const EMPTY: Cfg = {
  llm_provider: "ollama",
  anthropic_key: "", anthropic_model: "claude-sonnet-4-6", openai_api_key: "", openai_model: "gpt-4o-mini",
  deepseek_api_key: "", deepseek_model: "deepseek-chat", gemini_api_key: "", gemini_model: "gemini-2.5-flash",
  groq_api_key: "", groq_model: "llama-3.3-70b-versatile", nvidia_api_key: "",
  nvidia_model: "z-ai/glm-5.1", xai_api_key: "", xai_model: "grok-4", kimi_api_key: "", kimi_model: "kimi-k2.6",
  mistral_api_key: "", mistral_model: "mistral-large-latest", openrouter_api_key: "", openrouter_model: "openrouter/auto",
  together_api_key: "", together_model: "openai/gpt-oss-120b", fireworks_api_key: "", fireworks_model: "accounts/fireworks/models/llama-v3p1-70b-instruct",
  cerebras_api_key: "", cerebras_model: "llama-3.3-70b", perplexity_api_key: "", perplexity_model: "sonar",
  huggingface_api_key: "", huggingface_model: "openai/gpt-oss-120b", cohere_api_key: "", cohere_model: "command-a-03-2025",
  sambanova_api_key: "", sambanova_model: "Meta-Llama-3.3-70B-Instruct", qwen_api_key: "", qwen_model: "qwen-plus",
  azure_openai_api_key: "", azure_model: "gpt-4o-mini", azure_openai_endpoint: "",
  custom_api_key: "", custom_model: "model-id", custom_base_url: "https://api.openai.com/v1",
  ollama_url: "http://localhost:11434/v1",
  claude_cli_model: "claude-sonnet-4-6", codex_cli_model: "", gemini_cli_model: "", copilot_cli_model: "",
  scout_provider: "", scout_api_key: "", scout_model: "",
  evaluator_provider: "", evaluator_api_key: "", evaluator_model: "",
  generator_provider: "", generator_api_key: "", generator_model: "",
  ingestor_provider: "", ingestor_api_key: "", ingestor_model: "",
  actuator_provider: "", actuator_api_key: "", actuator_model: "",
  apify_token: "", apify_actor: "", linkedin_cookie: "", x_bearer_token: "", x_search_queries: "", x_watchlist: "",
  hunter_api_key: "", proxycurl_api_key: "", contact_lookup_enabled: "true",
  x_max_requests_per_scan: "5", x_max_results_per_query: "50", x_min_signal_score: "60", x_hot_lead_threshold: "80", x_enable_notifications: "false",
  free_sources_enabled: "", free_source_targets: "", company_watchlist: "", free_source_max_requests: "20", free_source_min_signal_score: "60",
  custom_connectors_enabled: "false", custom_connectors: "", custom_connector_headers: "",
  desired_position: "", onboarding_target_role: "", job_boards: "", job_market_focus: "global",
  ghost_mode: "false", auto_apply: "false", headed_browser: "false",
};

export const PROVIDERS = [
  { id: "claude_cli", label: "Claude · sub", tone: "purple", sub: "Your plan" },
  { id: "codex_cli",  label: "Codex · sub",  tone: "blue",   sub: "Your plan" },
  { id: "gemini_cli", label: "Gemini · sub", tone: "orange", sub: "Your plan" },
  { id: "copilot_cli", label: "Copilot · sub", tone: "green", sub: "Your plan" },
  { id: "gemini",    label: "Gemini",    tone: "green",  sub: "2.5 Flash" },
  { id: "deepseek",  label: "DeepSeek",  tone: "teal",   sub: "V3 / R1"   },
  { id: "nvidia",    label: "NVIDIA",    tone: "green",  sub: "GLM / NIM" },
  { id: "groq",      label: "Groq",      tone: "orange", sub: "Llama 3.3" },
  { id: "xai",       label: "Grok",      tone: "blue",   sub: "xAI"       },
  { id: "kimi",      label: "Kimi",      tone: "purple", sub: "Moonshot"  },
  { id: "mistral",   label: "Mistral",   tone: "orange", sub: "Large"     },
  { id: "openrouter", label: "OpenRouter", tone: "teal", sub: "Many"      },
  { id: "together",  label: "Together",  tone: "pink",   sub: "OSS"       },
  { id: "fireworks", label: "Fireworks", tone: "yellow", sub: "Fast OSS"  },
  { id: "cerebras",  label: "Cerebras",  tone: "green",  sub: "Fast"      },
  { id: "perplexity", label: "Perplexity", tone: "blue", sub: "Search"    },
  { id: "huggingface", label: "HuggingFace", tone: "yellow", sub: "Router" },
  { id: "cohere",   label: "Cohere",   tone: "green",  sub: "Command"   },
  { id: "sambanova", label: "SambaNova", tone: "orange", sub: "Cloud"    },
  { id: "qwen",     label: "Qwen",      tone: "teal",   sub: "DashScope" },
  { id: "azure",    label: "Azure",     tone: "blue",   sub: "OpenAI"    },
  { id: "openai",    label: "OpenAI",    tone: "blue",   sub: "GPT-4o"    },
  { id: "anthropic", label: "Anthropic", tone: "purple", sub: "Claude"    },
  { id: "custom",    label: "Custom",    tone: "pink",   sub: "OpenAI API" },
  { id: "ollama",    label: "Ollama",    tone: "pink",   sub: "Local"     },
];

// Providers that use the user's own logged-in CLI subscription (no API key).
export const SUBSCRIPTION_PROVIDERS = new Set(["claude_cli", "codex_cli", "gemini_cli", "copilot_cli"]);
export const isSubscriptionProvider = (id: string) => SUBSCRIPTION_PROVIDERS.has(id);

export const MODEL_HINTS: Record<string, string[]> = {
  gemini:    ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
  deepseek:  ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"],
  nvidia:    ["z-ai/glm-5.1", "nvidia/llama-3.3-nemotron-super-49b-v1", "meta/llama-3.1-70b-instruct", "openai/gpt-oss-120b"],
  groq:      ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
  xai:       ["grok-4", "grok-3", "grok-3-mini"],
  kimi:      ["kimi-k2.6", "kimi-k2.5", "kimi-k2-thinking", "kimi-k2-turbo-preview", "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
  mistral:   ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest", "ministral-8b-latest"],
  openrouter: ["openrouter/auto", "anthropic/claude-sonnet-4.5", "google/gemini-2.5-pro", "moonshotai/kimi-k2"],
  together:  ["openai/gpt-oss-120b", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "deepseek-ai/DeepSeek-V3.1", "moonshotai/Kimi-K2-Instruct"],
  fireworks: ["accounts/fireworks/models/llama-v3p1-70b-instruct", "accounts/fireworks/models/qwen2p5-72b-instruct", "accounts/fireworks/models/deepseek-v3"],
  cerebras:  ["llama-3.3-70b", "llama3.1-8b", "gpt-oss-120b"],
  perplexity: ["sonar", "sonar-pro", "sonar-reasoning", "sonar-deep-research"],
  huggingface: ["openai/gpt-oss-120b", "meta-llama/Llama-3.1-8B-Instruct", "Qwen/Qwen2.5-72B-Instruct"],
  cohere:    ["command-a-03-2025", "command-r-plus-08-2024", "command-r-08-2024"],
  sambanova: ["Meta-Llama-3.3-70B-Instruct", "DeepSeek-R1", "Qwen3-32B"],
  qwen:      ["qwen-plus", "qwen-max", "qwen-turbo", "qwen3-coder-plus"],
  azure:     ["gpt-4o-mini", "gpt-4o", "gpt-4.1", "deployment-name"],
  openai:    ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.2", "gpt-4o-mini", "gpt-4o"],
  anthropic: ["claude-opus-4-8", "claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5-20251001"],
  custom:    ["model-id", "provider/model", "chat-model"],
  ollama:    ["llama3", "mistral", "gemma2", "codellama"],
  claude_cli: ["claude-sonnet-4-6", "claude-opus-4-8", "claude-opus-4-7", "claude-haiku-4-5-20251001"],
  // ChatGPT-account Codex only allows its own default model (gpt-5.5 as of
  // 2026-06); -codex variants and other gpt-5.x 400 with "not supported when
  // using Codex with a ChatGPT account". "" = use your codex config default
  // (recommended). Backend auto-falls-back to the account default if an
  // override is rejected.
  codex_cli:  ["", "gpt-5.5"],
  // "" = let the CLI use your plan's default model.
  gemini_cli: ["", "gemini-2.5-pro", "gemini-2.5-flash"],
  copilot_cli: ["", "claude-sonnet-4.5", "gpt-5.3-codex", "claude-haiku-4.5"],
};

export const STEPS = [
  { id: "scout",     label: "Scout",     icon: "search", tone: "blue",
    desc: "Discovers job listings - a fast cheap model is ideal here" },
  { id: "evaluator", label: "Evaluator", icon: "pulse",  tone: "purple",
    desc: "Scores job fit - use a reasoning model (DeepSeek R1) for best results" },
  { id: "generator", label: "Generator", icon: "file",   tone: "orange",
    desc: "Writes tailored resumes + cover letters - quality matters here" },
  { id: "ingestor",  label: "Ingestor",  icon: "upload", tone: "green",
    desc: "Parses your resume into the knowledge graph" },
  { id: "actuator",  label: "Experimental Actuator",  icon: "ghost",  tone: "pink",
    desc: "Unsupported browser automation lab - not part of the core OSS workflow" },
];

export const GLOBAL_SOURCE_PRESET = [
  "hn-hiring,",
  "https://remoteok.com/api,",
  "https://remotive.com/api/remote-jobs,",
  "https://jobicy.com/api/v2/remote-jobs?count=50,",
  "https://jobicy.com/feed/newjobs,",
  "https://weworkremotely.com/remote-jobs.rss,",
  "site:boards.greenhouse.io,",
  "site:jobs.lever.co,",
  "site:jobs.ashbyhq.com,",
  "site:apply.workable.com,",
  "site:wellfound.com/jobs,",
  "site:linkedin.com/jobs,",
  "site:indeed.com/jobs,",
  "site:glassdoor.com/Job,",
  "site:jobs.smartrecruiters.com,",
  "site:workdayjobs.com,",
  "site:naukri.com,",
  "site:instahyre.com,",
  "site:cutshort.io/jobs,",
].join("\n");

export const INDIA_SOURCE_PRESET = [
  "site:wellfound.com/jobs India,",
  "site:cutshort.io/jobs India startup,",
  "site:instahyre.com jobs India,",
  "site:naukri.com jobs India,",
  "site:foundit.in jobs India,",
  "site:internshala.com/jobs India,",
  "site:linkedin.com/jobs India,",
  "site:indeed.com/jobs India,",
  "site:glassdoor.co.in Job India,",
  "site:boards.greenhouse.io India,",
  "site:jobs.lever.co India,",
  "site:jobs.ashbyhq.com India,",
  "site:apply.workable.com India,",
].join("\n");

export const KEY_FIELD: Record<string, keyof Cfg> = {
  anthropic: "anthropic_key", gemini: "gemini_api_key", groq: "groq_api_key",
  nvidia: "nvidia_api_key", openai: "openai_api_key", deepseek: "deepseek_api_key",
  xai: "xai_api_key", kimi: "kimi_api_key", mistral: "mistral_api_key",
  openrouter: "openrouter_api_key", together: "together_api_key", fireworks: "fireworks_api_key",
  cerebras: "cerebras_api_key", perplexity: "perplexity_api_key", huggingface: "huggingface_api_key",
  cohere: "cohere_api_key", sambanova: "sambanova_api_key", qwen: "qwen_api_key", azure: "azure_openai_api_key",
  custom: "custom_api_key",
};

export const GLOBAL_MODEL_FIELD: Record<string, keyof Cfg> = {
  anthropic: "anthropic_model",
  deepseek: "deepseek_model",
  gemini: "gemini_model",
  groq: "groq_model",
  nvidia: "nvidia_model",
  openai: "openai_model",
  xai: "xai_model",
  kimi: "kimi_model",
  mistral: "mistral_model",
  openrouter: "openrouter_model",
  together: "together_model",
  fireworks: "fireworks_model",
  cerebras: "cerebras_model",
  perplexity: "perplexity_model",
  huggingface: "huggingface_model",
  cohere: "cohere_model",
  sambanova: "sambanova_model",
  qwen: "qwen_model",
  azure: "azure_model",
  custom: "custom_model",
  claude_cli: "claude_cli_model",
  codex_cli: "codex_cli_model",
  gemini_cli: "gemini_cli_model",
  copilot_cli: "copilot_cli_model",
};

const SECRET_MASK = "__JHM_SECRET_SET__";
const LEGACY_BULLET_MASK = "\u2022".repeat(20);
const LEGACY_MOJIBAKE_BULLET_MASK = "\u00e2\u20ac\u00a2".repeat(20);
const LEGACY_DOUBLE_ENCODED_BULLET_MASK = "\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u00a2".repeat(20);

export const SECRET_MASKS = new Set([
  SECRET_MASK,
  LEGACY_BULLET_MASK,
  LEGACY_MOJIBAKE_BULLET_MASK,
  LEGACY_DOUBLE_ENCODED_BULLET_MASK,
]);

/* helpers */
export function LabelledField({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-2)" }}>{label}</span>
        {hint && <span style={{ fontSize: 11, color: "var(--ink-3)" }}>{hint}</span>}
      </div>
      {children}
    </div>
  );
}

export function SectionLabel({ label, sub }: { label: string; sub?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
      <span style={{ fontSize: 13, fontWeight: 700 }}>{label}</span>
      {sub && <span style={{ fontSize: 11, color: "var(--ink-3)", fontFamily: "var(--font-mono)" }}>{sub}</span>}
    </div>
  );
}

export function ProviderPills({ value, onChange, small }: { value: string; onChange: (v: string) => void; small?: boolean }) {
  return (
    <div style={{ display: "flex", gap: small ? 5 : 7, flexWrap: "wrap" }}>
      {PROVIDERS.map(p => {
        const active = value === p.id;
        return (
          <button key={p.id} onClick={() => onChange(p.id)} style={{
            padding: small ? "5px 10px" : "10px 12px", borderRadius: small ? 8 : 11, cursor: "pointer",
            background: active ? `var(--${p.tone}-soft)` : "var(--card)",
            border: `1.5px solid ${active ? `var(--${p.tone})` : "var(--line)"}`,
            display: "flex", flexDirection: "column", alignItems: "center",
            gap: small ? 2 : 5, transition: "all .15s ease", minWidth: small ? 0 : 78,
          }}>
            <div style={{ fontSize: small ? 12 : 13, fontWeight: 600, color: active ? `var(--${p.tone}-ink)` : "var(--ink-2)" }}>
              {p.label}
            </div>
            {!small && <div style={{ fontFamily: "var(--font-mono)", fontSize: 9.5, color: "var(--ink-3)" }}>{p.sub}</div>}
          </button>
        );
      })}
    </div>
  );
}

export type CatalogRow = {
  id: string; name?: string; release_date?: string; reasoning?: boolean;
  context?: number | null; input?: number | null; output?: number | null;
};

function fmtCtx(n?: number | null): string {
  if (!n) return "";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 ? 1 : 0)}M`;
  if (n >= 1000) return `${Math.round(n / 1000)}K`;
  return String(n);
}
function fmtMeta(c?: CatalogRow): string {
  if (!c) return "";
  const parts: string[] = [];
  const ctx = fmtCtx(c.context);
  if (ctx) parts.push(`${ctx} ctx`);
  if (c.input != null || c.output != null) parts.push(`$${c.input ?? "?"}/$${c.output ?? "?"}`);
  if (c.reasoning) parts.push("reasoning");
  if (c.release_date) parts.push(c.release_date.slice(0, 7));
  return parts.join("  ·  ");
}

/**
 * Model picker backed by the always-current models.dev catalog (fetched live and
 * cached server-side, with an offline snapshot) plus whatever the user's own key
 * can actually reach. It auto-loads the moment a provider is chosen — no button —
 * is searchable (providers like OpenRouter list hundreds), shows context/price/
 * date metadata, and is ALWAYS free-form: type any model id, even one neither the
 * catalog nor your key knows yet. `MODEL_HINTS` is only an offline fallback now.
 */
export function ModelChips({ provider, value, onChange, api, cfg }: {
  provider: string; value: string; onChange: (v: string) => void; api?: ApiFetch | null; cfg?: Cfg;
}) {
  const [models, setModels] = useState<string[]>([]);
  const [catalog, setCatalog] = useState<CatalogRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const reload = useCallback(() => {
    if (!api || !provider || isSubscriptionProvider(provider) || provider === "ollama") {
      setModels([]); setCatalog([]); return;
    }
    setLoading(true);
    settingsApi.models(api, provider, cfg || {})
      .then(r => r.json())
      .then(d => {
        setModels(Array.isArray(d.models) ? d.models : []);
        setCatalog(Array.isArray(d.catalog) ? d.catalog : []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
    // cfg intentionally excluded: reload on provider change, not every keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, provider]);
  useEffect(() => { reload(); }, [reload]);

  const ids = models.length ? models : (MODEL_HINTS[provider] || []);
  const meta = useMemo(() => new Map(catalog.map(c => [c.id, c])), [catalog]);
  const q = value.trim().toLowerCase();
  const exact = ids.some(m => m.toLowerCase() === q);
  const filtered = (q && !exact) ? ids.filter(m => m.toLowerCase().includes(q)) : ids;
  const shown = filtered.slice(0, 60);

  return (
    <div style={{ position: "relative", display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ position: "relative" }}>
        <input
          type="text"
          value={value}
          onChange={e => { onChange(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 160)}
          placeholder={ids.length ? `Search ${ids.length} models or type any id…` : "Type any model id…"}
          className="mono field-input"
          style={{ width: "100%", paddingRight: 70, fontSize: 12 }}
        />
        <div style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", display: "flex", alignItems: "center", gap: 6 }}>
          {loading
            ? <span className="spinner-sm" aria-hidden="true" />
            : ids.length > 0 && <span style={{ fontSize: 10, color: "var(--ink-3)", fontFamily: "var(--font-mono)" }}>{ids.length}</span>}
          <button type="button" onMouseDown={e => { e.preventDefault(); setOpen(o => !o); }}
            aria-label="Toggle model list" title="Browse models"
            style={{ border: "none", background: "transparent", cursor: "pointer", color: "var(--ink-3)", padding: 0, fontSize: 11, lineHeight: 1 }}>
            {open ? "▴" : "▾"}
          </button>
        </div>
      </div>
      {!open && ids.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
          {ids.slice(0, 8).map(m => {
            const active = value === m;
            const label = m === "" ? "Plan default" : (m.length > 28 ? `…${m.slice(-26)}` : m);
            return (
              <button key={m || "__default"} type="button" onClick={() => onChange(m)}
                title={m || "Use your plan's own default model"}
                style={{
                  padding: "3px 10px", borderRadius: 999, fontSize: 11, cursor: "pointer",
                  fontFamily: m === "" ? "inherit" : "var(--font-mono)",
                  background: active ? "var(--ink)" : "var(--paper-2)",
                  color: active ? "var(--paper)" : "var(--ink-2)",
                  border: `1px solid ${active ? "var(--ink)" : "var(--line)"}`,
                }}>
                {label}
              </button>
            );
          })}
          {ids.length > 8 && <span style={{ fontSize: 10.5, color: "var(--ink-3)", alignSelf: "center" }}>+{ids.length - 8} more — search above</span>}
        </div>
      )}
      {open && shown.length > 0 && (
        <div style={{
          position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 30,
          maxHeight: 300, overflowY: "auto", background: "var(--card)", border: "1px solid var(--line)",
          borderRadius: 10, boxShadow: "var(--shadow-md, 0 8px 28px rgba(0,0,0,0.14))", padding: 4,
        }}>
          {shown.map(m => {
            const c = meta.get(m);
            const metaText = fmtMeta(c);
            const active = value === m;
            return (
              <button key={m} type="button" onMouseDown={e => { e.preventDefault(); onChange(m); setOpen(false); }}
                style={{
                  width: "100%", textAlign: "left", border: "1px solid transparent", borderRadius: 7,
                  background: active ? "var(--paper-2)" : "transparent", cursor: "pointer",
                  padding: "7px 9px", display: "flex", flexDirection: "column", gap: 2,
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "var(--paper-2)"; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = active ? "var(--paper-2)" : "transparent"; }}>
                <span className={m === "" ? "" : "mono"} style={{ fontSize: 12, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m === "" ? "Plan default" : m}</span>
                {metaText && <span style={{ fontSize: 10, color: "var(--ink-3)" }}>{metaText}</span>}
              </button>
            );
          })}
          {filtered.length > shown.length && (
            <div style={{ fontSize: 10.5, color: "var(--ink-3)", padding: "6px 9px" }}>+{filtered.length - shown.length} more — keep typing to filter</div>
          )}
        </div>
      )}
    </div>
  );
}

export function ApiKeyInput({ value, onChange, provider, isStep, disabled = false, placeholder }: {
  value: string; onChange: (v: string) => void; provider: string; isStep?: boolean; disabled?: boolean; placeholder?: string;
}) {
  if (provider === "ollama" || isSubscriptionProvider(provider)) return null;
  const ph: Record<string, string> = {
    anthropic: "sk-ant-****", gemini: "AIza****", groq: "gsk_****", nvidia: "nvapi-****",
    openai: "sk-****", deepseek: "sk-****", xai: "xai-****", kimi: "sk-****",
    mistral: "****", openrouter: "sk-or-****", together: "****", fireworks: "fw_****",
    cerebras: "csk-****", perplexity: "pplx-****", huggingface: "hf_****", cohere: "co_****",
    sambanova: "****", qwen: "sk-****", azure: "Azure OpenAI key", custom: "API key",
  };
  return (
    <input type="password" value={SECRET_MASKS.has(value) ? "" : value} onChange={e => onChange(e.target.value)} disabled={disabled}
      placeholder={placeholder || (isStep ? `API key for ${provider}` : ph[provider] || "API key")}
      className="mono field-input"
      style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: disabled ? "var(--paper-3)" : "var(--card)", fontSize: 12, opacity: disabled ? 0.75 : 1, cursor: disabled ? "not-allowed" : "text" }}
    />
  );
}

export interface SubStatus {
  installed: boolean;
  logged_in: boolean;
  email?: string | null;
  plan?: string | null;
  install_hint?: { name: string; cmd: string; url: string; after?: string };
}

function subBadge(tone: string, text: React.ReactNode) {
  const s = tone === "bad"
    ? { background: "var(--bad-soft)", color: "var(--bad)", border: "1px solid var(--bad)" }
    : { background: `var(--${tone}-soft)`, color: `var(--${tone}-ink)`, border: `1px solid var(--${tone})` };
  return <span className="mono" style={{ alignSelf: "flex-start", fontSize: 10.5, padding: "3px 9px", borderRadius: 999, ...s }}>{text}</span>;
}

export function SubscriptionNote({ provider, status, onSignIn, busy }: {
  provider: string;
  status?: SubStatus;
  onSignIn?: () => void;
  busy?: boolean;
}) {
  const cli = ({ claude_cli: "claude", codex_cli: "codex", gemini_cli: "gemini", copilot_cli: "copilot" } as Record<string, string>)[provider] || provider;
  const plan = ({
    claude_cli: "Claude (Pro / Max)",
    codex_cli: "ChatGPT (Plus / Pro)",
    gemini_cli: "Google account / Gemini",
    copilot_cli: "GitHub Copilot",
  } as Record<string, string>)[provider] || "subscription";

  let inner: React.ReactNode;
  if (!status) {
    inner = subBadge("yellow", `Checking for the ${cli} CLI…`);
  } else if (!status.installed) {
    const h = status.install_hint;
    inner = (
      <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        {subBadge("bad", `${cli} CLI not installed`)}
        {h && <>
          <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>Install it, then click Sign in:</div>
          <code style={{ fontFamily: "var(--font-mono)", fontSize: 11.5, background: "var(--paper-3)", border: "1px solid var(--line)", borderRadius: 7, padding: "6px 9px", userSelect: "all" }}>{h.cmd}</code>
          <a href={h.url} target="_blank" rel="noreferrer" style={{ fontSize: 11.5, color: "var(--accent)" }}>installation guide ↗</a>
        </>}
      </div>
    );
  } else if (!status.logged_in) {
    inner = (
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        {subBadge("yellow", `${cli} CLI found — not signed in`)}
        <button className="btn" onClick={onSignIn} disabled={busy} style={{ fontSize: 12 }}>
          {busy ? "Opening sign-in…" : "Sign in"}
        </button>
        <span style={{ fontSize: 11, color: "var(--ink-3)" }}>opens a browser to your {plan} account</span>
      </div>
    );
  } else {
    inner = subBadge("green", `Signed in${status.email ? ` as ${status.email}` : ""}${status.plan ? ` · ${status.plan} plan` : ""} — ready`);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 9, padding: "11px 13px", borderRadius: 11, background: "var(--paper-2)", border: "1px solid var(--line)" }}>
      <div style={{ fontSize: 12, color: "var(--ink-2)", lineHeight: 1.5 }}>
        Runs on <b>your {plan} subscription</b> through the <span className="mono">{cli}</span> CLI — <b>no API key</b>. Your own local automation; usage draws from your plan, not per-token billing.
      </div>
      {inner}
    </div>
  );
}

export function StepCard({ step, cfg, onChange, api }: { step: typeof STEPS[0]; cfg: Cfg; onChange: (k: keyof Cfg, v: string) => void; api?: ApiFetch | null }) {
  const provKey  = `${step.id}_provider` as keyof Cfg;
  const apiKey   = `${step.id}_api_key`  as keyof Cfg;
  const modelKey = `${step.id}_model`    as keyof Cfg;
  const isCustom = !!(cfg[provKey] as string);
  const stepProv = (cfg[provKey] as string) || cfg.llm_provider || "ollama";
  const [forceStepKey, setForceStepKey] = useState(false);
  const usesGlobalKey = stepProv !== "ollama" && !forceStepKey && !(cfg[apiKey] as string);
  const keySourceLabel = stepProv === cfg.llm_provider
    ? `Use global ${stepProv} API key`
    : `Use saved ${stepProv} API key`;
  const enable  = () => { setForceStepKey(false); onChange(provKey, cfg.llm_provider || "ollama"); };
  const disable = () => { setForceStepKey(false); onChange(provKey, ""); onChange(apiKey, ""); onChange(modelKey, ""); };

  return (
    <div style={{ padding: 14, borderRadius: 14, background: isCustom ? "var(--card)" : "var(--paper-2)", border: `1.5px solid ${isCustom ? `var(--${step.tone})` : "var(--line)"}`, transition: "all .15s ease" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: isCustom ? 14 : 0 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <div style={{ width: 26, height: 26, borderRadius: 7, flexShrink: 0, background: isCustom ? `var(--${step.tone}-soft)` : "var(--paper-3)", color: isCustom ? `var(--${step.tone}-ink)` : "var(--ink-3)", display: "grid", placeItems: "center" }}>
              <Icon name={step.icon} size={13} />
            </div>
            <span style={{ fontSize: 13, fontWeight: 700 }}>{step.label}</span>
            {isCustom && (
              <span className="mono" style={{ fontSize: 9.5, letterSpacing: "0.1em", textTransform: "uppercase", background: `var(--${step.tone}-soft)`, color: `var(--${step.tone}-ink)`, padding: "2px 8px", borderRadius: 999 }}>
                {stepProv}{cfg[modelKey] ? ` / ${cfg[modelKey]}` : ""}
              </span>
            )}
          </div>
          <div style={{ fontSize: 11.5, color: "var(--ink-3)", paddingLeft: 33, lineHeight: 1.4 }}>{step.desc}</div>
        </div>
        <button onClick={isCustom ? disable : enable} style={{ padding: "4px 12px", borderRadius: 999, cursor: "pointer", fontSize: 11, fontWeight: 600, fontFamily: "var(--font-mono)", letterSpacing: "0.08em", textTransform: "uppercase", flexShrink: 0, background: isCustom ? "var(--ink)" : "var(--paper-3)", color: isCustom ? "var(--paper)" : "var(--ink-3)", border: `1.5px solid ${isCustom ? "var(--ink)" : "var(--line)"}`, transition: "all .15s ease" }}>
          {isCustom ? "custom" : "global"}
        </button>
      </div>
      {isCustom && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 7 }}>Provider</div>
            <ProviderPills value={stepProv} onChange={v => { setForceStepKey(false); onChange(provKey, v); onChange(apiKey, ""); }} small />
          </div>
          {stepProv !== "ollama" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--ink-2)", cursor: "pointer", userSelect: "none" }}>
                <input
                  type="checkbox"
                  checked={usesGlobalKey}
                  onChange={e => {
                    if (e.target.checked) {
                      setForceStepKey(false);
                      onChange(apiKey, "");
                    } else {
                      setForceStepKey(true);
                    }
                  }}
                  style={{ width: 14, height: 14, accentColor: "var(--accent)", cursor: "pointer" }}
                />
                <span>{keySourceLabel}</span>
              </label>
              <ApiKeyInput
                value={usesGlobalKey ? "" : (cfg[apiKey] as string)}
                onChange={v => { setForceStepKey(true); onChange(apiKey, v); }}
                provider={stepProv}
                isStep
                disabled={usesGlobalKey}
                placeholder={usesGlobalKey ? "Using global key; choose any model below" : `Optional ${stepProv} key for this step`}
              />
            </div>
          )}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 7 }}>Model</div>
            <ModelChips provider={stepProv} value={cfg[modelKey] as string} onChange={v => onChange(modelKey, v)} api={api} cfg={cfg} />
          </div>
        </div>
      )}
    </div>
  );
}

export function BigToggle({ active, onToggle, icon, label, badge, sub, tone }: { active: boolean; onToggle: () => void; icon: string; label: string; badge: string; sub: string; tone: string }) {
  return (
    <div onClick={onToggle} style={{ padding: 14, borderRadius: 14, cursor: "pointer", background: active ? `var(--${tone}-soft)` : "var(--paper-2)", border: `1px solid ${active ? `var(--${tone})` : "var(--line)"}`, transition: "all .2s ease", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 32, height: 32, borderRadius: 9, flexShrink: 0, background: active ? `var(--${tone})` : "var(--paper-3)", color: active ? `var(--${tone}-ink)` : "var(--ink-3)", display: "grid", placeItems: "center", transition: "all .2s ease" }}>
          <Icon name={icon} size={15} />
        </div>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>{label}</span>
            <span className="mono" style={{ fontSize: 9, letterSpacing: "0.1em", textTransform: "uppercase", background: active ? `var(--${tone})` : "var(--paper-3)", color: active ? `var(--${tone}-ink)` : "var(--ink-3)", padding: "2px 7px", borderRadius: 999, transition: "all .2s ease" }}>{badge}</span>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginTop: 2 }}>{sub}</div>
        </div>
      </div>
      <div style={{ width: 42, height: 24, borderRadius: 999, flexShrink: 0, background: active ? `var(--${tone})` : "var(--paper-4)", position: "relative", transition: "background .2s ease" }}>
        <div style={{ position: "absolute", top: 3, left: active ? 21 : 3, width: 18, height: 18, borderRadius: 999, background: "white", transition: "left .2s ease", boxShadow: "0 1px 4px rgba(0,0,0,0.15)" }} />
      </div>
    </div>
  );
}
