"use client";

import { TrendingUp, TrendingDown, AlertCircle, Calendar, Target, Activity, Wallet } from "lucide-react";
import { Event, PortfolioPosition, ConfirmationAlert } from "../types";


interface DashboardProps {
  positions: any[];
  events: Event[];
  alerts: ConfirmationAlert[];
  onSelectEvent: (id: string) => void;
}

export default function Dashboard({ events, positions, alerts, onSelectEvent }: DashboardProps) {
  const totalPl = positions.reduce((sum, p) => sum + toNum(p.plUsd), 0);
  const totalCost = positions.reduce((sum, p) => sum + toNum(p.shares) * toNum(p.avgCost), 0);
  const totalReturn = totalCost > 0 ? (totalPl / totalCost) * 100 : 0;

  return (
    <div className="flex flex-col h-full bg-[#0d1016] overflow-y-auto">
      <div className="p-5 space-y-5">
        {/* Top summary cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <SummaryCard
            icon={Wallet}
            label="포트폴리오 평가 손익"
            value={`$${totalPl.toLocaleString()}`}
            sub={`수익률 ${totalReturn >= 0 ? "+" : ""}${totalReturn.toFixed(2)}%`}
            positive={totalPl >= 0}
          />
          <SummaryCard
            icon={Activity}
            label="오늘 모니터 중인 사건"
            value={`${events.length}건`}
            sub="고신뢰 공식 발표 4건"
          />
          <SummaryCard
            icon={Target}
            label="확인이 필요한 시나리오"
            value={`${alerts.length}건`}
            sub="다음 7일 이내 결정 이벤트"
          />
          <SummaryCard
            icon={AlertCircle}
            label="위험 신호"
            value={`${events.filter((e) => e.status === "At Risk").length}건`}
            sub="포지션과 직접 연결됨"
            positive={false}
          />
        </div>

        {/* Main dashboard grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Portfolio positions */}
          <div className="lg:col-span-1 bg-panel border border-border rounded-lg p-4">
            <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
              <Wallet className="w-4 h-4 text-accent" /> 내 포지션
            </h3>
            <div className="space-y-3">
              {positions.map((pos) => (
                <PositionRow key={pos.ticker} pos={pos} onClick={() => pos.exposureEvents[0] && onSelectEvent(pos.exposureEvents[0])} />
              ))}
            </div>
          </div>

          {/* Scenario probability board */}
          <div className="lg:col-span-2 bg-panel border border-border rounded-lg p-4">
            <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
              <Target className="w-4 h-4 text-accent" /> 관심 가설별 시나리오 확률
            </h3>
            <div className="space-y-4">
              {events.slice(0, 5).map((e) => (
                <ScenarioBar key={e.id} event={e} onClick={() => onSelectEvent(e.id)} />
              ))}
            </div>
          </div>
        </div>

        {/* Confirmation alerts */}
        <div className="bg-panel border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
            <Calendar className="w-4 h-4 text-accent" /> 이번 주에 확인해야 할 이벤트
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {alerts.map((alert) => {
              const ev = events.find((e) => e.id === alert.eventId);
              return (
                <button
                  key={`${alert.eventId}-${alert.scenario}`}
                  onClick={() => ev && onSelectEvent(ev.id)}
                  className="text-left border border-border rounded-md p-3 hover:bg-panel-hover transition-colors"
                >
                  <div className="text-xs font-medium text-foreground mb-1">{ev?.titleKo}</div>
                  <div className="text-[10px] text-accent-amber mb-2">{alert.scenario} 시나리오 · {alert.deadline}까지</div>
                  <div className="text-xs text-muted mb-1.5">확인 포인트: {alert.whatToWatch}</div>
                  <div className="text-[10px] text-accent-green">확인 시: {alert.impactIfConfirmed}</div>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ icon: Icon, label, value, sub, positive }: { icon: any; label: string; value: string; sub: string; positive?: boolean }) {
  return (
    <div className="bg-panel border border-border rounded-lg p-4">
      <div className="flex items-center gap-2 text-muted text-[11px] uppercase tracking-wider mb-2">
        <Icon className="w-3.5 h-3.5" /> {label}
      </div>
      <div className={`text-2xl font-semibold ${positive === true ? "text-accent-green" : positive === false ? "text-accent-red" : "text-foreground"}`}>
        {value}
      </div>
      <div className="text-xs text-muted mt-1">{sub}</div>
    </div>
  );
}

function toNum(v: any): number {
  if (v === null || v === undefined || v === "") return 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function PositionRow({ pos, onClick }: { pos: PortfolioPosition; onClick: () => void }) {
  const plPercent = toNum(pos.plPercent);
  const plUsd = toNum(pos.plUsd);
  const isProfit = plPercent >= 0;
  return (
    <button onClick={onClick} className="w-full flex items-center justify-between p-3 rounded-md border border-border hover:bg-panel-hover transition-colors text-left">
      <div>
        <div className="text-sm font-semibold text-foreground">{pos.ticker}</div>
        <div className="text-[10px] text-muted">{pos.name} · {toNum(pos.shares)}주</div>
      </div>
      <div className="text-right">
        <div className={`text-sm font-semibold ${isProfit ? "text-accent-green" : "text-accent-red"}`}>
          {isProfit ? "+" : ""}{plPercent.toFixed(1)}%
        </div>
        <div className="text-[10px] text-muted">{isProfit ? "+" : ""}${plUsd.toLocaleString()}</div>
      </div>
    </button>
  );
}

function ScenarioBar({ event, onClick }: { event: Event; onClick: () => void }) {
  const bull = event.scenarios.find((s) => s.name === "Bull")?.probability || 0;
  const base = event.scenarios.find((s) => s.name === "Base")?.probability || 0;
  const bear = event.scenarios.find((s) => s.name === "Bear")?.probability || 0;
  const bullPrev = event.scenarios.find((s) => s.name === "Bull")?.prevProbability;
  const bearPrev = event.scenarios.find((s) => s.name === "Bear")?.prevProbability;

  return (
    <button onClick={onClick} className="w-full text-left group">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium text-foreground">{event.titleKo}</span>
        <span className="text-[10px] text-muted">{event.sectorKo}</span>
      </div>
      <div className="flex h-2.5 rounded-full overflow-hidden bg-panel-hover border border-border">
        <div className="h-full bg-accent-green" style={{ width: `${bull * 100}%` }} />
        <div className="h-full bg-accent-amber" style={{ width: `${base * 100}%` }} />
        <div className="h-full bg-accent-red" style={{ width: `${bear * 100}%` }} />
      </div>
      <div className="flex items-center gap-3 mt-1.5 text-[10px]">
        <span className="text-accent-green">Bull {(bull * 100).toFixed(0)}%{bullPrev !== undefined && bullPrev !== bull ? ` (${bull > bullPrev ? "▲" : "▼"}${Math.abs((bull - bullPrev) * 100).toFixed(0)})` : ""}</span>
        <span className="text-accent-amber">Base {(base * 100).toFixed(0)}%</span>
        <span className="text-accent-red">Bear {(bear * 100).toFixed(0)}%{bearPrev !== undefined && bearPrev !== bear ? ` (${bear > bearPrev ? "▲" : "▼"}${Math.abs((bear - bearPrev) * 100).toFixed(0)})` : ""}</span>
      </div>
    </button>
  );
}
