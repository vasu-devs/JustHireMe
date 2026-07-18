import type { GraphStats } from "../../types";
import { GraphCanvas } from "./GraphCanvas";
import { EmbeddingAtlas } from "./EmbeddingAtlas";
import { ProductionViewIntro } from "../../shared/components/ProductionViewIntro";

export function GraphView({ stats }: { stats: GraphStats }) {
  const hasGraphPayload = Array.isArray(stats.graph?.nodes);
  // A version-skewed sidecar can return `graph` without `nodes`/`edges` —
  // chain all the way down or this header crashes before the fallback renders.
  const total = stats.graph?.nodes?.length ?? 0;
  const relationCount = stats.graph?.edges?.length ?? 0;
  const isLoading = Boolean(stats.loading && !stats.loaded);
  const isRefreshing = Boolean(stats.loading);
  const requestError = stats.request_error || "";
  const isLive = stats.status === "live" && stats.available !== false && hasGraphPayload && !requestError;
  const syncedAt = stats.sync?.refreshed_at
    ? new Date(stats.sync.refreshed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "";

  return (
    <div className="scroll graph-page product-enter">
      <ProductionViewIntro
        index="04"
        eyebrow="Evidence atlas"
        title="The proof behind"
        accent="your pitch."
        description={<>Projects, skills, roles, and credentials connected the way Scout actually uses them when evaluating an opportunity.</>}
        note={<><strong>{total}</strong><span>evidence nodes</span><small>{relationCount} live connections</small></>}
        actions={<button className="btn graph-repair-button" disabled={isRefreshing} onClick={() => window.dispatchEvent(new CustomEvent("graph-repair"))}>{isRefreshing ? "Rebuilding…" : total ? "Rebuild graph" : "Build my graph"}</button>}
      />
      <div className="graph-shell graph-shell-single">
        <div className="card graph-overview graph-overview-sleek">
          <div className="graph-overview-copy">
            <span className="eyebrow">Knowledge Graph</span>
            <h1 style={{ fontSize: 30 }}>Your profile, connected</h1>
            <p>Every project, skill, role, and credential and how they relate. Click a node to focus it; scroll to zoom, drag to move.</p>
          </div>
          <div className="graph-overview-stats">
            <div>
              <span className="eyebrow">Total nodes</span>
              <div className="display tabular graph-total">{total}</div>
            </div>
            <div className="graph-mini-stats">
              <div><span>{relationCount}</span><small>Connections</small></div>
            </div>
            <span
              className="pill mono"
              title={!hasGraphPayload ? "Backend response is missing graph nodes and edges" : (stats.error || (syncedAt ? `Synced at ${syncedAt}` : "Graph status"))}
              style={{
                justifySelf: "end",
                background: isLive ? "var(--green-soft)" : "var(--bad-soft)",
                color: isLive ? "var(--green-ink)" : "var(--bad)",
                border: `1px solid ${isLive ? "var(--green)" : "var(--bad)"}`,
              }}
            >
              {isRefreshing ? "syncing" : isLive && total ? "live" : isLive ? "empty" : requestError ? "request failed" : hasGraphPayload ? "degraded" : "no graph payload"}
            </span>
          </div>
        </div>

        {!isLive && !isLoading && (
          <div className="card" style={{ color: "var(--bad)", background: "var(--bad-soft)", borderColor: "var(--bad)", padding: 14 }}>
            {requestError
              ? requestError
              : !hasGraphPayload
                ? "The graph endpoint returned a response without nodes or edges. Open Activity for the backend error, or restart the Tauri dev app if the backend was changed while it was running."
              : stats.error?.toLowerCase().includes("locked by another justhireme")
                ? stats.error
                : `Graph store is unavailable: ${stats.error || "unknown error"}`}
          </div>
        )}

        {isLoading && !hasGraphPayload ? (
          <div className="card kg-card"><div className="kg-laying" style={{ position: "static", padding: 48 }}>Loading your knowledge graph…</div></div>
        ) : (
          <GraphCanvas nodes={stats.graph?.nodes || []} edges={stats.graph?.edges || []} />
        )}

        {isLive && <EmbeddingAtlas stats={stats} />}
      </div>
    </div>
  );
}
