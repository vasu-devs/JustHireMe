import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent, TouchEvent, WheelEvent as ReactWheelEvent } from "react";
import type { GraphStats } from "../../types";

type GestureLikeEvent = Event & { scale?: number; clientX?: number; clientY?: number };
type GraphPayload = NonNullable<GraphStats["graph"]>;
type GraphNodePayload = GraphPayload["nodes"][number];
type GraphEdgePayload = GraphPayload["edges"][number];
type EmbeddingPoint = NonNullable<GraphStats["embedding"]>["points"][number];
type AtlasView = "ribbons" | "gravity";
type GraphMode = "curated" | "evidence" | "correlation" | "all";
type CameraMode = "orbit" | "front" | "top";
type SpatialCamera = { yaw: number; pitch: number; zoom: number };
type AtlasPoint = EmbeddingPoint & { hasVector: boolean };

type SkillGrade = {
  node: GraphNodePayload;
  score: number;
  grade: string;
  projectCount: number;
  relationCount: number;
  relatedCount: number;
};

type AtlasNode = GraphNodePayload & {
  x: number;
  y: number;
  w: number;
  h: number;
  tone: string;
  support: number;
  score?: number;
  grade?: string;
};

type AtlasEdge = {
  source: string;
  target: string;
  weight: number;
  label: string;
  kind: "evidence" | "correlation";
};

type ForceNode = GraphNodePayload & {
  x: number;
  y: number;
  anchorX: number;
  anchorY: number;
  vx: number;
  vy: number;
  radius: number;
  labelW: number;
  labelH: number;
  collisionRadius: number;
  tone: string;
  degree: number;
};

type ForceEdge = GraphEdgePayload & {
  weight: number;
};

const MAX_ATLAS_SKILLS = 24;
const ATLAS_VIEWPORT_WIDTH = 1180;
const GRAVITY_WIDTH = 1500;
const GRAVITY_HEIGHT = 900;

const PROFILE_EDGE_TYPES = new Set([
  "HAS_SKILL",
  "WORKED_AS",
  "BUILT",
  "HAS_CERTIFICATION",
  "HAS_EDUCATION",
  "HAS_ACHIEVEMENT",
  "PROJ_UTILIZES",
  "EXP_UTILIZES",
  "CERTIFIES",
  "EDUCATES",
  "ACHIEVEMENT_USES",
  "RELATED_SKILL",
  "SIMILAR_PROJECT",
  "SUPPORTS_EXPERIENCE",
]);

const SKILL_EDGE_TYPES = new Set(["HAS_SKILL", "PROJ_UTILIZES", "EXP_UTILIZES", "CERTIFIES", "EDUCATES", "ACHIEVEMENT_USES"]);
const CROSS_EDGE_TYPES = new Set(["RELATED_SKILL", "SIMILAR_PROJECT", "SUPPORTS_EXPERIENCE"]);
const EDGE_COPY: Record<string, string> = {
  HAS_SKILL: "profile skill",
  BUILT: "built",
  PROJ_UTILIZES: "uses",
  EXP_UTILIZES: "uses",
  CERTIFIES: "certifies",
  EDUCATES: "teaches",
  ACHIEVEMENT_USES: "uses",
  RELATED_SKILL: "related",
  SIMILAR_PROJECT: "similar",
  SUPPORTS_EXPERIENCE: "supports",
};

const TONES: Record<string, string> = {
  Profile: "purple",
  Skill: "orange",
  Project: "pink",
  Experience: "green",
  Candidate: "purple",
  Credential: "blue",
  Certification: "blue",
  Education: "blue",
  Achievement: "blue",
  JobLead: "blue",
};

function truncate(text: string, max = 24) {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  return clean.length > max ? `${clean.slice(0, max - 1)}...` : clean;
}

