"use client";

import { useMemo, useState, useCallback } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import Sidebar from "./components/Sidebar";
import Dashboard from "./components/Dashboard";
import PortfolioView from "./components/PortfolioView";
import CausalGraph from "./components/CausalGraph";
import EventTable from "./components/EventTable";
import ThesisPanel from "./components/ThesisPanel";
import ThesisLab from "./components/ThesisLab";
import ThesisInbox from "./components/ThesisInbox";
import BacktestDashboard from "./components/BacktestDashboard";
import { fetchRadar, fetchAlerts } from "./lib/api";
import { FilterState, ViewMode, CausalEdge, ConfirmationAlert, PortfolioPosition } from "./types";

function pageTitle(view: ViewMode) {
  if (view === "dashboard") return "이벤트 대시보드";
  if (view === "graph") return "인과 그래프";
  if (view === "backtest") return "Point-in-Time 백테스트";
  return "포트폴리오";
}
import { events as mockEvents } from "./lib/mockData";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

function mapApiEventToUI(e: any) { return { id: e.id, title: e.title || "", titleKo: e.title_ko || e.title || "", eventType: e.event_type, actor: e.actor || "", actorKo: e.actor_ko || e.actor || "", action: e.action || "", object: e.object || "", publishedAt: e.published_at || e.created_at, effectiveDate: e.effective_date || undefined, sourceType: e.source_type || "official", sourceReliability: e.source_reliability ?? 0.9, evidenceGrade: e.evidence_grade, urgency: e.urgency, status: e.status, sector: e.sector || "", sectorKo: e.sector_ko || e.sector || "", relatedTickers: e.related_tickers || [], mechanism: e.mechanism || "", mechanismKo: e.mechanism_ko || e.mechanism || "", counterevidence: e.counterevidence || [], counterevidenceKo: e.counterevidence_ko || e.counterevidence || [], nextEvents: e.next_events || [], nextEventsKo: e.next_events_ko || e.next_events || [], scenarios: (e.conditions || []).map((s: any) => ({ name: s.name, probability: s.probability, prevProbability: s.prev_probability, conditions: s.conditions || [], priceRange: s.price_range || "" })), count: 1, lat: 0, lng: 0, actionRequired: "Watch" as const, eventStage: (e as any).event_stage || "detected" }; }
function mapApiEdgeToUI(e: any): CausalEdge { return { source: e.source, target: e.target, strength: e.strength ?? 1, type: e.type || "market", labelKo: e.label_ko || e.label || "" }; }
function mapApiPositionToUI(p: any): PortfolioPosition { return { ticker: p.ticker, name: p.name || p.ticker, shares: p.shares ?? 0, avgCost: p.avg_cost ?? 0, currentPrice: p.current_price ?? 0, plPercent: p.pl_percent ?? 0, plUsd: p.pl_usd ?? 0, scenarioBias: p.scenario_bias || "Base", exposureEvents: p.exposure_events || [] }; }
function mapEventToCausalNode(e: any) {
  return {
    node_id: e.id,
    node_type: "root_event" as const,
    label_ko: e.title_ko || e.titleKo || e.title || "",
    description_ko: e.mechanism_ko || e.mechanismKo || e.mechanism || "",
    evidence_grade: e.evidence_grade || e.evidenceGrade || "E2",
    probability: 0.85,
    evidence_items: [],
    market_data: [],
    counterevidence: e.counterevidence_ko || e.counterevidenceKo || e.counterevidence || [],
    metadata: { event_type: e.event_type || e.eventType, actor: e.actor_ko || e.actorKo || e.actor, sector: e.sector_ko || e.sectorKo || e.sector },
  };
}

function mapEdgeToCausalEdge(e: any, idx: number) {
  return {
    edge_id: `e-${idx}`,
    source_node_id: e.source,
    target_node_id: e.target,
    relation_type: e.type || "market",
    label_ko: e.label_ko || e.labelKo || e.label || "",
    evidence_grade: "E2",
    strength: e.strength ?? 3,
    mechanism_detail: "",
    source_refs: [],
  };
}


