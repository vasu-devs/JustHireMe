#!/usr/bin/env python
"""Local job-search audit dashboard: one self-contained HTML file, generated
from the SAME database + the SAME audit trail (``events`` table) the rest of
the closed loop already writes to (see ``CLOSED_LOOP.md``, migration
``006_verify_status.sql``, ``backfill_audit_events.py``).

No server, no build step, no CDN, no charting library. Every number on the
page comes from a real SQL query against the live database -- nothing here
fabricates or estimates. Regenerating is one command:

    python scripts/dashboard.py                    # writes + opens dashboard.html
    python scripts/dashboard.py --no-open           # write only, don't launch a browser
    python scripts/dashboard.py --db path\\to\\crm.db --out report.html

Reporting only -- this reads the DB and draft folders, it never touches an
employer's site or submits anything (same boundary as the rest of the loop).
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import webbrowser
from html import escape
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

import run_scrape  # noqa: E402  sibling script, for resolve_db()
from data.sqlite.connection import get_connection, run_migrations  # noqa: E402
# Queries used to live here. Moved to reporting.service so the web dashboard's
# API and this CLI report render off the exact same tested functions instead of
# two copies that could drift (business package is "reporting", not "dashboard"
# -- this very module already owns that top-level name on the CLI's sys.path).
# `gather()` is all this script's own code calls; the rest (headline_metrics,
# funnel_stages, ...) are re-exported only so external callers that still say
# `dashboard.headline_metrics(...)` (see tests/unit/business/test_dashboard.py)
# keep working unchanged.
from reporting.service import (  # noqa: E402,F401
    DEFAULT_DRAFTS_DIR,
    FUNNEL_LABELS,
    applications,
    applications_per_day,
    funnel_stages,
    gather,
    headline_metrics,
    humanize_action as _humanize_action,
    kv as _kv,
    leads_per_day,
    next_actions,
    recent_activity,
    short_ts as _short_ts,
    source_breakdown,
    tag_tone as _tag_tone,
)

DEFAULT_OUT = Path(__file__).resolve().parent / "dashboard.html"
DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent / "candidate_profile.json"
FONTS_DIR = REPO_ROOT / "public" / "fonts"


# ---------------------------------------------------------------------------
# Rendering -- plain string templates, no framework. Numbers are pre-formatted
# here (comma grouping) since Jinja/etc. would be a dependency for one filter.
# ---------------------------------------------------------------------------

def _fmt(n: int) -> str:
    return f"{int(n):,}"


def _font_face_css() -> str:
    """Base64-embeds the same four vendored fonts src/web already ships
    (Instrument Serif/Sans, Geist Mono) so this file has zero runtime
    dependency on the filesystem or a CDN. Missing files degrade to the
    tokens' own system-font fallback (Georgia / system-ui / ui-monospace) --
    never Inter/Roboto/Arial."""
    specs = [
        ("Instrument Serif", "normal", 400, "InstrumentSerif-Regular.ttf"),
        ("Instrument Serif", "italic", 400, "InstrumentSerif-Italic.ttf"),
        ("Instrument Sans", "normal", 400, "InstrumentSans-Regular.ttf"),
        ("Instrument Sans", "normal", 700, "InstrumentSans-Bold.ttf"),
        ("Geist Mono", "normal", 400, "GeistMono-Regular.ttf"),
    ]
    faces = []
    for family, style, weight, filename in specs:
        path = FONTS_DIR / filename
        if not path.exists():
            continue
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        faces.append(
            f'@font-face{{font-family:"{family}";font-style:{style};font-weight:{weight};'
            f'src:url(data:font/ttf;base64,{b64}) format("truetype");font-display:swap;}}'
        )
    return "\n".join(faces)


def _svg_timeseries(leads_series: list[tuple[str, int]], apps_series: list[tuple[str, int]]) -> str:
    """The one inline-SVG chart: leads scraped vs. applications sent, per day.
    Hand-rolled two-line chart, no charting library. Single shared y-axis
    (both series are the same unit: a daily count), per dataviz's "never
    dual-axis" rule."""
    if not leads_series:
        return '<p class="empty-note">No dated leads yet.</p>'
    width, height = 720, 200
    pad_l, pad_r, pad_t, pad_b = 4, 4, 14, 22
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b

    dates = [d for d, _ in leads_series]
    apps_by_date = dict(apps_series)
    leads_vals = [c for _, c in leads_series]
    apps_vals = [apps_by_date.get(d, 0) for d in dates]
    max_v = max([*leads_vals, *apps_vals, 1])
    n = len(dates)

    def x(i: int) -> float:
        return pad_l + (i / max(1, n - 1)) * plot_w

    def y(v: int) -> float:
        return pad_t + plot_h - (v / max_v) * plot_h

    def path(vals: list[int]) -> str:
        return "M " + " L ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))

    leads_path = path(leads_vals)
    area_path = f"{leads_path} L {x(n - 1):.1f},{pad_t + plot_h:.1f} L {x(0):.1f},{pad_t + plot_h:.1f} Z"
    apps_path = path(apps_vals)
    baseline_y = pad_t + plot_h

    note = ""
    if not any(apps_vals):
        note = '<p class="empty-note">No applications recorded yet -- this line will fill in once roles are marked applied via review.py.</p>'

    return f"""
    <div class="chart-legend">
      <span class="legend-item"><i class="swatch swatch--leads"></i>Leads scraped / day</span>
      <span class="legend-item"><i class="swatch swatch--apps"></i>Applications sent / day</span>
    </div>
    <svg viewBox="0 0 {width} {height}" class="chart-svg" role="img"
         aria-label="Leads scraped and applications sent per day, {escape(dates[0])} to {escape(dates[-1])}">
      <line x1="{pad_l}" y1="{baseline_y:.1f}" x2="{width - pad_r}" y2="{baseline_y:.1f}" class="chart-axis" />
      <path d="{area_path}" class="chart-area" />
      <path d="{leads_path}" class="chart-line chart-line--leads" />
      <path d="{apps_path}" class="chart-line chart-line--apps" />
      <text x="{pad_l}" y="{height - 4}" class="chart-axis-label">{escape(dates[0])}</text>
      <text x="{width - pad_r}" y="{height - 4}" class="chart-axis-label" text-anchor="end">{escape(dates[-1])}</text>
    </svg>
    {note}
    """


