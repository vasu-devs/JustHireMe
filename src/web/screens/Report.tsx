// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Vasudev Siddh and vasu-devs

import { useEffect, useMemo, useState } from "react";
import { DemoIcon } from "../../demo/DemoIcon";
import { ProductionViewIntro } from "../../shared/components/ProductionViewIntro";
import { dashboardApi } from "../../api";
import type { ActivityRow, ApiFetch, DashboardOverview, FunnelStage, SourceRow } from "../../api";
import { ApiError, json } from "../lib/session";

/**
 * The audit-report screen — leads funnel, per-source confirm rate, daily
 * volume, recent activity. No desktop equivalent (the desktop "Overview" tab
 * is the journal-style DashboardView) — kept web-only, restyled onto the real
 * app's own classes (ProductionViewIntro, .card, .eyebrow, .pill, .btn) from
 * src/index.css. The handful of genuinely new shapes here (funnel bars,
 * source bars, the hand-rolled timeseries chart) live in ./web-extra.css,
 * additive only — src/index.css itself is never touched.
 */

const HEADLINE_SPECS: [keyof DashboardOverview["headline"], string][] = [
  ["total", "Leads"],
  ["verified_confirmed", "Confirmed"],
  ["in_apply_queue", "Queued"],
  ["applied", "Applied"],
  ["interviews", "Interviews"],
  ["offers", "Offers"],
  ["rejections", "Rejections"],
];

function FunnelRow({ stage, maxCount }: { stage: FunnelStage; maxCount: number }) {
  const pct = maxCount ? Math.round((stage.count / maxCount) * 1000) / 10 : 0;
  return (
    <div className="report-funnel-row">
      <div className="report-funnel-label">{stage.label}</div>
      <div className="report-track"><div className="report-fill" style={{ width: `${pct}%` }} /></div>
      <div className="report-funnel-count">
        {stage.count.toLocaleString()}
        {stage.dropoff_pct !== null && stage.dropoff_pct > 0 && <span className="report-drop">-{stage.dropoff_pct}%</span>}
      </div>
    </div>
  );
}

function SourceBar({ row, maxTotal }: { row: SourceRow; maxTotal: number }) {
  const pct = maxTotal ? Math.round((row.total / maxTotal) * 1000) / 10 : 0;
  const rate = row.confirm_rate === null ? "—" : `${Math.round(row.confirm_rate)}%`;
  return (
    <div className="report-src-row">
      <div className="report-src-label">{row.platform.replace(/_/g, " ")}</div>
      <div className="report-track"><div className="report-fill" style={{ width: `${pct}%` }} /></div>
      <div className="report-src-nums"><span>{row.confirmed}/{row.verified}</span><span className="report-src-rate">{rate}</span></div>
    </div>
  );
}

/** Hand-rolled two-line SVG chart, no charting library: leads scraped vs.
 *  applications sent, per day, one shared y-axis. */
function Timeseries({ leads, apps }: { leads: [string, number][]; apps: [string, number][] }) {
  if (leads.length === 0) return <p className="report-empty-note">No dated leads yet.</p>;
  const width = 720, height = 200;
  const padL = 4, padR = 4, padT = 14, padB = 22;
  const plotW = width - padL - padR, plotH = height - padT - padB;
  const dates = leads.map(([d]) => d);
  const appsByDate = new Map(apps);
  const leadsVals = leads.map(([, c]) => c);
  const appsVals = dates.map((d) => appsByDate.get(d) ?? 0);
  const maxV = Math.max(...leadsVals, ...appsVals, 1);
  const n = dates.length;
  const x = (i: number) => padL + (i / Math.max(1, n - 1)) * plotW;
  const y = (v: number) => padT + plotH - (v / maxV) * plotH;
  const path = (vals: number[]) => "M " + vals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" L ");
  const leadsPath = path(leadsVals);
  const baselineY = padT + plotH;
  const areaPath = `${leadsPath} L ${x(n - 1).toFixed(1)},${baselineY.toFixed(1)} L ${x(0).toFixed(1)},${baselineY.toFixed(1)} Z`;
  const appsPath = path(appsVals);
  const noApps = !appsVals.some(Boolean);

  return (
    <>
      <div className="report-chart-legend">
        <span className="report-legend-item"><i className="report-swatch report-swatch--leads" />Leads scraped / day</span>
        <span className="report-legend-item"><i className="report-swatch report-swatch--apps" />Applications sent / day</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="report-chart-svg" role="img"
        aria-label={`Leads scraped and applications sent per day, ${dates[0]} to ${dates[n - 1]}`}>
        <line x1={padL} y1={baselineY} x2={width - padR} y2={baselineY} className="report-chart-axis" />
        <path d={areaPath} className="report-chart-area" />
        <path d={leadsPath} className="report-chart-line report-chart-line--leads"><title>Leads scraped per day</title></path>
        <path d={appsPath} className="report-chart-line report-chart-line--apps"><title>Applications sent per day</title></path>
        <text x={padL} y={height - 4} className="report-chart-axis-label">{dates[0]}</text>
        <text x={width - padR} y={height - 4} className="report-chart-axis-label" textAnchor="end">{dates[n - 1]}</text>
      </svg>
      {noApps && <p className="report-empty-note">No applications recorded yet — this line fills in once a role is marked applied.</p>}
    </>
  );
}