export default function Home() {
  const [filter, setFilter] = useState<FilterState>({ keyword: "", eventType: "All", evidenceGrade: "All", urgency: "All", status: "All", sector: "All" });
  const [view, setView] = useState<ViewMode>("dashboard");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({ queryKey: ["radar"], queryFn: fetchRadar });
  const { data: alertsData } = useQuery({ queryKey: ["alerts"], queryFn: fetchAlerts });

  const events = useMemo(() => { const raw = data?.events || []; if (raw.length === 0 && error) return mockEvents; return raw.map(mapApiEventToUI); }, [data, error]);
  const positions = useMemo(() => (data?.positions || []).map(mapApiPositionToUI), [data]);
  const edges = useMemo(() => (data?.edges || []).map(mapApiEdgeToUI), [data]);

  const alerts = useMemo<ConfirmationAlert[]>(() => (alertsData || []).map((a: any) => ({ eventId: a.event_id, scenario: a.scenario, whatToWatch: a.what_to_watch, deadline: a.deadline === "미정" ? a.deadline : new Date(a.deadline).toLocaleDateString("ko-KR"), impactIfConfirmed: a.impact_if_confirmed })), [alertsData]);
  const filteredEvents = useMemo(() => events.filter((e: any) => { const mk = filter.keyword === "" || e.titleKo.toLowerCase().includes(filter.keyword.toLowerCase()) || e.actorKo.toLowerCase().includes(filter.keyword.toLowerCase()) || e.sectorKo.toLowerCase().includes(filter.keyword.toLowerCase()) || e.relatedTickers.some((t: string) => t.toLowerCase().includes(filter.keyword.toLowerCase())); return mk && (filter.eventType === "All" || e.eventType === filter.eventType) && (filter.evidenceGrade === "All" || e.evidenceGrade === filter.evidenceGrade) && (filter.urgency === "All" || e.urgency === filter.urgency) && (filter.status === "All" || e.status === filter.status) && (filter.sector === "All" || e.sector === filter.sector); }), [events, filter]);
  const selectedEvent = useMemo(() => filteredEvents.find((e: any) => e.id === selectedId) || null, [filteredEvents, selectedId]);

  // ---- Full-screen views (take over the entire viewport) ----
  if (view === "thesislab") return <ThesisLab />;
  if (view === "inbox") return <ThesisInbox />;
  if (view === "backtest") return <BacktestDashboard />;

  // ---- Default: Dashboard layout (main screen) ----
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      <Sidebar filter={filter} setFilter={setFilter} totalCount={events.length} filteredCount={filteredEvents.length} view={view} setView={setView} alertCount={alerts.length} />
      <main className="flex-1 flex flex-col min-w-0">
        <header className="h-14 flex items-center justify-between px-4 border-b border-border bg-panel flex-shrink-0">
          <div className="flex items-center gap-4">
            <h1 className="text-sm font-semibold text-foreground">
              {pageTitle(view)}
            </h1>
            <span className="text-xs text-muted">리서치 / 모의 거래 모드</span>
            {isLoading && <span className="text-xs text-accent">로딩 중...</span>}
            {error && <span className="text-xs text-accent-red">API 연결 실패 (mock 사용)</span>}
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted">저비용 모니터링 활성</span>
            <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-accent-green/20 text-accent-green">Live</span>
          </div>
        </header>
        <div className="flex-1 flex min-h-0">
          <div className="flex-1 flex flex-col min-w-0">
            <div className="relative flex-1 min-h-0">
              {view === "dashboard" ? <Dashboard events={filteredEvents} positions={positions} alerts={alerts} onSelectEvent={setSelectedId} />
              : view === "graph" ? <CausalGraph nodes={filteredEvents.map(mapEventToCausalNode)} edges={edges.map(mapEdgeToCausalEdge)} interventions={{}} selectedNodeId={selectedId} hoveredNodeId={null} onSelectNode={setSelectedId} onHoverNode={() => {}} />
              : <PortfolioView positions={positions} events={filteredEvents} onSelectEvent={setSelectedId} />}
            </div>
            <div className="h-[38%] min-h-[220px]"><EventTable events={filteredEvents} selectedId={selectedId} onSelect={setSelectedId} /></div>
          </div>
          <ThesisPanel event={selectedEvent} onClose={() => setSelectedId(null)} />
        </div>
      </main>
    </div>
  );
}
