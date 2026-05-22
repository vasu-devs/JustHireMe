import { useState, type ChangeEvent } from "react";
import type { Cfg } from "./shared";
import { BigToggle, GLOBAL_SOURCE_PRESET, INDIA_SOURCE_PRESET, LabelledField, SectionLabel } from "./shared";

export function DiscoverySettings({ cfg, set, onChange }: { cfg: Cfg; set: (k: keyof Cfg) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void; onChange: (k: keyof Cfg, v: string) => void }) {
  const [siteDraft, setSiteDraft] = useState("");

  const sourceTargetFromSite = (raw: string) => {
    const value = raw.trim().replace(/,$/, "");
    if (!value) return "";
    const lower = value.toLowerCase();
    if (/^(hn-hiring|site:|ats:|github:|hn:|reddit:|https?:\/\/)/i.test(value)) {
      if (lower.includes("greenhouse.io") || lower.includes("lever.co") || lower.includes("ashbyhq.com") || lower.includes("workable.com")) {
        return value;
      }
      return value;
    }
    const domain = value.replace(/^www\./i, "").replace(/\/+$/, "");
    return `site:${domain} ("jobs" OR "careers" OR "hiring" OR "open roles") (remote OR hybrid OR onsite OR India OR global)`;
  };

  const addSiteSource = () => {
    const target = sourceTargetFromSite(siteDraft);
    if (!target || cfg.job_boards.includes(target)) return;
    const sep = cfg.job_boards.trim() ? ",\n" : "";
    onChange("job_boards", cfg.job_boards.trim() + sep + target);
    setSiteDraft("");
  };

  return (
    <>
{/* 3. Scraping */}
          <div style={{ borderTop: "1px dashed var(--line)", paddingTop: 18 }}>
            <SectionLabel label="Scraping & Discovery" />
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <LabelledField label="Target roles / titles" hint="optional; the profile graph still stays primary">
                <textarea value={cfg.desired_position || cfg.onboarding_target_role || ""} onChange={e => {
                  onChange("desired_position", e.target.value);
                  onChange("onboarding_target_role", e.target.value);
                }} rows={3} className="mono field-input"
                  placeholder={"Backend Engineer\nAI Engineer\nFull-stack Developer"}
                  style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 11.5, resize: "vertical", lineHeight: 1.6 }} />
              </LabelledField>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <LabelledField label="Apify Token" hint="for LinkedIn/X scraping">
                  <input type="password" placeholder="apify_api_***" value={cfg.apify_token} onChange={set("apify_token")} className="mono field-input"
                    style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 12 }} />
                </LabelledField>
                <LabelledField label="Apify Actor ID" hint="actor to run">
                  <input type="text" placeholder="drobnikj/..." value={cfg.apify_actor} onChange={set("apify_actor")} className="mono field-input"
                    style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 12 }} />
                </LabelledField>
              </div>
              <LabelledField label="LinkedIn session cookie" hint="li_at value">
                <input type="password" placeholder="li_at=***" value={cfg.linkedin_cookie} onChange={set("linkedin_cookie")} className="mono field-input"
                  style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 12 }} />
              </LabelledField>
              <div style={{ padding: 13, borderRadius: 13, background: "var(--paper-2)", border: "1px solid var(--line)", display: "flex", flexDirection: "column", gap: 10 }}>
                <SectionLabel label="Recruiter Lookup" sub="Hunter.io emails, optional Proxycurl LinkedIn" />
                <BigToggle
                  active={cfg.contact_lookup_enabled !== "false"}
                  onToggle={() => onChange("contact_lookup_enabled", cfg.contact_lookup_enabled === "false" ? "true" : "false")}
                  icon="user"
                  label="Who to contact"
                  badge={cfg.contact_lookup_enabled !== "false" ? "on" : "off"}
                  sub="Runs after package generation and stores the best contact on the lead"
                  tone="blue"
                />
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <LabelledField label="Hunter.io API key" hint="domain search">
                    <input type="password" placeholder="hunter key" value={cfg.hunter_api_key} onChange={set("hunter_api_key")} className="mono field-input"
                      style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 12 }} />
                  </LabelledField>
                  <LabelledField label="Proxycurl API key" hint="optional LinkedIn resolve">
                    <input type="password" placeholder="proxycurl key" value={cfg.proxycurl_api_key} onChange={set("proxycurl_api_key")} className="mono field-input"
                      style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 12 }} />
                  </LabelledField>
                </div>
              </div>

              <div style={{ padding: 13, borderRadius: 13, background: "var(--paper-2)", border: "1px solid var(--line)", display: "flex", flexDirection: "column", gap: 10 }}>
                <SectionLabel label="X Signals" sub="recent posts for job leads" />
                <LabelledField label="X API Bearer Token" hint="Developer Console token">
                  <input type="password" placeholder="Bearer token" value={cfg.x_bearer_token} onChange={set("x_bearer_token")} className="mono field-input"
                    style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 12 }} />
                </LabelledField>
                <LabelledField label="X recent-search queries" hint="one query per line; leave blank for AI defaults">
                  <textarea value={cfg.x_search_queries} onChange={set("x_search_queries")} rows={4} className="mono field-input"
                    placeholder={[
                      "(\"hiring\" OR \"job opening\" OR \"open role\") (\"marketing\" OR \"sales\" OR \"operations\" OR \"developer\") lang:en -is:retweet",
                      "(\"we are hiring\" OR \"is hiring\") (\"remote\" OR \"hybrid\" OR \"India\" OR \"global\") lang:en -is:retweet",
                      "(\"apply\" OR \"open role\") (\"entry level\" OR \"associate\" OR \"manager\" OR \"specialist\") lang:en -is:retweet",
                    ].join("\n")}
                    style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 11.5, resize: "vertical", lineHeight: 1.6 }} />
                </LabelledField>
                <LabelledField label="X watchlist handles" hint="one founder, hiring, or company account per line">
                  <textarea value={cfg.x_watchlist} onChange={set("x_watchlist")} rows={3} className="mono field-input"
                    placeholder={"@target_company\n@founder_or_hiring_team\n@job_board_handle"}
                    style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 11.5, resize: "vertical", lineHeight: 1.6 }} />
                </LabelledField>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 8 }}>
                  <LabelledField label="Requests" hint="per scan">
                    <input type="number" min={1} max={50} value={cfg.x_max_requests_per_scan} onChange={set("x_max_requests_per_scan")} className="mono field-input"
                      style={{ width: "100%", padding: "9px 10px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 12 }} />
                  </LabelledField>
                  <LabelledField label="Posts" hint="per query">
                    <input type="number" min={10} max={100} value={cfg.x_max_results_per_query} onChange={set("x_max_results_per_query")} className="mono field-input"
                      style={{ width: "100%", padding: "9px 10px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 12 }} />
                  </LabelledField>
                  <LabelledField label="Min signal" hint="0-100">
                    <input type="number" min={0} max={100} value={cfg.x_min_signal_score} onChange={set("x_min_signal_score")} className="mono field-input"
                      style={{ width: "100%", padding: "9px 10px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 12 }} />
                  </LabelledField>
                  <LabelledField label="Hot score" hint="0-100">
                    <input type="number" min={1} max={100} value={cfg.x_hot_lead_threshold} onChange={set("x_hot_lead_threshold")} className="mono field-input"
                      style={{ width: "100%", padding: "9px 10px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 12 }} />
                  </LabelledField>
                </div>
                <BigToggle
                  active={cfg.x_enable_notifications === "true"}
                  onToggle={() => onChange("x_enable_notifications", cfg.x_enable_notifications === "true" ? "false" : "true")}
                  icon="spark"
                  label="Hot X notifications"
                  badge={cfg.x_enable_notifications === "true" ? "on" : "off"}
                  sub="Desktop alert when an X lead crosses the hot score"
                  tone="orange"
                />
              </div>
              <div style={{ padding: 13, borderRadius: 13, background: "var(--paper-2)", border: "1px solid var(--line)", display: "flex", flexDirection: "column", gap: 10 }}>
                <SectionLabel label="Free Source Stack" sub="Optional job-only ATS, GitHub, HN, and Reddit sources" />
                <BigToggle
                  active={cfg.free_sources_enabled !== "false"}
                  onToggle={() => onChange("free_sources_enabled", cfg.free_sources_enabled === "false" ? "true" : "false")}
                  icon="search"
                  label="Free scouts"
                  badge={cfg.free_sources_enabled !== "false" ? "on" : "off"}
                  sub="Off by default; saves job leads and classifies seniority for filtering"
                  tone="green"
                />
                <LabelledField label="Company watchlist" hint="provider,slug per line: greenhouse,<company-slug>">
                  <textarea value={cfg.company_watchlist} onChange={set("company_watchlist")} rows={4} className="mono field-input"
                    placeholder={[
                      "greenhouse,<company-slug>",
                      "lever,<company-slug>",
                      "ashby,<company-slug>",
                      "workable,<company-slug>",
                      "https://careers.<company-domain>/jobs",
                    ].join("\n")}
                    style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 11.5, resize: "vertical", lineHeight: 1.6 }} />
                </LabelledField>
                <LabelledField label="Free source targets" hint="github:, hn:, reddit:, or ats: targets">
                  <textarea value={cfg.free_source_targets} onChange={set("free_source_targets")} rows={5} className="mono field-input"
                    placeholder={[
                      "github:<target role> hiring help wanted",
                      "hn:<target role> remote hiring",
                      "reddit:forhire:<target role> hiring remote",
                      "ats:greenhouse:<company-slug>",
                    ].join("\n")}
                    style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 11.5, resize: "vertical", lineHeight: 1.6 }} />
                </LabelledField>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 8 }}>
                  <LabelledField label="Free requests" hint="per scan">
                    <input type="number" min={1} max={80} value={cfg.free_source_max_requests} onChange={set("free_source_max_requests")} className="mono field-input"
                      style={{ width: "100%", padding: "9px 10px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 12 }} />
                  </LabelledField>
                  <LabelledField label="Free min signal" hint="0-100">
                    <input type="number" min={0} max={100} value={cfg.free_source_min_signal_score} onChange={set("free_source_min_signal_score")} className="mono field-input"
                      style={{ width: "100%", padding: "9px 10px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 12 }} />
                  </LabelledField>
                </div>
              </div>
              <div style={{ padding: 13, borderRadius: 13, background: "var(--paper-2)", border: "1px solid var(--line)", display: "flex", flexDirection: "column", gap: 10 }}>
                <SectionLabel label="Custom Connectors" sub="Premium/private JSON APIs normalized into job leads" />
                <BigToggle
                  active={cfg.custom_connectors_enabled === "true"}
                  onToggle={() => onChange("custom_connectors_enabled", cfg.custom_connectors_enabled === "true" ? "false" : "true")}
                  icon="layers"
                  label="Connector scan"
                  badge={cfg.custom_connectors_enabled === "true" ? "on" : "off"}
                  sub="Use this for paid tools, internal feeds, private job APIs, and premium lead providers"
                  tone="purple"
                />
                <LabelledField label="Connector definitions" hint="JSON array; no secrets here">
                  <textarea value={cfg.custom_connectors} onChange={set("custom_connectors")} rows={9} className="mono field-input"
                    placeholder={JSON.stringify([
                      {
                        name: "JobFeed",
                        url: "https://jobs-api.your-domain.test/jobs",
                        method: "GET",
                        items_path: "jobs",
                        fields: {
                          title: "title",
                          company: "company.name",
                          url: "apply_url",
                          description: "description",
                          posted_date: "posted_at",
                          location: "location",
                          budget: "salary",
                        },
                      },
                    ], null, 2)}
                    style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 11.5, resize: "vertical", lineHeight: 1.6 }} />
                </LabelledField>
                <LabelledField label="Connector headers" hint="JSON object; sensitive, preserved when masked">
                  <textarea value={cfg.custom_connector_headers} onChange={set("custom_connector_headers")} rows={5} className="mono field-input"
                    placeholder={JSON.stringify({
                      JobFeed: {
                        Authorization: "Bearer YOUR_TOKEN",
                        "X-API-Key": "optional-key",
                      },
                    }, null, 2)}
                    style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 11.5, resize: "vertical", lineHeight: 1.6 }} />
                </LabelledField>
                <div style={{ fontSize: 11.5, color: "var(--ink-3)", lineHeight: 1.45 }}>
                  Each connector fetches JSON, reads <span className="mono">items_path</span>, maps fields, then sends leads through the same quality gate. Keep tokens in headers, not definitions.
                </div>
              </div>
              <LabelledField label="Target job boards / search URLs" hint="comma-separated">
                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 10 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Market focus</div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                    {[
                      { id: "global", label: "Global market", sub: "Worldwide job boards, ATS pages, remote feeds, and role-neutral sources" },
                      { id: "india", label: "India market", sub: "India job boards, Indian startups, local ATS pages, and remote-India roles" },
                    ].map(mode => {
                      const active = (cfg.job_market_focus || "global") === mode.id;
                      return (
                        <button key={mode.id} onClick={() => onChange("job_market_focus", mode.id)} style={{
                          textAlign: "left", padding: "10px 12px", borderRadius: 10, cursor: "pointer",
                          background: active ? "var(--blue-soft)" : "var(--paper-3)",
                          border: `1.5px solid ${active ? "var(--blue)" : "var(--line)"}`,
                          color: active ? "var(--blue-ink)" : "var(--ink-2)",
                        }}>
                          <div style={{ fontSize: 12, fontWeight: 700 }}>{mode.label}</div>
                          <div style={{ fontSize: 11, marginTop: 3, lineHeight: 1.35, color: "var(--ink-3)" }}>{mode.sub}</div>
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div style={{ marginBottom: 8 }}>
                  <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 8, marginBottom: 10 }}>
                    <input
                      className="mono field-input"
                      value={siteDraft}
                      onChange={e => setSiteDraft(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          addSiteSource();
                        }
                      }}
                      placeholder="Paste a job site, ATS board, RSS/API URL, or domain"
                      style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 11.5 }}
                    />
                    <button className="btn btn-accent" onClick={addSiteSource} disabled={!siteDraft.trim()} style={{ minWidth: 110, justifyContent: "center" }}>
                      Add source
                    </button>
                  </div>
                  {siteDraft.trim() && (
                    <div className="mono" style={{ marginBottom: 10, color: "var(--ink-3)", fontSize: 10.5, lineHeight: 1.45 }}>
                      Will add: {sourceTargetFromSite(siteDraft)}
                    </div>
                  )}
                  <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 7 }}>Quick add sources</div>
                  <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                    {[
                      { label: "Global preset", url: GLOBAL_SOURCE_PRESET },
                      { label: "India preset", url: INDIA_SOURCE_PRESET },
                      { label: "HN Hiring", url: "hn-hiring" },
                      { label: "RemoteOK", url: "https://remoteok.com/api" },
                      { label: "LinkedIn", url: "site:linkedin.com/jobs" },
                      { label: "Indeed", url: "site:indeed.com/jobs" },
                      { label: "Naukri", url: "site:naukri.com jobs India" },
                      { label: "Instahyre", url: "site:instahyre.com jobs India" },
                      { label: "Cutshort", url: "site:cutshort.io/jobs India startup" },
                      { label: "Foundit", url: "site:foundit.in jobs India" },
                      { label: "Internshala", url: "site:internshala.com/jobs India" },
                      { label: "Greenhouse", url: "site:boards.greenhouse.io" },
                      { label: "Lever", url: "site:jobs.lever.co" },
                      { label: "Ashby", url: "site:jobs.ashbyhq.com" },
                      { label: "Workable", url: "site:apply.workable.com" },
                      { label: "Wellfound", url: "site:wellfound.com/jobs" },
                      { label: "WWR", url: "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss" },
                      { label: "Remotive All", url: "https://remotive.com/api/remote-jobs" },
                      { label: "Jobicy All", url: "https://jobicy.com/api/v2/remote-jobs?count=50" },
                      { label: "Jobicy", url: "https://jobicy.com/feed/newjobs" },
                    ].map(p => {
                      const already = cfg.job_boards.includes(p.url);
                      return (
                        <button key={p.label} onClick={() => {
                          if (already) return;
                          const sep = cfg.job_boards.trim() ? ",\n" : "";
                          if (p.label === "India preset") onChange("job_market_focus", "india");
                          if (p.label === "Global preset") onChange("job_market_focus", "global");
                          onChange("job_boards", cfg.job_boards.trim() + sep + p.url);
                        }} style={{
                          padding: "4px 10px", borderRadius: 7, fontSize: 10.5, cursor: already ? "default" : "pointer",
                          fontWeight: 600, transition: "all .12s ease",
                          background: already ? "var(--blue-soft)" : "var(--paper-3)",
                          color: already ? "var(--blue-ink)" : "var(--ink-2)",
                          border: `1px solid ${already ? "var(--blue)" : "var(--line)"}`,
                          opacity: already ? 0.7 : 1,
                        }}>
                          {already ? "Added " : "+ "}{p.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <textarea value={cfg.job_boards} onChange={set("job_boards")} rows={5} className="mono field-input"
                  placeholder={[
                    "# Hacker News Who is Hiring (Algolia API)",
                    "hn-hiring,",
                    "# Direct API / RSS feeds",
                    "https://remoteok.com/api,",
                    "https://remotive.com/api/remote-jobs,",
                    "https://jobicy.com/api/v2/remote-jobs?count=50,",
                    "https://jobicy.com/feed/newjobs,",
                    "https://weworkremotely.com/remote-jobs.rss,",
                    "# ATS and job boards (query generation tailors these to your profile)",
                    "site:boards.greenhouse.io,",
                    "site:jobs.lever.co,",
                    "site:jobs.ashbyhq.com,",
                    "site:apply.workable.com,",
                    "site:wellfound.com/jobs,",
                    "site:linkedin.com/jobs,",
                    "site:indeed.com/jobs,",
                    "site:naukri.com jobs India,",
                  ].join("\n")}
                  style={{ width: "100%", padding: "9px 12px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--card)", fontSize: 11.5, resize: "vertical", lineHeight: 1.6 }} />
              </LabelledField>
            </div>
          </div>
    </>
  );
}