function isBadVectorLabel(value: string) {
  const lower = String(value || "").trim().toLowerCase();
  return !lower
    || lower.includes("404:")
    || lower.includes("not_found")
    || lower.includes("not found")
    || lower.includes("error code")
    || lower.includes("failed to fetch")
    || lower.includes("server returned")
    || lower.includes("traceback");
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function normalizeAngle(value: number) {
  let next = value % 360;
  if (next > 180) next -= 360;
  if (next < -180) next += 360;
  return Number(next.toFixed(1));
}

function edgeLabel(type: string) {
  return EDGE_COPY[type] || type.replace(/_/g, " ").toLowerCase();
}

function seededUnit(seed: string, salt: number) {
  let hash = 2166136261 ^ salt;
  for (let i = 0; i < seed.length; i += 1) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return ((hash >>> 0) % 10000) / 10000;
}

function buildGravityGraph(allNodes: GraphNodePayload[], allEdges: GraphEdgePayload[]) {
  const sourceNodes = allNodes
    .filter(node => !["JobLead", "Candidate", "Profile"].includes(node.type))
    .sort((a, b) => a.type.localeCompare(b.type) || a.label.localeCompare(b.label))
    .slice(0, 140);
  const nodeIds = new Set(sourceNodes.map(node => node.id));
  const sourceEdges = allEdges
    .filter(edge => PROFILE_EDGE_TYPES.has(edge.type) && nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .slice(0, 320);
  const degree = new Map<string, number>();
  sourceEdges.forEach(edge => {
    degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
  });
  const typeCenters: Record<string, { x: number; y: number }> = {
    Project: { x: GRAVITY_WIDTH * 0.30, y: GRAVITY_HEIGHT * 0.56 },
    Skill: { x: GRAVITY_WIDTH * 0.72, y: GRAVITY_HEIGHT * 0.46 },
    Experience: { x: GRAVITY_WIDTH * 0.43, y: GRAVITY_HEIGHT * 0.22 },
    Credential: { x: GRAVITY_WIDTH * 0.62, y: GRAVITY_HEIGHT * 0.78 },
    Certification: { x: GRAVITY_WIDTH * 0.62, y: GRAVITY_HEIGHT * 0.78 },
    Education: { x: GRAVITY_WIDTH * 0.74, y: GRAVITY_HEIGHT * 0.76 },
    Achievement: { x: GRAVITY_WIDTH * 0.50, y: GRAVITY_HEIGHT * 0.82 },
  };
  const edgeWeight = (type: string) => {
    if (type === "PROJ_UTILIZES") return 1.42;
    if (type === "HAS_SKILL") return 0.55;
    if (type === "BUILT" || type === "WORKED_AS") return 1.2;
    if (CROSS_EDGE_TYPES.has(type)) return 0.38;
    return 1;
  };
  const verticalOffsetByType: Record<string, number> = {
    Skill: -145,
    Experience: -245,
    Credential: 165,
    Certification: 165,
    Education: 230,
    Achievement: 250,
  };
  const typeIndex = new Map<string, number>();
  const visibleNodes = sourceNodes.filter(node => (degree.get(node.id) || 0) > 0);
  const projectCount = visibleNodes.filter(node => node.type === "Project").length;
  const projectStep = projectCount <= 1 ? 0 : Math.min(230, Math.max(150, (GRAVITY_WIDTH - 300) / (projectCount - 1)));
  let projectLaneIndex = 0;
  const projectAnchors = new Map<string, { x: number; y: number }>();
  visibleNodes.filter(node => node.type === "Project").forEach(node => {
    const projectIndex = projectLaneIndex++;
    projectAnchors.set(node.id, {
      x: projectCount <= 1 ? typeCenters.Project.x : 150 + projectIndex * projectStep,
      y: GRAVITY_HEIGHT * 0.56,
    });
  });
  const directProjectAnchors = (nodeId: string) => sourceEdges
    .map(edge => {
      if (edge.source === nodeId && projectAnchors.has(edge.target)) return { anchor: projectAnchors.get(edge.target)!, weight: edgeWeight(edge.type) };
      if (edge.target === nodeId && projectAnchors.has(edge.source)) return { anchor: projectAnchors.get(edge.source)!, weight: edgeWeight(edge.type) };
      return null;
    })
    .filter((item): item is { anchor: { x: number; y: number }; weight: number } => Boolean(item));
  const weightedAnchorFor = (node: GraphNodePayload, index: number) => {
    const directProjects = directProjectAnchors(node.id);
    if (!directProjects.length) {
      const center = typeCenters[node.type] || { x: GRAVITY_WIDTH * 0.5, y: GRAVITY_HEIGHT * 0.5 };
      const ring = Math.floor(index / 7);
      const angle = index * 2.399963229728653 + ring * 0.35;
      const distance = 72 + ring * 92 + (index % 7) * 8;
      return {
        x: center.x + Math.cos(angle) * distance,
        y: center.y + Math.sin(angle) * distance * 0.72,
      };
    }
    const total = directProjects.reduce((sum, item) => sum + item.weight, 0) || 1;
    const x = directProjects.reduce((sum, item) => sum + item.anchor.x * item.weight, 0) / total;
    const y = directProjects.reduce((sum, item) => sum + item.anchor.y * item.weight, 0) / total;
    const side = seededUnit(node.id, 17) > 0.5 ? 1 : -1;
    const spread = (seededUnit(node.id, 23) - 0.5) * 84;
    return {
      x: clamp(x + spread, 68, GRAVITY_WIDTH - 68),
      y: clamp(y + (verticalOffsetByType[node.type] ?? side * 170) + (seededUnit(node.id, 29) - 0.5) * 70, 70, GRAVITY_HEIGHT - 70),
    };
  };
  const nodes: ForceNode[] = visibleNodes.map(node => {
    const d = degree.get(node.id) || 0;
    const index = typeIndex.get(node.type) || 0;
    typeIndex.set(node.type, index + 1);
    const anchor = node.type === "Project" ? projectAnchors.get(node.id)! : weightedAnchorFor(node, index);
    const label = truncate(node.label, 28);
    const labelW = clamp(56 + label.length * 7.2, 92, 260);
    const labelH = 32;
    return {
      ...node,
      x: anchor.x,
      y: anchor.y,
      anchorX: anchor.x,
      anchorY: anchor.y,
      vx: 0,
      vy: 0,
      radius: clamp(7 + Math.sqrt(d + 1) * 2.2, 10, 20),
      labelW,
      labelH,
      collisionRadius: clamp(7 + Math.sqrt(d + 1) * 2.2, 10, 20) + 44,
      tone: TONES[node.type] || "orange",
      degree: d,
    };
  });
  const lookup = new Map(nodes.map(node => [node.id, node]));
  const visibleNodeIds = new Set(nodes.map(node => node.id));
  const candidateEdges: ForceEdge[] = sourceEdges
    .filter(edge => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target))
    .map(edge => ({ ...edge, weight: edgeWeight(edge.type) }));
  const edgeLimitByNode = new Map<string, number>();
  const edges: ForceEdge[] = [];
  candidateEdges
    .filter(edge => edge.type !== "HAS_SKILL" || (degree.get(edge.target) || degree.get(edge.source) || 0) <= 7)
    .sort((a, b) => b.weight - a.weight)
    .forEach(edge => {
      const sourceCount = edgeLimitByNode.get(edge.source) || 0;
      const targetCount = edgeLimitByNode.get(edge.target) || 0;
      const maxEdges = edge.type === "PROJ_UTILIZES" ? 7 : 3;
      if (sourceCount >= maxEdges || targetCount >= maxEdges) return;
      edges.push(edge);
      edgeLimitByNode.set(edge.source, sourceCount + 1);
      edgeLimitByNode.set(edge.target, targetCount + 1);
    });

  for (let tick = 0; tick < 360; tick += 1) {
    const alpha = 1 - tick / 360;
    for (let i = 0; i < nodes.length; i += 1) {
      const a = nodes[i];
      const anchorPull = a.type === "Project" ? 0.0044 : 0.0019;
      a.vx += (a.anchorX - a.x) * anchorPull * alpha;
      a.vy += (a.anchorY - a.y) * anchorPull * alpha;
      for (let j = i + 1; j < nodes.length; j += 1) {
        const b = nodes[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let dist2 = dx * dx + dy * dy;
        if (dist2 < 0.01) {
          dx = seededUnit(`${a.id}:${b.id}`, 3) - 0.5;
          dy = seededUnit(`${b.id}:${a.id}`, 5) - 0.5;
          dist2 = dx * dx + dy * dy || 0.01;
        }
        const dist = Math.sqrt(dist2);
        const minDist = a.collisionRadius + b.collisionRadius + 22;
        const repel = Math.min(9.4, ((minDist * minDist) / dist2) * 0.92 * alpha);
        const nx = dx / dist;
        const ny = dy / dist;
        a.vx -= nx * repel;
        a.vy -= ny * repel;
        b.vx += nx * repel;
        b.vy += ny * repel;
        if (dist < minDist) {
          const push = (minDist - dist) * 0.16;
          a.vx -= nx * push;
          a.vy -= ny * push;
          b.vx += nx * push;
          b.vy += ny * push;
        }
      }
    }
    edges.forEach(edge => {
      const a = lookup.get(edge.source);
      const b = lookup.get(edge.target);
      if (!a || !b) return;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const target = 176 + (a.type === b.type ? 50 : 24) - edge.weight * 22;
      const force = (dist - target) * 0.0068 * edge.weight * alpha;
      const nx = dx / dist;
      const ny = dy / dist;
      a.vx += nx * force;
      a.vy += ny * force;
      b.vx -= nx * force;
      b.vy -= ny * force;
    });
    nodes.forEach(node => {
      node.vx *= 0.72;
      node.vy *= 0.72;
      node.x = clamp(node.x + node.vx, 34, GRAVITY_WIDTH - 34);
      node.y = clamp(node.y + node.vy, 34, GRAVITY_HEIGHT - 34);
    });
  }
  return { nodes, edges, lookup };
}

function resolveGravityCollisions(nodes: ForceNode[], offsets: Record<string, { x: number; y: number }>) {
  const next: Record<string, { x: number; y: number }> = { ...offsets };
  const placed = nodes.map(node => {
    const offset = next[node.id] || { x: 0, y: 0 };
    return { node, x: node.x + offset.x, y: node.y + offset.y };
  });
  for (let pass = 0; pass < 3; pass += 1) {
    for (let i = 0; i < placed.length; i += 1) {
      for (let j = i + 1; j < placed.length; j += 1) {
        const a = placed[i];
        const b = placed[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let distance = Math.sqrt(dx * dx + dy * dy);
        if (distance < 0.001) {
          const angle = seededUnit(`${a.node.id}:${b.node.id}`, pass + 101) * Math.PI * 2;
          dx = Math.cos(angle);
          dy = Math.sin(angle);
          distance = 1;
        }
        const minDistance = a.node.collisionRadius + b.node.collisionRadius + 12;
        if (distance >= minDistance) continue;
        const push = (minDistance - distance) / 2;
        const nx = dx / distance;
        const ny = dy / distance;
        const aOffset = next[a.node.id] || { x: 0, y: 0 };
        const bOffset = next[b.node.id] || { x: 0, y: 0 };
        next[a.node.id] = { x: aOffset.x - nx * push, y: aOffset.y - ny * push };
        next[b.node.id] = { x: bOffset.x + nx * push, y: bOffset.y + ny * push };
        a.x -= nx * push;
        a.y -= ny * push;
        b.x += nx * push;
        b.y += ny * push;
      }
    }
  }
  return next;
}

function nodeSupport(nodeId: string, edges: GraphEdgePayload[]) {
  return edges.filter(edge => edge.source === nodeId || edge.target === nodeId).length;
}

function otherNode(edge: GraphEdgePayload, nodeId: string, nodeMap: Map<string, GraphNodePayload>) {
  const otherId = edge.source === nodeId ? edge.target : edge.source;
  return nodeMap.get(otherId);
}

function uniqueNodes(nodes: (GraphNodePayload | undefined)[]) {
  const seen = new Set<string>();
  return nodes.filter((node): node is GraphNodePayload => {
    if (!node || seen.has(node.id)) return false;
    seen.add(node.id);
    return true;
  });
}

function skillIdsFor(nodeId: string, edges: GraphEdgePayload[], nodeMap: Map<string, GraphNodePayload>) {
  return new Set(
    edges
      .filter(edge => (edge.source === nodeId || edge.target === nodeId) && SKILL_EDGE_TYPES.has(edge.type))
      .map(edge => otherNode(edge, nodeId, nodeMap))
      .filter((node): node is GraphNodePayload => Boolean(node && node.type === "Skill"))
      .map(node => node.id)
  );
}

function scoreSkill(skill: GraphNodePayload, edges: GraphEdgePayload[], nodeMap: Map<string, GraphNodePayload>): SkillGrade {
  const touching = edges.filter(edge => edge.source === skill.id || edge.target === skill.id);
  const projects = uniqueNodes(touching.filter(edge => SKILL_EDGE_TYPES.has(edge.type)).map(edge => otherNode(edge, skill.id, nodeMap))).filter(node => node.type === "Project");
  const related = uniqueNodes(touching.filter(edge => CROSS_EDGE_TYPES.has(edge.type)).map(edge => otherNode(edge, skill.id, nodeMap))).filter(node => node.type === "Skill");
  const relationCount = touching.length;
  const score = Math.min(100, Math.round(projects.length * 24 + relationCount * 4 + related.length * 5));
  const grade = score >= 82 ? "A" : score >= 64 ? "B" : score >= 42 ? "C" : score >= 24 ? "D" : "Seed";
  return { node: skill, score, grade, projectCount: projects.length, relationCount, relatedCount: related.length };
}

function buildRelationAtlas(allNodes: GraphNodePayload[], allEdges: GraphEdgePayload[], limit: number, query: string) {
  const profileNodes = allNodes.filter(node => node.type !== "JobLead");
  const nodeMap = new Map(profileNodes.map(node => [node.id, node]));
  const graphEdges = allEdges.filter(edge => PROFILE_EDGE_TYPES.has(edge.type) && nodeMap.has(edge.source) && nodeMap.has(edge.target));
  const normalizedQuery = query.trim().toLowerCase();
  const projects = profileNodes
    .filter(node => node.type === "Project")
    .filter(node => !normalizedQuery || node.label.toLowerCase().includes(normalizedQuery))
    .sort((a, b) => nodeSupport(b.id, graphEdges) - nodeSupport(a.id, graphEdges))
    .slice(0, 10);
  const rankedGrades = profileNodes
    .filter(node => node.type === "Skill")
    .map(skill => scoreSkill(skill, graphEdges, nodeMap))
    .filter(item => !normalizedQuery || item.node.label.toLowerCase().includes(normalizedQuery) || projects.some(project => skillIdsFor(project.id, graphEdges, nodeMap).has(item.node.id)))
    .sort((a, b) => b.score - a.score || b.relationCount - a.relationCount)
    .slice(0, limit);
  const visibleGrades = rankedGrades.slice(0, MAX_ATLAS_SKILLS);
  const overflowGrades = rankedGrades.slice(MAX_ATLAS_SKILLS);
  const overflowGroups = ["A", "B", "C", "D", "Seed"]
    .map(grade => {
      const items = overflowGrades.filter(item => item.grade === grade);
      if (!items.length) return null;
      const score = Math.round(items.reduce((sum, item) => sum + item.score, 0) / items.length);
      return { id: `skill-cluster:${grade}`, label: `${grade} skills`, type: "SkillCluster", grade, score, items };
    })
    .filter((item): item is { id: string; label: string; type: string; grade: string; score: number; items: SkillGrade[] } => Boolean(item));
  const grades = visibleGrades;
  const skillToCluster = new Map<string, string>();
  overflowGroups.forEach(group => group.items.forEach(item => skillToCluster.set(item.node.id, group.id)));
  const projectIds = new Set(projects.map(project => project.id));
  const allRankedSkillIds = new Set(rankedGrades.map(grade => grade.node.id));
  const drawableSkillIds = new Set([...grades.map(grade => grade.node.id), ...overflowGroups.map(group => group.id)]);
  const clusterRows = Math.max(1, Math.ceil(grades.length / 2) + overflowGroups.length);
  const height = 680;
  const projectGap = projects.length <= 1 ? 0 : Math.min(68, (height - 170) / (projects.length - 1));
  const skillGap = clusterRows <= 1 ? 0 : Math.min(70, (height - 180) / (clusterRows - 1));
  const projectStart = height / 2 - ((projects.length - 1) * projectGap) / 2;
  const skillStart = height / 2 - ((clusterRows - 1) * skillGap) / 2;
  const projectNodes: AtlasNode[] = projects.map((project, index) => ({
    ...project,
    x: 180 + (index % 2) * 92,
    y: projectStart + index * projectGap,
    w: 220,
    h: 42,
    tone: "pink",
    support: nodeSupport(project.id, graphEdges),
  }));
  const skillNodes: AtlasNode[] = grades.map((grade, index) => ({
    ...grade.node,
    x: 820 + (index % 2) * 235,
    y: skillStart + Math.floor(index / 2) * skillGap,
    w: 210,
    h: 38,
    tone: "orange",
    support: grade.relationCount,
    score: grade.score,
    grade: grade.grade,
  }));
  const clusterNodes: AtlasNode[] = overflowGroups.map((group, index) => ({
    id: group.id,
    label: group.label,
    type: group.type,
    subtitle: `${group.items.length} grouped skills`,
    x: 940,
    y: skillStart + (Math.ceil(grades.length / 2) + index) * skillGap,
    w: 240,
    h: 38,
    tone: "blue",
    support: group.items.reduce((sum, item) => sum + item.relationCount, 0),
    score: group.score,
    grade: group.grade,
  }));
  const evidenceEdges: AtlasEdge[] = graphEdges.flatMap(edge => {
    if (!SKILL_EDGE_TYPES.has(edge.type)) return [];
    const source = nodeMap.get(edge.source);
    const target = nodeMap.get(edge.target);
    if (!source || !target) return [];
    const project = source.type === "Project" ? source : target.type === "Project" ? target : null;
    const skill = source.type === "Skill" ? source : target.type === "Skill" ? target : null;
    if (!project || !skill || !projectIds.has(project.id) || !allRankedSkillIds.has(skill.id)) return [];
    const grade = grades.find(item => item.node.id === skill.id);
    const targetId = drawableSkillIds.has(skill.id) ? skill.id : skillToCluster.get(skill.id);
    if (!targetId) return [];
    const overflowGrade = rankedGrades.find(item => item.node.id === skill.id);
    return [{ source: project.id, target: targetId, weight: Math.max(1, (grade?.score || overflowGrade?.score || 25) / 24), label: edgeLabel(edge.type), kind: "evidence" as const }];
  });
  const correlationEdges: AtlasEdge[] = [];
  for (let i = 0; i < projects.length; i += 1) {
    const a = projects[i];
    const aSkills = skillIdsFor(a.id, graphEdges, nodeMap);
    for (let j = i + 1; j < projects.length; j += 1) {
      const b = projects[j];
      const bSkills = skillIdsFor(b.id, graphEdges, nodeMap);
      const shared = [...aSkills].filter(id => bSkills.has(id) && allRankedSkillIds.has(id)).length;
      if (shared > 0) correlationEdges.push({ source: a.id, target: b.id, weight: shared, label: `${shared} shared skills`, kind: "correlation" });
    }
  }
  const nodes = [...projectNodes, ...skillNodes, ...clusterNodes];
  const nodeLookup = new Map(nodes.map(node => [node.id, node]));
  return { projects: projectNodes, skills: skillNodes, clusters: clusterNodes, nodes, edges: evidenceEdges, correlations: correlationEdges, grades: rankedGrades, nodeLookup, height };
}

function relationPath(source: AtlasNode, target: AtlasNode, kind: AtlasEdge["kind"]) {
  if (kind === "correlation") {
    const x = source.x - source.w / 2 - 32;
    const c = x - Math.max(45, Math.abs(source.y - target.y) * 0.25);
    return `M ${source.x - source.w / 2} ${source.y} C ${c} ${source.y}, ${c} ${target.y}, ${target.x - target.w / 2} ${target.y}`;
  }
  const startX = source.x + source.w / 2;
  const endX = target.x - target.w / 2;
  const c1 = startX + 220;
  const c2 = endX - 220;
  return `M ${startX} ${source.y} C ${c1} ${source.y}, ${c2} ${target.y}, ${endX} ${target.y}`;
}

function GravityRelationGraph({ stats }: { stats: GraphStats }) {
  const [selectedId, setSelectedId] = useState("");
  const [zoom, setZoom] = useState(0.82);
  const [pan, setPan] = useState({ x: -120, y: -80 });
  const [isPanning, setIsPanning] = useState(false);
  const [draggingId, setDraggingId] = useState("");
  const [nodeOffsets, setNodeOffsets] = useState<Record<string, { x: number; y: number }>>({});
  const stageRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const panRef = useRef({ active: false, x: 0, y: 0, panX: 0, panY: 0 });
  const offsetsRef = useRef<Record<string, { x: number; y: number }>>({});
  const velocitiesRef = useRef<Record<string, { x: number; y: number }>>({});
  const dragRef = useRef({
    active: false,
    id: "",
    startX: 0,
    startY: 0,
    targetX: 0,
    targetY: 0,
    moved: false,
    offsets: {} as Record<string, { x: number; y: number }>,
  });
  const springRef = useRef<number | null>(null);
  const liquidFrameRef = useRef<number | null>(null);
  const graph = useMemo(() => buildGravityGraph(stats.graph?.nodes || [], stats.graph?.edges || []), [stats.graph?.nodes, stats.graph?.edges]);
  useEffect(() => {
    setNodeOffsets({});
    offsetsRef.current = {};
    velocitiesRef.current = {};
    setSelectedId("");
  }, [graph]);
  useEffect(() => () => {
    if (springRef.current !== null) cancelAnimationFrame(springRef.current);
    if (liquidFrameRef.current !== null) cancelAnimationFrame(liquidFrameRef.current);
  }, []);
  const displayNodes = useMemo<ForceNode[]>(() => graph.nodes.map(node => {
    const offset = nodeOffsets[node.id] || { x: 0, y: 0 };
    return { ...node, x: node.x + offset.x, y: node.y + offset.y };
  }), [graph.nodes, nodeOffsets]);
  const displayLookup = useMemo(() => new Map(displayNodes.map(node => [node.id, node])), [displayNodes]);
  const selected = selectedId ? displayLookup.get(selectedId) : undefined;
  const selectedEdges = selected ? graph.edges.filter(edge => edge.source === selected.id || edge.target === selected.id) : [];
  const focusId = draggingId || selected?.id || "";
  const focusEdges = focusId ? graph.edges.filter(edge => edge.source === focusId || edge.target === focusId) : [];
  const focused = new Set(focusId ? [focusId, ...focusEdges.flatMap(edge => [edge.source, edge.target])] : graph.nodes.map(node => node.id));
  const related = selected ? selectedEdges.map(edge => displayLookup.get(edge.source === selected.id ? edge.target : edge.source)).filter((node): node is ForceNode => Boolean(node)) : [...displayNodes].sort((a, b) => b.degree - a.degree).slice(0, 8);
  const counts = graph.nodes.reduce<Record<string, number>>((acc, node) => {
    acc[node.type] = (acc[node.type] || 0) + 1;
    return acc;
  }, {});
  const clientToGraph = (clientX: number, clientY: number) => {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const rect = svg.getBoundingClientRect();
    return {
      x: (((clientX - rect.left) / rect.width) * GRAVITY_WIDTH - pan.x) / zoom,
      y: (((clientY - rect.top) / rect.height) * GRAVITY_HEIGHT - pan.y) / zoom,
    };
  };
  const runLiquidFrame = () => {
    liquidFrameRef.current = null;
    const drag = dragRef.current;
    const currentOffsets = offsetsRef.current;
    const currentVelocities = velocitiesRef.current;
    const targets: Record<string, { x: number; y: number; stiffness: number }> = {};
    if (drag.active) {
      const dx = drag.targetX - drag.startX;
      const dy = drag.targetY - drag.startY;
      targets[drag.id] = {
        x: (drag.offsets[drag.id]?.x || 0) + dx,
        y: (drag.offsets[drag.id]?.y || 0) + dy,
        stiffness: 0.17,
      };
      graph.edges
        .filter(edge => edge.source === drag.id || edge.target === drag.id)
        .forEach(edge => {
          const otherId = edge.source === drag.id ? edge.target : edge.source;
          const strength = clamp(0.22 + edge.weight * 0.08, 0.18, 0.42);
          targets[otherId] = {
            x: (drag.offsets[otherId]?.x || 0) + dx * strength,
            y: (drag.offsets[otherId]?.y || 0) + dy * strength,
            stiffness: 0.060,
          };
        });
    } else {
      Object.keys(currentOffsets).forEach(id => {
        targets[id] = { x: 0, y: 0, stiffness: 0.024 };
      });
    }
    const ids = new Set([...Object.keys(currentOffsets), ...Object.keys(targets)]);
    const nextOffsets: Record<string, { x: number; y: number }> = {};
    const nextVelocities: Record<string, { x: number; y: number }> = {};
    let active = drag.active;
    ids.forEach(id => {
      const offset = currentOffsets[id] || { x: 0, y: 0 };
      const velocity = currentVelocities[id] || { x: 0, y: 0 };
      const target = targets[id] || { x: 0, y: 0, stiffness: 0.018 };
      const damping = drag.active ? (id === drag.id ? 0.64 : 0.74) : 0.58;
      const vx = velocity.x * damping + (target.x - offset.x) * target.stiffness;
      const vy = velocity.y * damping + (target.y - offset.y) * target.stiffness;
      const x = offset.x + vx;
      const y = offset.y + vy;
      if (Math.abs(x) > 0.35 || Math.abs(y) > 0.35 || Math.abs(vx) > 0.06 || Math.abs(vy) > 0.06 || drag.active) {
        nextOffsets[id] = { x, y };
        nextVelocities[id] = { x: vx, y: vy };
        active = true;
      }
    });
    const separatedOffsets = resolveGravityCollisions(graph.nodes, nextOffsets);
    offsetsRef.current = separatedOffsets;
    velocitiesRef.current = nextVelocities;
    setNodeOffsets(separatedOffsets);
    if (active) liquidFrameRef.current = requestAnimationFrame(runLiquidFrame);
  };
  const ensureLiquidLoop = () => {
    if (liquidFrameRef.current === null) liquidFrameRef.current = requestAnimationFrame(runLiquidFrame);
  };
  const springHome = () => {
    const tick = () => {
      ensureLiquidLoop();
      springRef.current = null;
    };
    springRef.current = requestAnimationFrame(tick);
  };
  const handleWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    const nextZoom = clamp(Number((zoom - event.deltaY * 0.001).toFixed(2)), 0.45, 1.8);
    setZoom(nextZoom);
  };
  const handlePanStart = (event: PointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    if ((event.target as Element).closest(".gravity-node")) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    panRef.current = { active: true, x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
    setIsPanning(true);
  };
  const handlePanMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!panRef.current.active) return;
    event.preventDefault();
    setPan({
      x: panRef.current.panX + event.clientX - panRef.current.x,
      y: panRef.current.panY + event.clientY - panRef.current.y,
    });
  };
  const stopPan = (event?: PointerEvent<HTMLDivElement>) => {
    if (event?.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    panRef.current.active = false;
    setIsPanning(false);
  };
  const handleNodeDragStart = (event: PointerEvent<SVGGElement>, node: ForceNode) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    if (springRef.current !== null) cancelAnimationFrame(springRef.current);
    const start = clientToGraph(event.clientX, event.clientY);
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { active: true, id: node.id, startX: start.x, startY: start.y, targetX: start.x, targetY: start.y, moved: false, offsets: offsetsRef.current };
    setDraggingId(node.id);
    setSelectedId(node.id);
    ensureLiquidLoop();
  };
  const handleNodeDragMove = (event: PointerEvent<SVGGElement>) => {
    const drag = dragRef.current;
    if (!drag.active) return;
    event.preventDefault();
    event.stopPropagation();
    const current = clientToGraph(event.clientX, event.clientY);
    drag.targetX = current.x;
    drag.targetY = current.y;
    if (Math.abs(current.x - drag.startX) + Math.abs(current.y - drag.startY) > 3) drag.moved = true;
    ensureLiquidLoop();
  };
  const handleNodeDragEnd = (event: PointerEvent<SVGGElement>, node: ForceNode) => {
    const drag = dragRef.current;
    event.preventDefault();
    event.stopPropagation();
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    dragRef.current = { ...dragRef.current, active: false };
    setDraggingId("");
    if (!drag.moved) setSelectedId(selectedId === node.id ? "" : node.id);
    springHome();
  };
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return undefined;
    const stopNativeWheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
    };
    stage.addEventListener("wheel", stopNativeWheel, { passive: false });
    return () => stage.removeEventListener("wheel", stopNativeWheel);
  }, []);

  return (
    <div className="gravity-graph-layout">
      <div
        ref={stageRef}
        className={`gravity-graph-stage ${isPanning ? "panning" : ""}`}
        onWheel={handleWheel}
        onPointerDown={handlePanStart}
        onPointerMove={handlePanMove}
        onPointerUp={stopPan}
        onPointerCancel={stopPan}
      >
        <svg ref={svgRef} viewBox={`0 0 ${GRAVITY_WIDTH} ${GRAVITY_HEIGHT}`} className="gravity-graph-svg" role="img" aria-label="Weighted gravitational entity graph">
          <defs>
            <linearGradient id="gravityEdge" x1="0" x2="1">
              <stop offset="0%" stopColor="rgba(91, 140, 68, 0.30)" />
              <stop offset="100%" stopColor="rgba(199, 100, 66, 0.44)" />
            </linearGradient>
          </defs>
          <rect x="0" y="0" width={GRAVITY_WIDTH} height={GRAVITY_HEIGHT} rx="28" className="gravity-graph-bg" />
          <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
          <g className="gravity-edges">
            {graph.edges.map((edge, index) => {
              const source = displayLookup.get(edge.source);
              const target = displayLookup.get(edge.target);
              if (!source || !target) return null;
              const active = !focusId || edge.source === focusId || edge.target === focusId;
              const curve = Math.min(80, Math.max(24, Math.abs(source.y - target.y) * 0.18));
              const midX = (source.x + target.x) / 2;
              const midY = (source.y + target.y) / 2;
              const path = `M ${source.x} ${source.y} Q ${midX} ${midY - curve} ${target.x} ${target.y}`;
              return (
                <path
                  key={`${edge.source}-${edge.target}-${index}`}
                  d={path}
                  strokeWidth={clamp(0.7 + edge.weight * 0.85, 0.8, 3.8)}
                  className={active ? "active" : "dimmed"}
                />
              );
            })}
          </g>
          <g className="gravity-nodes">
            {displayNodes.map(node => {
              const active = selected?.id === node.id;
              const dimmed = !focused.has(node.id);
              return (
                <g
                  key={node.id}
                  className={`gravity-node ${active ? "active" : ""} ${dimmed ? "dimmed" : ""} ${draggingId === node.id ? "dragging" : ""}`}
                  transform={`translate(${node.x},${node.y})`}
                  role="button"
                  tabIndex={0}
                  aria-label={`${node.type} ${node.label}`}
                  onPointerDown={event => handleNodeDragStart(event, node)}
                  onPointerMove={handleNodeDragMove}
                  onPointerUp={event => handleNodeDragEnd(event, node)}
                  onPointerCancel={event => handleNodeDragEnd(event, node)}
                  onKeyDown={event => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedId(active ? "" : node.id);
                    }
                  }}
                >
                  <circle r={node.radius + 11} className="gravity-node-aura" fill={`var(--${node.tone}-soft)`} />
                  <circle r={node.radius} fill={`var(--${node.tone})`} stroke={`var(--${node.tone}-ink)`} />
                  <g transform={`translate(${-node.labelW / 2},${-node.radius - 38})`}>
                    <rect width={node.labelW} height={node.labelH} rx="14" className="gravity-label-pill floating" />
                    <text x={node.labelW / 2} y="20" textAnchor="middle" className="gravity-node-label">{truncate(node.label, 28)}</text>
                  </g>
                  {active && <circle r={node.radius + 7} className="gravity-node-focus-ring" />}
                  <title>{`${node.label} (${node.type}) - ${node.degree} links`}</title>
                </g>
              );
            })}
          </g>
          </g>
          {graph.nodes.length === 0 && (
            <g>
              <text x={GRAVITY_WIDTH / 2} y={GRAVITY_HEIGHT / 2 - 8} textAnchor="middle" className="graph-empty-svg">No entity graph yet</text>
              <text x={GRAVITY_WIDTH / 2} y={GRAVITY_HEIGHT / 2 + 22} textAnchor="middle" className="graph-empty-svg-sub">Add profile projects and skills, then refresh the graph.</text>
            </g>
          )}
        </svg>
      </div>
      <aside className="graph-studio-inspector gravity-inspector">
        <div className="graph-board-subhead">
          <span className="eyebrow">Gravity focus</span>
          <span className="pill mono">{graph.edges.length} edges</span>
        </div>
        <h4>{selected ? selected.label : "Weighted entity field"}</h4>
        <p>
          {selected
            ? `${selected.type} node with ${selected.degree} weighted relations. Nearby nodes are pulled by shared evidence and pushed apart by collision spacing.`
            : "A force-style view of all profile entities. Strong relationships pull nodes together while unrelated entities repel into natural clusters."}
        </p>
        <div className="graph-mini-label">View controls</div>
        <div className="graph-zoom-controls gravity-controls" aria-label="Gravity graph zoom controls">
          <button onClick={() => setZoom(value => clamp(Number((value - 0.12).toFixed(2)), 0.45, 1.8))}>-</button>
          <input aria-label="Gravity graph zoom" type="range" min="0.45" max="1.8" step="0.03" value={zoom} onChange={event => setZoom(Number(event.target.value))} />
          <button onClick={() => setZoom(value => clamp(Number((value + 0.12).toFixed(2)), 0.45, 1.8))}>+</button>
          <button onClick={() => { setZoom(0.82); setPan({ x: -120, y: -80 }); }}>Reset</button>
          <span>{Math.round(zoom * 100)}%</span>
        </div>
        <div className="graph-mini-label">Connected entities</div>
        <div className="graph-node-pick-list compact">
          {related.slice(0, 10).map(node => (
            <button key={node.id} className="graph-node-pick" onClick={() => setSelectedId(node.id)}>
              <span>{truncate(node.label, 26)}</span>
              <small>{node.type}</small>
            </button>
          ))}
        </div>
        <div className="graph-mini-label">Groups</div>
        <div className="graph-legend stacked">
          {Object.entries(counts).map(([type, count]) => (
            <span key={type}><i className={`legend-dot ${type.toLowerCase()}`} /> {type}<b>{count}</b></span>
          ))}
        </div>
      </aside>
    </div>
  );
}

