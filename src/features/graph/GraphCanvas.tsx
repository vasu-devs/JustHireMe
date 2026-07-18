import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  forceX,
  forceY,
  type Simulation,
} from "d3-force";
import type { GraphStats } from "../../types";

type GraphPayload = NonNullable<GraphStats["graph"]>;
type RawNode = GraphPayload["nodes"][number];
type RawEdge = GraphPayload["edges"][number];

type SimNode = RawNode & { x: number; y: number; vx?: number; vy?: number; fx?: number | null; fy?: number | null };
type SimLink = { source: string | SimNode; target: string | SimNode; type: string };

const W = 1200;
const H = 760;

// One palette + size per type. Skills grow with how connected they are, giving a
// natural hierarchy with no extra UI.
const TYPE_META: Record<string, { tone: string; radius: number; z: number }> = {
  Candidate: { tone: "ink", radius: 17, z: 5 },
  Project: { tone: "purple", radius: 12, z: 4 },
  Experience: { tone: "orange", radius: 11, z: 3 },
  Credential: { tone: "teal", radius: 9, z: 2 },
  Skill: { tone: "blue", radius: 6, z: 1 },
};
const toneOf = (type: string) => TYPE_META[type]?.tone ?? "blue";

const FILTERS: { key: string; label: string }[] = [
  { key: "all", label: "All" },
  { key: "Project", label: "Projects" },
  { key: "Skill", label: "Skills" },
  { key: "Experience", label: "Experience" },
  { key: "Credential", label: "Credentials" },
];

const REL_COPY: Record<string, string> = {
  BUILT: "built", WORKED_AS: "role", HAS_SKILL: "skill", PROJ_UTILIZES: "uses", EXP_UTILIZES: "uses",
  CERTIFIES: "certifies", EDUCATES: "teaches", ACHIEVEMENT_USES: "uses", RELATED_SKILL: "related",
  SIMILAR_PROJECT: "similar", SUPPORTS_EXPERIENCE: "supports", HAS_CERTIFICATION: "credential",
  HAS_EDUCATION: "education", HAS_ACHIEVEMENT: "achievement",
};

const radiusFor = (type: string, degree: number) => {
  const base = TYPE_META[type]?.radius ?? 6;
  return type === "Skill" ? base + Math.min(7, degree) : base;
};
// Pull a skill toward the PROJECT that uses it, not onto the candidate hub — this
// is what stops the whole graph collapsing into a starburst.
const linkStrength = (type: string) =>
  type === "HAS_SKILL" ? 0.03 : type === "PROJ_UTILIZES" || type === "EXP_UTILIZES" ? 0.4 : type === "BUILT" || type === "WORKED_AS" ? 0.2 : 0.12;
const linkDistance = (type: string) => (type === "HAS_SKILL" ? 150 : type === "PROJ_UTILIZES" ? 52 : 96);

