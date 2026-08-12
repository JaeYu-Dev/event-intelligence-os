"use client";

import { useMemo } from "react";
import {
  Wallet, TrendingUp, TrendingDown, AlertTriangle, Calendar,
  Shield, Layers, PieChart, Target
} from "lucide-react";
import { Event, PortfolioPosition } from "../types";

interface PortfolioViewProps {
  positions: PortfolioPosition[];
  events: Event[];
  onSelectEvent: (id: string) => void;
  onSelectPosition?: (pos: PortfolioPosition) => void;
}

// Pre-configured latent factors from the spec
const LATENT_FACTORS: Record<string, { name: string; nameKo: string; sensors: string[]; relatedSectors: string[] }> = {
  "rate_cut_expectation": {
    name: "Rate Cut Expectation",
    nameKo: "금리 인하 기대",
    sensors: ["TLT", "GLD", "QQQ"],
    relatedSectors: ["Macro / Rates", "Semiconductors"],
  },
  "ai_capex_expectation": {
    name: "AI Capex Expectation",
    nameKo: "AI 투자 기대",
    sensors: ["NVDA", "SMH"],
    relatedSectors: ["Semiconductors", "Cybersecurity / Cloud"],
  },
  "energy_supply_tightness": {
    name: "Energy Supply Tightness",
    nameKo: "에너지 공급 타이트니스",
    sensors: ["XLE", "XOM", "USO"],
    relatedSectors: ["Energy", "CleanTech / Battery"],
  },
  "regulatory_approval_probability": {
    name: "Regulatory Approval Probability",
    nameKo: "규제 승인 확률",
    sensors: ["XBI", "IBB"],
    relatedSectors: ["Biotech"],
  },
  "supply_chain_disruption_severity": {
    name: "Supply Chain Disruption",
    nameKo: "공급망 차질",
    sensors: ["FCX", "COPX"],
    relatedSectors: ["Materials"],
  },
  "risk_appetite": {
    name: "Risk Appetite",
    nameKo: "위험 선호도",
    sensors: ["SPY", "VIX"],
    relatedSectors: ["Macro / Rates", "Biotech"],
  },
};