function KnowledgeRelationAtlas({ stats }: { stats: GraphStats }) {
  const [view, setView] = useState<AtlasView>("ribbons");
  const [mode, setMode] = useState<GraphMode>("curated");
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(18);
  const [selectedId, setSelectedId] = useState<string>("");
  const [zoom, setZoom] = useState(1);
  const [isPanning, setIsPanning] = useState(false);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const stageRef = useRef<HTMLDivElement | null>(null);
  const atlasHoverRef = useRef(false);
  const panRef = useRef({ active: false, x: 0, y: 0, panX: 0, panY: 0 });
  const pinchRef = useRef({ active: false, distance: 0, zoom: 1, centerX: 0, centerY: 0, panX: 0, panY: 0 });
  const gestureRef = useRef({ active: false, scale: 1, zoom: 1, clientX: 0, clientY: 0 });
  const viewportPinchRef = useRef({ scale: 1, zoom: 1 });
  const atlas = useMemo(() => buildRelationAtlas(stats.graph?.nodes || [], stats.graph?.edges || [], limit, query), [stats.graph?.nodes, stats.graph?.edges, limit, query]);
  const selected = selectedId ? atlas.nodeLookup.get(selectedId) : undefined;
  const modeEdges = mode === "all"
    ? [...atlas.edges, ...atlas.correlations]
    : mode === "correlation"
      ? atlas.correlations
      : mode === "evidence"
        ? atlas.edges
        : atlas.edges.filter(edge => edge.weight >= 2.25).slice(0, 28);
  const selectedEdges = selected ? modeEdges.filter(edge => edge.source === selected.id || edge.target === selected.id) : [];
  const visibleEdges = selected ? selectedEdges : modeEdges;
  const focusedIds = new Set(selected ? [selected.id, ...selectedEdges.flatMap(edge => [edge.source, edge.target])] : atlas.nodes.map(node => node.id));
  const selectedGrade = selected?.type === "Skill" ? atlas.grades.find(item => item.node.id === selected.id) : null;
  const averageScore = atlas.grades.length ? Math.round(atlas.grades.reduce((sum, item) => sum + item.score, 0) / atlas.grades.length) : 0;
  const related = selected ? uniqueNodes(selectedEdges.map(edge => edge.source === selected.id ? atlas.nodeLookup.get(edge.target) : atlas.nodeLookup.get(edge.source))) : [...atlas.projects.slice(0, 4), ...atlas.skills.slice(0, 5)];
  const strongestSkill = atlas.grades[0];
  const relationDensity = atlas.nodes.length ? Math.round((atlas.edges.length / atlas.nodes.length) * 10) / 10 : 0;
  const clampPanToView = (nextPan: { x: number; y: number }, nextZoom = zoom) => {
    const stage = stageRef.current;
    if (!stage) return nextPan;
    const viewWidth = stage.clientWidth;
    const viewHeight = stage.clientHeight;
    const scaledWidth = ATLAS_VIEWPORT_WIDTH * nextZoom;
    const scaledHeight = atlas.height * nextZoom;
    const edgePeekX = Math.min(90, viewWidth * 0.18);
    const edgePeekY = Math.min(80, viewHeight * 0.18);
    const clampAxis = (value: number, viewSize: number, contentSize: number, edgePeek: number) => {
      if (contentSize <= viewSize) return (viewSize - contentSize) / 2;
      const min = viewSize - contentSize - edgePeek;
      const max = edgePeek;
      return clamp(value, min, max);
    };
    return {
      x: clampAxis(nextPan.x, viewWidth, scaledWidth, edgePeekX),
      y: clampAxis(nextPan.y, viewHeight, scaledHeight, edgePeekY),
    };
  };
  const zoomAtClientPoint = (clientX: number, clientY: number, nextZoom: number) => {
    const stage = stageRef.current;
    if (!stage || nextZoom === zoom) return;
    const rect = stage.getBoundingClientRect();
    const cursorX = clientX ? clientX - rect.left : rect.width / 2;
    const cursorY = clientY ? clientY - rect.top : rect.height / 2;
    const worldX = (cursorX - pan.x) / zoom;
    const worldY = (cursorY - pan.y) / zoom;
    setZoom(nextZoom);
    setPan(clampPanToView({ x: cursorX - worldX * nextZoom, y: cursorY - worldY * nextZoom }, nextZoom));
  };
  useEffect(() => {
    setPan(value => clampPanToView(value, zoom));
  }, [atlas.height, zoom]);
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return undefined;
    const wheelScale = (event: globalThis.WheelEvent) => event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? stage.clientHeight : 1;
    const eventIsInsideAtlas = (event: globalThis.WheelEvent) => {
      if (event.target instanceof Node && stage.contains(event.target)) return true;
      const rect = stage.getBoundingClientRect();
      return (
        atlasHoverRef.current &&
        event.clientX >= rect.left &&
        event.clientX <= rect.right &&
        event.clientY >= rect.top &&
        event.clientY <= rect.bottom
      );
    };
    const handleAtlasWheel = (event: globalThis.WheelEvent) => {
      if (!eventIsInsideAtlas(event)) return;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      const scale = wheelScale(event);
      const delta = (Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX) * scale;
      const zoomSpeed = event.ctrlKey || event.metaKey ? 0.0016 : 0.0011;
      const nextZoom = clamp(Number((zoom - delta * zoomSpeed).toFixed(2)), 0.65, 1.9);
      zoomAtClientPoint(event.clientX, event.clientY, nextZoom);
    };
    const handleGestureStart = (event: Event) => {
      const gesture = event as GestureLikeEvent;
      const rect = stage.getBoundingClientRect();
      const clientX = gesture.clientX || rect.left + rect.width / 2;
      const clientY = gesture.clientY || rect.top + rect.height / 2;
      if (
        !atlasHoverRef.current &&
        (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom)
      ) return;
      event.preventDefault();
      event.stopPropagation();
      gestureRef.current = { active: true, scale: gesture.scale || 1, zoom, clientX, clientY };
    };
    const handleGestureChange = (event: Event) => {
      if (!gestureRef.current.active) return;
      const gesture = event as GestureLikeEvent;
      event.preventDefault();
      event.stopPropagation();
      const baseScale = gestureRef.current.scale || 1;
      const nextZoom = clamp(Number((gestureRef.current.zoom * ((gesture.scale || 1) / baseScale)).toFixed(2)), 0.65, 1.9);
      zoomAtClientPoint(gesture.clientX || gestureRef.current.clientX, gesture.clientY || gestureRef.current.clientY, nextZoom);
    };
    const handleGestureEnd = () => {
      gestureRef.current.active = false;
    };
    const handleViewportResize = () => {
      const viewport = window.visualViewport;
      if (!viewport || !atlasHoverRef.current) return;
      const scale = viewport.scale || 1;
      if (Math.abs(scale - viewportPinchRef.current.scale) < 0.015) return;
      const rect = stage.getBoundingClientRect();
      if (Math.abs(viewportPinchRef.current.scale - 1) < 0.015) viewportPinchRef.current.zoom = zoom;
      const nextZoom = clamp(Number((viewportPinchRef.current.zoom * scale).toFixed(2)), 0.65, 1.9);
      zoomAtClientPoint(rect.left + rect.width / 2, rect.top + rect.height / 2, nextZoom);
      viewportPinchRef.current.scale = scale;
    };
    window.addEventListener("wheel", handleAtlasWheel, { passive: false, capture: true });
    window.addEventListener("gesturestart", handleGestureStart, { passive: false, capture: true });
    window.addEventListener("gesturechange", handleGestureChange, { passive: false, capture: true });
    window.addEventListener("gestureend", handleGestureEnd, { capture: true });
    window.visualViewport?.addEventListener("resize", handleViewportResize);
    return () => {
      window.removeEventListener("wheel", handleAtlasWheel, { capture: true });
      window.removeEventListener("gesturestart", handleGestureStart, { capture: true });
      window.removeEventListener("gesturechange", handleGestureChange, { capture: true });
      window.removeEventListener("gestureend", handleGestureEnd, { capture: true });
      window.visualViewport?.removeEventListener("resize", handleViewportResize);
    };
  }, [pan.x, pan.y, zoom]);
  const handleWheelZoom = (event: ReactWheelEvent<HTMLDivElement>) => {
    if (!event.currentTarget.contains(event.target as Node)) return;
    event.preventDefault();
    event.stopPropagation();
  };
  const handlePanStart = (event: PointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    if ((event.target as Element).closest(".graph-atlas-node")) return;
    event.preventDefault();
    const stage = stageRef.current;
    if (!stage) return;
    stage.setPointerCapture(event.pointerId);
    panRef.current = { active: true, x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
    setIsPanning(true);
  };
  const handlePanMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!panRef.current.active) return;
    event.preventDefault();
    setPan({
      ...clampPanToView({
        x: panRef.current.panX + (event.clientX - panRef.current.x),
        y: panRef.current.panY + (event.clientY - panRef.current.y),
      }),
    });
  };
  const stopPan = (event?: PointerEvent<HTMLDivElement>) => {
    if (event?.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    panRef.current.active = false;
    setIsPanning(false);
  };
  const touchDistance = (touches: React.TouchList) => {
    if (touches.length < 2) return 0;
    const [first, second] = [touches[0], touches[1]];
    return Math.hypot(first.clientX - second.clientX, first.clientY - second.clientY);
  };
  const touchCenter = (touches: React.TouchList) => {
    const stage = stageRef.current;
    const rect = stage?.getBoundingClientRect();
    const [first, second] = [touches[0], touches[1]];
    const clientX = (first.clientX + second.clientX) / 2;
    const clientY = (first.clientY + second.clientY) / 2;
    return { x: rect ? clientX - rect.left : clientX, y: rect ? clientY - rect.top : clientY };
  };
  const handleTouchStart = (event: TouchEvent<HTMLDivElement>) => {
    if (event.touches.length === 2) {
      event.preventDefault();
      event.stopPropagation();
      const center = touchCenter(event.touches);
      pinchRef.current = { active: true, distance: touchDistance(event.touches), zoom, centerX: center.x, centerY: center.y, panX: pan.x, panY: pan.y };
      stopPan();
    }
  };
  const handleTouchMove = (event: TouchEvent<HTMLDivElement>) => {
    if (!pinchRef.current.active || event.touches.length !== 2) return;
    event.preventDefault();
    event.stopPropagation();
    const start = pinchRef.current.distance || 1;
    const next = clamp(Number((pinchRef.current.zoom * (touchDistance(event.touches) / start)).toFixed(2)), 0.65, 1.9);
    const worldX = (pinchRef.current.centerX - pinchRef.current.panX) / pinchRef.current.zoom;
    const worldY = (pinchRef.current.centerY - pinchRef.current.panY) / pinchRef.current.zoom;
    setZoom(next);
    setPan(clampPanToView({ x: pinchRef.current.centerX - worldX * next, y: pinchRef.current.centerY - worldY * next }, next));
  };
  const handleTouchEnd = () => {
    pinchRef.current.active = false;
  };

  return (
    <section className="card graph-studio-card" aria-labelledby="knowledge-atlas-title">
      <div className="graph-card-head graph-studio-head">
        <div>
          <span className="eyebrow">Knowledge relation atlas</span>
          <h3 id="knowledge-atlas-title">Evidence, skills, and project cohesion</h3>
          <p>Weighted ribbons show how profile projects prove skills. Select anything to reduce the scene to its actual neighborhood.</p>
        </div>
        <div className="graph-head-pills">
          <span className="pill mono">{atlas.projects.length} projects</span>
          <span className="pill mono">{atlas.skills.length} skills</span>
          <span className="pill mono">{averageScore} avg skill</span>
        </div>
      </div>
      <div className="graph-studio-toolbar">
        <div className="graph-filter-bar graph-view-switch" aria-label="Knowledge atlas view">
          {[
            ["ribbons", "Relation atlas"],
            ["gravity", "Gravity graph"],
          ].map(([id, label]) => (
            <button key={id} className={view === id ? "active" : ""} onClick={() => setView(id as AtlasView)}>{label}</button>
          ))}
        </div>
        {view === "ribbons" && (
          <>
        <div className="graph-filter-bar" aria-label="Relation atlas mode">
          {[
            ["curated", "Curated"],
            ["evidence", "Evidence"],
            ["correlation", "Correlations"],
            ["all", "All links"],
          ].map(([id, label]) => (
            <button key={id} className={mode === id ? "active" : ""} onClick={() => setMode(id as GraphMode)}>{label}</button>
          ))}
          {selected && <button onClick={() => setSelectedId("")}>Clear focus</button>}
        </div>
        <label className="graph-search-control">
          <span>Search</span>
          <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Project or skill" />
        </label>
        <label className="graph-search-control compact">
          <span>Depth</span>
          <select value={limit} onChange={event => setLimit(Number(event.target.value))}>
            <option value={12}>Clean</option>
            <option value={18}>Balanced</option>
            <option value={32}>Deep</option>
            <option value={70}>Full</option>
          </select>
        </label>
        <div className="graph-zoom-controls" aria-label="Graph zoom controls">
          <button onClick={() => setZoom(value => clamp(Number((value - 0.15).toFixed(2)), 0.65, 1.9))}>-</button>
          <input
            aria-label="Graph zoom"
            type="range"
            min="0.65"
            max="1.9"
            step="0.05"
            value={zoom}
            onChange={event => setZoom(Number(event.target.value))}
          />
          <button onClick={() => setZoom(value => clamp(Number((value + 0.15).toFixed(2)), 0.65, 1.9))}>+</button>
          <button onClick={() => {
            setZoom(1);
            setPan(clampPanToView({ x: 0, y: 0 }, 1));
          }}>Reset</button>
          <span>{Math.round(zoom * 100)}%</span>
        </div>
          </>
        )}
      </div>
      {view === "gravity" ? (
        <GravityRelationGraph stats={stats} />
      ) : (
      <>
      <div className="graph-studio-metrics" aria-label="Knowledge graph summary">
        <div>
          <span>{visibleEdges.length}</span>
          <small>{selected ? "focused links" : "visible links"}</small>
        </div>
        <div>
          <span>{atlas.correlations.length}</span>
          <small>project correlations</small>
        </div>
        <div>
          <span>{relationDensity}</span>
          <small>links per node</small>
        </div>
        <div>
          <span>{strongestSkill?.grade || "Seed"}</span>
          <small>{strongestSkill ? truncate(strongestSkill.node.label, 18) : "top skill"}</small>
        </div>
      </div>
      <div className="graph-studio-layout">
        <div
          ref={stageRef}
          className={`graph-atlas-stage ${isPanning ? "panning" : ""}`}
          onWheel={handleWheelZoom}
          onMouseEnter={() => { atlasHoverRef.current = true; }}
          onMouseLeave={() => {
            atlasHoverRef.current = false;
            stopPan();
          }}
          onPointerDown={handlePanStart}
          onPointerMove={handlePanMove}
          onPointerUp={stopPan}
          onPointerCancel={stopPan}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          onTouchCancel={handleTouchEnd}
        >
          <svg
            viewBox={`0 0 ${ATLAS_VIEWPORT_WIDTH} ${atlas.height}`}
            className="graph-atlas-svg"
            role="img"
            aria-label="Weighted graph relationship atlas"
            style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
          >
            <defs>
              <linearGradient id="evidenceRibbon" x1="0" x2="1">
                <stop offset="0%" stopColor="rgba(203, 124, 154, 0.55)" />
                <stop offset="100%" stopColor="rgba(209, 120, 71, 0.72)" />
              </linearGradient>
            </defs>
            <text x="170" y="48" textAnchor="middle" className="graph-lane-label">Proof projects</text>
            <text x="560" y="48" textAnchor="middle" className="graph-lane-label">Weighted relationships</text>
            <text x="940" y="48" textAnchor="middle" className="graph-lane-label">Skills and clusters</text>
            {visibleEdges.map((edge, index) => {
              const source = atlas.nodeLookup.get(edge.source);
              const target = atlas.nodeLookup.get(edge.target);
              if (!source || !target) return null;
              const active = !selected || edge.source === selected.id || edge.target === selected.id;
              return (
                <g key={`${edge.source}-${edge.target}-${edge.kind}-${index}`} className={`graph-atlas-edge ${edge.kind} ${active ? "active" : "dimmed"}`}>
                  <path d={relationPath(source, target, edge.kind)} strokeWidth={Math.min(7, 1.4 + edge.weight)} />
                  {selected && active && (
                    <text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 8} textAnchor="middle" className="graph-edge-label">{edge.label}</text>
                  )}
                </g>
              );
            })}
            {atlas.nodes.map(node => {
              const isDimmed = !focusedIds.has(node.id);
              const isActive = selected?.id === node.id;
              return (
                <g
                  key={node.id}
                  className={`graph-atlas-node ${isActive ? "active" : ""} ${isDimmed ? "dimmed" : ""}`}
                  transform={`translate(${node.x},${node.y})`}
                  role="button"
                  tabIndex={0}
                  aria-label={`${node.type} ${node.label}`}
                  onClick={() => setSelectedId(isActive ? "" : node.id)}
                  onKeyDown={event => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedId(isActive ? "" : node.id);
                    }
                  }}
                >
                  <rect x={-node.w / 2} y={-node.h / 2} width={node.w} height={node.h} rx="12" fill={`var(--${node.tone}-soft)`} stroke={`var(--${node.tone})`} />
                  <circle cx={-node.w / 2 + 18} cy="0" r="5" fill={`var(--${node.tone})`} />
                  <text x={-node.w / 2 + 34} y="-4" className="graph-atlas-label">{truncate(node.label, node.type === "Project" ? 27 : 24)}</text>
                  <text x={-node.w / 2 + 34} y="12" className="graph-node-type">
                    {node.type === "Skill" ? `${node.grade} / ${node.score}` : node.type === "SkillCluster" ? `${node.subtitle}` : `${node.support} links`}
                  </text>
                </g>
              );
            })}
            {atlas.nodes.length === 0 && (
              <g>
                <text x="500" y="285" textAnchor="middle" className="graph-empty-svg">No project-skill evidence yet</text>
                <text x="500" y="313" textAnchor="middle" className="graph-empty-svg-sub">Add profile projects and skills, then refresh graph repair.</text>
              </g>
            )}
          </svg>
          <div className="graph-atlas-legend">
            <span><i className="legend-line evidence" /> Evidence link</span>
            <span><i className="legend-line correlation" /> Shared-skill correlation</span>
            <span><i className="legend-node project" /> Project</span>
            <span><i className="legend-node skill" /> Skill</span>
          </div>
        </div>
        <aside className="graph-studio-inspector">
          <div className="graph-board-subhead">
            <span className="eyebrow">Inspector</span>
            <span className="pill mono">{visibleEdges.length} links</span>
          </div>
          <h4>{selected ? selected.label : "Curated graph"}</h4>
          <p>
            {selectedGrade
              ? `Grade ${selectedGrade.grade}, score ${selectedGrade.score}/100. Backed by ${selectedGrade.projectCount} projects and ${selectedGrade.relatedCount} related skills.`
              : selected
                ? `${selected.support} evidence relationships connect this project to the profile graph.`
                : "Default mode hides noisy edges and shows the strongest evidence routes. Search or click to focus a real graph neighborhood."}
          </p>
          {selectedGrade && (
            <div className="graph-grade-meter" aria-label={`Skill score ${selectedGrade.score}`}>
              <span style={{ width: `${selectedGrade.score}%` }} />
            </div>
          )}
          <div className="graph-mini-label">Related nodes</div>
          <div className="graph-node-pick-list compact">
            {related.slice(0, 10).map(node => (
              <button key={node.id} className="graph-node-pick" onClick={() => setSelectedId(node.id)}>
                <span>{truncate(node.label, 26)}</span>
                <small>{atlas.nodeLookup.get(node.id)?.score ?? atlas.nodeLookup.get(node.id)?.support ?? node.type}</small>
              </button>
            ))}
          </div>
          {related.length === 0 && <span className="graph-chip muted">No visible neighbors in this filter</span>}
        </aside>
      </div>
      </>
      )}
    </section>
  );
}

