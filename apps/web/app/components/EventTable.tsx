"use client";

import { Event } from "../types";

interface EventTableProps {
  events: Event[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export default function EventTable({ events, selectedId, onSelect }: EventTableProps) {
  return (
    <div className="flex flex-col h-full bg-panel border-t border-border">
      <div className="flex-1 overflow-auto">
        <table className="w-full text-left border-collapse">
          <thead className="sticky top-0 z-10 bg-panel border-b border-border">
            <tr>
              {["사건", "단계", "주체", "유형", "등급", "긴급도", "상태", "필요 액션", "섹터", "발표일"].map((h) => (
                <th key={h} className="px-3 py-2 text-[10px] font-semibold text-muted uppercase tracking-wider whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr
                key={e.id}
                onClick={() => onSelect(e.id)}
                className={`border-b border-border cursor-pointer transition-colors ${
                  selectedId === e.id ? "bg-accent/10" : "hover:bg-panel-hover"
                }`}
              >
                <td className="px-3 py-2 max-w-xs">
                  <div className="font-medium text-foreground truncate">{e.titleKo}</div>
                  <div className="text-[10px] text-muted truncate">{e.relatedTickers.join(", ")}</div>
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <StageBadge stage={(e as any).eventStage || (e as any).event_stage || "detected"} />
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-foreground">{e.actorKo}</td>
                <td className="px-3 py-2 whitespace-nowrap text-muted">{eventTypeLabel(e.eventType)}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <GradeBadge grade={e.evidenceGrade} />
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <UrgencyBadge urgency={e.urgency} />
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <StatusBadge status={e.status} />
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-foreground">{actionLabel(e.actionRequired)}</td>
                <td className="px-3 py-2 whitespace-nowrap text-muted">{e.sectorKo}</td>
                <td className="px-3 py-2 whitespace-nowrap text-muted">{formatDate(e.publishedAt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function eventTypeLabel(type: Event["eventType"]) {
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

function actionLabel(action: Event["actionRequired"]) {
  const map: Record<string, string> = {
    "Research Required": "리서치 필요",
    Watch: "지켜보기",
    "Paper Trade": "모의 거래",
    Reduce: "축소 검토",
    Hold: "유지",
  };
  return map[action] || action;
}

function GradeBadge({ grade }: { grade: Event["evidenceGrade"] }) {
  const color = grade === "E4" ? "#3fb950" : grade === "E3" ? "#58a6ff" : grade === "E2" ? "#d29922" : "#8b949e";
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold" style={{ backgroundColor: `${color}22`, color }}>
      {grade}
    </span>
  );
}

function UrgencyBadge({ urgency }: { urgency: Event["urgency"] }) {
  const labels = { Low: "낮음", Medium: "보통", High: "높음", Critical: "심각" };
  const color = urgency === "Critical" ? "#d73a49" : urgency === "High" ? "#e16a2e" : urgency === "Medium" ? "#d29922" : "#8b949e";
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold" style={{ backgroundColor: `${color}22`, color }}>
      {labels[urgency]}
    </span>
  );
}

function StatusBadge({ status }: { status: Event["status"] }) {
  const labels = { Active: "활성", Strengthening: "강화 중", "At Risk": "위험", Invalidated: "무효화", Resolved: "해결", Watching: "관찰 중" };
  const color =
    status === "Strengthening" ? "#3fb950" : status === "At Risk" ? "#d73a49" : status === "Active" ? "#58a6ff" : "#8b949e";
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold" style={{ backgroundColor: `${color}22`, color }}>
      {labels[status] || status}
    </span>
  );
}

function StageBadge({ stage }: { stage: string }) {
  const labels: Record<string, string> = {
    detected: "탐지", announcement: "발표", application_submitted: "신청",
    application_accepted: "접수", review_started: "심사", approval: "승인",
    rejection: "거절", commercial_launch: "출시", revenue_confirmation: "매출",
    contract_announcement: "계약", production_start: "생산", shipment: "출하",
    rumor: "루머", official_proposal: "제안", board_approval: "이사회",
    filing: "제소", court_acceptance: "접수", trial: "재판", verdict: "판결",
    settlement: "합의", pre_announcement: "예비", earnings_release: "실적",
    earnings_call: "컨콜", analyst_revision: "수정", bill_introduced: "발의",
    implementation: "시행", corporate_impact: "영향",
  };
  const colors: Record<string, string> = {
    approval: "#3fb950", commercial_launch: "#3fb950", revenue_confirmation: "#3fb950",
    rejection: "#d73a49", rumor: "#d29922", detected: "#8b949e",
    application_submitted: "#58a6ff", application_accepted: "#58a6ff",
    review_started: "#a371f7", announcement: "#d29922",
  };
  const label = labels[stage] || stage;
  const color = colors[stage] || "#8b949e";
  return <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold" style={{ backgroundColor: `${color}22`, color }}>{label}</span>;
}

function formatDate(iso: string) {
  const d = new Date(iso);
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
}