export default function PortfolioView({ positions, events, onSelectEvent, onSelectPosition }: PortfolioViewProps) {
  // Compute holdings data
  const holdings = useMemo(() => {
    return positions.map((pos) => {
      const linkedEvents = (pos.exposureEvents || [])
        .map((eid) => events.find((e) => e.id === eid))
        .filter(Boolean) as Event[];

      return {
        ...pos,
        plPercent: pos.plPercent ?? 0,
        plUsd: pos.plUsd ?? 0,
        currentValue: (pos.currentPrice ?? 0) * (pos.shares ?? 0),
        linkedEvents,
      };
    });
  }, [positions, events]);

  // Compute factor exposure
  const factorExposure = useMemo(() => {
    const exposure: Record<string, {
      factor: typeof LATENT_FACTORS[string];
      totalValue: number;
      positions: Array<{ ticker: string; value: number; bias: string }>;
      linkedEvents: Event[];
      concentrationPct: number;
    }> = {};

    const totalPortfolioValue = holdings.reduce((sum, h) => sum + h.currentValue, 0);

    for (const [factorId, factor] of Object.entries(LATENT_FACTORS)) {
      const matchingTickers = new Set(factor.sensors.map((s) => s.toUpperCase()));
      const matchingSectors = new Set(factor.relatedSectors.map((s) => s.toLowerCase()));

      let factorValue = 0;
      const factorPositions: Array<{ ticker: string; value: number; bias: string }> = [];
      const factorEvents: Event[] = [];

      for (const h of holdings) {
        const ticker = (h.ticker || "").toUpperCase();
        const linkedToFactor = h.linkedEvents.some((e) => {
          const sectorLower = (e.sector || "").toLowerCase();
          return matchingSectors.has(sectorLower) || matchingTickers.has(ticker);
        });

        if (linkedToFactor || matchingTickers.has(ticker)) {
          factorValue += h.currentValue;
          factorPositions.push({
            ticker: h.ticker || "",
            value: h.currentValue,
            bias: h.scenarioBias || "Base",
          });
          for (const ev of h.linkedEvents) {
            if (!factorEvents.find((fe) => fe.id === ev.id)) {
              factorEvents.push(ev);
            }
          }
        }
      }

      if (factorPositions.length > 0) {
        exposure[factorId] = {
          factor,
          totalValue: factorValue,
          positions: factorPositions,
          linkedEvents: factorEvents,
          concentrationPct: totalPortfolioValue > 0 ? (factorValue / totalPortfolioValue) * 100 : 0,
        };
      }
    }

    return exposure;
  }, [holdings]);

  const totalPl = holdings.reduce((sum, h) => sum + (h.plUsd ?? 0), 0);
  const totalValue = holdings.reduce((sum, h) => sum + h.currentValue, 0);
  const totalReturn = totalValue > 0 ? (totalPl / (totalValue - totalPl)) * 100 : 0;

  // Events with upcoming risk in next 7 days
  const upcomingRiskEvents = useMemo(() => {
    const now = new Date();
    const nextWeek = new Date(now.getTime() + 7 * 86400000);
    return events.filter((e) => {
      if (!e.effectiveDate) return false;
      const d = new Date(e.effectiveDate);
      return d >= now && d <= nextWeek;
    });
  }, [events]);

  return (
    <div className="flex flex-col h-full bg-[#0d1016] overflow-y-auto">
      <div className="p-5 space-y-5">
        {/* Summary bar */}
        <div className="grid grid-cols-4 gap-4">
          <SummaryBox
            icon={Wallet}
            label="총 평가액"
            value={`$${totalValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
            sub={`손익 ${totalReturn >= 0 ? "+" : ""}${totalReturn.toFixed(2)}%`}
            positive={totalPl >= 0}
          />
          <SummaryBox
            icon={Layers}
            label="팩터 노출"
            value={`${Object.keys(factorExposure).length}개`}
            sub={`${holdings.length}개 포지션`}
          />
          <SummaryBox
            icon={Calendar}
            label="향후 7일 이벤트"
            value={`${upcomingRiskEvents.length}건`}
            sub="리스크 노출 이벤트"
          />
          <SummaryBox
            icon={Shield}
            label="집중 위험"
            value={(() => {
              const maxConc = Math.max(...Object.values(factorExposure).map((f) => f.concentrationPct), 0);
              return `${maxConc.toFixed(1)}%`;
            })()}
            sub="최대 단일 팩터"
            positive={false}
          />
        </div>

        {/* Main layout */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
          {/* Left: Factor exposure */}
          <div className="lg:col-span-3 bg-panel border border-border rounded-lg p-4">
            <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
              <PieChart className="w-4 h-4 text-accent" /> 원인 노출 (Causal Exposure)
            </h3>
            <div className="space-y-4">
              {Object.entries(factorExposure)
                .sort((a, b) => b[1].concentrationPct - a[1].concentrationPct)
                .map(([factorId, exp]) => (
                  <div key={factorId} className="border border-border rounded-md p-3">
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <div className="text-sm font-semibold text-foreground">
                          {exp.factor.nameKo}
                        </div>
                        <div className="text-[10px] text-muted">{exp.factor.name}</div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-semibold text-foreground">
                          ${exp.totalValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        </div>
                        <div
                          className={`text-[10px] ${
                            exp.concentrationPct > 30 ? "text-accent-red" : "text-muted"
                          }`}
                        >
                          {exp.concentrationPct.toFixed(1)}% 집중
                        </div>
                      </div>
                    </div>

                    {/* Concentration bar */}
                    <div className="h-2 rounded-full bg-panel-hover border border-border mb-2">
                      <div
                        className={`h-full rounded-full transition-all ${
                          exp.concentrationPct > 30
                            ? "bg-accent-red"
                            : exp.concentrationPct > 15
                            ? "bg-accent-amber"
                            : "bg-accent-green"
                        }`}
                        style={{ width: `${Math.min(exp.concentrationPct, 100)}%` }}
                      />
                    </div>

                    {/* Linked positions + events */}
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {exp.positions.map((p) => (
                        <span
                          key={p.ticker}
                          className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                            p.bias === "Bull"
                              ? "bg-accent-green/15 text-accent-green"
                              : p.bias === "Bear"
                              ? "bg-accent-red/15 text-accent-red"
                              : "bg-panel-hover text-muted"
                          }`}
                        >
                          {p.ticker} ({p.bias === "Bull" ? "▲" : p.bias === "Bear" ? "▼" : "―"})
                        </span>
                      ))}
                    </div>

                    {/* Linked events */}
                    {exp.linkedEvents.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {exp.linkedEvents.slice(0, 3).map((ev) => (
                          <button
                            key={ev.id}
                            onClick={() => onSelectEvent(ev.id)}
                            className="text-[10px] text-accent-blue hover:underline"
                          >
                            {ev.titleKo.length > 20 ? ev.titleKo.slice(0, 20) + "…" : ev.titleKo}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}

              {Object.keys(factorExposure).length === 0 && (
                <div className="text-sm text-muted text-center py-8">
                  포지션을 등록하면 팩터 노출 분석이 표시됩니다.
                </div>
              )}
            </div>
          </div>

          {/* Right: Holdings + Upcoming risk */}
          <div className="lg:col-span-2 space-y-5">
            {/* Holdings list */}
            <div className="bg-panel border border-border rounded-lg p-4">
              <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                <Wallet className="w-4 h-4 text-accent" /> 보유 포지션
              </h3>
              <div className="space-y-2">
                {holdings.map((h) => (
                  <button
                    key={h.ticker}
                    onClick={() => {
                      if (onSelectPosition) {
                        onSelectPosition(h);
                      } else {
                        const ev = h.linkedEvents[0];
                        if (ev) onSelectEvent(ev.id);
                      }
                    }}
                    className="w-full flex items-center justify-between p-2.5 rounded-md border border-border hover:bg-panel-hover transition-colors cursor-pointer text-left"
                  >
                    <div>
                      <div className="text-sm font-semibold text-foreground">{h.ticker}</div>
                      <div className="text-[10px] text-muted">
                        {h.name} · {(h.shares ?? 0).toLocaleString()}주 · ${(h.avgCost ?? 0).toFixed(1)}
                      </div>
                    </div>
                    <div className="text-right">
                      <div
                        className={`text-sm font-semibold ${
                          (h.plPercent ?? 0) >= 0 ? "text-accent-green" : "text-accent-red"
                        }`}
                      >
                        {(h.plPercent ?? 0) >= 0 ? "+" : ""}
                        {(h.plPercent ?? 0).toFixed(1)}%
                      </div>
                      <div className="text-[10px] text-muted">
                        {(h.plUsd ?? 0) >= 0 ? "+" : ""}$
                        {Math.abs(h.plUsd ?? 0).toLocaleString()}
                      </div>
                    </div>
                  </button>
                ))}
                {holdings.length === 0 && (
                  <div className="text-sm text-muted text-center py-4">
                    등록된 포지션이 없습니다.
                  </div>
                )}
              </div>
            </div>

            {/* Upcoming risk events */}
            <div className="bg-panel border border-border rounded-lg p-4">
              <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-accent-red" /> 7일 내 리스크 이벤트
              </h3>
              <div className="space-y-2">
                {upcomingRiskEvents.slice(0, 6).map((ev) => (
                  <button
                    key={ev.id}
                    onClick={() => onSelectEvent(ev.id)}
                    className="w-full text-left border border-border rounded-md p-2.5 hover:bg-panel-hover transition-colors"
                  >
                    <div className="text-xs font-medium text-foreground mb-0.5">{ev.titleKo}</div>
                    <div className="flex items-center gap-2 text-[10px]">
                      <span className="text-accent-amber">
                        {ev.effectiveDate
                          ? new Date(ev.effectiveDate).toLocaleDateString("ko-KR")
                          : "날짜 미정"}
                      </span>
                      <span className="text-muted">{ev.sectorKo}</span>
                      <UrgencyBadge urgency={ev.urgency} />
                    </div>
                  </button>
                ))}
                {upcomingRiskEvents.length === 0 && (
                  <div className="text-sm text-muted text-center py-4">
                    향후 7일 내 리스크 이벤트가 없습니다.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SummaryBox({
  icon: Icon,
  label,
  value,
  sub,
  positive,
}: {
  icon: any;
  label: string;
  value: string;
  sub: string;
  positive?: boolean;
}) {
  return (
    <div className="bg-panel border border-border rounded-lg p-4">
      <div className="flex items-center gap-2 text-muted text-[11px] uppercase tracking-wider mb-2">
        <Icon className="w-3.5 h-3.5" /> {label}
      </div>
      <div
        className={`text-2xl font-semibold ${
          positive === true
            ? "text-accent-green"
            : positive === false
            ? "text-accent-red"
            : "text-foreground"
        }`}
      >
        {value}
      </div>
      <div className="text-xs text-muted mt-1">{sub}</div>
    </div>
  );
}

function UrgencyBadge({ urgency }: { urgency: string }) {
  const labels: Record<string, string> = {
    Low: "낮음",
    Medium: "보통",
    High: "높음",
    Critical: "심각",
  };
  const color =
    urgency === "Critical"
      ? "#d73a49"
      : urgency === "High"
      ? "#e16a2e"
      : urgency === "Medium"
      ? "#d29922"
      : "#8b949e";
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold"
      style={{ backgroundColor: `${color}22`, color }}
    >
      {labels[urgency] || urgency}
    </span>
  );
}
