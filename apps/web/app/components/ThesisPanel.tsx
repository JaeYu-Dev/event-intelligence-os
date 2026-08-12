"use client";

import { useEffect, useState } from "react";
import { X, FileText, AlertTriangle, Calendar, TrendingUp, TrendingDown, Minus, Plus, Briefcase } from "lucide-react";
import { Event } from "../types";
import { createThesisFromEvent, reassessThesis, createPaperTrade } from "../lib/api";

interface ThesisPanelProps {
  event: Event | null;
  onClose: () => void;
}

export default function ThesisPanel({ event, onClose }: ThesisPanelProps) {
  const [thesis, setThesis] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [tradeTicker, setTradeTicker] = useState("");
  const [tradeAction, setTradeAction] = useState<"BUY" | "SELL">("BUY");
  const [tradeShares, setTradeShares] = useState("");
  const [tradePrice, setTradePrice] = useState("");

  useEffect(() => {
    setThesis(null);
    setMessage("");
    setTradeTicker(event?.relatedTickers?.[0] || "");
  }, [event?.id]);

  async function handleCreateThesis() {
    if (!event) return;
    setLoading(true);
    try {
      const data = await createThesisFromEvent(event.id);
      setThesis(data.thesis);
      setMessage("가설로 등록되었습니다.");
    } catch (e: any) {
      setMessage(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleReassess(status: string, action: string) {
    if (!thesis) return;
    setLoading(true);
    try {
      const data = await reassessThesis(thesis.id, { status, action });
      setThesis(data.thesis);
      setMessage(`상태를 ${status}로 변경했습니다.`);
    } catch (e: any) {
      setMessage(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handlePaperTrade(e: React.FormEvent) {
    e.preventDefault();
    if (!thesis || !event) return;
    setLoading(true);
    try {
      await createPaperTrade({
        thesis_id: thesis.id,
        ticker: tradeTicker || event.relatedTickers[0] || "CASH",
        action: tradeAction,
        shares: parseFloat(tradeShares),
        price: parseFloat(tradePrice),
      });
      setMessage("모의 거래가 기록되었습니다.");
      setTradeShares("");
      setTradePrice("");
    } catch (err: any) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (!event) {
    return (
      <div className="w-80 flex-shrink-0 bg-panel border-l border-border flex flex-col items-center justify-center text-muted p-6 text-center">
        <FileText className="w-10 h-10 mb-3 opacity-40" />
        <p className="text-sm">이벤트를 선택하면<br />시나리오와 인과 메커니즘을 볼 수 있어요.</p>
      </div>
    );
  }

  return (
    <div className="w-80 flex-shrink-0 bg-panel border-l border-border flex flex-col h-full overflow-hidden">
      <div className="flex items-start justify-between p-4 border-b border-border">
        <div>
          <div className="text-[10px] text-muted uppercase tracking-wider mb-1">{event.id} · {event.sectorKo}</div>
          <h2 className="text-sm font-semibold text-foreground leading-snug">{event.titleKo}</h2>
        </div>
        <button onClick={onClose} className="text-muted hover:text-foreground p-1">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {message && (
          <div className="text-[11px] p-2 rounded-md bg-accent/10 text-accent border border-accent/20">{message}</div>
        )}

        <div className="flex flex-wrap gap-2">
          <MetaBadge label="증거 등급" value={event.evidenceGrade} />
          <MetaBadge label="긴급도" value={urgencyLabel(event.urgency)} />
          <MetaBadge label="상태" value={thesis?.status || statusLabel(event.status)} />
          <MetaBadge label="액션" value={thesis?.action || actionLabel(event.actionRequired)} />
        </div>

        <div>
          <h3 className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-2">왜 이 사건이 중요한가?</h3>
          <p className="text-sm text-foreground leading-relaxed bg-panel-hover border border-border rounded-md p-3">
            {event.mechanismKo}
          </p>
        </div>

        <div>
          <h3 className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-2">시나리오</h3>
          <div className="space-y-2">
            {event.scenarios.map((s) => (
              <div key={s.name} className="border border-border rounded-md p-3 bg-panel-hover">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    {s.name === "Bull" ? <TrendingUp className="w-3.5 h-3.5 text-accent-green" /> : s.name === "Bear" ? <TrendingDown className="w-3.5 h-3.5 text-accent-red" /> : <Minus className="w-3.5 h-3.5 text-accent-amber" />}
                    <span className="text-sm font-semibold text-foreground">{scenarioLabel(s.name)}</span>
                  </div>
                  <span className="text-sm font-semibold text-foreground">{(s.probability * 100).toFixed(0)}%</span>
                </div>
                <div className="text-xs text-accent-amber mb-1.5">예상 수익률 {s.priceRange}</div>
                <ul className="space-y-1">
                  {s.conditions.map((c, i) => (
                    <li key={i} className="text-[11px] text-muted flex items-start gap-1.5">
                      <span className="text-accent">•</span> {c}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h3 className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> 반대 증거
          </h3>
          <ul className="space-y-1.5">
            {event.counterevidenceKo.map((c, i) => (
              <li key={i} className="text-xs text-foreground bg-accent-red/10 border border-accent-red/20 rounded-md p-2">
                {c}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <Calendar className="w-3.5 h-3.5" /> 다음 확인 이벤트
          </h3>
          <ul className="space-y-1.5">
            {event.nextEventsKo.map((e, i) => (
              <li key={i} className="text-xs text-foreground border border-border rounded-md p-2 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-accent-blue" />
                {e}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-2">관련 종목</h3>
          <div className="flex flex-wrap gap-1.5">
            {event.relatedTickers.map((t) => (
              <span key={t} className="px-2 py-1 rounded-md bg-panel-hover border border-border text-xs text-foreground">{t}</span>
            ))}
          </div>
        </div>

        {thesis && (
          <div className="border border-border rounded-md p-3 bg-panel-hover">
            <h3 className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Briefcase className="w-3.5 h-3.5" /> 모의 거래 기록
            </h3>
            <form onSubmit={handlePaperTrade} className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="text"
                  value={tradeTicker}
                  onChange={(e) => setTradeTicker(e.target.value)}
                  placeholder="종목"
                  className="bg-background border border-border rounded-md px-2 py-1.5 text-xs"
                />
                <select
                  value={tradeAction}
                  onChange={(e) => setTradeAction(e.target.value as "BUY" | "SELL")}
                  className="bg-background border border-border rounded-md px-2 py-1.5 text-xs"
                >
                  <option value="BUY">매수</option>
                  <option value="SELL">매도</option>
                </select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="number"
                  value={tradeShares}
                  onChange={(e) => setTradeShares(e.target.value)}
                  placeholder="수량"
                  className="bg-background border border-border rounded-md px-2 py-1.5 text-xs"
                />
                <input
                  type="number"
                  step="0.01"
                  value={tradePrice}
                  onChange={(e) => setTradePrice(e.target.value)}
                  placeholder="가격"
                  className="bg-background border border-border rounded-md px-2 py-1.5 text-xs"
                />
              </div>
              <button
                type="submit"
                disabled={loading || !tradeShares || !tradePrice}
                className="w-full py-1.5 rounded-md bg-accent hover:bg-accent/90 disabled:opacity-50 text-white text-xs font-semibold flex items-center justify-center gap-1"
              >
                <Plus className="w-3 h-3" /> 모의 거래 추가
              </button>
            </form>
          </div>
        )}
      </div>

      <div className="p-3 border-t border-border flex gap-2">
        {thesis ? (
          <>
            <button
              onClick={() => handleReassess("Watching", "WATCH")}
              disabled={loading}
              className="flex-1 py-2 rounded-md border border-border hover:bg-panel-hover text-foreground text-xs font-semibold"
            >
              지켜보기
            </button>
            <button
              onClick={() => handleReassess("Paper Active", "PAPER_TRADE")}
              disabled={loading}
              className="flex-1 py-2 rounded-md bg-accent hover:bg-accent/90 text-white text-xs font-semibold"
            >
              모의 거래
            </button>
          </>
        ) : (
          <button
            onClick={handleCreateThesis}
            disabled={loading}
            className="flex-1 py-2 rounded-md bg-accent hover:bg-accent/90 text-white text-xs font-semibold"
          >
            이 가설로 등록
          </button>
        )}
      </div>
    </div>
  );
}

function MetaBadge({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-2 py-1 rounded-md bg-panel-hover border border-border">
      <div className="text-[9px] text-muted uppercase">{label}</div>
      <div className="text-xs font-medium text-foreground">{value}</div>
    </div>
  );
}

function urgencyLabel(u: Event["urgency"]) {
  return { Low: "낮음", Medium: "보통", High: "높음", Critical: "심각" }[u];
}

function statusLabel(s: Event["status"]) {
  return { Active: "활성", Strengthening: "강화 중", "At Risk": "위험", Invalidated: "무효화", Resolved: "해결", Watching: "관찰 중" }[s];
}

function actionLabel(a: Event["actionRequired"]) {
  return { "Research Required": "리서치 필요", Watch: "지켜보기", "Paper Trade": "모의 거래", Reduce: "축소 검토", Hold: "유지" }[a];
}

function scenarioLabel(name: "Bull" | "Base" | "Bear") {
  return { Bull: "강세", Base: "기본", Bear: "약세" }[name];
}
