"use client";

import { useMemo, useState } from "react";
import { Event, PortfolioPosition, CausalEdge, Scenario } from "../types";
import {
  TrendingUp, TrendingDown, Minus, ChevronDown, ChevronRight,
  AlertTriangle, Calendar, Briefcase, Target, BarChart3,
  ExternalLink, Zap, Shield, ArrowRight
} from "lucide-react";

interface UnifiedPortfolioViewProps {
  position: PortfolioPosition;
  allEvents: Event[];
  allEdges: CausalEdge[];
  onSelectEvent: (id: string) => void;
  onRunDeepScan?: () => void;
  isScanning?: boolean;
}

const NODE_COLORS: Record<string, string> = {
  policy_announcement: "#3fb950",
  filing: "#58a6ff",
  macro: "#d29922",
  regulatory: "#a371f7",
  prediction_market: "#e16a2e",
  supply_chain: "#2ea043",
};

export default function UnifiedPortfolioView({
  position,
  allEvents,
  allEdges,
  onSelectEvent,
  onRunDeepScan,
  isScanning,
}: UnifiedPortfolioViewProps) {
  const [expandedScenario, setExpandedScenario] = useState<string>("Bull");

  // Filter events linked to this position
  const linkedEvents = useMemo(() => {
    if (!position.exposureEvents) return [];
    return position.exposureEvents
      .map((eid) => allEvents.find((e) => e.id === eid))
      .filter(Boolean) as Event[];
  }, [position, allEvents]);

  const linkedIds = useMemo(() => new Set(linkedEvents.map((e) => e.id)), [linkedEvents]);

  // Filter edges relevant to linked events
  const linkedEdges = useMemo(() => {
    return allEdges.filter((e) => linkedIds.has(e.source) || linkedIds.has(e.target));
  }, [allEdges, linkedIds]);

  // Aggregate scenarios across all linked events
  const aggregateScenarios = useMemo(() => {
    const result: Scenario[] = [
      { name: "Bull", probability: 0, conditions: [], priceRange: "" },
      { name: "Base", probability: 0, conditions: [], priceRange: "" },
      { name: "Bear", probability: 0, conditions: [], priceRange: "" },
    ];

    for (const ev of linkedEvents) {
      for (const s of ev.scenarios) {
        const target = result.find((r) => r.name === s.name);
        if (target) {
          target.probability += s.probability;
          target.conditions.push(...s.conditions);
        }
      }
    }

    // Average probabilities
    const n = Math.max(linkedEvents.length, 1);
    for (const r of result) {
      r.probability /= n;
    }

    // Normalize
    const total = result.reduce((s, r) => s + r.probability, 0);
    if (total > 0) {
      for (const r of result) {
        r.probability /= total;
      }
    } else {
      result[0].probability = 0.4;
      result[1].probability = 0.38;
      result[2].probability = 0.22;
    }

    // Estimated price ranges
    const currentPrice = position.currentPrice ?? position.avgCost ?? 100;
    result[0].priceRange = `$${(currentPrice * 1.15).toFixed(1)} ~ $${(currentPrice * 1.28).toFixed(1)}`;
    result[1].priceRange = `$${(currentPrice * 1.02).toFixed(1)} ~ $${(currentPrice * 1.12).toFixed(1)}`;
    result[2].priceRange = `$${(currentPrice * 0.86).toFixed(1)} ~ $${(currentPrice * 0.94).toFixed(1)}`;

    return result;
  }, [linkedEvents, position]);

  // Build natural language causal explanation
  const causalNarrative = useMemo(() => {
    if (linkedEvents.length === 0) {
      return `${position.ticker}(${position.name})에 연결된 이벤트가 없습니다. 이벤트를 연결하려면 이벤트를 선택하고 "이 가설로 등록"을 누르세요.`;
    }

    const parts: string[] = [];
    const bearEvents = linkedEvents.filter((e) => e.status === "At Risk" || e.status === "Invalidated");
    const activeEvents = linkedEvents.filter((e) => e.status === "Active" || e.status === "Strengthening");

    parts.push(`${position.ticker}(${position.name})은 현재 ${linkedEvents.length}개의 사건과 연결되어 있습니다.`);

    if (activeEvents.length > 0) {
      const names = activeEvents.map((e) => e.titleKo).join(", ");
      parts.push(`\n\n활성 가설: ${names}.`);
    }

    if (bearEvents.length > 0) {
      const names = bearEvents.map((e) => e.titleKo).join(", ");
      parts.push(`\n\n⚠️ 위험 신호: ${names}.`);
    }

    // Add mechanism explanations
    for (const ev of linkedEvents.slice(0, 3)) {
      if (ev.mechanismKo) {
        parts.push(`\n\n📌 ${ev.titleKo} → ${ev.mechanismKo}`);
        if (ev.counterevidenceKo && ev.counterevidenceKo.length > 0) {
          parts.push(`\n   반대 증거: ${ev.counterevidenceKo[0]}`);
        }
        if (ev.nextEventsKo && ev.nextEventsKo.length > 0) {
          parts.push(`\n   다음 확인: ${ev.nextEventsKo[0]}`);
        }
      }
    }

    return parts.join("");
  }, [linkedEvents, position]);

  // Causal graph for this position
  const graphNodes = useMemo(() => {
    const nodes = [...linkedEvents];
    // Add positions that share events as related nodes
    for (const edge of linkedEdges) {
      const srcEv = allEvents.find((e) => e.id === edge.source);
      const tgtEv = allEvents.find((e) => e.id === edge.target);
      if (srcEv && !nodes.find((n) => n.id === srcEv.id)) nodes.push(srcEv);
      if (tgtEv && !nodes.find((n) => n.id === tgtEv.id)) nodes.push(tgtEv);
    }
    return nodes;
  }, [linkedEvents, linkedEdges, allEvents]);

  const plPercent = position.plPercent ?? 0;
  const plUsd = position.plUsd ?? 0;
  const currentPrice = position.currentPrice ?? position.avgCost ?? 0;

  return (
    <div className="flex flex-col h-full bg-[#0d1016] overflow-y-auto">
      {/* === TOP BAR: Position Summary === */}
      <div className="flex-shrink-0 bg-panel border-b border-border">
        <div className="flex items-center justify-between px-5 py-3">
          <div className="flex items-center gap-4">
            <div>
              <div className="text-[10px] text-accent-blue uppercase tracking-wider">{position.ticker}</div>
              <div className="text-lg font-bold text-foreground">{position.name || position.ticker}</div>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-right">
                <div className="text-[10px] text-muted uppercase">평가손익</div>
                <div className={`text-lg font-semibold ${plPercent >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                  {plPercent >= 0 ? "+" : ""}{plPercent.toFixed(1)}%
                </div>
              </div>
              <div className="text-right">
                <div className="text-[10px] text-muted uppercase">현재가</div>
                <div className="text-lg font-semibold text-foreground">
                  ${currentPrice.toFixed(1)}
                </div>
              </div>
              <div className="text-right">
                <div className="text-[10px] text-muted uppercase">보유</div>
                <div className="text-lg font-semibold text-foreground">
                  {(position.shares ?? 0).toLocaleString()}주
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
              position.scenarioBias === "Bull" ? "bg-accent-green/20 text-accent-green" :
              position.scenarioBias === "Bear" ? "bg-accent-red/20 text-accent-red" :
              "bg-panel-hover text-muted"
            }`}>
              {position.scenarioBias === "Bull" ? "▲ 강세" : position.scenarioBias === "Bear" ? "▼ 약세" : "― 중립"}
            </span>
            <button
              onClick={onRunDeepScan}
              disabled={isScanning}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-accent hover:bg-accent/90 disabled:opacity-60 text-white text-xs font-semibold transition-colors"
            >
              {isScanning ? (
                <span className="animate-pulse">스캔 중...</span>
              ) : (
                <>
                  <Zap className="w-3.5 h-3.5" />
                  Deep Scan
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="p-5 space-y-5">
        {/* === NATURAL LANGUAGE CAUSAL EXPLANATION === */}
        <div className="bg-panel border border-border rounded-lg p-4">
          <h3 className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-3 flex items-center gap-1.5">
            <Target className="w-3.5 h-3.5 text-accent" /> 인과관계 분석
          </h3>
          <div className="text-sm text-foreground leading-relaxed whitespace-pre-line">
            {causalNarrative}
          </div>
          {linkedEvents.length === 0 && (
            <button
              onClick={onRunDeepScan}
              className="mt-3 flex items-center gap-1.5 text-xs text-accent-blue hover:underline"
            >
              <Zap className="w-3 h-3" />
              Deep Scan으로 연결된 이벤트 찾기
            </button>
          )}
        </div>

        {/* === MAIN GRID: Graph + Scenarios === */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
          {/* Causal Graph */}
          <div className="lg:col-span-3 bg-panel border border-border rounded-lg overflow-hidden">
            <h3 className="text-[10px] font-semibold text-muted uppercase tracking-wider px-4 pt-4 mb-0 flex items-center gap-1.5">
              <Share2Icon className="w-3.5 h-3.5 text-accent" /> 인과 그래프
            </h3>
            <div className="h-[320px]">
              <MiniCausalGraph
                nodes={graphNodes}
                edges={linkedEdges}
                onSelect={onSelectEvent}
                ticker={position.ticker}
              />
            </div>
          </div>

          {/* Scenarios + Expected Return */}
          <div className="lg:col-span-2 space-y-4">
            {/* Scenarios */}
            <div className="bg-panel border border-border rounded-lg p-4">
              <h3 className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-3 flex items-center gap-1.5">
                <BarChart3 className="w-3.5 h-3.5 text-accent" /> 시나리오 & 기대수익
              </h3>
              <div className="space-y-3">
                {aggregateScenarios.map((s) => (
                  <ScenarioCard
                    key={s.name}
                    scenario={s}
                    isExpanded={expandedScenario === s.name}
                    onToggle={() => setExpandedScenario(expandedScenario === s.name ? "" : s.name)}
                  />
                ))}
              </div>

              {/* Expected return summary */}
              <div className="mt-4 pt-4 border-t border-border">
                <div className="text-[10px] text-muted uppercase mb-2">기대 수익률</div>
                <div className="flex items-center justify-between">
                  <div className="text-lg font-semibold text-foreground">
                    {(() => {
                      const bullRet = 0.21;
                      const baseRet = 0.07;
                      const bearRet = -0.10;
                      const ev =
                        aggregateScenarios[0].probability * bullRet +
                        aggregateScenarios[1].probability * baseRet +
                        aggregateScenarios[2].probability * bearRet;
                      return `${(ev * 100) >= 0 ? "+" : ""}${(ev * 100).toFixed(1)}%`;
                    })()}
                  </div>
                  <div className="text-xs text-muted">
                    거래비용 차감 전 · {linkedEvents.length}개 사건 기준
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* === Related Tickers === */}
        <div className="bg-panel border border-border rounded-lg p-4">
          <h3 className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-3 flex items-center gap-1.5">
            <Briefcase className="w-3.5 h-3.5 text-accent" /> 관련 종목 ({position.ticker} 노출 경로)
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border">
                  {["종목", "연결 사건", "영향 방향", "증거 등급", "다음 확인"].map((h) => (
                    <th key={h} className="px-3 py-2 text-[10px] font-semibold text-muted uppercase">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {linkedEvents.map((ev) => (
                  <tr
                    key={ev.id}
                    className="border-b border-border hover:bg-panel-hover cursor-pointer transition-colors"
                    onClick={() => onSelectEvent(ev.id)}
                  >
                    <td className="px-3 py-2">
                      <div className="text-xs font-medium text-foreground">
                        {ev.relatedTickers.filter((t) => t !== position.ticker).slice(0, 2).join(", ") || position.ticker}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <div className="text-xs text-foreground max-w-[200px] truncate">{ev.titleKo}</div>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`text-xs ${
                        ev.scenarios.find((s) => s.name === "Bull") && (ev.scenarios.find((s) => s.name === "Bull")!.probability > (ev.scenarios.find((s) => s.name === "Bear")?.probability || 0))
                          ? "text-accent-green"
                          : "text-accent-red"
                      }`}>
                        {ev.scenarios.find((s) => s.name === "Bull") && (ev.scenarios.find((s) => s.name === "Bull")!.probability > (ev.scenarios.find((s) => s.name === "Bear")?.probability || 0))
                          ? "▲ 강세"
                          : "▼ 약세"}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <EvidenceBadge grade={ev.evidenceGrade} />
                    </td>
                    <td className="px-3 py-2">
                      <div className="text-[10px] text-muted">
                        {ev.nextEventsKo?.[0] || ev.nextEvents?.[0] || ev.effectiveDate
                          ? new Date(ev.effectiveDate!).toLocaleDateString("ko-KR")
                          : "―"}
                      </div>
                    </td>
                  </tr>
                ))}
                {linkedEvents.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-3 py-8 text-center text-xs text-muted">
                      연결된 사건이 없습니다. Deep Scan을 실행하거나 이벤트를 수동으로 연결하세요.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Mini Causal Graph (SVG)
// --------------------------------------------------------------------------

function Share2Icon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
    </svg>
  );
}

function MiniCausalGraph({
  nodes,
  edges,
  onSelect,
  ticker,
}: {
  nodes: Event[];
  edges: CausalEdge[];
  onSelect: (id: string) => void;
  ticker: string;
}) {
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  const layout = useMemo(() => {
    const width = 500;
    const height = 300;
    const cx = width / 2;
    const cy = height / 2;
    const radius = Math.min(width, height) * 0.38;
    return nodes.map((n, i) => {
      const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2 - Math.PI / 2;
      return { ...n, x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius };
    });
  }, [nodes]);

  const nodeMap = useMemo(() => new Map(layout.map((n) => [n.id, n])), [layout]);

  if (nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-xs text-muted">
        연결된 사건이 없어 그래프를 그릴 수 없습니다.
      </div>
    );
  }

  return (
    <svg viewBox="0 0 500 300" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
      <defs>
        <marker id="mini-arrow" markerWidth="6" markerHeight="5" refX="5" refY="2.5" orient="auto">
          <polygon points="0 0, 6 2.5, 0 5" fill="#8b949e" />
        </marker>
      </defs>

      {/* Ticker center node */}
      <circle cx={250} cy={150} r={24} fill="none" stroke="#e16a2e" strokeWidth={2} strokeDasharray="4,2" />
      <text x={250} y={154} textAnchor="middle" fill="#e16a2e" fontSize="11" fontWeight={700}>{ticker}</text>

      {/* Edges */}
      {edges.map((edge, i) => {
        const src = nodeMap.get(edge.source);
        const tgt = nodeMap.get(edge.target);
        if (!src || !tgt) return null;
        const dx = tgt.x - src.x;
        const dy = tgt.y - src.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const off = 24;
        return (
          <line
            key={i}
            x1={src.x + (dx / dist) * off}
            y1={src.y + (dy / dist) * off}
            x2={tgt.x - (dx / dist) * off}
            y2={tgt.y - (dy / dist) * off}
            stroke="#8b949e"
            strokeWidth={0.5 + edge.strength * 0.3}
            markerEnd="url(#mini-arrow)"
            opacity={0.6}
          />
        );
      })}

      {/* Event nodes */}
      {layout.map((n) => {
        const isHovered = hoveredNode === n.id;
        return (
          <g
            key={n.id}
            transform={`translate(${n.x}, ${n.y})`}
            className="cursor-pointer"
            onClick={() => onSelect(n.id)}
            onMouseEnter={() => setHoveredNode(n.id)}
            onMouseLeave={() => setHoveredNode(null)}
          >
            <circle
              r={isHovered ? 16 : 13}
              fill={NODE_COLORS[n.eventType] || "#8b949e"}
              fillOpacity={0.8}
              stroke="#11141a"
              strokeWidth={1}
            />
            <text y={24} textAnchor="middle" fill="#c9d1d9" fontSize="9">
              {n.titleKo.length > 10 ? n.titleKo.slice(0, 10) + "…" : n.titleKo}
            </text>
            {isHovered && (
              <g transform="translate(0, -38)">
                <rect x={-50} y={-14} width={100} height={16} rx={3} fill="#181b22" stroke="#2d333b" />
                <text y={-4} textAnchor="middle" fill="#c9d1d9" fontSize="8">
                  {n.evidenceGrade} · {n.mechanismKo ? "✓" : "?"} 메커니즘
                </text>
              </g>
            )}
          </g>
        );
      })}

      {/* Line from ticker to first event */}
      {layout.length > 0 && (
        <line
          x1={250} y1={150}
          x2={layout[0].x} y2={layout[0].y}
          stroke="#e16a2e"
          strokeWidth={1}
          strokeDasharray="4,3"
          opacity={0.5}
        />
      )}
    </svg>
  );
}

// --------------------------------------------------------------------------
// Scenario Card
// --------------------------------------------------------------------------

function ScenarioCard({
  scenario,
  isExpanded,
  onToggle,
}: {
  scenario: Scenario;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const config = {
    Bull: { icon: TrendingUp, color: "#3fb950", bgColor: "#3fb95015", label: "강세" },
    Base: { icon: Minus, color: "#d29922", bgColor: "#d2992215", label: "기본" },
    Bear: { icon: TrendingDown, color: "#d73a49", bgColor: "#d73a4915", label: "약세" },
  };
  const c = config[scenario.name] || config.Base;
  const Icon = c.icon;

  return (
    <div
      className="border rounded-md cursor-pointer transition-colors"
      style={{ borderColor: `${c.color}30`, backgroundColor: c.bgColor }}
      onClick={onToggle}
    >
      <div className="flex items-center justify-between p-3">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4" style={{ color: config[scenario.name]?.color || "#8b949e" }} />
          <span className="text-sm font-semibold text-foreground">{c.label}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-foreground">
            {(scenario.probability * 100).toFixed(0)}%
          </span>
          {isExpanded ? <ChevronDown className="w-3.5 h-3.5 text-muted" /> : <ChevronRight className="w-3.5 h-3.5 text-muted" />}
        </div>
      </div>

      {isExpanded && (
        <div className="px-3 pb-3 space-y-2">
          <div className="text-[10px] text-muted">
            <span className="text-foreground font-medium">예상 가격 범위:</span> {scenario.priceRange}
          </div>
          {scenario.conditions.length > 0 && (
            <div>
              <div className="text-[10px] text-muted mb-1">필요 조건:</div>
              <ul className="space-y-0.5">
                {scenario.conditions.slice(0, 3).map((c, i) => (
                  <li key={i} className="text-[10px] text-foreground flex items-start gap-1">
                    <span style={{ color: config[scenario.name]?.color || "#8b949e" }}>•</span> {c}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function EvidenceBadge({ grade }: { grade: string }) {
  const color = grade === "E4" ? "#3fb950" : grade === "E3" ? "#58a6ff" : grade === "E2" ? "#d29922" : "#8b949e";
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold" style={{ backgroundColor: `${color}22`, color }}>
      {grade}
    </span>
  );
}