def _funnel_html(stages: list[dict]) -> str:
    max_count = max((s["count"] for s in stages), default=0) or 1
    rows = []
    for stage in stages:
        pct = round(stage["count"] / max_count * 100, 1)
        drop = stage["dropoff_pct"]
        drop_html = f'<span class="funnel-drop">-{drop}%</span>' if drop is not None and drop > 0 else ""
        rows.append(f"""
        <div class="funnel-row">
          <div class="funnel-label">{escape(stage['label'])}</div>
          <div class="funnel-track"><div class="funnel-fill" style="width:{pct}%"></div></div>
          <div class="funnel-count">{_fmt(stage['count'])} {drop_html}</div>
        </div>""")
    return "\n".join(rows)


def _source_html(sources: list[dict]) -> str:
    verified_sources = [s for s in sources if s["verified"] > 0]
    if not verified_sources:
        return '<div class="state"><h2>No verified sources yet</h2><p>Run verify_shortlist.py to see which platforms actually produce CONFIRMED roles.</p></div>'
    max_total = max((s["total"] for s in verified_sources), default=0) or 1
    rows = []
    for s in verified_sources:
        pct = round(s["total"] / max_total * 100, 1)
        rate = f"{s['confirm_rate']:.0f}%" if s["confirm_rate"] is not None else "-"
        rows.append(f"""
        <div class="src-row">
          <div class="src-label">{escape(s['platform'])}</div>
          <div class="src-track"><div class="src-fill" style="width:{pct}%"></div></div>
          <div class="src-nums"><span>{s['confirmed']}/{s['verified']}</span><span class="src-rate">{rate}</span></div>
        </div>""")
    return "\n".join(rows)


