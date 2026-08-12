"use client";

import { useMemo, useState } from "react";
import { Event, CausalEdge, PortfolioPosition } from "../types";
import {
  FileText, TrendingUp, TrendingDown, Clock, BarChart3,
  AlertTriangle, CheckCircle, XCircle, HelpCircle, Target
} from "lucide-react";

interface ReplayViewProps {
  events: Event[];
  edges: CausalEdge[];
  positions: PortfolioPosition[];
  onSelectEvent: (id: string) => void;
}

interface FailureRecord {
  id: string;
  thesisId: string;
  thesisTitle: string;
  failureType: string;
  failureTypeKo: string;
  description: string;
  descriptionKo: string;
  occurredAt: string;
  preventable: boolean;
}

// Mock failure data for now — in production from POST /engine/post-mortem
const MOCK_FAILURES: FailureRecord[] = [
  {
    id: "fail-001",
    thesisId: "thesis-001",
    thesisTitle: "전기차 배터리 국내 생산 보조금",
    failureType: "TIMING_ERROR",
    failureTypeKo: "타이밍 오류",
    description: "올바른 인과 경로였으나 이미 시장에 반영됨",
    descriptionKo: "인과 경로는 맞았지만, 보조금 발표 전 이미 가격에 반영되어 있었습니다.",
    occurredAt: "2026-07-01T14:30:00Z",
    preventable: true,
  },
  {
    id: "fail-002",
    thesisId: "thesis-002",
    thesisTitle: "TSMC 투자 삭감 → 반도체 장비주",
    failureType: "EVIDENCE_ERROR",
    failureTypeKo: "증거 오류",
    description: "투자 삭감이 일시적 요인이었음",
    descriptionKo: "투자 삭감이 구조적 변화가 아닌 일시적 재고 조정이었습니다.",
    occurredAt: "2026-07-02T09:15:00Z",
    preventable: true,
  },
];

const FAILURE_TYPE_META: Record<string, { icon: any; color: string; label: string }> = {
  EVIDENCE_ERROR: { icon: FileText, color: "#d29922", label: "증거 오류" },
  ENTITY_ERROR: { icon: HelpCircle, color: "#e16a2e", label: "엔티티 오류" },
  MECHANISM_ERROR: { icon: BarChart3, color: "#a371f7", label: "인과 경로 오류" },
  TIMING_ERROR: { icon: Clock, color: "#58a6ff", label: "타이밍 오류" },
  REGIME_ERROR: { icon: Target, color: "#f0883e", label: "국면 오류" },
  EXECUTION_ERROR: { icon: XCircle, color: "#d73a49", label: "실행 오류" },
};

