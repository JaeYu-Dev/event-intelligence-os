"use client";

import { useMemo } from "react";
import {
  Bell, TrendingUp, Calendar, ShieldAlert, Eye, CheckCircle2,
  ExternalLink, AlertTriangle, Clock, Target
} from "lucide-react";
import { Event, ConfirmationAlert } from "../types";

interface AlertsViewProps {
  events: Event[];
  alerts: ConfirmationAlert[];
  onSelectEvent: (id: string) => void;
}

export default function AlertsView({ events, alerts, onSelectEvent }: AlertsViewProps) {
  // Group alerts by urgency
  const grouped = useMemo(() => {
    const critical = alerts.filter((a) => {
      const ev = events.find((e) => e.id === a.eventId);
      return ev?.urgency === "Critical";
    });
    const high = alerts.filter((a) => {
      const ev = events.find((e) => e.id === a.eventId);
      return ev?.urgency === "High";
    });
    const others = alerts.filter((a) => {
      const ev = events.find((e) => e.id === a.eventId);
      return ev?.urgency !== "Critical" && ev?.urgency !== "High";
    });
    return { critical, high, others };
  }, [alerts, events]);

  // Polymarket-linked events
  const polymarketEvents = useMemo(
    () => events.filter((e) => e.eventType === "prediction_market"),
    [events]
  );

  const urgencyConfig: Record<string, { icon: any; color: string; bgColor: string; label: string }> = {
    Critical: { icon: ShieldAlert, color: "#d73a49", bgColor: "#d73a4922", label: "심각" },
    High: { icon: AlertTriangle, color: "#e16a2e", bgColor: "#e16a2e22", label: "높음" },
    Medium: { icon: Bell, color: "#d29922", bgColor: "#d2992222", label: "보통" },
    Low: { icon: Eye, color: "#8b949e", bgColor: "#8b949e22", label: "낮음" },
  };

  return (
    <div className="flex flex-col h-full bg-[#0d1016] overflow-y-auto">
      <div className="p-5 space-y-5">
        {/* Top bar */}
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-panel border border-border rounded-lg p-4">
            <div className="text-[11px] text-muted uppercase tracking-wider mb-1">
              총 알림
            </div>
            <div className="text-2xl font-semibold text-foreground">{alerts.length}건</div>
          </div>
          <div className="bg-panel border border-accent-red/30 rounded-lg p-4">
            <div className="text-[11px] text-muted uppercase tracking-wider mb-1">
              심각
            </div>
            <div className="text-2xl font-semibold text-accent-red">{grouped.critical.length}건</div>
          </div>
          <div className="bg-panel border border-accent-amber/30 rounded-lg p-4">
            <div className="text-[11px] text-muted uppercase tracking-wider mb-1">
              높음
            </div>
            <div className="text-2xl font-semibold text-accent-amber">{grouped.high.length}건</div>
          </div>
          <div className="bg-panel border border-border rounded-lg p-4">
            <div className="text-[11px] text-muted uppercase tracking-wider mb-1">
              Polymarket
            </div>
            <div className="text-2xl font-semibold text-foreground">{polymarketEvents.length}건</div>
          </div>
        </div>

        {/* Alert list */}
        <div className="space-y-3">
          {[...grouped.critical, ...grouped.high, ...grouped.others].map((alert) => {
            const ev = events.find((e) => e.id === alert.eventId);
            const config = urgencyConfig[ev?.urgency || "Low"] || urgencyConfig.Low;
            const UrgencyIcon = config.icon;

            return (
              <button
                key={`${alert.eventId}-${alert.scenario}`}
                onClick={() => onSelectEvent(alert.eventId)}
                className="w-full text-left bg-panel border border-border rounded-lg p-4 hover:bg-panel-hover transition-colors"
              >
                <div className="flex items-start gap-3">
                  <div
                    className="w-8 h-8 rounded-md flex items-center justify-center flex-shrink-0 mt-0.5"
                    style={{ backgroundColor: config.bgColor }}
                  >
                    <UrgencyIcon className="w-4 h-4" style={{ color: config.color }} />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-sm font-semibold text-foreground">
                        {ev?.titleKo || "알 수 없는 이벤트"}
                      </span>
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                        style={{ backgroundColor: config.bgColor, color: config.color }}
                      >
                        {config.label}
                      </span>
                    </div>

                    <div className="text-[10px] text-accent-amber mb-2">
                      {alert.scenario} 시나리오 · {alert.deadline}까지
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <div className="text-[10px] text-muted uppercase mb-0.5">확인 포인트</div>
                        <div className="text-xs text-foreground">{alert.whatToWatch}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-muted uppercase mb-0.5">확인 시 영향</div>
                        <div className="text-xs text-accent-green">{alert.impactIfConfirmed}</div>
                      </div>
                    </div>

                    {ev && (
                      <div className="flex items-center gap-2 mt-2 text-[10px] text-muted">
                        <span>{ev.sectorKo}</span>
                        <span>·</span>
                        <span>증거 {ev.evidenceGrade}</span>
                        <span>·</span>
                        <span className="text-accent-blue">{ev.relatedTickers.slice(0, 3).join(", ")}</span>
                      </div>
                    )}
                  </div>

                  <div className="text-[10px] text-muted flex-shrink-0">
                    <Calendar className="w-3.5 h-3.5" />
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Polymarket section */}
        {polymarketEvents.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-accent" /> Polymarket 확률 센서
            </h3>

            {polymarketEvents.map((ev) => (
              <button
                key={ev.id}
                onClick={() => onSelectEvent(ev.id)}
                className="w-full text-left bg-panel border border-border rounded-lg p-4 hover:bg-panel-hover transition-colors"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="text-sm font-medium text-foreground">{ev.titleKo}</div>
                  <span className="text-[10px] text-muted flex items-center gap-1">
                    <ExternalLink className="w-3 h-3" />
                    Polymarket
                  </span>
                </div>

                {/* Scenario probability bar */}
                <div className="flex h-3 rounded-full overflow-hidden bg-panel-hover border border-border">
                  {ev.scenarios.map((s) => (
                    <div
                      key={s.name}
                      className={`h-full ${
                        s.name === "Bull"
                          ? "bg-accent-green"
                          : s.name === "Bear"
                          ? "bg-accent-red"
                          : "bg-accent-amber"
                      }`}
                      style={{ width: `${s.probability * 100}%` }}
                    />
                  ))}
                </div>
                <div className="flex items-center gap-3 mt-1.5 text-[10px]">
                  {ev.scenarios.map((s) => (
                    <span
                      key={s.name}
                      className={
                        s.name === "Bull"
                          ? "text-accent-green"
                          : s.name === "Bear"
                          ? "text-accent-red"
                          : "text-accent-amber"
                      }
                    >
                      {s.name} {(s.probability * 100).toFixed(0)}%
                    </span>
                  ))}
                </div>

                {/* Resolution conditions */}
                <div className="mt-2 text-[10px] text-muted space-y-0.5">
                  {ev.scenarios.slice(0, 1).map((s) =>
                    s.conditions.slice(0, 2).map((c, i) => (
                      <div key={i} className="flex items-center gap-1">
                        <CheckCircle2 className="w-2.5 h-2.5" />
                        {c}
                      </div>
                    ))
                  )}
                </div>
              </button>
            ))}
          </div>
        )}

        {alerts.length === 0 && (
          <div className="text-sm text-muted text-center py-16">
            <Bell className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p>현재 활성 알림이 없습니다.</p>
            <p className="text-xs mt-1">
              가설을 등록하고 확인 이벤트가 다가오면 알림이 생성됩니다.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