function ActivityList({ rows }: { rows: ActivityRow[] }) {
  return (
    <div className="report-activity">
      {rows.map((row, index) => (
        <div className="report-activity-row" key={`${row.ts}-${index}`}>
          <span className="report-activity-num">{String(index + 1).padStart(2, "0")}</span>
          <span className="report-activity-ts">{row.ts}</span>
          <span className="report-activity-label">
            {row.label}
            {row.title && <span className="report-activity-who"> — {row.title}{row.company ? ` @ ${row.company}` : ""}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}

/** The one concrete sentence Sources exists to tell: which platform is worth
 *  trusting and which is noise. */
function contrastLine(rows: SourceRow[]): string | null {
  const verified = rows.filter((row) => row.verified > 0);
  if (verified.length < 2) return null;
  const sorted = [...verified].sort((a, b) => (b.confirm_rate ?? -1) - (a.confirm_rate ?? -1));
  const best = sorted[0];
  const worst = sorted[sorted.length - 1];
  if (best.platform === worst.platform || (best.confirm_rate ?? 0) === (worst.confirm_rate ?? 0)) return null;
  return `${best.platform} confirms ${best.confirmed}/${best.verified} verified roles (${Math.round(best.confirm_rate ?? 0)}%); ${worst.platform} confirms ${worst.confirmed}/${worst.verified} (${Math.round(worst.confirm_rate ?? 0)}%).`;
}

type Tab = "overview" | "sources";

export function Report({ api }: { api: ApiFetch }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      // The single-worker sidecar (see leads/service.py's module docstring) can
      // still be settling a just-finished huge GET /api/v1/leads response (tens
      // of MB) when this fires -- confirmed live: dashboard/overview alone takes
      // ~1-3s, but arriving right on the tail of that request can push it past
      // 15s even though nothing here is actually slow on its own. 30s matches the
      // desktop client's own default budget.
      setData(await json<DashboardOverview>(await dashboardApi.overview(api, { timeoutMs: 30000 })));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load the report.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const story = useMemo(() => (data ? contrastLine(data.sources) : null), [data]);

  return (
    <div className="scroll report-page product-enter">
      <ProductionViewIntro
        index="08"
        eyebrow="Audit report"
        title="The loop,"
        accent="end to end."
        description="Every number below comes from a real query against your own database — nothing here is estimated."
        actions={
          <div className="report-tabs" role="tablist">
            <button className="btn" role="tab" aria-selected={tab === "overview"} onClick={() => setTab("overview")}>Overview</button>
            <button className="btn" role="tab" aria-selected={tab === "sources"} onClick={() => setTab("sources")}>Sources</button>
          </div>
        }
      />

      {error && (
        <div className="card report-state" role="alert">
          <DemoIcon name="close" />
          <strong>Can't load the report</strong>
          <p>{error}</p>
          <button className="btn" onClick={() => void load()}>Try again</button>
        </div>
      )}

      {!error && (loading || !data) && (
        <div className="card report-state" aria-busy="true">
          <div className="spinner" />
          <strong>Reading your database…</strong>
        </div>
      )}

      {!error && data && tab === "overview" && (() => {
        const maxFunnel = Math.max(...data.funnel.map((stage) => stage.count), 0) || 1;
        return (
          <>
            <div className="report-stats">
              {HEADLINE_SPECS.map(([key, label]) => (
                <div className="card report-stat" key={key}>
                  <span className="eyebrow">{label}</span>
                  <div className="display tabular">{data.headline[key].toLocaleString()}</div>
                </div>
              ))}
            </div>

            <div className="card report-panel">
              <span className="eyebrow">Funnel</span>
              <p className="report-panel-sub">Scraped through to interview, with drop-off between each stage.</p>
              <div className="report-funnel">{data.funnel.map((stage) => <FunnelRow key={stage.label} stage={stage} maxCount={maxFunnel} />)}</div>
            </div>

            <div className="card report-panel">
              <span className="eyebrow">Progress over time</span>
              <p className="report-panel-sub">Leads scraped and applications sent, per day.</p>
              <Timeseries leads={data.leads_per_day} apps={data.applications_per_day} />
            </div>

            <div className="card report-panel">
              <span className="eyebrow">Recent activity</span>
              {data.activity.length === 0
                ? <p className="report-panel-sub">Nothing yet — run a scan and the loop's activity trail lands here.</p>
                : <ActivityList rows={data.activity} />}
            </div>
          </>
        );
      })()}

      {!error && data && tab === "sources" && (() => {
        const verifiedSources = data.sources.filter((row) => row.verified > 0);
        const maxTotal = Math.max(...data.sources.map((row) => row.total), 0) || 1;
        return (
          <>
            <p className="report-panel-sub report-lede">{story ?? "Which platforms produce confirmed roles, and which are mostly noise — measured, not guessed."}</p>

            <div className="card report-panel">
              <span className="eyebrow">Confirmed vs. noise</span>
              <p className="report-panel-sub">Confirmed / verified per platform, ranked by confirmed roles first.</p>
              {verifiedSources.length === 0
                ? <div className="report-state"><strong>No verified sources yet</strong><p>Run verification and this fills in with which platforms actually produce confirmed roles.</p></div>
                : <div className="report-sources">{verifiedSources.map((row) => <SourceBar key={row.platform} row={row} maxTotal={maxTotal} />)}</div>}
            </div>

            <div className="card report-panel">
              <span className="eyebrow">All platforms</span>
              <p className="report-panel-sub">Total leads seen per platform, verified or not.</p>
              <div className="report-sources">{data.sources.map((row) => <SourceBar key={row.platform} row={row} maxTotal={maxTotal} />)}</div>
            </div>
          </>
        );
      })()}
    </div>
  );
}