function vectorTone(type: string) {
  return TONES[type] || "orange";
}

function graphNodePoint(node: GraphNodePayload, index: number): AtlasPoint {
  const typeSalt = node.type.split("").reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const angle = seededUnit(node.id, 211 + typeSalt) * Math.PI * 2;
  const ring = 0.22 + seededUnit(node.id, 307 + index) * 0.72;
  const vertical = (seededUnit(node.id, 419 + typeSalt) - 0.5) * 1.7;
  return {
    id: node.id,
    label: node.label,
    type: node.type,
    x: clamp(Math.cos(angle) * ring, -1, 1),
    y: clamp(Math.sin(angle) * ring * 0.74 + vertical * 0.18, -1, 1),
    z: clamp(vertical, -1, 1),
    hasVector: false,
  };
}

function profileAtlasPoints(stats: GraphStats): AtlasPoint[] {
  const vectorPoints: AtlasPoint[] = (stats.embedding?.points || [])
    .filter(point => !isBadVectorLabel(point.label))
    .map(point => ({ ...point, hasVector: true }));
  const vectorKeys = new Set(vectorPoints.flatMap(point => [
    point.id,
    `${point.type}:${point.label}`.toLowerCase(),
  ]));
  const graphNodes = (stats.graph?.nodes || [])
    .filter(node => node.type !== "JobLead" && !isBadVectorLabel(node.label));
  const fallbackPoints = graphNodes
    .filter(node => !vectorKeys.has(node.id) && !vectorKeys.has(`${node.type}:${node.label}`.toLowerCase()))
    .map((node, index) => graphNodePoint(node, index));
  return [...vectorPoints, ...fallbackPoints].slice(0, 220);
}

