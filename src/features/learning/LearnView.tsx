import { useEffect, useState } from "react";
import { DemoIcon } from "../../demo/DemoIcon";
import type { ApiFetch } from "../../types";

interface ExampleRole {
  title: string;
  company: string;
  score: number;
}

interface GapInsight {
  skill: string;
  category: string;
  demand: number;
  postings: number;
  share_pct: number;
  near_miss_postings: number;
  adjacent: boolean;
  example_roles: ExampleRole[];
  first_step: string;
}

interface ThemeInsight {
  theme: string;
  demand: number;
  share_pct: number;
}

interface LearningInsights {
  generated_at: string;
  sample_size: number;
  gaps: GapInsight[];
  strengths: GapInsight[];
  themes: ThemeInsight[];
  note: string;
  phrase_mining_skipped?: boolean;
}

export function LearnView({ api }: { api: ApiFetch }) {
  const [insights, setInsights] = useState<LearningInsights | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    (async () => {
      try {
        // First read over a big corpus computes for several seconds before the
        // server-side cache warms — give it more room than the default 30s.
        const response = await api("/api/v1/learning/insights", { timeoutMs: 60000 });
        if (!response.ok) throw new Error(`Insights failed (${response.status})`);
        const data = (await response.json()) as LearningInsights;
        if (!cancelled) setInsights(data);
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Could not read your market yet");
      }
    })();
    return () => { cancelled = true; };
  }, [api, attempt]);

  if (error) {
    return <div className="learn-view product-enter scroll"><div className="learn-state" role="alert">
      <DemoIcon name="close" /><strong>Couldn’t read your market.</strong>
      <p>{error}</p>
      <button className="learn-retry" onClick={() => setAttempt(n => n + 1)}>Try again</button>
    </div></div>;
  }
  if (!insights) {
    return <div className="learn-view product-enter scroll"><div className="learn-state"><DemoIcon name="radar" /><strong>Reading your market…</strong><p>Weighing every live posting in your journal against your evidence.</p></div></div>;
  }

  const { gaps, strengths, themes, sample_size: sampleSize, note } = insights;

  return <div className="learn-view product-enter scroll">
    <div className="view-toolbar">
      <div>
        <span className="product-eyebrow">Skill intelligence</span>
        <h2>What to learn <em>next.</em></h2>
        <span className="toolbar-scribble">your market is talking ↓</span>
      </div>
      <div className="learn-sample" aria-label={`Based on ${sampleSize} live postings`}>
        <strong>{sampleSize}</strong>
        <span>live postings read</span>
      </div>
    </div>

    {note && <p className="learn-note">{note}</p>}

    <div className="learn-columns">
      <section className="learn-gaps" aria-label="Ranked skill gaps">
        <header>
          <span>Highest-leverage gaps</span>
          <p>Skills your market keeps asking for that your evidence doesn’t show yet — near-miss roles count double.</p>
        </header>
        {gaps.length === 0 && <div className="learn-state"><DemoIcon name="tailor" /><strong>No urgent gaps.</strong><p>Nothing in high demand is missing from your evidence. Keep your strengths sharp.</p></div>}
        {gaps.map((gap, index) => (
          <article className="learn-gap-card" key={gap.skill}>
            <div className="learn-gap-head">
              <b>{index + 1}</b>
              <h3>{gap.skill}</h3>
              {gap.category && <span className="learn-chip">{gap.category}</span>}
              {gap.adjacent && <span className="learn-chip fast">fast to close</span>}
            </div>
            <div className="learn-demand" role="img" aria-label={`${gap.skill} appears in ${gap.share_pct}% of live postings`}>
              <i style={{ width: `${Math.max(4, Math.min(100, gap.share_pct))}%` }} />
              <small>in {gap.postings} of {sampleSize} live postings{gap.near_miss_postings > 0 ? ` · ${gap.near_miss_postings} near-miss ${gap.near_miss_postings === 1 ? "role" : "roles"}` : ""}</small>
            </div>
            {gap.example_roles.length > 0 && (
              <p className="learn-examples">
                {gap.example_roles.map(role => `${role.title}${role.company ? ` · ${role.company}` : ""}`).join("  ·  ")}
              </p>
            )}
            <p className="learn-step"><span>first step</span>{gap.first_step}</p>
          </article>
        ))}
      </section>

      <aside className="learn-rail">
        <section aria-label="Strengths in demand">
          <header><span>Lead with these</span><p>The market keeps asking for what you already have.</p></header>
          {strengths.length === 0 && <p className="learn-rail-empty">Run a scan to see which of your skills are in live demand.</p>}
          {strengths.map(strength => (
            <div className="learn-strength" key={strength.skill}>
              <strong>{strength.skill}</strong>
              <div className="learn-demand slim" aria-hidden="true"><i style={{ width: `${Math.max(4, Math.min(100, strength.share_pct))}%` }} /></div>
              <small>{strength.share_pct}% of postings</small>
            </div>
          ))}
        </section>
        <section aria-label="Market themes">
          <header><span>Currents in your market</span><p>What the freshest postings are building.</p></header>
          {themes.length === 0 && <p className="learn-rail-empty">Themes appear once the journal holds enough postings.</p>}
          <div className="learn-themes">
            {themes.map(theme => (
              <span className="learn-theme" key={theme.theme}><b>{theme.theme}</b><small>{theme.share_pct}%</small></span>
            ))}
          </div>
        </section>
        {insights.phrase_mining_skipped && (
          <p className="learn-footnote">Semantic runtime not installed — showing taxonomy gaps only. Install it from Settings to also mine field-specific phrases from your market.</p>
        )}
        <p className="learn-footnote">Mined locally from your own lead journal — recency-weighted, no model calls.</p>
      </aside>
    </div>
  </div>;
}
