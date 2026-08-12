"use client";

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Play, History, BarChart3, TrendingUp, TrendingDown, Activity,
  Target, AlertTriangle, CheckCircle2, XCircle, Loader2, ChevronRight,
  Calendar, Clock, Layers, GitBranch, ArrowRight,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

interface BacktestRun {
  backtest_run_id: string;
  run_name: string;
  status: string;
  created_at?: string;
  completed_at?: string;
  metrics?: any;
  result_summary?: any;
}

interface BacktestDetail extends BacktestRun {
  config: any;
  windows: number;
  metrics: any;
  improvement_decision: any;
  failure_analysis: any;
  summaries: any[];
}

export default function BacktestDashboard() {
  const queryClient = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    run_name: "walk-forward-" + new Date().toISOString().slice(0, 10),
    cutoff_start: "2024-01-01",
    cutoff_end: "2024-12-31",
    train_window_days: "365",
    val_window_days: "90",
    test_window_days: "90",
    step_days: "30",
    max_motifs_per_cutoff: "50",
    min_events_per_motif: "3",
    universe: "",
  });

  const { data: runsData, isLoading: runsLoading } = useQuery({
    queryKey: ["backtest-runs"],
    queryFn: async () => {
      const r = await fetch(`${API_BASE}/engine/backtests`);
      return r.json();
    },
  });

  const runs: BacktestRun[] = useMemo(() => runsData?.runs || [], [runsData]);

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ["backtest-detail", selectedRunId],
    queryFn: async () => {
      if (!selectedRunId) return null;
      const r = await fetch(`${API_BASE}/engine/backtest/${selectedRunId}`);
      return r.json();
    },
    enabled: !!selectedRunId,
  });

  const { data: postmortem } = useQuery({
    queryKey: ["backtest-postmortem", selectedRunId],
    queryFn: async () => {
      if (!selectedRunId) return null;
      const r = await fetch(`${API_BASE}/engine/backtest/${selectedRunId}/postmortem`);
      return r.json();
    },
    enabled: !!selectedRunId,
  });

  const runMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        run_name: form.run_name,
        cutoff_start: new Date(form.cutoff_start).toISOString(),
        cutoff_end: new Date(form.cutoff_end).toISOString(),
        train_window_days: Number(form.train_window_days),
        val_window_days: Number(form.val_window_days),
        test_window_days: Number(form.test_window_days),
        step_days: Number(form.step_days),
        max_motifs_per_cutoff: Number(form.max_motifs_per_cutoff),
        min_events_per_motif: Number(form.min_events_per_motif),
        universe: form.universe ? { tickers: form.universe.split(",").map((s) => s.trim()) } : {},
      };
      const r = await fetch(`${API_BASE}/engine/backtest/walk-forward`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!r.ok) throw new Error("Backtest request failed");
      return r.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["backtest-runs"] });
      setSelectedRunId(data.backtest_run_id);
      setShowForm(false);
    },
  });

  const selectedRun = runs.find((r) => r.backtest_run_id === selectedRunId);
  const detailData = detail as BacktestDetail | null;
  const resultSummary = detailData?.result_summary || detailData?.metrics || selectedRun?.result_summary || {};
  const metrics = resultSummary;

  return (
    <div className="flex h-full w-full bg-[#0d1016] overflow-hidden">
      {/* Left: runs list */}
      <aside className="w-64 flex-shrink-0 border-r border-border bg-panel flex flex-col">
        <div className="h-12 flex items-center justify-between px-4 border-b border-border">
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-accent" />
            <span className="text-xs font-semibold text-foreground">백테스트 기록</span>
          </div>
          <button onClick={() => setShowForm(true)} className="p-1 rounded hover:bg-panel-hover text-accent">
            <Play className="w-3.5 h-3.5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {runsLoading && <div className="text-[11px] text-muted text-center py-4">로딩 중...</div>}
          {runs.map((run) => (
            <button
              key={run.backtest_run_id}
              onClick={() => setSelectedRunId(run.backtest_run_id)}
              className={`w-full text-left px-3 py-2 rounded-md border text-[11px] transition-colors ${
                selectedRunId === run.backtest_run_id
                  ? "border-accent/40 bg-accent/10 text-foreground"
                  : "border-border bg-panel hover:bg-panel-hover text-muted"
              }`}
            >
              <div className="truncate font-medium">{run.run_name}</div>
              <div className="flex items-center gap-2 mt-1">
                <StatusBadge status={run.status} />
                {run.result_summary?.direction_accuracy != null && (
                  <span className="text-accent-blue">정확도 {(run.result_summary.direction_accuracy * 100).toFixed(1)}%</span>
                )}
              </div>
            </button>
          ))}
          {runs.length === 0 && !runsLoading && (
            <div className="text-[11px] text-muted text-center py-6">백테스트 기록이 없습니다</div>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0">
        <header className="h-12 flex items-center justify-between px-5 border-b border-border bg-panel flex-shrink-0">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-accent" />
            <h1 className="text-sm font-semibold text-foreground">Point-in-Time 백테스트 대시보드</h1>
          </div>
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-accent hover:bg-accent/90 text-white text-xs font-semibold"
          >
            <Play className="w-3.5 h-3.5" /> 새 백테스트
          </button>
        </header>

        {showForm && (
          <div className="flex-shrink-0 border-b border-border bg-panel p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs font-semibold text-foreground">새 백테스트 설정</div>
              <button onClick={() => setShowForm(false)} className="text-muted hover:text-foreground text-xs">✕</button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              <Field label="Run name" value={form.run_name} onChange={(v) => setForm((f) => ({ ...f, run_name: v }))} />
              <Field label="Cutoff start" type="date" value={form.cutoff_start} onChange={(v) => setForm((f) => ({ ...f, cutoff_start: v }))} />
              <Field label="Cutoff end" type="date" value={form.cutoff_end} onChange={(v) => setForm((f) => ({ ...f, cutoff_end: v }))} />
              <Field label="Step days" value={form.step_days} onChange={(v) => setForm((f) => ({ ...f, step_days: v }))} />
              <Field label="Train days" value={form.train_window_days} onChange={(v) => setForm((f) => ({ ...f, train_window_days: v }))} />
              <Field label="Val days" value={form.val_window_days} onChange={(v) => setForm((f) => ({ ...f, val_window_days: v }))} />
              <Field label="Test days" value={form.test_window_days} onChange={(v) => setForm((f) => ({ ...f, test_window_days: v }))} />
              <Field label="Max motifs" value={form.max_motifs_per_cutoff} onChange={(v) => setForm((f) => ({ ...f, max_motifs_per_cutoff: v }))} />
            </div>
            <div className="flex items-center gap-3">
              <input
                type="text"
                value={form.universe}
                onChange={(e) => setForm((f) => ({ ...f, universe: e.target.value }))}
                placeholder="Universe tickers (comma separated, e.g. NVDA,TSLA,AAPL)"
                className="flex-1 bg-background border border-border rounded-md px-2 py-1.5 text-xs text-foreground placeholder:text-muted focus:outline-none focus:border-accent"
              />
              <button
                onClick={() => runMutation.mutate()}
                disabled={runMutation.isPending}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-md bg-accent hover:bg-accent/90 disabled:opacity-60 text-white text-xs font-semibold"
              >
                {runMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                실행
              </button>
            </div>
            {runMutation.isError && <div className="text-[11px] text-accent-red mt-2">백테스트 실행 실패</div>}
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-5">
          {!selectedRunId ? (
            <div className="flex flex-col items-center justify-center h-full text-muted">
              <BarChart3 className="w-14 h-14 mb-4 opacity-20" />
              <p className="text-sm">좌측에서 백테스트를 선택하거나 새로 실행하세요</p>
            </div>
          ) : detailLoading ? (
            <div className="flex items-center justify-center h-full text-muted"><Loader2 className="w-8 h-8 animate-spin mr-2" /> 상세 로딩 중...</div>
          ) : (
            <div className="space-y-5">
              {/* Metrics cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <MetricCard icon={Target} label="방향 정확도" value={metrics.direction_accuracy != null ? `${(metrics.direction_accuracy * 100).toFixed(1)}%` : "-"} />
                <MetricCard icon={Activity} label="Brier Score" value={metrics.brier_score != null ? metrics.brier_score.toFixed(3) : "-"} />
                <MetricCard icon={Activity} label="Log Loss" value={metrics.log_loss != null ? metrics.log_loss.toFixed(3) : "-"} />
                <MetricCard icon={TrendingUp} label="평균 초과 수익" value={metrics.mean_excess_return != null ? `${(metrics.mean_excess_return * 100).toFixed(2)}%` : "-"} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                {/* Windows summary */}
                <div className="lg:col-span-2 bg-panel border border-border rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3 text-xs font-semibold text-foreground">
                    <Layers className="w-3.5 h-3.5 text-accent" /> 윈도우별 요약 ({resultSummary?.summaries?.length || resultSummary?.windows || 0})
                  </div>
                  {resultSummary?.summaries && resultSummary.summaries.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-[11px]">
                        <thead>
                          <tr className="text-muted border-b border-border">
                            <th className="text-left py-1.5 px-2">Cutoff</th>
                            <th className="text-right py-1.5 px-2">Motifs</th>
                            <th className="text-right py-1.5 px-2">Qualified</th>
                            <th className="text-right py-1.5 px-2">Predictions</th>
                            <th className="text-right py-1.5 px-2">Resolved</th>
                          </tr>
                        </thead>
                        <tbody>
                          {resultSummary.summaries.map((s: any, i: number) => (
                            <tr key={i} className="border-b border-border/50 text-foreground">
                              <td className="py-1.5 px-2">{s.cutoff?.slice(0, 10)}</td>
                              <td className="text-right py-1.5 px-2">{s.motifs_scanned}</td>
                              <td className="text-right py-1.5 px-2">{s.qualified}</td>
                              <td className="text-right py-1.5 px-2">{s.predictions}</td>
                              <td className="text-right py-1.5 px-2">{s.outcomes?.filter((o: any) => o.resolved).length || 0}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="text-[11px] text-muted">윈도우 요약 없음</div>
                  )}
                </div>

                {/* Improvement / Failure */}
                <div className="space-y-4">
                  <div className="bg-panel border border-border rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-2 text-xs font-semibold text-foreground">
                      <GitBranch className="w-3.5 h-3.5 text-accent" /> 개선 결정
                    </div>
                    {resultSummary?.improvement_decision ? (
                      <div className="text-[11px] text-muted leading-relaxed">
                        <div className="text-foreground font-medium mb-1">{resultSummary.improvement_decision.decision || resultSummary.improvement_decision}</div>
                        {resultSummary.improvement_decision.reason && <div>{resultSummary.improvement_decision.reason}</div>}
                      </div>
                    ) : (
                      <div className="text-[11px] text-muted">데이터 없음</div>
                    )}
                  </div>

                  <div className="bg-panel border border-border rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-2 text-xs font-semibold text-foreground">
                      <AlertTriangle className="w-3.5 h-3.5 text-accent-red" /> 실패 모드 분석
                    </div>
                    {postmortem?.failure_analysis && Object.keys(postmortem.failure_analysis).length > 0 ? (
                      <div className="space-y-1.5 text-[11px]">
                        {Object.entries(postmortem.failure_analysis).slice(0, 6).map(([k, v]: [string, any]) => (
                          <div key={k} className="flex items-start gap-2">
                            <span className="text-muted whitespace-nowrap">{k}</span>
                            <span className="text-foreground ml-auto text-right max-w-[120px] truncate">{typeof v === "number" ? v.toFixed(2) : typeof v === "object" ? JSON.stringify(v).slice(0, 40) : String(v)}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-[11px] text-muted">데이터 없음</div>
                    )}
                  </div>
                </div>
              </div>

              {/* Postmortem */}
              {postmortem?.failure_analysis && (
                <div className="bg-panel border border-border rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3 text-xs font-semibold text-foreground">
                    <Activity className="w-3.5 h-3.5 text-accent" /> 포스트모템
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-[11px]">
                    {Object.entries(postmortem.failure_analysis).slice(0, 12).map(([k, v]: [string, any]) => (
                      <div key={k} className="border border-border rounded-md p-2">
                        <div className="text-muted mb-1">{k}</div>
                        <div className="text-foreground font-medium">{typeof v === "number" ? v.toFixed(3) : typeof v === "object" ? JSON.stringify(v).slice(0, 80) : String(v)}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function Field({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (v: string) => void; type?: string }) {
  return (
    <div>
      <label className="block text-[10px] text-muted mb-1">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-background border border-border rounded-md px-2 py-1.5 text-xs text-foreground focus:outline-none focus:border-accent"
      />
    </div>
  );
}

function MetricCard({ icon: Icon, label, value, positive }: { icon: any; label: string; value: string; positive?: boolean }) {
  return (
    <div className="bg-panel border border-border rounded-lg p-4">
      <div className="flex items-center gap-2 text-[10px] text-muted uppercase tracking-wider mb-2">
        <Icon className="w-3.5 h-3.5" /> {label}
      </div>
      <div className={`text-2xl font-semibold ${positive === true ? "text-accent-green" : positive === false ? "text-accent-red" : "text-foreground"}`}>
        {value}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cls = status === "completed"
    ? "bg-accent-green/15 text-accent-green"
    : status === "running"
    ? "bg-accent/15 text-accent"
    : "bg-accent-red/15 text-accent-red";
  return <span className={`px-1.5 py-0.5 rounded text-[10px] ${cls}`}>{status}</span>;
}