export default function ReplayView({ events, edges, positions, onSelectEvent }: ReplayViewProps) {
  const [activeTab, setActiveTab] = useState<"scorecard" | "failures" | "event-study">("scorecard");
  const [selectedFailure, setSelectedFailure] = useState<string | null>(null);

  // Hypothesis scorecard
  const scorecard = useMemo(() => {
    const totalEvents = events.length;
    const highEvidence = events.filter((e) => e.evidenceGrade === "E4" || e.evidenceGrade === "E3").length;
    const atRisk = events.filter((e) => e.status === "At Risk" || e.status === "Invalidated").length;
    const withMechanism = events.filter((e) => e.mechanismKo && e.mechanismKo.length > 0).length;
    const withCounterevidence = events.filter((e) => e.counterevidenceKo && e.counterevidenceKo.length > 0).length;

    return {
      totalEvents,
      highEvidence,
      highEvidencePct: totalEvents > 0 ? (highEvidence / totalEvents) * 100 : 0,
      atRisk,
      totalEdges: edges.length,
      withMechanism,
      mechanismCoverage: totalEvents > 0 ? (withMechanism / totalEvents) * 100 : 0,
      withCounterevidence,
      positionsCount: positions.length,
    };
  }, [events, edges, positions]);

  // Event study mock data — by event family
  const eventFamilies = useMemo(() => {
    const families = new Map<string, Event[]>();
    for (const e of events) {
      const family = e.eventType || "other";
      if (!families.has(family)) families.set(family, []);
      families.get(family)!.push(e);
    }

    return Array.from(families.entries()).map(([family, evs]) => ({
      family,
      label: eventTypeLabel(family),
      count: evs.length,
      avgEvidence: evs.filter((e) => e.evidenceGrade === "E4" || e.evidenceGrade === "E3").length,
      atRisk: evs.filter((e) => e.status === "At Risk").length,
    }));
  }, [events]);

  const selectedFail = MOCK_FAILURES.find((f) => f.id === selectedFailure);

  return (
    <div className="flex flex-col h-full bg-[#0d1016] overflow-hidden">
      {/* Tab bar */}
      <div className="flex-shrink-0 border-b border-border bg-panel px-4">
        <div className="flex gap-1">
          {[
            { id: "scorecard" as const, label: "가설 스코어카드", icon: CheckCircle },
            { id: "failures" as const, label: "실패 분석", icon: AlertTriangle },
            { id: "event-study" as const, label: "이벤트 스터디", icon: BarChart3 },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? "border-accent text-foreground"
                  : "border-transparent text-muted hover:text-foreground"
              }`}
            >
              <tab.icon className="w-3.5 h-3.5" />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        {activeTab === "scorecard" && (
          <div className="space-y-5">
            {/* Summary metrics */}
            <div className="grid grid-cols-3 gap-4">
              <MetricCard
                label="전체 가설"
                value={`${scorecard.totalEvents}건`}
                sub={`고증거 ${scorecard.highEvidence}건 (${scorecard.highEvidencePct.toFixed(0)}%)`}
              />
              <MetricCard
                label="인과경로 완성도"
                value={`${scorecard.mechanismCoverage.toFixed(0)}%`}
                sub={`${scorecard.withMechanism}건 메커니즘 설명`}
              />
              <MetricCard
                label="반대 증거"
                value={`${scorecard.withCounterevidence}건`}
                sub="반례 존재 가설"
              />
            </div>

            {/* Event family breakdown */}
            <div className="bg-panel border border-border rounded-lg p-4">
              <h3 className="text-sm font-semibold text-foreground mb-4">
                이벤트 패밀리별 현황
              </h3>
              <div className="space-y-2">
                {eventFamilies.map((fam) => (
                  <div
                    key={fam.family}
                    className="flex items-center justify-between border border-border rounded-md p-3"
                  >
                    <div>
                      <div className="text-sm font-medium text-foreground">{fam.label}</div>
                      <div className="text-[10px] text-muted">
                        {fam.count}건 · 고증거 {fam.avgEvidence}건
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <div className="text-xs text-muted">위험</div>
                        <div className={`text-sm font-semibold ${fam.atRisk > 0 ? "text-accent-red" : "text-accent-green"}`}>
                          {fam.atRisk}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Learning insights */}
            <div className="bg-panel border border-border rounded-lg p-4">
              <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
                <Target className="w-4 h-4 text-accent" /> 다중 검정 방어
              </h3>
              <div className="text-xs text-muted space-y-2">
                <p>
                  이벤트 조합을 대량으로 탐색하면 우연 패턴이 발생합니다. 
                  Discovery / Validation / Paper-Live를 분리하고, 
                  PBO(Probability of Backtest Overfitting)와 DSR(Deflated Sharpe Ratio)로 
                  성과 부풀림을 점검합니다.
                </p>
                <div className="flex gap-3 mt-2">
                  <div className="flex-1 border border-border rounded-md p-2 text-center">
                    <div className="text-[10px] text-muted uppercase">시도 횟수</div>
                    <div className="text-lg font-semibold text-foreground">{scorecard.totalEvents}</div>
                  </div>
                  <div className="flex-1 border border-border rounded-md p-2 text-center">
                    <div className="text-[10px] text-muted uppercase">검증 분리</div>
                    <div className="text-lg font-semibold text-accent-green">적용됨</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "failures" && (
          <div className="flex gap-5 h-full">
            {/* Failure list */}
            <div className="w-80 flex-shrink-0 space-y-2">
              {MOCK_FAILURES.map((f) => {
                const meta = FAILURE_TYPE_META[f.failureType] || FAILURE_TYPE_META.EVIDENCE_ERROR;
                return (
                  <button
                    key={f.id}
                    onClick={() => setSelectedFailure(f.id)}
                    className={`w-full text-left border rounded-md p-3 transition-colors ${
                      selectedFailure === f.id
                        ? "border-accent bg-accent/5"
                        : "border-border hover:bg-panel-hover"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <meta.icon className="w-3.5 h-3.5" style={{ color: meta.color }} />
                      <span className="text-xs font-medium text-foreground">{meta.label}</span>
                      {f.preventable && (
                        <span className="ml-auto text-[10px] text-accent-green">예방 가능</span>
                      )}
                    </div>
                    <div className="text-xs text-foreground mb-0.5">{f.thesisTitle}</div>
                    <div className="text-[10px] text-muted">
                      {new Date(f.occurredAt).toLocaleDateString("ko-KR")}
                    </div>
                  </button>
                );
              })}
              {MOCK_FAILURES.length === 0 && (
                <div className="text-sm text-muted text-center py-8">
                  분석된 실패 사례가 아직 없습니다.
                </div>
              )}
            </div>

            {/* Failure detail */}
            <div className="flex-1">
              {selectedFail ? (
                <div className="bg-panel border border-border rounded-lg p-4 space-y-4">
                  <div>
                    <div className="text-[10px] text-muted uppercase tracking-wider mb-1">
                      {FAILURE_TYPE_META[selectedFail.failureType]?.label}
                    </div>
                    <h3 className="text-sm font-semibold text-foreground">
                      {selectedFail.thesisTitle}
                    </h3>
                  </div>

                  <div className="border border-accent-red/30 bg-accent-red/5 rounded-md p-3">
                    <div className="text-xs font-medium text-accent-red mb-1">실패 원인</div>
                    <div className="text-xs text-foreground">{selectedFail.descriptionKo}</div>
                  </div>

                  <div>
                    <div className="text-[10px] font-semibold text-muted uppercase mb-2">
                      교훈
                    </div>
                    <div className="space-y-2">
                      <div className="text-xs text-foreground border border-border rounded-md p-2.5">
                        {selectedFail.failureType === "EVIDENCE_ERROR" &&
                          "향후 유사 가설에서는 반대 증거를 더 높은 가중치로 반영해야 합니다. 원문/수치/조건을 재확인하는 검증 단계를 추가하세요."}
                        {selectedFail.failureType === "TIMING_ERROR" &&
                          "타이밍이 맞았더라도 먼저 외부 센서의 반응을 확인하세요. 이미 반영된 정보에 후행 진입하지 않도록 Assimilation 체크를 강화하세요."}
                        {selectedFail.failureType === "MECHANISM_ERROR" &&
                          "인과 경로의 중간 메커니즘을 더 구체적으로 검증해야 합니다. 공급망·계약조건·대체재 여부를 확인하세요."}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 text-[10px] text-muted">
                    <span>
                      {new Date(selectedFail.occurredAt).toLocaleString("ko-KR")}
                    </span>
                    <span className={selectedFail.preventable ? "text-accent-green" : "text-accent-amber"}>
                      {selectedFail.preventable ? "예방 가능" : "구조적 한계"}
                    </span>
                  </div>
                </div>
              ) : (
                <div className="h-full flex items-center justify-center text-muted text-sm">
                  실패 사례를 선택하면 상세 분석이 표시됩니다.
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === "event-study" && (
          <div className="space-y-4">
            {eventFamilies.map((fam) => (
              <div
                key={fam.family}
                className="bg-panel border border-border rounded-lg p-4"
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-foreground">{fam.label}</h3>
                  <span className="text-[10px] text-muted">{fam.count}건</span>
                </div>
                <div className="grid grid-cols-4 gap-3 text-center">
                  <div className="border border-border rounded-md p-2">
                    <div className="text-[10px] text-muted uppercase">표본</div>
                    <div className="text-lg font-semibold text-foreground">{fam.count}</div>
                  </div>
                  <div className="border border-border rounded-md p-2">
                    <div className="text-[10px] text-muted uppercase">고증거</div>
                    <div className="text-lg font-semibold text-accent-green">{fam.avgEvidence}</div>
                  </div>
                  <div className="border border-border rounded-md p-2">
                    <div className="text-[10px] text-muted uppercase">리스크</div>
                    <div className="text-lg font-semibold text-accent-red">{fam.atRisk}</div>
                  </div>
                  <div className="border border-border rounded-md p-2">
                    <div className="text-[10px] text-muted uppercase">성공률</div>
                    <div className="text-lg font-semibold text-foreground">
                      {fam.count > 0
                        ? `${(((fam.count - fam.atRisk) / fam.count) * 100).toFixed(0)}%`
                        : "N/A"}
                    </div>
                  </div>
                </div>
              </div>
            ))}

            {eventFamilies.length === 0 && (
              <div className="text-sm text-muted text-center py-12">
                이벤트 데이터가 충분하지 않아 이벤트 스터디를 수행할 수 없습니다.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function MetricCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="bg-panel border border-border rounded-lg p-4">
      <div className="text-[10px] text-muted uppercase tracking-wider mb-1">{label}</div>
      <div className="text-xl font-semibold text-foreground">{value}</div>
      <div className="text-xs text-muted mt-0.5">{sub}</div>
    </div>
  );
}

function eventTypeLabel(type: string) {
  const map: Record<string, string> = {
    policy_announcement: "정책 발표",
    filing: "공시",
    earnings: "실적",
    macro: "매크로",
    supply_chain: "공급망",
    regulatory: "규제",
    prediction_market: "예측시장",
  };
  return map[type] || type;
}
