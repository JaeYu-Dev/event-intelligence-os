"use client";

import { useMemo, useState, useCallback, useRef } from "react";
import {
  Maximize2, Minimize2, MousePointer2, GitBranch, Layers,
  Info, ArrowRight, TrendingUp, TrendingDown, Minus, AlertTriangle,
  FileText, DollarSign, Briefcase, Clock, Activity, Shield,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types (matching backend causal_path.py output)
// ---------------------------------------------------------------------------

export interface CausalNode {
  node_id: string;
  node_type: "root_event" | "mechanism" | "latent_factor" | "entity" | "instrument" | "confirmation" | "risk";
  label_ko: string;
  label_en?: string;
  description_ko: string;
  evidence_grade: string;
  probability: number;
  evidence_items?: { type: string; text: string }[];
  market_data?: { symbol: string; change: string; period?: string }[];
  counterevidence?: string[];
  metadata?: any;
}

export interface CausalEdge {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  relation_type: string;
  label_ko: string;
  label_en?: string;
  evidence_grade: string;
  strength: number;
  mechanism_detail?: string;
  source_refs?: string[];
}

export interface InterventionItem {
  id: string;
  label: string;
  type: "ticker" | "actor" | "risk" | "evidence" | "market" | "calendar" | "polymarket" | "analyst" | "regime" | "sensor";
  value?: string;
  icon?: any;
  color?: string;
  strength?: number;
}

interface CausalGraphProps {
  nodes: CausalNode[];
  edges: CausalEdge[];
  interventions?: Record<string, InterventionItem[]>;
  selectedNodeId: string | null;
  hoveredNodeId: string | null;
  onSelectNode: (id: string | null) => void;
  onHoverNode: (id: string | null) => void;
  onSelectEdge?: (edge: CausalEdge | null) => void;
  asOfTime?: string;
}

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const NODE_CFG: Record<CausalNode["node_type"], { color: string; shape: "circle" | "diamond" | "rect" | "pill"; label: string }> = {
  root_event: { color: "#e16a2e", shape: "rect", label: "루트 사건" },
  mechanism: { color: "#a371f7", shape: "diamond", label: "메커니즘" },
  latent_factor: { color: "#58a6ff", shape: "circle", label: "잠재 요인" },
  entity: { color: "#3fb950", shape: "rect", label: "영향 대상" },
  instrument: { color: "#d29922", shape: "pill", label: "거래 대상" },
  confirmation: { color: "#8b949e", shape: "circle", label: "확인/무효화" },
  risk: { color: "#d73a49", shape: "diamond", label: "리스크" },
};

const EVIDENCE_COLORS: Record<string, string> = {
  E4: "#3fb950",
  E3: "#58a6ff",
  E2: "#d29922",
  E1: "#f0883e",
  E0: "#8b949e",
};

const INTERVENTION_ICON: Record<string, any> = {
  ticker: DollarSign,
  actor: Briefcase,
  risk: AlertTriangle,
  evidence: FileText,
  market: Activity,
  calendar: Clock,
  polymarket: TrendingUp,
  analyst: Activity,
  regime: Shield,
  sensor: Activity,
};

// ---------------------------------------------------------------------------
// Layout engine
// ---------------------------------------------------------------------------

type GraphLayout = "flow" | "radial" | "compact";

interface LayoutNode extends CausalNode {
  x: number;
  y: number;
  width: number;
  height: number;
  ix: number;
}

interface LayoutIntervention {
  id: string;
  item: InterventionItem;
  hostId: string;
  x: number;
  y: number;
  angle: number;
}

function computeLayout(
  nodes: CausalNode[],
  edges: CausalEdge[],
  interventions: Record<string, InterventionItem[]>,
  layout: GraphLayout,
  width: number,
  height: number,
): { mainNodes: LayoutNode[]; interventions: LayoutIntervention[]; edgeBundles: CausalEdge[] } {
  const mainNodes: LayoutNode[] = [];
  const interventionItems: LayoutIntervention[] = [];

  if (nodes.length === 0) return { mainNodes, interventions: interventionItems, edgeBundles: edges };

  const marginX = 120;
  const marginY = 110;
  const usableW = width - marginX * 2;
  const usableH = height - marginY * 2;

  if (layout === "radial") {
    const cx = width / 2;
    const cy = height / 2;
    const radius = Math.min(usableW, usableH) * 0.38;
    nodes.forEach((n, i) => {
      const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2 - Math.PI / 2;
      mainNodes.push({
        ...n,
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius,
        width: 120,
        height: 52,
        ix: i,
      });
    });
  } else if (layout === "compact") {
    const cols = Math.ceil(nodes.length / 2);
    const stepX = usableW / Math.max(cols, 1);
    nodes.forEach((n, i) => {
      const row = i % 2;
      const col = Math.floor(i / 2);
      mainNodes.push({
        ...n,
        x: marginX + col * stepX + stepX / 2,
        y: row === 0 ? height * 0.35 : height * 0.65,
        width: 110,
        height: 48,
        ix: i,
      });
    });
  } else {
    const stepX = usableW / Math.max(nodes.length - 1, 1);
    const centerY = height / 2;
    nodes.forEach((n, i) => {
      mainNodes.push({
        ...n,
        x: marginX + i * stepX,
        y: centerY,
        width: 132,
        height: 64,
        ix: i,
      });
    });
  }

  mainNodes.forEach((host) => {
    const items = (interventions[host.node_id] || []).slice(0, 8);
    if (items.length === 0) return;
    const orbitR = layout === "flow" ? 82 : 64;
    items.forEach((it, idx) => {
      let angle: number;
      if (layout === "flow") {
        const side = idx % 2 === 0 ? -1 : 1;
        const offset = Math.PI / 6 + ((idx / 2) * Math.PI) / Math.max(items.length / 2, 1);
        angle = side * offset;
      } else {
        angle = (idx / Math.max(items.length, 1)) * Math.PI * 2 - Math.PI / 2;
      }
      interventionItems.push({
        id: it.id,
        item: it,
        hostId: host.node_id,
        x: host.x + Math.cos(angle) * orbitR,
        y: host.y + Math.sin(angle) * orbitR,
        angle,
      });
    });
  });

  return { mainNodes, interventions: interventionItems, edgeBundles: edges };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CausalGraph({
  nodes,
  edges,
  interventions = {},
  selectedNodeId,
  hoveredNodeId,
  onSelectNode,
  onHoverNode,
  onSelectEdge,
  asOfTime,
}: CausalGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [layout, setLayout] = useState<GraphLayout>("flow");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [showInterventions, setShowInterventions] = useState(true);

  const width = 1100;
  const height = 520;

  const { mainNodes, interventions: ivItems } = useMemo(
    () => computeLayout(nodes, edges, interventions, layout, width, height),
    [nodes, edges, interventions, layout]
  );

  const nodeMap = useMemo(() => new Map(mainNodes.map((n) => [n.node_id, n])), [mainNodes]);
  const edgeMap = useMemo(() => new Map(edges.map((e) => [e.edge_id, e])), [edges]);

  const handleSvgMouseDown = useCallback((e: React.MouseEvent) => {
    if ((e.target as Element).tagName === "svg") {
      setDragging(true);
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    }
  }, [pan]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (dragging) {
      setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
    }
  }, [dragging, dragStart]);

  const handleMouseUp = useCallback(() => setDragging(false), []);

  const resetView = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  const selectedEdge = selectedEdgeId ? edgeMap.get(selectedEdgeId) || null : null;
  const hoveredEdge = hoveredEdgeId ? edgeMap.get(hoveredEdgeId) || null : null;
  const activeEdge = hoveredEdge || selectedEdge;

  return (
    <div className="relative w-full h-full bg-[#0d1016] overflow-hidden flex flex-col">
      {/* Toolbar */}
      <div className="flex-shrink-0 h-11 bg-panel border-b border-border px-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <LayoutButton layout={layout} value="flow" icon={ArrowRight} label="흐름" onClick={setLayout} />
          <LayoutButton layout={layout} value="radial" icon={GitBranch} label="방사" onClick={setLayout} />
          <LayoutButton layout={layout} value="compact" icon={Layers} label="紧凑" onClick={setLayout} />
          <span className="w-px h-4 bg-border mx-1" />
          <button onClick={() => setShowInterventions((v) => !v)} className={`px-2 py-1 rounded text-[10px] border ${showInterventions ? "bg-accent/15 border-accent/40 text-accent" : "border-border text-muted hover:text-foreground"}`}>개입 변수</button>
        </div>
        <div className="flex items-center gap-2">
          {asOfTime && <span className="text-[10px] text-muted">as-of {new Date(asOfTime).toLocaleDateString("ko-KR")}</span>}
          <button onClick={() => setZoom((z) => Math.min(z * 1.15, 3))} className="p-1 rounded hover:bg-panel-hover text-muted"><Maximize2 className="w-3.5 h-3.5" /></button>
          <button onClick={() => setZoom((z) => Math.max(z / 1.15, 0.4))} className="p-1 rounded hover:bg-panel-hover text-muted"><Minimize2 className="w-3.5 h-3.5" /></button>
          <button onClick={resetView} className="px-2 py-1 rounded text-[10px] border border-border text-muted hover:text-foreground">리셋</button>
        </div>
      </div>

      {/* Graph area */}
      <div className="flex-1 relative cursor-grab active:cursor-grabbing">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${width} ${height}`}
          className="absolute inset-0 w-full h-full"
          preserveAspectRatio="xMidYMid meet"
          onMouseDown={handleSvgMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          <defs>
            <marker id="arrowhead-main" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="#8b949e" />
            </marker>
            <marker id="arrowhead-accent" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="#e16a2e" />
            </marker>
          </defs>

          <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
            {/* Causal river background */}
            {layout === "flow" && mainNodes.length > 1 && (
              <path
                d={`M ${mainNodes[0].x} ${mainNodes[0].y} ${mainNodes.slice(1).map((n) => `L ${n.x} ${n.y}`).join(" ")}`}
                fill="none"
                stroke="#30363d"
                strokeWidth="18"
                strokeLinecap="round"
                strokeLinejoin="round"
                opacity="0.35"
              />
            )}

            {/* Edges between main nodes */}
            {edges.map((edge) => {
              const src = nodeMap.get(edge.source_node_id);
              const tgt = nodeMap.get(edge.target_node_id);
              if (!src || !tgt) return null;
              const isHovered = hoveredEdgeId === edge.edge_id;
              const isSelected = selectedEdgeId === edge.edge_id;
              const isDimmed = activeEdge && activeEdge.edge_id !== edge.edge_id;
              const strokeWidth = 1.2 + edge.strength * 0.25;
              const color = isHovered || isSelected ? "#e16a2e" : "#8b949e";

              const dx = tgt.x - src.x;
              const dy = tgt.y - src.y;
              const dist = Math.sqrt(dx * dx + dy * dy) || 1;
              const offSrc = nodeAnchor(src, tgt, layout);
              const offTgt = nodeAnchor(tgt, src, layout);
              const x1 = src.x + (dx / dist) * offSrc;
              const y1 = src.y + (dy / dist) * offSrc;
              const x2 = tgt.x - (dx / dist) * offTgt;
              const y2 = tgt.y - (dy / dist) * offTgt;
              const midX = (x1 + x2) / 2 + (layout === "flow" ? 0 : (y1 - y2) * 0.12);
              const midY = (y1 + y2) / 2 + (layout === "flow" ? 0 : (x2 - x1) * 0.12);
              const d = layout === "flow"
                ? `M${x1},${y1} C${midX},${src.y} ${midX},${tgt.y} ${x2},${y2}`
                : `M${x1},${y1} Q${midX},${midY} ${x2},${y2}`;

              return (
                <g key={edge.edge_id} opacity={isDimmed ? 0.12 : 1} className="cursor-pointer">
                  <path
                    d={d}
                    fill="none"
                    stroke={color}
                    strokeWidth={isHovered || isSelected ? strokeWidth + 1.2 : strokeWidth}
                    strokeDasharray={edge.evidence_grade === "E0" ? "4,4" : undefined}
                    markerEnd={isHovered || isSelected ? "url(#arrowhead-accent)" : "url(#arrowhead-main)"}
                    onMouseEnter={() => setHoveredEdgeId(edge.edge_id)}
                    onMouseLeave={() => setHoveredEdgeId(null)}
                    onClick={(e) => {
                      e.stopPropagation();
                      const next = selectedEdgeId === edge.edge_id ? null : edge;
                      setSelectedEdgeId(next?.edge_id || null);
                      onSelectEdge?.(next);
                    }}
                  />
                  {/* Edge label badge */}
                  <g transform={`translate(${midX}, ${midY})`}>
                    <rect x={-48} y={-10} width={96} height={18} rx={9} fill="#181b22" stroke="#2d333b" />
                    <text x={0} y={4} textAnchor="middle" fill="#c9d1d9" fontSize="9" fontWeight={500}>
                      {edge.label_ko.length > 16 ? edge.label_ko.slice(0, 16) + "…" : edge.label_ko}
                    </text>
                  </g>
                </g>
              );
            })}

            {/* Intervention bubbles */}
            {showInterventions && ivItems.map((iv) => {
              const host = nodeMap.get(iv.hostId);
              if (!host) return null;
              const isHostActive = hoveredNodeId === iv.hostId || selectedNodeId === iv.hostId;
              const Icon = iv.item.icon || INTERVENTION_ICON[iv.item.type] || Info;
              const color = iv.item.color || "#8b949e";
              return (
                <g key={iv.id} transform={`translate(${iv.x}, ${iv.y})`} opacity={isHostActive ? 1 : 0.75} className="cursor-pointer">
                  {/* Dotted link to host */}
                  <line x1={0} y1={0} x2={host.x - iv.x} y2={host.y - iv.y} stroke={`${color}40`} strokeWidth={1} strokeDasharray="2,2" />
                  <circle r={10} fill="#0d1016" stroke={`${color}80`} strokeWidth={1.5} />
                  <foreignObject x={-8} y={-8} width={16} height={16}>
                    <div className="flex items-center justify-center w-4 h-4" style={{ color }}>
                      <Icon className="w-2.5 h-2.5" />
                    </div>
                  </foreignObject>
                  <text y={18} textAnchor="middle" fill="#c9d1d9" fontSize="8" fontWeight={500}>
                    {iv.item.label.length > 10 ? iv.item.label.slice(0, 10) + "…" : iv.item.label}
                  </text>
                  <title>{iv.item.type}: {iv.item.value || iv.item.label}</title>
                </g>
              );
            })}

            {/* Main nodes */}
            {mainNodes.map((node) => {
              const cfg = NODE_CFG[node.node_type] || NODE_CFG.root_event;
              const isSelected = selectedNodeId === node.node_id;
              const isHovered = hoveredNodeId === node.node_id;
              const gradeColor = EVIDENCE_COLORS[node.evidence_grade] || "#8b949e";
              const dimOthers = (hoveredNodeId || selectedNodeId) && !isHovered && !isSelected;

              return (
                <g
                  key={node.node_id}
                  transform={`translate(${node.x}, ${node.y})`}
                  opacity={dimOthers ? 0.35 : 1}
                  className="cursor-pointer"
                  onMouseEnter={() => onHoverNode(node.node_id)}
                  onMouseLeave={() => onHoverNode(null)}
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectNode(isSelected ? null : node.node_id);
                  }}
                >
                  {/* Glow ring on active */}
                  {(isSelected || isHovered) && (
                    <circle r={46} fill="none" stroke={cfg.color} strokeWidth={1} strokeOpacity={0.25} strokeDasharray="4,4" />
                  )}
                  {/* Evidence grade ring */}
                  <circle r={40} fill="none" stroke={gradeColor} strokeWidth={2} strokeOpacity={0.6} />
                  {/* Main shape */}
                  {cfg.shape === "circle" && (
                    <circle r={34} fill="#181b22" stroke={cfg.color} strokeWidth={2} />
                  )}
                  {cfg.shape === "diamond" && (
                    <polygon points="0,-36 36,0 0,36 -36,0" fill="#181b22" stroke={cfg.color} strokeWidth={2} />
                  )}
                  {cfg.shape === "rect" && (
                    <rect x={-48} y={-32} width={96} height={64} rx={8} fill="#181b22" stroke={cfg.color} strokeWidth={2} />
                  )}
                  {cfg.shape === "pill" && (
                    <rect x={-56} y={-24} width={112} height={48} rx={24} fill="#181b22" stroke={cfg.color} strokeWidth={2} />
                  )}
                  {/* Type icon / label */}
                  <text y={-8} textAnchor="middle" fill="#8b949e" fontSize="8" fontWeight={600}>{cfg.label}</text>
                  <text y={6} textAnchor="middle" fill="#f0f6fc" fontSize="10" fontWeight={600}>
                    {node.label_ko.length > 12 ? node.label_ko.slice(0, 12) + "…" : node.label_ko}
                  </text>
                  <text y={20} textAnchor="middle" fill={gradeColor} fontSize="9" fontWeight={600}>{node.evidence_grade} · {(node.probability * 100).toFixed(0)}%</text>
                </g>
              );
            })}
          </g>
        </svg>

        {/* Floating legend */}
        <div className="absolute bottom-3 left-3 bg-panel/95 backdrop-blur border border-border rounded-md p-2.5 text-[10px] max-w-[180px]">
          <div className="font-medium text-foreground mb-1.5">노드 유형</div>
          <div className="space-y-1 text-muted">
            {Object.entries(NODE_CFG).map(([key, cfg]) => (
              <div key={key} className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: cfg.color }} />
                {cfg.label}
              </div>
            ))}
          </div>
          <div className="mt-2 pt-2 border-t border-border">
            <div className="flex items-center gap-2">
              <MousePointer2 className="w-3 h-3" /> 노드/엣지 클릭 상세
            </div>
          </div>
        </div>
      </div>

      {/* Active edge detail panel */}
      {activeEdge && (
        <div className="absolute bottom-0 left-0 right-0 bg-panel/95 backdrop-blur border-t border-border p-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-xs text-foreground mb-1">
                <GitBranch className="w-3.5 h-3.5 text-accent" />
                <span className="font-semibold">{activeEdge.label_ko}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-panel-hover text-muted">{activeEdge.relation_type}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded text-white" style={{ backgroundColor: EVIDENCE_COLORS[activeEdge.evidence_grade] || "#8b949e" }}>{activeEdge.evidence_grade}</span>
              </div>
              {activeEdge.mechanism_detail && (
                <div className="text-[11px] text-muted leading-relaxed">{activeEdge.mechanism_detail}</div>
              )}
            </div>
            <div className="text-right text-[10px] text-muted whitespace-nowrap">
              <div>연결 강도 {activeEdge.strength.toFixed(1)}</div>
              {activeEdge.source_refs && activeEdge.source_refs.length > 0 && <div>근거 {activeEdge.source_refs.length}건</div>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function LayoutButton({
  layout, value, icon: Icon, label, onClick,
}: {
  layout: GraphLayout; value: GraphLayout; icon: any; label: string; onClick: (v: GraphLayout) => void;
}) {
  const active = layout === value;
  return (
    <button
      onClick={() => onClick(value)}
      className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] border ${active ? "bg-accent/15 border-accent/40 text-accent" : "border-border text-muted hover:text-foreground"}`}
    >
      <Icon className="w-3 h-3" /> {label}
    </button>
  );
}

function nodeAnchor(node: LayoutNode, other: LayoutNode, layout: GraphLayout): number {
  if (layout !== "flow") return 44;
  // For flow layout, use rectangle-based anchor so edges do not overlap labels
  const dx = Math.abs(other.x - node.x);
  const dy = Math.abs(other.y - node.y);
  const hw = node.width / 2;
  const hh = node.height / 2;
  if (dx === 0) return hh;
  if (dy === 0) return hw;
  const t = Math.min(hw / dx, hh / dy);
  return Math.sqrt((dx * t) ** 2 + (dy * t) ** 2);
}

export { TrendingUp, TrendingDown, Minus, AlertTriangle, FileText, DollarSign, Briefcase, Clock, Activity, Shield };