function projectPoint(point: EmbeddingPoint, index: number, mode: CameraMode, camera: SpatialCamera) {
  const x = Math.max(-1, Math.min(1, point.x));
  const y = Math.max(-1, Math.min(1, point.y));
  const z = Math.max(-1, Math.min(1, point.z ?? Math.sin((index + 1) * 1.618) * 0.72));
  const base = mode === "front" ? { x, y, z } : mode === "top" ? { x, y: z, z: y } : { x, y, z };
  const yaw = (mode === "orbit" ? camera.yaw : 0) * (Math.PI / 180);
  const pitch = (mode === "orbit" ? camera.pitch : 0) * (Math.PI / 180);
  const yawed = {
    x: base.x * Math.cos(yaw) - base.z * Math.sin(yaw),
    y: base.y,
    z: base.x * Math.sin(yaw) + base.z * Math.cos(yaw),
  };
  return {
    x: yawed.x,
    y: yawed.y * Math.cos(pitch) - yawed.z * Math.sin(pitch),
    z: yawed.y * Math.sin(pitch) + yawed.z * Math.cos(pitch),
  };
}

function EmbeddingAtlas({ stats }: { stats: GraphStats }) {
  const [mode, setMode] = useState<CameraMode>("orbit");
  const [selectedId, setSelectedId] = useState<string>("");
  const [camera, setCamera] = useState<SpatialCamera>({ yaw: -38, pitch: 24, zoom: 1 });
  const embeddingStageRef = useRef<HTMLDivElement | null>(null);
  const embeddingPinchRef = useRef({ active: false, distance: 0, zoom: 1 });
  const points = profileAtlasPoints(stats);
  const vectorRows = points.filter(point => point.hasVector).length;
  const graphRows = (stats.graph?.nodes || []).filter(node => node.type !== "JobLead").length;
  const selected = points.find(point => point.id === selectedId);
  const projected = points
    .map((point, index) => ({ point, projected: projectPoint(point, index, mode, camera) }))
    .sort((a, b) => a.projected.z - b.projected.z);
  const counts = points.reduce<Record<string, number>>((acc, point) => {
    acc[point.type] = (acc[point.type] || 0) + 1;
    return acc;
  }, {});
  const selectedProjected = selected ? projectPoint(selected, points.findIndex(point => point.id === selected.id), mode, camera) : null;
  const nearest = selected && selectedProjected
    ? points
        .filter(point => point.id !== selected.id)
        .map((point, index) => {
          const p = projectPoint(point, index, mode, camera);
          const distance = Math.sqrt((p.x - selectedProjected.x) ** 2 + (p.y - selectedProjected.y) ** 2 + (p.z - selectedProjected.z) ** 2);
          return { point, distance };
        })
        .sort((a, b) => a.distance - b.distance)
        .slice(0, 6)
    : points.slice(0, 6).map(point => ({ point, distance: 0 }));
  const embeddingTouchDistance = (touches: React.TouchList) => {
    if (touches.length < 2) return 0;
    const [first, second] = [touches[0], touches[1]];
    return Math.hypot(first.clientX - second.clientX, first.clientY - second.clientY);
  };
  const rotateEmbedding = (deltaX: number, deltaY: number) => {
    if (mode !== "orbit") return;
    setCamera(value => ({
      ...value,
      yaw: normalizeAngle(value.yaw + deltaX * 0.28),
      pitch: normalizeAngle(value.pitch - deltaY * 0.22),
    }));
  };
  const handleEmbeddingWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    if (!event.currentTarget.contains(event.target as Node)) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.ctrlKey) {
      setCamera(value => ({ ...value, zoom: clamp(Number((value.zoom - event.deltaY * 0.0011).toFixed(2)), 0.65, 2.2) }));
      return;
    }
    rotateEmbedding(event.deltaX, event.deltaY);
  };
  const handleEmbeddingTouchStart = (event: TouchEvent<HTMLDivElement>) => {
    if (event.touches.length === 2) {
      event.stopPropagation();
      embeddingPinchRef.current = { active: true, distance: embeddingTouchDistance(event.touches), zoom: camera.zoom };
    }
  };
  const handleEmbeddingTouchMove = (event: TouchEvent<HTMLDivElement>) => {
    if (event.touches.length !== 2) return;
    event.preventDefault();
    event.stopPropagation();
    const distance = embeddingTouchDistance(event.touches);
    const start = embeddingPinchRef.current.distance || distance || 1;
    if (embeddingPinchRef.current.active && Math.abs(distance - start) > 8) {
      setCamera(value => ({ ...value, zoom: clamp(Number((embeddingPinchRef.current.zoom * (distance / start)).toFixed(2)), 0.65, 2.2) }));
      return;
    }
    const first = event.touches[0];
    const second = event.touches[1];
    const midpointX = (first.clientX + second.clientX) / 2;
    const midpointY = (first.clientY + second.clientY) / 2;
    const previous = embeddingStageRef.current?.dataset;
    const lastX = Number(previous?.touchX || midpointX);
    const lastY = Number(previous?.touchY || midpointY);
    rotateEmbedding(midpointX - lastX, midpointY - lastY);
    if (previous) {
      previous.touchX = String(midpointX);
      previous.touchY = String(midpointY);
    }
  };
  const handleEmbeddingTouchEnd = () => {
    embeddingPinchRef.current.active = false;
    if (embeddingStageRef.current?.dataset) {
      delete embeddingStageRef.current.dataset.touchX;
      delete embeddingStageRef.current.dataset.touchY;
    }
  };

  return (
    <section className="card graph-embedding-atlas-card" aria-labelledby="embedding-atlas-title">
      <div className="graph-card-head graph-studio-head">
        <div>
          <span className="eyebrow">Profile atlas</span>
          <h3 id="embedding-atlas-title">Profile space</h3>
          <p>Every profile graph entity is shown. Items with vectors use embedding coordinates; missing vectors get stable graph positions.</p>
        </div>
        <div className="graph-head-pills">
          <span className="pill mono">{points.length} items</span>
          <span className="pill mono">{vectorRows} vectors</span>
          <span className="pill mono">{mode}</span>
        </div>
      </div>
      <div className="graph-studio-toolbar">
        <div className="graph-filter-bar" aria-label="Embedding camera">
          {[
            ["orbit", "3D orbit"],
            ["front", "2D map"],
            ["top", "Depth map"],
          ].map(([id, label]) => (
            <button key={id} className={mode === id ? "active" : ""} onClick={() => setMode(id as CameraMode)}>{label}</button>
          ))}
        </div>
        <div className="graph-zoom-controls" aria-label="Embedding zoom controls">
          <button onClick={() => setCamera(value => ({ ...value, zoom: clamp(Number((value.zoom - 0.15).toFixed(2)), 0.65, 2.2) }))}>-</button>
          <input
            aria-label="Embedding zoom"
            type="range"
            min="0.65"
            max="2.2"
            step="0.05"
            value={camera.zoom}
            onChange={event => setCamera(value => ({ ...value, zoom: Number(event.target.value) }))}
          />
          <button onClick={() => setCamera(value => ({ ...value, zoom: clamp(Number((value.zoom + 0.15).toFixed(2)), 0.65, 2.2) }))}>+</button>
          <button onClick={() => setCamera({ yaw: -38, pitch: 24, zoom: 1 })}>Reset</button>
          <span>{Math.round(camera.zoom * 100)}%</span>
        </div>
        {mode === "orbit" && (
          <div className="graph-rotation-controls" aria-label="3D rotation controls">
            <label>
              <span>Yaw</span>
              <input type="range" min="-180" max="180" step="2" value={camera.yaw} onChange={event => setCamera(value => ({ ...value, yaw: Number(event.target.value) }))} />
            </label>
            <label>
              <span>Pitch</span>
              <input type="range" min="-180" max="180" step="2" value={camera.pitch} onChange={event => setCamera(value => ({ ...value, pitch: Number(event.target.value) }))} />
            </label>
          </div>
        )}
      </div>
      <div className="graph-studio-metrics" aria-label="Embedding summary">
        <div>
          <span>{points.length}</span>
          <small>profile items</small>
        </div>
        <div>
          <span>{vectorRows}</span>
          <small>vector-backed</small>
        </div>
        <div>
          <span>{Object.keys(counts).length}</span>
          <small>entity groups</small>
        </div>
        <div>
          <span>{graphRows}</span>
          <small>graph rows</small>
        </div>
      </div>
      <div className="graph-embedding-atlas-layout">
        <div
          ref={embeddingStageRef}
          className="graph-embedding-stage graph-embedding-stage-interactive"
          onWheel={handleEmbeddingWheel}
          onTouchStart={handleEmbeddingTouchStart}
          onTouchMove={handleEmbeddingTouchMove}
          onTouchEnd={handleEmbeddingTouchEnd}
          onTouchCancel={handleEmbeddingTouchEnd}
        >
          {points.length > 0 ? (
            <svg viewBox="0 0 920 520" className="graph-embedding-atlas-svg" role="img" aria-label="Profile graph and vector projection">
              <defs>
                <radialGradient id="embeddingGlow">
                  <stop offset="0%" stopColor="rgba(255,255,255,0.95)" />
                  <stop offset="100%" stopColor="rgba(244,239,230,0.25)" />
                </radialGradient>
              </defs>
              <ellipse cx="460" cy="260" rx="330" ry="170" className="graph-embedding-orbit" />
              <line x1="130" y1="260" x2="790" y2="260" className="graph-embedding-axis" />
              <line x1="460" y1="84" x2="460" y2="436" className="graph-embedding-axis" />
              <circle cx="460" cy="260" r="112" className="graph-embedding-core" />
              {projected.map(({ point, projected: p }) => {
                const tone = vectorTone(point.type);
                const perspective = 1 + p.z * 0.18;
                const px = 460 + p.x * 310 * camera.zoom * perspective;
                const py = 260 + p.y * 170 * camera.zoom * perspective;
                const depth = (p.z + 1) / 2;
                const radius = (4.5 + depth * 7) * (0.82 + camera.zoom * 0.18);
                const active = point.id === selected?.id;
                return (
                  <g
                    key={`${point.type}-${point.id}`}
                    className={`graph-embedding-point ${active ? "active" : ""} ${point.hasVector ? "vector-backed" : "graph-backed"}`}
                    transform={`translate(${px},${py})`}
                    role="button"
                    tabIndex={0}
                    aria-label={`${point.type} ${point.hasVector ? "vector" : "profile item"} ${point.label}`}
                    onClick={() => setSelectedId(active ? "" : point.id)}
                    onKeyDown={event => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelectedId(active ? "" : point.id);
                      }
                    }}
                  >
                    <circle r={radius + 7} fill={`var(--${tone}-soft)`} opacity={0.15 + depth * 0.25} />
                    <circle
                      r={radius}
                      fill={`var(--${tone})`}
                      stroke={`var(--${tone}-ink)`}
                      strokeWidth={active ? 2.6 : 1.4}
                    >
                      <title>{`${point.label} (${point.type}${point.hasVector ? ", vector-backed" : ", graph-only"})`}</title>
                    </circle>
                    {active && (
                      <>
                        <line x1={0} y1={0} x2="42" y2="-24" className="graph-embedding-callout-line" />
                        <rect x="42" y="-42" width="170" height="32" rx="9" className="graph-embedding-callout" />
                        <text x="54" y="-23" className="graph-atlas-label">{truncate(point.label, 22)}</text>
                      </>
                    )}
                  </g>
                );
              })}
            </svg>
          ) : (
            <div className="graph-vector-empty compact">
              <strong>No vector rows yet</strong>
              <span>No profile graph items are available yet. Add profile context or run graph repair.</span>
            </div>
          )}
        </div>
        <aside className="graph-studio-inspector">
          <div className="graph-board-subhead">
            <span className="eyebrow">Profile focus</span>
            <span className="pill mono">{Object.keys(counts).length} groups</span>
          </div>
          <h4>{selected ? selected.label : "Profile atlas"}</h4>
          <p>{selected ? `${selected.type} profile item${selected.hasVector ? " with a local vector row." : " without a vector yet, placed from the graph."}` : points.length ? "Select a point to inspect nearby visible profile evidence and entity group." : "No profile graph items are available yet."}</p>
          <div className="graph-mini-label">Nearest visible profile items</div>
          <div className="graph-node-pick-list compact">
            {nearest.map(({ point }) => (
              <button key={point.id} className="graph-node-pick" onClick={() => setSelectedId(point.id)}>
                <span>{truncate(point.label, 26)}</span>
                <small>{point.hasVector ? point.type : `${point.type} · graph`}</small>
              </button>
            ))}
          </div>
          <div className="graph-mini-label">Groups</div>
          <div className="graph-legend stacked">
            {Object.entries(counts).map(([type, count]) => (
              <span key={type}><i className={`legend-dot ${type.toLowerCase()}`} /> {type}<b>{count}</b></span>
            ))}
          </div>
        </aside>
      </div>
    </section>
  );
}

