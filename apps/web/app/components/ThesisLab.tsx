"use client";

import { useState, useMemo, useCallback, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  TrendingUp, TrendingDown, Minus, Target, BarChart3, AlertTriangle, Clock, Briefcase, FileText, Calendar,
  Shield, ChevronRight, DollarSign, Activity, CheckCircle2, XCircle, HelpCircle, Layers, Zap, Plus, Edit3, ExternalLink,
  History,
} from "lucide-react";
import CausalGraph from "./CausalGraph";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

// ==========================================================================
// Main Component
// ==========================================================================

export default function ThesisLab() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [centerTab, setCenterTab] = useState<"map" | "narrative" | "scenarios" | "timeline" | "replay">("map");
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [cutoff, setCutoff] = useState<string>("");
  const [snapshotData, setSnapshotData] = useState<any>(null);
  const [externalScenarios, setExternalScenarios] = useState<Array<{ name: string; source: string; text: string }>>([]);
  const [newScenarioText, setNewScenarioText] = useState("");
  const [newScenarioSource, setNewScenarioSource] = useState("");

  const { data: thesisList } = useQuery({ queryKey: ["my-theses"], queryFn: async () => { const r = await fetch(`${API_BASE}/engine/theses`); return r.json(); } });
  const theses = thesisList?.theses || [];

  useEffect(() => { if (theses.length > 0 && !selectedId) setSelectedId(theses[0].thesis_id); }, [theses, selectedId]);

  const { data: pathData } = useQuery({ queryKey: ["causal-path", selectedId], queryFn: async () => { if (!selectedId) return null; const r = await fetch(`${API_BASE}/engine/causal-path/${selectedId}`); return r.json(); }, enabled: !!selectedId });

  const thesisMeta = theses.find((t: any) => t.thesis_id === selectedId);

  const fetchSnapshot = useCallback(async () => {
    if (!cutoff) return;
    const r = await fetch(`${API_BASE}/engine/pit-snapshot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cutoff_time: new Date(cutoff).toISOString(), universe: {} }),
    });
    if (r.ok) setSnapshotData(await r.json());
  }, [cutoff]);

  const interventionNodes = useMemo<Record<string, any[]>>(() => {
    if (!pathData) return {};
    const nodes = pathData.nodes || [];
    const interventions: Record<string, any[]> = {};
    for (const n of nodes) {
      const items: any[] = [];
      // Related tickers as intervention bubbles
      if (n.node_type === "instrument" && n.metadata?.all_tickers) {
        for (const t of n.metadata.all_tickers.slice(0, 5)) {
          items.push({ id: `${n.node_id}-ticker-${t}`, label: t, type: "ticker", value: t, icon: DollarSign, color: "#d29922" });
        }
      }
      if (n.node_type === "root_event" && n.metadata?.actor) {
        items.push({ id: `${n.node_id}-actor`, label: n.metadata.actor, type: "actor", value: n.metadata.actor, icon: Briefcase, color: "#58a6ff" });
      }
      // Counterevidence as risk bubbles
      if (n.counterevidence && n.counterevidence.length > 0) {
        for (const ce of n.counterevidence.slice(0, 2)) {
          items.push({ id: `${n.node_id}-counter-${ce.substring(0,10)}`, label: ce.substring(0, 18), type: "risk", value: ce, icon: AlertTriangle, color: "#d73a49" });
        }
      }
      // Evidence items
      if (n.evidence_items) {
        for (const ei of n.evidence_items.slice(0, 2)) {
          items.push({ id: `${n.node_id}-ev-${ei.type}`, label: ei.type, type: "evidence", value: ei.text?.substring(0, 40) || ei.type, icon: FileText, color: "#3fb950" });
        }
      }
      // Market data
      if (n.market_data) {
        for (const md of n.market_data.slice(0, 2)) {
          items.push({ id: `${n.node_id}-md-${md.symbol}`, label: `${md.symbol} ${md.change}`, type: "market", value: `${md.symbol}: ${md.change}`, icon: TrendingUp, color: (md.change || "").includes("-") ? "#d73a49" : "#3fb950" });
        }
      }
      if (items.length > 0) interventions[n.node_id] = items;
    }
    return interventions;
  }, [pathData]);

  const addExternalScenario = () => {
    if (!newScenarioText.trim()) return;
    setExternalScenarios(prev => [...prev, { name: `외부 시나리오 ${prev.length + 1}`, source: newScenarioSource || "사용자 입력", text: newScenarioText }]);
    setNewScenarioText("");
    setNewScenarioSource("");
  };

  if (!thesisList) return <div className="flex items-center justify-center h-screen bg-[#0d1016] text-muted text-sm">로딩 중...</div>;
  if (theses.length === 0) return <div className="flex flex-col items-center justify-center h-screen bg-[#0d1016] text-muted p-5"><Target className="w-14 h-14 mb-4 opacity-20" /><p className="text-base">등록된 가설이 없습니다</p></div>;

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0d1016]">
      {/* LEFT: Thesis List + Checklist */}
      <aside className="w-56 flex-shrink-0 bg-panel border-r border-border flex flex-col">
        <div className="h-12 flex items-center gap-2 px-3 border-b border-border">
          <div className="w-5 h-5 rounded-sm bg-accent flex items-center justify-center text-[10px] font-bold text-white">EI</div>
          <span className="text-xs font-semibold text-foreground">Thesis Lab</span>
        </div>
        <div className="px-3 pt-3 pb-1.5"><div className="text-[9px] font-semibold text-muted uppercase tracking-wider">내 가설</div></div>
        {theses.map((t: any) => (
          <button key={t.thesis_id} onClick={() => setSelectedId(t.thesis_id)}
            className={`w-full text-left px-3 py-2 text-xs transition-colors border-l-2 ${selectedId === t.thesis_id ? "border-accent bg-accent/5 text-foreground" : "border-transparent text-muted hover:text-foreground hover:bg-panel-hover"}`}>
            <div className="truncate font-medium">{(t.title || "").slice(0, 24)}</div>
            <div className="text-[9px] text-muted mt-0.5">{t.status} · {t.evidence_grade}</div>
          </button>
        ))}
        {pathData && (
          <div className="flex-1 overflow-y-auto p-3 space-y-1.5 mt-2 border-t border-border">
            <div className="text-[9px] font-semibold text-muted uppercase tracking-wider mb-1">체크리스트</div>
            {Object.entries(pathData.checklist || {}).map(([key, done]: [string, any]) => {
              const labels: Record<string, string> = { trigger: "트리거", constraint: "제약 조건", transmission: "전파 경로", exposure: "노출 분석", timing: "타이밍", falsifier: "무효화 조건" };
              return (
                <div key={key} className="flex items-start gap-1 text-[10px]">
                  {done ? <CheckCircle2 className="w-3 h-3 text-accent-green mt-0.5" /> : <XCircle className="w-3 h-3 text-muted mt-0.5" />}
                  <span className={done ? "text-foreground" : "text-muted"}>{labels[key] || key}</span>
                </div>
              );
            })}
          </div>
        )}
      </aside>

      {/* CENTER: Main workspace */}
      <main className="flex-1 flex flex-col min-w-0">
        {thesisMeta && pathData && (
          <div className="flex-shrink-0 h-14 bg-panel border-b border-border flex items-center justify-between px-5">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-2 h-2 rounded-full bg-accent" />
              <h1 className="text-sm font-bold text-foreground truncate max-w-[350px]">{pathData.root_event?.title_ko}</h1>
              <span className="text-[10px] text-accent-green font-semibold">PathScore {(pathData.path_score * 100).toFixed(1)}%</span>
            </div>
            <div className="flex items-center gap-2 text-[10px]">
              <span className="px-1.5 py-0.5 rounded bg-accent/15 text-accent font-medium">{thesisMeta.status}</span>
              <span>{pathData.root_event?.evidence_grade}</span>
              <span className="text-muted">·</span>
              <span>{pathData.root_event?.sector_ko}</span>
              <span className="w-px h-3 bg-border mx-1" />
              <History className="w-3 h-3 text-muted" />
              <input type="datetime-local" value={cutoff} onChange={(e) => setCutoff(e.target.value)} className="bg-background border border-border rounded px-1.5 py-0.5 text-[10px] text-foreground focus:outline-none focus:border-accent" />
              {cutoff && <button onClick={fetchSnapshot} className="px-1.5 py-0.5 rounded bg-accent/15 text-accent hover:bg-accent/25">스냅샷</button>}
              {cutoff && <button onClick={() => { setCutoff(""); setSnapshotData(null); }} className="text-muted hover:text-foreground">✕</button>}
            </div>
          </div>
        )}

        <div className="flex-shrink-0 bg-panel border-b border-border flex items-center gap-0.5 px-2">
          {[{ id: "map" as const, label: "인과 네트워크", icon: Layers }, { id: "narrative" as const, label: "분석 노트", icon: FileText }, { id: "scenarios" as const, label: "시나리오", icon: BarChart3 }, { id: "timeline" as const, label: "타임라인", icon: Clock }, { id: "replay" as const, label: "과거 재생", icon: History }].map(tab => (
            <button key={tab.id} onClick={() => setCenterTab(tab.id)}
              className={`flex items-center gap-1 px-3 py-2 text-xs border-b-2 transition-colors ${centerTab === tab.id ? "border-accent text-foreground" : "border-transparent text-muted hover:text-foreground"}`}>
              <tab.icon className="w-3 h-3" /> {tab.label}
            </button>
          ))}
        </div>

        <div className="flex-1 flex min-h-0">
          <div className="flex-1 overflow-y-auto">
            {!pathData ? <div className="flex items-center justify-center h-full text-muted text-sm">좌측에서 가설을 선택하세요</div>
            : centerTab === "map" ? <CausalGraph nodes={pathData.nodes || []} edges={pathData.edges || []} interventions={interventionNodes} hoveredNodeId={hoveredNodeId} selectedNodeId={selectedNodeId} onHoverNode={setHoveredNodeId} onSelectNode={(id: string | null) => setSelectedNodeId(id)} onSelectEdge={(e) => {}} asOfTime={cutoff || pathData.root_event?.published_at} />
            : centerTab === "narrative" ? <NarrativeView pathData={pathData} />
            : centerTab === "scenarios" ? <ScenariosView pathData={pathData} externalScenarios={externalScenarios} />
            : <TimelineView timeline={pathData.timeline || []} pathData={pathData} />}
          </div>

          {/* Right Rail: Node detail + External scenario input */}
          {pathData && (
            <aside className="w-72 flex-shrink-0 bg-panel border-l border-border overflow-y-auto p-4 space-y-4">
              <div>
                <div className="text-[9px] font-semibold text-muted uppercase tracking-wider mb-2 flex items-center gap-1"><Target className="w-3 h-3 text-accent" /> Path Score</div>
                <div className="text-2xl font-bold text-foreground mb-2">{(pathData.path_score * 100).toFixed(1)}%</div>
                {Object.entries(pathData.score_breakdown || {}).map(([key, val]: [string, any]) => (
                  <div key={key} className="flex items-center justify-between text-[10px]"><span className="text-muted">{key.replace(/_/g, " ")}</span><span className="text-foreground font-medium">{(val * 100).toFixed(1)}%</span></div>
                ))}
              </div>
              <div className="border-t border-border" />
              {selectedNodeId ? (
                <NodeDetail node={pathData.nodes?.find((n: any) => n.node_id === selectedNodeId)} onClose={() => setSelectedNodeId(null)} />
              ) : (
                <div>
                  <div className="text-[9px] font-semibold text-muted uppercase tracking-wider mb-2">외부 시나리오 추가</div>
                  <textarea value={newScenarioText} onChange={(e) => setNewScenarioText(e.target.value)} placeholder="전문가 시나리오 / 인터넷에서 발견한 관점을 입력..." className="w-full bg-background border border-border rounded-md p-2 text-xs text-foreground placeholder:text-muted h-20 resize-none focus:outline-none focus:border-accent" />
                  <input value={newScenarioSource} onChange={(e) => setNewScenarioSource(e.target.value)} placeholder="출처 (선택)" className="w-full bg-background border border-border rounded-md px-2 py-1 text-xs text-foreground placeholder:text-muted mt-1 focus:outline-none focus:border-accent" />
                  <button onClick={addExternalScenario} className="w-full mt-1.5 flex items-center justify-center gap-1 px-2 py-1.5 rounded-md bg-accent hover:bg-accent/90 text-white text-xs font-semibold"><Plus className="w-3 h-3" /> 추가</button>
                  {externalScenarios.length > 0 && (
                    <div className="mt-3 space-y-1.5">
                      <div className="text-[9px] text-muted uppercase">추가된 시나리오 ({externalScenarios.length})</div>
                      {externalScenarios.map((es, i) => (
                        <div key={i} className="border border-border rounded p-2 text-[10px]">
                          <div className="text-accent font-medium">{es.name} <span className="text-muted">({es.source})</span></div>
                          <div className="text-foreground mt-0.5">{es.text.substring(0, 80)}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </aside>
          )}
        </div>
      </main>
    </div>
  );
}

// ==========================================================================
// Narrative View — with Executive Summary at top
// ==========================================================================

function NarrativeView({ pathData }: { pathData: any }) {
  const sections = (pathData.narrative_ko || "").split("## ").filter(Boolean);
  return (
    <div className="p-6 overflow-y-auto">
      <div className="max-w-3xl mx-auto space-y-5">
        {/* Executive Summary */}
        <div className="border-2 border-accent/30 rounded-lg bg-accent/5 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-bold text-foreground">Executive Summary</h2>
          </div>
          <p className="text-sm text-foreground leading-relaxed">{pathData.executive_summary_ko || "요약 생성 중..."}</p>
        </div>

        {/* Detailed sections */}
        {sections.map((section: string, idx: number) => {
          const lines = section.trim().split("\n");
          const title = lines[0].replace(/^##\s*/, "").trim();
          const body = lines.slice(1).join("\n").trim();
          const key = title.includes("트리거") ? "trigger" : title.includes("제약") ? "constraint" : title.includes("전파") ? "transmission" : title.includes("노출") ? "exposure" : title.includes("타이밍") ? "timing" : "falsifier";
          const done = pathData.checklist?.[key];
          return (
            <div key={idx} className="border border-border rounded-lg bg-panel p-4">
              <div className="flex items-center gap-2 mb-2">
                {done ? <CheckCircle2 className="w-4 h-4 text-accent-green" /> : <HelpCircle className="w-4 h-4 text-muted" />}
                <h3 className="text-sm font-semibold text-foreground">{title}</h3>
              </div>
              <div className="text-xs text-foreground leading-relaxed whitespace-pre-wrap">{body}</div>
              {pathData.checklist_notes?.[key] && <div className="mt-2 pt-2 border-t border-border text-[10px] text-accent-blue">{pathData.checklist_notes[key]}</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ==========================================================================
// Scenarios View
// ==========================================================================

function ScenariosView({ pathData, externalScenarios }: { pathData: any; externalScenarios: any[] }) {
  const dist = pathData.scenario_distribution || {};
  const config: Record<string, any> = {
    Bull: { icon: TrendingUp, color: "#3fb950", bg: "#3fb95015", label: "강세 (Bull)" },
    Base: { icon: Minus, color: "#d29922", bg: "#d2992215", label: "기본 (Base)" },
    Bear: { icon: TrendingDown, color: "#d73a49", bg: "#d73a4915", label: "약세 (Bear)" },
  };

  return (
    <div className="p-6 overflow-y-auto">
      <div className="max-w-2xl mx-auto space-y-4">
        {/* System scenarios */}
        {Object.entries(dist).map(([name, data]: [string, any]) => {
          const cfg = config[name] || config.Base;
          const Icon = cfg.icon;
          return (
            <div key={name} className="border border-border rounded-lg p-4 bg-panel" style={{ backgroundColor: cfg.bg }}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2"><Icon className="w-5 h-5" style={{ color: cfg.color }} /><span className="text-lg font-bold text-foreground">{cfg.label}</span></div>
                <span className="text-2xl font-bold" style={{ color: cfg.color }}>{(data.probability * 100).toFixed(0)}%</span>
              </div>
              <div className="h-2.5 rounded-full bg-panel-hover border border-border mb-2"><div className="h-full rounded-full" style={{ width: `${data.probability * 100}%`, backgroundColor: cfg.color }} /></div>
              {data.price_range && <div className="text-sm text-foreground font-medium">예상 수익률: {data.price_range}</div>}
            </div>
          );
        })}

        {/* External scenarios */}
        {externalScenarios.length > 0 && (
          <div>
            <div className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-3 flex items-center gap-1"><Edit3 className="w-3 h-3 text-accent" /> 외부/전문가 시나리오</div>
            <div className="space-y-2">
              {externalScenarios.map((es, i) => (
                <div key={i} className="border border-border rounded-lg p-3 bg-panel">
                  <div className="flex items-center justify-between mb-1"><span className="text-xs font-semibold text-foreground">{es.name}</span><span className="text-[9px] text-muted">{es.source}</span></div>
                  <div className="text-xs text-foreground leading-relaxed">{es.text}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ==========================================================================
// Timeline View — with branching scenarios at each checkpoint
// ==========================================================================

function TimelineView({ timeline, pathData }: { timeline: any[]; pathData: any }) {
  if (timeline.length === 0) return <div className="flex items-center justify-center h-full text-muted text-sm">타임라인 데이터 없음</div>;
  const dist = pathData.scenario_distribution || {};

  return (
    <div className="p-6 overflow-y-auto">
      <div className="max-w-2xl mx-auto">
        <div className="mb-4">
          <div className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-2 flex items-center gap-1"><Clock className="w-3.5 h-3.5 text-accent" /> 사건 타임라인 & 시나리오 분기</div>
          <p className="text-xs text-muted">주요 확인 시점마다 시나리오가 어떻게 분기되는지 보여줍니다. 각 분기점에서 Bull/Base/Bear 확률이 업데이트됩니다.</p>
        </div>

        <div className="relative pl-8 border-l-2 border-border space-y-6">
          {timeline.map((entry: any, idx: number) => (
            <div key={idx} className="relative">
              <div className="absolute -left-[2.35rem] top-1 w-4 h-4 rounded-full border-2 border-accent bg-[#0d1016]" />
              <div className="border border-border rounded-lg bg-panel p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-accent/15 text-accent">{entry.time_label}</span>
                    <span className="text-xs font-semibold text-foreground">{entry.title_ko}</span>
                  </div>
                  <span className="text-[10px] text-muted">{entry.date}</span>
                </div>
                <div className="text-xs text-foreground mb-2">{entry.description_ko}</div>
                {entry.impact_ko && <div className="text-[10px] text-muted mb-3">예상 영향: {entry.impact_ko}</div>}

                {/* Branching scenarios */}
                {entry.branching && entry.branching.length > 0 && (
                  <div className="space-y-2 mt-2 pt-3 border-t border-border">
                    <div className="text-[9px] font-semibold text-muted uppercase mb-1">이 시점의 시나리오 분기:</div>
                    <div className="grid grid-cols-3 gap-2">
                      {entry.branching.map((branch: any) => {
                        const colors: Record<string, string> = { Bull: "#3fb950", Base: "#d29922", Bear: "#d73a49" };
                        return (
                          <div key={branch.name} className="border border-border rounded-md p-2 text-center" style={{ borderColor: `${colors[branch.name] || "#8b949e"}40`, backgroundColor: `${colors[branch.name] || "#8b949e"}08` }}>
                            <div className="text-[11px] font-bold" style={{ color: colors[branch.name] || "#8b949e" }}>{branch.name}</div>
                            <div className="text-lg font-semibold text-foreground">{(branch.prob * 100).toFixed(0)}%</div>
                            {branch.price && <div className="text-[9px] text-muted mt-0.5">{branch.price}</div>}
                            {branch.condition && <div className="text-[9px] text-foreground mt-1">{branch.condition}</div>}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}


// ==========================================================================
// Replay Snapshot View — PIT data at selected cutoff
// ==========================================================================

function ReplaySnapshotView({ snapshot, cutoff }: { snapshot: any; cutoff: string }) {
  if (!cutoff) return <div className="flex items-center justify-center h-full text-muted text-sm">좌측 상단에서 과거 시점을 선택하세요</div>;
  if (!snapshot) return <div className="flex items-center justify-center h-full text-muted text-sm">스냅샷을 불러오는 중...</div>;
  return (
    <div className="p-6 overflow-y-auto">
      <div className="max-w-4xl mx-auto space-y-5">
        <div className="border border-border rounded-lg bg-panel p-4">
          <div className="flex items-center gap-2 mb-2">
            <History className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-bold text-foreground">Point-in-Time 스냅샷</h2>
          </div>
          <p className="text-xs text-muted">{new Date(snapshot.cutoff_time).toLocaleString("ko-KR")} 시점에 관찰 가능했던 데이터</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <SnapshotMetric label="문서" value={snapshot.source_snapshot?.document_count ?? 0} />
          <SnapshotMetric label="가격" value={snapshot.market_snapshot?.price_count ?? 0} />
          <SnapshotMetric label="활성 시나리오" value={snapshot.active_scenarios?.length ?? 0} />
        </div>
        {snapshot.market_snapshot?.prices && snapshot.market_snapshot.prices.length > 0 && (
          <div className="border border-border rounded-lg bg-panel p-4">
            <div className="text-[10px] font-semibold text-muted uppercase mb-3">시장 데이터</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]">
              {snapshot.market_snapshot.prices.slice(0, 8).map((p: any) => (
                <div key={p.symbol} className="border border-border rounded p-2">
                  <div className="text-foreground font-medium">{p.symbol}</div>
                  <div className="text-muted">{p.close?.toFixed(2)}</div>
                </div>
              ))}
            </div>
          </div>
        )}
        {snapshot.graph_snapshot && (
          <div className="border border-border rounded-lg bg-panel p-4">
            <div className="text-[10px] font-semibold text-muted uppercase mb-2">그래프 스냅샷</div>
            <pre className="text-[10px] text-foreground overflow-x-auto">{JSON.stringify(snapshot.graph_snapshot, null, 2).slice(0, 1200)}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

function SnapshotMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="border border-border rounded-lg bg-panel p-4 text-center">
      <div className="text-[10px] text-muted uppercase mb-1">{label}</div>
      <div className="text-2xl font-bold text-foreground">{value}</div>
    </div>
  );
}

function NodeDetail({ node, onClose }: { node: any; onClose: () => void }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div className="text-[9px] font-semibold text-muted uppercase tracking-wider flex items-center gap-1"><FileText className="w-3 h-3 text-accent" /> 노드 상세</div>
        <button onClick={onClose} className="text-muted hover:text-foreground text-[10px]">✕</button>
      </div>
      <div className="space-y-2 text-[10px]">
        <div><div className="text-muted uppercase">유형</div><div className="text-foreground font-semibold">{node.node_type}</div></div>
        <div><div className="text-muted uppercase">증거 등급</div><div className="text-foreground font-semibold">{node.evidence_grade}</div></div>
        <div><div className="text-muted uppercase">확률</div><div className="text-foreground font-semibold">{(node.probability * 100).toFixed(0)}%</div></div>
        {node.evidence_items && node.evidence_items.length > 0 && (
          <div><div className="text-muted uppercase mb-1">근거</div>
            {node.evidence_items.map((ei: any, i: number) => <div key={i} className="text-foreground border border-border rounded p-1.5 mb-1"><span className="text-accent">{ei.type}:</span> {typeof ei.text === 'string' ? ei.text.substring(0, 60) : ''}</div>)}
          </div>
        )}
        {node.market_data && node.market_data.length > 0 && (
          <div><div className="text-muted uppercase mb-1">시장 데이터</div>
            {node.market_data.map((md: any, i: number) => <div key={i} className={`px-1.5 py-0.5 rounded text-[10px] ${(md.change || "").includes("-") ? "text-accent-red" : "text-accent-green"}`}>{md.symbol}: {md.change} ({md.period})</div>)}
          </div>
        )}
        {node.counterevidence && node.counterevidence.length > 0 && (
          <div><div className="text-muted uppercase mb-1 flex items-center gap-1"><AlertTriangle className="w-2.5 h-2.5 text-accent-red" /> 반대 증거</div>
            {node.counterevidence.map((ce: string, i: number) => <div key={i} className="text-accent-red/80 bg-accent-red/5 border border-accent-red/20 rounded p-1.5 mb-1">{ce}</div>)}
          </div>
        )}
      </div>
    </div>
  );
}