export function GraphCanvas({ nodes, edges }: { nodes: RawNode[]; edges: RawEdge[] }) {
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [hoverId, setHoverId] = useState("");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [ready, setReady] = useState(false);

  const svgRef = useRef<SVGSVGElement | null>(null);
  const viewRef = useRef<SVGGElement | null>(null);
  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null);
  const nodeElCache = useRef<Map<string, SVGGElement>>(new Map());
  const edgeElCache = useRef<SVGLineElement[]>([]);
  const panState = useRef({ active: false, lastX: 0, lastY: 0, moved: false });
  const dragState = useRef<{ id: string; moved: boolean; sx: number; sy: number } | null>(null);

  const degree = useMemo(() => {
    const map = new Map<string, number>();
    for (const e of edges) { map.set(e.source, (map.get(e.source) || 0) + 1); map.set(e.target, (map.get(e.target) || 0) + 1); }
    return map;
  }, [edges]);

  // Visible set for the current filter (chosen type + the candidate hub).
  const { simNodes, simLinks, nodeById } = useMemo(() => {
    const keep = (n: RawNode) => n.type !== "JobLead" && (filter === "all" || n.type === filter || n.type === "Candidate");
    const vNodes = nodes.filter(keep);
    const sNodes: SimNode[] = vNodes.map((n, i) => ({
      ...n,
      x: W / 2 + Math.cos(i) * (40 + i),
      y: H / 2 + Math.sin(i) * (40 + i),
    }));
    const index = new Map(sNodes.map(n => [n.id, n]));
    const sLinks: SimLink[] = edges
      .filter(e => index.has(e.source) && index.has(e.target))
      .map(e => ({ source: e.source, target: e.target, type: e.type }));
    return { simNodes: sNodes, simLinks: sLinks, nodeById: index };
  }, [nodes, edges, filter]);

  const fitToView = useCallback((sNodes: SimNode[]) => {
    if (!sNodes.length) { setZoom(1); setPan({ x: 0, y: 0 }); return; }
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of sNodes) { minX = Math.min(minX, n.x); maxX = Math.max(maxX, n.x); minY = Math.min(minY, n.y); maxY = Math.max(maxY, n.y); }
    const pad = 90;
    const z = Math.max(0.3, Math.min(1.6, Math.min(W / (maxX - minX + pad * 2), H / (maxY - minY + pad * 2))));
    setZoom(z);
    setPan({ x: W / 2 - ((minX + maxX) / 2) * z, y: H / 2 - ((minY + maxY) / 2) * z });
  }, []);

  // ── live force simulation, rendered imperatively for smoothness ─────────────
  useEffect(() => {
    setReady(false);
    if (!simNodes.length) {
      simRef.current?.stop();
      simRef.current = null;
      setZoom(1);
      setPan({ x: 0, y: 0 });
      // An empty result is still a completed layout. Leaving `ready` false
      // suppressed both the loading and empty states and produced a blank board.
      setReady(true);
      return;
    }
    // Resolve the DOM elements React just rendered (stable keys → cached by id).
    const view = viewRef.current;
    nodeElCache.current = new Map();
    edgeElCache.current = [];
    if (view) {
      view.querySelectorAll<SVGGElement>("[data-node]").forEach(el => nodeElCache.current.set(el.dataset.node || "", el));
      view.querySelectorAll<SVGLineElement>("[data-edge]").forEach(el => { edgeElCache.current[Number(el.dataset.edge)] = el; });
    }

    const paint = () => {
      for (const n of simNodes) {
        const el = nodeElCache.current.get(n.id);
        if (el) el.setAttribute("transform", `translate(${n.x.toFixed(1)} ${n.y.toFixed(1)})`);
      }
      simLinks.forEach((l, i) => {
        const el = edgeElCache.current[i];
        const s = l.source as SimNode, t = l.target as SimNode;
        if (el && typeof s === "object" && typeof t === "object") {
          el.setAttribute("x1", String(s.x)); el.setAttribute("y1", String(s.y));
          el.setAttribute("x2", String(t.x)); el.setAttribute("y2", String(t.y));
        }
      });
    };

    const sim = forceSimulation(simNodes)
      .force("link", forceLink<SimNode, SimLink>(simLinks).id(n => n.id).distance(l => linkDistance(l.type)).strength(l => linkStrength(l.type)))
      .force("charge", forceManyBody<SimNode>().strength(n => (n.type === "Skill" ? -150 : -420)).distanceMax(560))
      .force("center", forceCenter(W / 2, H / 2))
      .force("collide", forceCollide<SimNode>().radius(n => radiusFor(n.type, degree.get(n.id) || 0) + 6).iterations(2))
      .force("x", forceX(W / 2).strength(0.04))
      .force("y", forceY(H / 2).strength(0.06))
      .stop();

    // Pre-settle off-screen so the first painted frame is already laid out and
    // fit, then run live for a short, gentle, animated cool-down.
    for (let i = 0; i < 90; i += 1) sim.tick();
    paint();
    fitToView(simNodes);
    setReady(true);
    sim.on("tick", paint).alpha(0.5).alphaDecay(0.035).restart();
    simRef.current = sim;
    return () => { sim.stop(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simNodes, simLinks]);

  // ── pointer → graph coords (handles viewBox + pan/zoom) ─────────────────────
  const toGraph = (clientX: number, clientY: number) => {
    const g = viewRef.current, svg = svgRef.current;
    if (!g || !svg) return { x: 0, y: 0 };
    const pt = svg.createSVGPoint(); pt.x = clientX; pt.y = clientY;
    const ctm = g.getScreenCTM();
    if (!ctm) return { x: 0, y: 0 };
    const p = pt.matrixTransform(ctm.inverse());
    return { x: p.x, y: p.y };
  };
  const rootScale = () => svgRef.current?.getScreenCTM()?.a || 1;

  const onWheel = (e: React.WheelEvent) => {
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    const next = Math.max(0.25, Math.min(2.8, zoom * factor));
    const gp = toGraph(e.clientX, e.clientY);
    setPan(prev => ({ x: prev.x + (zoom - next) * gp.x, y: prev.y + (zoom - next) * gp.y }));
    setZoom(next);
  };

  const onNodePointerDown = (e: React.PointerEvent, id: string) => {
    e.stopPropagation();
    dragState.current = { id, moved: false, sx: e.clientX, sy: e.clientY };
    const node = simRef.current?.nodes().find(n => n.id === id);
    if (node) { node.fx = node.x; node.fy = node.y; }
    simRef.current?.alphaTarget(0.3).restart();
    svgRef.current?.setPointerCapture(e.pointerId);
  };
  const onStagePointerDown = (e: React.PointerEvent) => {
    if (dragState.current) return;
    panState.current = { active: true, lastX: e.clientX, lastY: e.clientY, moved: false };
    svgRef.current?.setPointerCapture(e.pointerId);
  };
  const onStagePointerMove = (e: React.PointerEvent) => {
    if (dragState.current) {
      const gp = toGraph(e.clientX, e.clientY);
      const node = simRef.current?.nodes().find(n => n.id === dragState.current?.id);
      if (node) { node.fx = gp.x; node.fy = gp.y; }
      if (Math.hypot(e.clientX - dragState.current.sx, e.clientY - dragState.current.sy) > 3) dragState.current.moved = true;
      return;
    }
    if (!panState.current.active) return;
    const scale = rootScale();
    setPan(prev => ({ x: prev.x + (e.clientX - panState.current.lastX) / scale, y: prev.y + (e.clientY - panState.current.lastY) / scale }));
    panState.current.lastX = e.clientX; panState.current.lastY = e.clientY; panState.current.moved = true;
  };
  const onStagePointerUp = (e: React.PointerEvent) => {
    if (dragState.current) {
      const id = dragState.current.id;
      if (!dragState.current.moved) setSelectedId(prev => (prev === id ? "" : id));
      const node = simRef.current?.nodes().find(n => n.id === id);
      if (node) { node.fx = null; node.fy = null; }
      simRef.current?.alphaTarget(0);
      dragState.current = null;
    } else if (panState.current.active && !panState.current.moved) {
      setSelectedId("");
    }
    panState.current.active = false;
    svgRef.current?.releasePointerCapture?.(e.pointerId);
  };

  // block native page scroll-zoom over the canvas
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const stop = (ev: WheelEvent) => ev.preventDefault();
    svg.addEventListener("wheel", stop, { passive: false });
    return () => svg.removeEventListener("wheel", stop);
  }, []);

  const neighbourhood = useMemo(() => {
    if (!selectedId) return null;
    const set = new Set<string>([selectedId]);
    for (const e of simLinks) {
      const s = typeof e.source === "object" ? e.source.id : e.source;
      const t = typeof e.target === "object" ? e.target.id : e.target;
      if (s === selectedId) set.add(t);
      if (t === selectedId) set.add(s);
    }
    return set;
  }, [selectedId, simLinks]);

  const nq = query.trim().toLowerCase();
  const isActive = useCallback((id: string, label: string) => {
    if (nq && !label.toLowerCase().includes(nq)) return false;
    if (neighbourhood) return neighbourhood.has(id);
    return true;
  }, [nq, neighbourhood]);

  const selectedNode = selectedId ? nodeById.get(selectedId) : undefined;
  const connections = useMemo(() => {
    if (!selectedId) return [] as { node: RawNode; rel: string }[];
    const out: { node: RawNode; rel: string }[] = [];
    const seen = new Set<string>();
    for (const e of edges) {
      const other = e.source === selectedId ? e.target : e.target === selectedId ? e.source : "";
      if (!other || seen.has(other)) continue;
      const node = nodes.find(n => n.id === other);
      if (!node) continue;
      seen.add(other);
      out.push({ node, rel: REL_COPY[e.type] || e.type.toLowerCase().replace(/_/g, " ") });
    }
    return out.sort((a, b) => (TYPE_META[b.node.type]?.z ?? 0) - (TYPE_META[a.node.type]?.z ?? 0));
  }, [selectedId, edges, nodes]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const n of nodes) if (n.type !== "JobLead") c[n.type] = (c[n.type] || 0) + 1;
    return c;
  }, [nodes]);

  const showLabel = (type: string, id: string, label: string) =>
    type !== "Skill"
    || simNodes.length <= 30
    || (degree.get(id) || 0) >= 2
    || hoverId === id
    || selectedId === id
    || (!!nq && label.toLowerCase().includes(nq))
    || (neighbourhood?.has(id) ?? false);

  return (
    <section className="card kg-card" aria-label="Knowledge graph">
      <div className="kg-toolbar">
        <div className="kg-filters" role="group" aria-label="Filter by type">
          {FILTERS.map(({ key, label }) => (
            <button key={key} className={filter === key ? "active" : ""} onClick={() => { setFilter(key); setSelectedId(""); }}>
              {label}{key !== "all" && <span className="mono">{counts[key] || 0}</span>}
            </button>
          ))}
        </div>
        <input className="field-input kg-search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search nodes…" aria-label="Search graph nodes" />
        <div className="kg-zoom">
          <button className="btn btn-icon" onClick={() => setZoom(z => Math.max(0.25, z / 1.15))} aria-label="Zoom out">−</button>
          <button className="btn btn-icon" onClick={() => setZoom(z => Math.min(2.8, z * 1.15))} aria-label="Zoom in">+</button>
          <button className="btn" onClick={() => fitToView(simRef.current?.nodes() || simNodes)}>Fit</button>
        </div>
      </div>

      <div className="kg-body">
        <div className="kg-stage">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${H}`}
            className="kg-svg"
            preserveAspectRatio="xMidYMid meet"
            onWheel={onWheel}
            onPointerDown={onStagePointerDown}
            onPointerMove={onStagePointerMove}
            onPointerUp={onStagePointerUp}
            onPointerLeave={onStagePointerUp}
            role="application"
            aria-label="Interactive knowledge graph. Scroll to zoom, drag to pan, click a node to focus."
          >
            <g ref={viewRef} className={`kg-view ${ready ? "ready" : ""}`} transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
              {simLinks.map((edge, i) => {
                const s = typeof edge.source === "object" ? edge.source.id : edge.source;
                const t = typeof edge.target === "object" ? edge.target.id : edge.target;
                const active = (!neighbourhood || (neighbourhood.has(s) && neighbourhood.has(t)))
                  && (!nq || (nodeById.get(s)?.label.toLowerCase().includes(nq) || nodeById.get(t)?.label.toLowerCase().includes(nq)));
                return <line key={`${s}->${t}-${i}`} data-edge={i} className={`kg-edge ${active ? "" : "dim"}`} />;
              })}
              {simNodes.map(node => {
                const r = radiusFor(node.type, degree.get(node.id) || 0);
                const tone = toneOf(node.type);
                const active = isActive(node.id, node.label);
                const selected = node.id === selectedId;
                return (
                  <g
                    key={node.id}
                    data-node={node.id}
                    className={`kg-node ${active ? "" : "dim"} ${selected ? "selected" : ""}`}
                    onPointerDown={e => onNodePointerDown(e, node.id)}
                    onMouseEnter={() => setHoverId(node.id)}
                    onMouseLeave={() => setHoverId("")}
                    style={{ ["--kg-tone" as string]: `var(--${tone})` }}
                  >
                    {selected && <circle r={r + 6} className="kg-node-ring" />}
                    <circle r={r} className="kg-node-dot" />
                    {showLabel(node.type, node.id, node.label) && (
                      <text y={r + 13} className="kg-node-label">{node.label.length > 26 ? `${node.label.slice(0, 25)}…` : node.label}</text>
                    )}
                  </g>
                );
              })}
            </g>
          </svg>

          {!ready && simNodes.length > 0 && <div className="kg-overlay">Laying out graph…</div>}
          {ready && !simNodes.length && <div className="kg-overlay">No {filter === "all" ? "" : `${filter.toLowerCase()} `}nodes yet. Add context to build your graph.</div>}

          <div className="kg-legend" aria-hidden="true">
            {Object.entries(TYPE_META).filter(([type]) => type !== "Candidate").map(([type, meta]) => (
              <span key={type}><i style={{ background: `var(--${meta.tone})` }} />{type}</span>
            ))}
          </div>
        </div>

        <aside className="kg-inspector">
          {selectedNode ? (
            <>
              <div className="kg-inspector-head">
                <span className="pill" style={{ background: `var(--${toneOf(selectedNode.type)}-soft)`, color: `var(--${toneOf(selectedNode.type)}-ink)`, border: `1px solid var(--${toneOf(selectedNode.type)})` }}>{selectedNode.type}</span>
                <button className="btn-icon kg-close" onClick={() => setSelectedId("")} aria-label="Close">×</button>
              </div>
              <div className="profile-card-title kg-inspector-title">{selectedNode.label}</div>
              {selectedNode.subtitle && <p className="kg-inspector-sub">{selectedNode.subtitle}</p>}
              <span className="eyebrow">{connections.length} connection{connections.length === 1 ? "" : "s"}</span>
              <ul className="kg-conn-list">
                {connections.map(({ node, rel }) => (
                  <li key={node.id}>
                    <button onClick={() => setSelectedId(node.id)}>
                      <i style={{ background: `var(--${toneOf(node.type)})` }} />
                      <span className="kg-conn-label">{node.label}</span>
                      <span className="pill kg-conn-rel">{rel}</span>
                    </button>
                  </li>
                ))}
                {!connections.length && <li className="kg-conn-empty">No connections yet.</li>}
              </ul>
            </>
          ) : (
            <div className="kg-inspector-hint">
              <span className="eyebrow">Explore</span>
              <h3>Click any node to focus it</h3>
              <p>See what each project, skill, and role connects to. Scroll to zoom, drag to pan, drag a node to rearrange.</p>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