export function GraphView({ stats }: { stats: GraphStats }) {
  const hasGraphPayload = Array.isArray(stats.graph?.nodes);
  const total = stats.graph?.nodes.length ?? 0;
  const relationCount = stats.graph?.edges.length ?? 0;
  const vectorCount = stats.embedding?.points.length ?? 0;
  const isLoading = Boolean(stats.loading && !stats.loaded);
  const requestError = stats.request_error || "";
  const isLive = stats.status === "live" && stats.available !== false && hasGraphPayload && !requestError;
  const syncedAt = stats.sync?.refreshed_at ? new Date(stats.sync.refreshed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";

  return (
    <div className="scroll graph-page">
      <div className="graph-shell graph-shell-single">
        <div className="card graph-overview graph-overview-sleek">
          <div className="graph-overview-copy">
            <span className="eyebrow">Knowledge Studio</span>
            <h1 style={{ fontSize: 34 }}>Knowledge Graph</h1>
            <p>Market-style graph exploration: clustered relations, focused neighborhoods, and real local embedding projections.</p>
          </div>
          <div className="graph-overview-stats">
            <div>
              <span className="eyebrow">Total nodes</span>
              <div className="display tabular graph-total">{total}</div>
            </div>
            <div className="graph-mini-stats">
              <div><span>{relationCount}</span><small>Relations</small></div>
              <div><span>{vectorCount}</span><small>Vectors</small></div>
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
              {isLive ? "live" : isLoading ? "loading" : requestError ? "request failed" : hasGraphPayload ? "degraded" : "no graph payload"}
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

        <KnowledgeRelationAtlas stats={stats} />
        <EmbeddingAtlas stats={stats} />
      </div>
    </div>
  );
}