def _applications_html(rows: list[dict]) -> str:
    if not rows:
        return (
            '<div class="state"><h2>No applications yet</h2>'
            "<p>Nothing has been marked applied through <code>review.py</code> or "
            "<code>apply_assist.py</code> in this database yet. Once a role is applied to, "
            "it shows up here with the exact answers that were submitted.</p></div>"
        )
    body = []
    for row in rows:
        tone = _tag_tone(row["band"])
        status_tone = _tag_tone(row["status"])
        answers_html = (
            f'<details class="answers"><summary>view answers submitted</summary>'
            f'<pre>{escape(row["answers"])}</pre></details>'
            if row["answers"] else '<span class="empty-note">no packet on disk</span>'
        )
        body.append(f"""
        <tr>
          <td>{escape(row['company'])}</td>
          <td>{escape(row['title'])}</td>
          <td><span class="tag" data-tone="{tone}">{escape(row['band'])}</span></td>
          <td class="num">{row['score']}</td>
          <td class="num">{escape(row['applied_at'][:10] or '-')}</td>
          <td><span class="tag" data-tone="{status_tone}">{escape(row['status'])}</span></td>
          <td><a href="{escape(row['url'])}" target="_blank" rel="noopener">apply link</a></td>
          <td>{answers_html}</td>
        </tr>""")
    return f"""
    <div class="table-scroll">
    <table class="ledger">
      <thead><tr>
        <th>Company</th><th>Role</th><th>Band</th><th>Score</th>
        <th>Applied</th><th>Status</th><th>Link</th><th>Answers</th>
      </tr></thead>
      <tbody>{''.join(body)}</tbody>
    </table>
    </div>"""


def _activity_html(rows: list[dict]) -> str:
    if not rows:
        return '<div class="state"><h2>No activity yet</h2><p>Run job_loop.py or any of the individual scripts once to populate the audit trail.</p></div>'
    items = []
    for row in rows:
        who = f" -- {escape(row['title'])} @ {escape(row['company'])}" if row["title"] else ""
        items.append(f"""
        <div class="activity-row">
          <div class="activity-ts">{escape(row['ts'])}</div>
          <div class="activity-label">{escape(row['label'])}{who}</div>
        </div>""")
    return "\n".join(items)


def _next_actions_html(rows: list[dict]) -> str:
    if not rows:
        return '<div class="state"><h2>Queue is empty</h2><p>Nothing at draft_ready/approved right now -- run job_loop.py to generate more drafts.</p></div>'
    items = []
    for row in rows:
        tone = _tag_tone(row["band"])
        items.append(f"""
        <div class="next-row">
          <div class="next-head">
            <span class="next-role">{escape(row['title'])} @ {escape(row['company'])}</span>
            <span class="tag" data-tone="{tone}">{escape(row['band'])}</span>
            <span class="next-score">{row['score']}</span>
          </div>
          <code class="next-cmd">{escape(row['command'])}</code>
        </div>""")
    return "\n".join(items)


HEADLINE_SPECS = (
    ("total", "Total leads"),
    ("verified_confirmed", "Verified CONFIRMED"),
    ("in_apply_queue", "In apply queue"),
    ("applied", "Applied"),
    ("interviews", "Interviews"),
    ("offers", "Offers"),
    ("rejections", "Rejections"),
)


