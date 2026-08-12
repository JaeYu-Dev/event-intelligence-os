"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  TrendingUp, TrendingDown, Minus, ChevronDown, ChevronRight,
  Target, BarChart3, AlertTriangle, Clock, Briefcase, Share2,
  FileText, Loader2,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

const NODE_COLORS: Record<string, string> = {
  policy_announcement: "#3fb950",
  filing: "#58a6ff", earnings: "#58a6ff",
  macro: "#d29922",
  regulatory: "#a371f7",
  prediction_market: "#e16a2e",
  supply_chain: "#2ea043",
};

export default function MyTheses() {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detailData, setDetailData] = useState<Record<string, any>>({});

  const { data, isLoading } = useQuery({
    queryKey: ["my-theses"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/engine/theses`);
      return res.json();
    },
  });

  const theses = data?.theses || [];

  const fetchDetail = async (thesisId: string) => {
    if (detailData[thesisId]) return;
    const res = await fetch(`${API_BASE}/engine/thesis/${thesisId}`);
    const d = await res.json();
    setDetailData((prev) => ({ ...prev, [thesisId]: d }));
  };

  const handleToggle = (thesisId: string) => {
    if (expandedId === thesisId) {
      setExpandedId(null);
    } else {
      setExpandedId(thesisId);
      fetchDetail(thesisId);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full text-muted">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  if (theses.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted p-5">
        <Target className="w-12 h-12 mb-4 opacity-20" />
        <p className="text-sm mb-1">아직 등록된 가설이 없습니다.</p>
        <p className="text-xs">
          Deep Scan에서 투자 가설 후보를 찾아 수용하면 여기에 표시됩니다.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-[#0d1016] overflow-y-auto">
      <div className="p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Target className="w-4 h-4 text-accent" /> 내 가설 (My Theses)
            </h2>
            <p className="text-[10px] text-muted mt-0.5">
              {theses.length}개의 가설이 모니터링 중입니다.
            </p>
          </div>
        </div>

        <div className="space-y-4">
          {theses.map((thesis: any) => {
            const isExpanded = expandedId === thesis.thesis_id;
            const detail = detailData[thesis.thesis_id];
            const statusColor =
              thesis.status === "Research Required" ? "#58a6ff" :
              thesis.status === "Active" ? "#3fb950" :
              thesis.status === "At Risk" ? "#d73a49" : "#8b949e";

            return (
              <div
                key={thesis.thesis_id}
                className={`border rounded-lg transition-all ${
                  isExpanded ? "border-accent/50" : "border-border"
                } bg-panel`}
              >
                {/* Thesis header */}
                <button
                  onClick={() => handleToggle(thesis.thesis_id)}
                  className="w-full text-left p-4"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: statusColor }}
                        />
                        <span className="text-sm font-semibold text-foreground">
                          {thesis.title}
                        </span>
                        <span
                          className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                          style={{ backgroundColor: `${statusColor}22`, color: statusColor }}
                        >
                          {thesis.status}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-muted">
                        <span>{thesis.sector_ko || thesis.event_type}</span>
                        {thesis.evidence_grade && (
                          <>
                            <span>·</span>
                            <EvidenceBadge grade={thesis.evidence_grade} />
                          </>
                        )}
                        {thesis.urgency && (
                          <>
                            <span>·</span>
                            <UrgencyBadge urgency={thesis.urgency} />
                          </>
                        )}
                      </div>
                    </div>
                    <div className="flex-shrink-0 text-muted">
                      {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    </div>
                  </div>
                </button>

                {/* Expanded detail */}
                {isExpanded && (
                  <div className="border-t border-border px-4 pb-4">
                    {!detail ? (
                      <div className="flex items-center justify-center py-8">
                        <Loader2 className="w-5 h-5 animate-spin text-muted" />
                      </div>
                    ) : (
                      <div className="space-y-4 pt-4">
                        {/* Natural language narrative */}
                        {detail.narrative && (
                          <div>
                            <div className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
                              <FileText className="w-3 h-3 text-accent" /> 인과관계 설명
                            </div>
                            <div className="text-xs text-foreground leading-relaxed whitespace-pre-line bg-panel-hover border border-border rounded-md p-3">
                              {detail.narrative}
                            </div>
                          </div>
                        )}

                        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
                          {/* Scenarios */}
                          <div className="lg:col-span-3">
                            <div className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-2">
                              시나리오 분포
                            </div>
                            <div className="space-y-2">
                              {(detail.scenarios || []).length > 0 ? (
                                detail.scenarios.map((s: any) => {
                                  const config = {
                                    Bull: { icon: TrendingUp, color: "#3fb950", bg: "#3fb95015", label: "강세" },
                                    Base: { icon: Minus, color: "#d29922", bg: "#d2992215", label: "기본" },
                                    Bear: { icon: TrendingDown, color: "#d73a49", bg: "#d73a4915", label: "약세" },
                                    Tail: { icon: AlertTriangle, color: "#a371f7", bg: "#a371f715", label: "꼬리" },
                                  };
                                  const cfg = (config as any)[s.name] || config.Base;
                                  const Icon = cfg.icon;
                                  return (
                                    <div key={s.name} className="border border-border rounded-md p-3" style={{ backgroundColor: cfg.bg }}>
                                      <div className="flex items-center justify-between mb-1">
                                        <div className="flex items-center gap-2">
                                          <Icon className="w-3.5 h-3.5" style={{ color: cfg.color }} />
                                          <span className="text-xs font-semibold text-foreground">{cfg.label}</span>
                                        </div>
                                        <span className="text-sm font-semibold text-foreground">
                                          {(s.probability * 100).toFixed(0)}%
                                        </span>
                                      </div>
                                      {s.price_range && (
                                        <div className="text-[10px] text-muted mb-1">
                                          예상 수익률: {s.price_range}
                                        </div>
                                      )}
                                      {s.conditions && s.conditions.length > 0 && (
                                        <ul className="space-y-0.5">
                                          {s.conditions.slice(0, 3).map((cond: string, i: number) => (
                                            <li key={i} className="text-[10px] text-foreground flex items-start gap-1">
                                              <span className="text-accent">•</span> {cond}
                                            </li>
                                          ))}
                                        </ul>
                                      )}
                                    </div>
                                  );
                                })
                              ) : (
                                <div className="text-xs text-muted">시나리오 데이터 없음</div>
                              )}
                            </div>
                          </div>

                          {/* Mini causal graph + linked positions */}
                          <div className="lg:col-span-2 space-y-4">
                            {/* Mini graph */}
                            <div>
                              <div className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
                                <Share2 className="w-3 h-3 text-accent" /> 인과 그래프
                              </div>
                              <div className="h-[180px] bg-panel-hover border border-border rounded-md overflow-hidden">
                                <MiniGraph
                                  coreEvent={detail.core_event}
                                  relatedEvents={detail.related_events || []}
                                  edges={detail.edges || []}
                                />
                              </div>
                            </div>

                            {/* Linked positions */}
                            {detail.linked_positions && detail.linked_positions.length > 0 && (
                              <div>
                                <div className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
                                  <Briefcase className="w-3 h-3 text-accent" /> 포트폴리오 노출
                                </div>
                                <div className="space-y-1">
                                  {detail.linked_positions.map((pos: any) => (
                                    <div key={pos.ticker} className="flex items-center justify-between border border-border rounded-md px-2 py-1.5 text-xs">
                                      <div>
                                        <span className="font-semibold text-foreground">{pos.ticker}</span>
                                        <span className="text-[10px] text-muted ml-2">{pos.name} · {pos.shares}주</span>
                                      </div>
                                      <span className={(pos.pl_percent ?? 0) >= 0 ? "text-accent-green" : "text-accent-red"}>
                                        {(pos.pl_percent ?? 0) >= 0 ? "+" : ""}{(pos.pl_percent ?? 0).toFixed(1)}%
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Related events */}
                        {detail.related_events && detail.related_events.length > 0 && (
                          <div>
                            <div className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
                              <Clock className="w-3 h-3 text-accent" /> 연결된 사건
                            </div>
                            <div className="space-y-1">
                              {detail.related_events.map((re: any) => (
                                <div key={re.event_id} className="flex items-center justify-between border border-border rounded-md px-3 py-2 text-xs">
                                  <span className="text-foreground">{re.title_ko}</span>
                                  <div className="flex items-center gap-2 text-[10px]">
                                    <EvidenceBadge grade={re.evidence_grade || "E0"} />
                                    <span className="text-muted">{re.event_type}</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// Mini SVG causal graph for thesis detail
function MiniGraph({ coreEvent, relatedEvents, edges }: { coreEvent: any; relatedEvents: any[]; edges: any[] }) {
  const allNodes = useMemo(() => {
    const nodes: Array<{ id: string; label: string; type: string; x: number; y: number; isCore: boolean }> = [];
    if (coreEvent?.id) {
      nodes.push({ id: coreEvent.id, label: (coreEvent.title_ko || "").slice(0, 10), type: coreEvent.event_type || "", x: 200, y: 80, isCore: true });
    }
    relatedEvents.forEach((re: any, i: number) => {
      const angle = (i / Math.max(relatedEvents.length, 1)) * Math.PI * 2 - Math.PI / 2;
      nodes.push({
        id: re.event_id, label: (re.title_ko || "").slice(0, 8),
        type: re.event_type || "", x: 200 + Math.cos(angle) * 100, y: 80 + Math.sin(angle) * 70,
        isCore: false,
      });
    });
    return nodes;
  }, [coreEvent, relatedEvents]);

  if (allNodes.length === 0) return <div className="flex items-center justify-center h-full text-[10px] text-muted">연결된 사건 없음</div>;

  return (
    <svg viewBox="0 0 400 160" className="w-full h-full">
      <defs>
        <marker id="mg-arrow" markerWidth="5" markerHeight="4" refX="4" refY="2" orient="auto">
          <polygon points="0 0, 5 2, 0 4" fill="#8b949e" />
        </marker>
      </defs>
      {allNodes.filter((n) => !n.isCore).map((n) => (
        <line key={`e-${n.id}`} x1={200} y1={80} x2={n.x} y2={n.y} stroke="#8b949e" strokeWidth={0.8} markerEnd="url(#mg-arrow)" opacity={0.5} />
      ))}
      {allNodes.map((n) => (
        <g key={n.id} transform={`translate(${n.x}, ${n.y})`}>
          <circle r={n.isCore ? 14 : 9} fill={n.isCore ? "#e16a2e" : (NODE_COLORS[n.type] || "#8b949e")} fillOpacity={0.8} stroke="#11141a" strokeWidth={1} />
          <text y={n.isCore ? 22 : 16} textAnchor="middle" fill="#c9d1d9" fontSize="8">{n.label}</text>
        </g>
      ))}
    </svg>
  );
}

function EvidenceBadge({ grade }: { grade: string }) {
  const c = grade === "E4" ? "#3fb950" : grade === "E3" ? "#58a6ff" : grade === "E2" ? "#d29922" : "#8b949e";
  return <span className="inline-flex items-center px-1 py-0.5 rounded text-[10px] font-semibold" style={{ backgroundColor: `${c}22`, color: c }}>{grade}</span>;
}

function UrgencyBadge({ urgency }: { urgency: string }) {
  const labels: Record<string, string> = { Critical: "심각", High: "높음", Medium: "보통", Low: "낮음" };
  return <span className="text-[10px]">{labels[urgency] || urgency}</span>;
}