def render_html(data: dict, *, db_path: str, candidate_name: str, generated_at: str) -> str:
    headline = data["headline"]
    headline_html = "\n".join(
        f'<div class="metric"><div class="metric-num">{_fmt(headline[key])}</div>'
        f'<div class="metric-label">{escape(label)}</div></div>'
        for key, label in HEADLINE_SPECS
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JustHireMe -- Audit Report</title>
<style>
{_font_face_css()}
{_CSS}
</style>
</head>
<body>
<header class="masthead">
  <div class="masthead-top">
    <span class="wordmark">JustHireMe</span>
    <span class="masthead-sub">Audit Report</span>
  </div>
  <div class="masthead-meta">
    <span>{escape(candidate_name)}</span>
    <span>Generated {escape(generated_at)}</span>
    <span class="masthead-db" title="{escape(db_path)}">{escape(db_path)}</span>
  </div>
</header>

<main class="report">

  <section class="headline-strip">
    {headline_html}
  </section>

  <section>
    <h2 class="report-h2">Funnel</h2>
    <p class="report-sub">Scraped through to interview, with drop-off between each stage.</p>
    <div class="funnel">
      {_funnel_html(data['funnel'])}
    </div>
  </section>

  <section class="two-col">
    <div>
      <h2 class="report-h2">Source breakdown</h2>
      <p class="report-sub">Which platforms produce CONFIRMED roles, vs. noise.</p>
      <div class="sources">
        {_source_html(data['sources'])}
      </div>
    </div>
    <div>
      <h2 class="report-h2">Progress over time</h2>
      <p class="report-sub">Leads scraped and applications sent, per day.</p>
      {_svg_timeseries(data['leads_per_day'], data['applications_per_day'])}
    </div>
  </section>

  <section>
    <h2 class="report-h2">Applications</h2>
    <p class="report-sub">Every role marked applied, with the answers that actually went out.</p>
    {_applications_html(data['applications'])}
  </section>

  <section>
    <h2 class="report-h2">Recent activity</h2>
    <p class="report-sub">What the loop did, most recent first.</p>
    <div class="activity">
      {_activity_html(data['activity'])}
    </div>
  </section>

  <section>
    <h2 class="report-h2">Next actions</h2>
    <p class="report-sub">Top queued roles, ready to apply.</p>
    <div class="next-actions">
      {_next_actions_html(data['next_actions'])}
    </div>
  </section>

</main>
</body>
</html>
"""


_CSS = """
:root {
  --paper: #f6f2e9;
  --card: #fdfbf5;
  --ink: #1f1a14;
  --ink-soft: rgba(31, 26, 20, 0.62);
  --ink-faint: rgba(31, 26, 20, 0.42);
  --line: rgba(31, 26, 20, 0.08);
  --line-lo: rgba(31, 26, 20, 0.04);
  --accent: #c96442;
  --accent-soft: rgba(201, 100, 66, 0.1);
  --ok: #5b8c44;
  --ok-soft: rgba(91, 140, 68, 0.12);
  --warn: #b57828;
  --warn-soft: rgba(181, 120, 40, 0.12);
  --bad: #b4452c;
  --bad-soft: rgba(180, 69, 44, 0.1);
  --shadow-xs: 0 1px 2px rgba(31, 26, 20, 0.04);
  --font-display: "Instrument Serif", Georgia, serif;
  --font-sans: "Instrument Sans", system-ui, -apple-system, sans-serif;
  --font-mono: "Geist Mono", ui-monospace, "Courier New", monospace;
  --radius: 12px;
  --radius-pill: 999px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper: #17140f; --card: #1f1b15; --ink: #f2ece1;
    --ink-soft: rgba(242, 236, 225, 0.66); --ink-faint: rgba(242, 236, 225, 0.44);
    --line: rgba(242, 236, 225, 0.12); --line-lo: rgba(242, 236, 225, 0.06);
    --accent: #e08762; --accent-soft: rgba(224, 135, 98, 0.14);
    --ok: #8fbf74; --ok-soft: rgba(143, 191, 116, 0.16);
    --warn: #d8a44f; --warn-soft: rgba(216, 164, 79, 0.16);
    --bad: #e0765a; --bad-soft: rgba(224, 118, 90, 0.16);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--paper); color: var(--ink);
  font-family: var(--font-sans); font-size: 15px; line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--accent); }
code { font-family: var(--font-mono); }

.masthead {
  padding: 22px 28px 18px; border-bottom: 1px solid var(--line);
  display: flex; flex-direction: column; gap: 6px;
}
.masthead-top { display: flex; align-items: baseline; gap: 12px; }
.wordmark { font-family: var(--font-display); font-size: 26px; letter-spacing: -0.01em; }
.masthead-sub { color: var(--ink-soft); font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase; }
.masthead-meta {
  display: flex; flex-wrap: wrap; gap: 4px 18px;
  font-family: var(--font-mono); font-size: 12px; color: var(--ink-faint);
  font-variant-numeric: tabular-nums;
}
.masthead-db { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }

.report { max-width: 1080px; margin: 0 auto; padding: 32px 28px 96px; }
.report > section { margin-bottom: 48px; }
.report-h2 { font-family: var(--font-display); font-weight: 400; font-size: 26px; margin: 0 0 4px; letter-spacing: -0.01em; }
.report-sub { color: var(--ink-soft); margin: 0 0 18px; font-size: 14px; }

/* headline strip: baseline-aligned mono numbers, hairline-divided, no cards */
.headline-strip {
  display: flex; flex-wrap: wrap; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line);
  padding: 22px 0;
}
.metric {
  flex: 1 1 130px; padding: 0 20px; border-left: 1px solid var(--line);
}
.metric:first-child { border-left: none; }
.metric-num {
  font-family: var(--font-mono); font-size: 30px; font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em; line-height: 1.1; color: var(--ink);
}
.metric-label { color: var(--ink-soft); font-size: 12.5px; margin-top: 4px; }

/* funnel: ledger-style bars, magnitude by width, single hue */
.funnel-row {
  display: grid; grid-template-columns: 110px 1fr 140px; align-items: center;
  gap: 14px; padding: 7px 0;
}
.funnel-label { font-size: 13.5px; color: var(--ink-soft); }
.funnel-track { height: 20px; background: var(--line-lo); border-radius: 4px; overflow: hidden; }
.funnel-fill { height: 100%; background: var(--accent-soft); border-right: 2px solid var(--accent); min-width: 2px; }
.funnel-count {
  font-family: var(--font-mono); font-size: 13px; font-variant-numeric: tabular-nums;
  text-align: right; color: var(--ink); white-space: nowrap;
}
.funnel-drop { color: var(--warn); margin-left: 6px; font-size: 11.5px; }

.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; }

/* source breakdown bars */
.src-row {
  display: grid; grid-template-columns: 96px 1fr 90px; align-items: center;
  gap: 12px; padding: 6px 0;
}
.src-label { font-size: 13px; color: var(--ink-soft); text-transform: capitalize; }
.src-track { height: 14px; background: var(--line-lo); border-radius: 3px; overflow: hidden; }
.src-fill { height: 100%; background: var(--accent-soft); border-right: 2px solid var(--accent); min-width: 2px; }
.src-nums {
  font-family: var(--font-mono); font-size: 12px; font-variant-numeric: tabular-nums;
  text-align: right; display: flex; justify-content: flex-end; gap: 8px; white-space: nowrap;
}
.src-rate { color: var(--ink-faint); }

/* time-series SVG chart */
.chart-legend { display: flex; gap: 18px; font-size: 12.5px; color: var(--ink-soft); margin-bottom: 10px; }
.legend-item { display: flex; align-items: center; gap: 6px; }
.swatch { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.swatch--leads { background: var(--ink-faint); }
.swatch--apps { background: var(--accent); }
.chart-svg { width: 100%; height: auto; overflow: visible; }
.chart-axis { stroke: var(--line); stroke-width: 1; }
.chart-area { fill: var(--line-lo); stroke: none; }
.chart-line { fill: none; stroke-width: 2; }
.chart-line--leads { stroke: var(--ink-faint); }
.chart-line--apps { stroke: var(--accent); }
.chart-axis-label { font-family: var(--font-mono); font-size: 10px; fill: var(--ink-faint); }
.empty-note { color: var(--ink-faint); font-size: 12.5px; margin-top: 10px; }

/* ledger tables */
.table-scroll { overflow-x: auto; }
table.ledger { width: 100%; border-collapse: collapse; font-size: 13.5px; }
table.ledger th {
  text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--ink-faint); font-weight: 600; padding: 0 10px 8px; white-space: nowrap;
}
table.ledger td { padding: 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
table.ledger td.num { font-family: var(--font-mono); font-variant-numeric: tabular-nums; white-space: nowrap; }
table.ledger tr:last-child td { border-bottom: none; }

.tag {
  border: 1px solid var(--line); border-radius: var(--radius-pill); padding: 2px 9px;
  font-size: 11.5px; color: var(--ink-soft); white-space: nowrap; display: inline-block;
}
.tag[data-tone="ok"] { border-color: transparent; background: var(--ok-soft); color: var(--ok); }
.tag[data-tone="bad"] { border-color: transparent; background: var(--bad-soft); color: var(--bad); }
.tag[data-tone="warn"] { border-color: transparent; background: var(--warn-soft); color: var(--warn); }

.answers summary { cursor: pointer; color: var(--accent); font-size: 12.5px; }
.answers pre {
  white-space: pre-wrap; font-family: var(--font-sans); font-size: 12.5px; color: var(--ink-soft);
  background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 12px 14px; margin-top: 8px; max-height: 320px; overflow-y: auto;
}

/* activity feed */
.activity-row {
  display: grid; grid-template-columns: 130px 1fr; gap: 14px; padding: 7px 0;
  border-bottom: 1px solid var(--line-lo); font-size: 13.5px;
}
.activity-row:last-child { border-bottom: none; }
.activity-ts {
  font-family: var(--font-mono); font-size: 12px; color: var(--ink-faint);
  font-variant-numeric: tabular-nums; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.activity-label { color: var(--ink); min-width: 0; overflow-wrap: anywhere; }

/* next actions */
.next-row { padding: 12px 0; border-bottom: 1px solid var(--line-lo); }
.next-row:last-child { border-bottom: none; }
.next-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 6px; }
.next-role { font-size: 14.5px; }
.next-score { margin-left: auto; font-family: var(--font-mono); font-variant-numeric: tabular-nums; color: var(--accent); }
.next-cmd {
  display: block; background: var(--line-lo); border-radius: 6px; padding: 7px 10px;
  font-size: 12.5px; color: var(--ink-soft); overflow-x: auto; white-space: nowrap;
}

/* graceful empty state -- reused across every section */
.state {
  border: 1px dashed var(--line); border-radius: var(--radius); padding: 36px 24px;
  text-align: center; color: var(--ink-soft); background: var(--card);
}
.state h2 { font-family: var(--font-display); font-weight: 400; font-size: 21px; margin: 0 0 8px; color: var(--ink); }
.state p { margin: 0 auto; max-width: 48ch; font-size: 13.5px; }

@media (max-width: 720px) {
  .report { padding: 24px 16px 72px; }
  .masthead { padding: 18px 16px 14px; }
  .two-col { grid-template-columns: 1fr; gap: 32px; }
  .headline-strip { padding: 16px 0; }
  .metric { flex: 1 1 45%; border-left: none; padding: 8px 12px; }
  .metric-num { font-size: 24px; }
  .funnel-row { grid-template-columns: 78px 1fr 82px; gap: 8px; }
  .funnel-count { font-size: 11.5px; }
  .src-row { grid-template-columns: 68px 1fr 70px; gap: 8px; }
  .activity-row { grid-template-columns: 1fr; gap: 2px; }
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=None, help="database file (defaults to the installed app's)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output HTML path")
    parser.add_argument("--drafts-dir", default=str(DEFAULT_DRAFTS_DIR))
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE_PATH))
    parser.add_argument("--no-open", action="store_true", help="write the file but don't launch a browser")
    args = parser.parse_args()

    db_path = run_scrape.resolve_db(args.db)
    run_migrations(db_path)

    candidate_name = "Candidate"
    try:
        candidate_name = json.loads(Path(args.profile).read_text(encoding="utf-8")).get("n") or candidate_name
    except (OSError, ValueError):
        pass

    conn = get_connection(db_path)
    try:
        data = gather(conn, db_path, Path(args.drafts_dir))
    finally:
        conn.close()

    import datetime

    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = render_html(data, db_path=db_path, candidate_name=candidate_name, generated_at=generated_at)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    h = data["headline"]
    print(f"\n  dashboard written to {out_path.resolve()}")
    print(
        f"  total={h['total']} confirmed={h['verified_confirmed']} in_queue={h['in_apply_queue']} "
        f"applied={h['applied']} interviews={h['interviews']} offers={h['offers']} rejections={h['rejections']}\n"
    )
    if not args.no_open:
        webbrowser.open(out_path.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
