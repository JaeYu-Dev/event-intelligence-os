"use client";

import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Zap, CheckCircle2, XCircle, Filter, ChevronDown, ChevronUp,
  TrendingUp, AlertTriangle, Clock, Target, Search, Loader2,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

interface MotifEvent {
  event_id: string; title_ko: string; event_type: string; evidence_grade: string;
  urgency: string; sector_ko: string; mechanism_ko: string; related_tickers: string[];
}

interface MotifCandidate {
  motif_id: string; root_title_ko: string;
  events: MotifEvent[]; edge_count: number;
  combined_score: number; evidence_score: number; causal_score: number;
  novelty_score: number; diversity_score: number; backtest_score: number;
  portfolio_score: number;
  aggregated_tickers: string[]; aggregated_sectors: string[];
  narrative_ko: string;
  scenario_distribution: Record<string, number>;
  risk_flags: string[]; event_count: number;
  gate_status?: string;
  gate_score?: number;
  passed_gates?: number;
  failed_gates?: string[];
}

interface DeepScanResult {
  run_at: string;
  total_motifs_found: number;
  total_motifs_qualified: number;
  total_motifs_backtested: number;
  motifs: MotifCandidate[];
  failure_modes?: Array<{ mode: string; severity: string; fix: string }>;
  gate_summary?: Record<string, number>;
}

export default function ThesisInbox() {
  const queryClient = useQueryClient();
  const [filterText, setFilterText] = useState("");
  const [sortBy, setSortBy] = useState<"score" | "grade" | "urgency">("score");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [scanTriggered, setScanTriggered] = useState(false);

  // Fetch accepted theses to mark already-accepted candidates
  const { data: myTheses } = useQuery({
    queryKey: ["my-theses"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/engine/theses`);
      return res.json();
    },
  });

  const acceptedIds = new Set(
    (myTheses?.theses || []).map((t: any) => t.event_id).filter(Boolean)
  );

  // Deep scan mutation
  const scanMutation = useMutation({
    mutationFn: async (): Promise<DeepScanResult> => {
      const res = await fetch(`${API_BASE}/engine/deep-scan`, { method: "POST" });
      if (!res.ok) throw new Error(`Scan failed: ${res.status}`);
      return res.json();
    },
    onSuccess: () => setScanTriggered(true),
  });

  // Accept mutation
  const acceptMutation = useMutation({
    mutationFn: async (eventId: string) => {
      const res = await fetch(`${API_BASE}/engine/thesis/accept/${eventId}`, { method: "POST" });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["my-theses"] });
      queryClient.invalidateQueries({ queryKey: ["radar"] });
    },
  });

  // Reject mutation
  const rejectMutation = useMutation({
    mutationFn: async (eventId: string) => {
      const res = await fetch(`${API_BASE}/engine/thesis/reject/${eventId}`, { method: "POST" });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["my-theses"] });
    },
  });

  const handleAccept = useCallback(
    (eventId: string) => {
      acceptMutation.mutate(eventId);
    },
    [acceptMutation]
  );

  const handleAcceptMotif = useCallback(
    (motif: MotifCandidate) => {
      const eventIds = motif.events.map((e) => e.event_id);
      fetch(`${API_BASE}/engine/thesis/accept/${eventIds[0]}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ motif_events: eventIds }),
      })
        .then((res) => res.json())
        .then(() => {
          queryClient.invalidateQueries({ queryKey: ["my-theses"] });
          queryClient.invalidateQueries({ queryKey: ["radar"] });
        });
    },
    [queryClient]
  );

  const handleReject = useCallback(
    (eventId: string) => {
      rejectMutation.mutate(eventId);
    },
    [rejectMutation]
  );

  const handleRejectMotif = useCallback(
    (motif: MotifCandidate) => {
      const eventIds = motif.events.map((e) => e.event_id);
      Promise.all(
        eventIds.map((id) =>
          fetch(`${API_BASE}/engine/thesis/reject/${id}`, { method: "POST" }).then((res) => res.json())
        )
      ).then(() => {
        queryClient.invalidateQueries({ queryKey: ["my-theses"] });
        queryClient.invalidateQueries({ queryKey: ["radar"] });
      });
    },
    [queryClient]
  );

  const candidates = scanMutation.data?.motifs || [];

  const handleAcceptSelected = useCallback(() => {
    for (const id of selectedIds) {
      if (acceptedIds.has(id)) continue;
      const motif = candidates.find((c) => c.motif_id === id);
      if (motif) {
        handleAcceptMotif(motif);
      }
    }
    setSelectedIds(new Set());
  }, [selectedIds, acceptedIds, candidates, handleAcceptMotif]);

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  // Filter and sort
  const filtered = candidates
    .filter((c) => {
      if (!filterText) return true;
      const q = filterText.toLowerCase();
      return (
        c.root_title_ko.toLowerCase().includes(q) ||
        c.aggregated_sectors.some((s: string) => s.toLowerCase().includes(q)) ||
        c.aggregated_tickers.some((t) => t.toLowerCase().includes(q)) ||
        c.narrative_ko.toLowerCase().includes(q)
      );
    })
    .sort((a, b) => {
      if (sortBy === "score") return b.combined_score - a.combined_score;
      if (sortBy === "grade") {
        return (b.evidence_score || 0) - (a.evidence_score || 0);
      }
      if (sortBy === "urgency") {
        return b.combined_score - a.combined_score;
      }
      return b.combined_score - a.combined_score;
    });

  return (
    <div className="flex flex-col h-full bg-[#0d1016]">
      {/* Header bar */}
      <div className="flex-shrink-0 bg-panel border-b border-border px-5 py-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Target className="w-4 h-4 text-accent" /> 가설 인박스 (Thesis Inbox)
            </h2>
            <p className="text-[10px] text-muted mt-0.5">
              Deep Scan이 발견한 투자 가설 후보들입니다. 수용할 가설을 선택하세요.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {selectedIds.size > 0 && (
              <button
                onClick={handleAcceptSelected}
                disabled={acceptMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-accent-green/15 border border-accent-green/30 hover:bg-accent-green/25 text-accent-green text-xs font-medium"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                {selectedIds.size}건 수용
              </button>
            )}
            <button
              onClick={() => scanMutation.mutate()}
              disabled={scanMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-accent hover:bg-accent/90 disabled:opacity-60 text-white text-xs font-semibold transition-colors"
            >
              {scanMutation.isPending ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  스캔 중...
                </>
              ) : (
                <>
                  <Zap className="w-3.5 h-3.5" />
                  Deep Scan 실행
                </>
              )}
            </button>
          </div>
        </div>

        {/* Scan stats */}
        {scanMutation.data && (
          <div className="flex items-center gap-4 text-[10px] text-muted mb-2">
            <span>발견된 모티프: {scanMutation.data.total_motifs_found}건</span>
            <span>필터링 후: {scanMutation.data.total_motifs_qualified}건</span>
            <span className="text-accent-green">투자 적합: {scanMutation.data.total_motifs_qualified}건</span>
            <span className="text-muted">|</span>
            <span>내 가설: {myTheses?.theses?.length || 0}건</span>
            {scanMutation.data?.gate_summary && (
              <span className="text-muted">|</span>
            )}
            {scanMutation.data?.gate_summary?.active_scenarios != null && (
              <span className="text-accent-green">Active: {scanMutation.data.gate_summary.active_scenarios}건</span>
            )}
            {scanMutation.data?.gate_summary?.high_conviction != null && (
              <span className="text-accent">HC: {scanMutation.data.gate_summary.high_conviction}건</span>
            )}

          </div>
        )}

        {/* Failure Modes */}
        {scanMutation.data?.failure_modes && scanMutation.data.failure_modes.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {scanMutation.data.failure_modes.filter((fm: any) => fm.severity === "high").map((fm: any, i: number) => (
              <span key={i} className="px-1.5 py-0.5 rounded text-[9px] bg-accent-red/10 text-accent-red border border-accent-red/20">
                {fm.mode}: {fm.fix?.substring(0, 40)}
              </span>
            ))}
          </div>
        )}

        {/* Toolbar */}
        <div className="flex items-center gap-3">
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted" />
            <input
              type="text"
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              placeholder="종목, 키워드, 섹터 필터..."
              className="w-full bg-background border border-border rounded-md py-1 pl-7 pr-2 text-xs text-foreground placeholder:text-muted focus:outline-none focus:border-accent"
            />
          </div>
          <div className="flex items-center gap-1 text-[10px] text-muted">
            <span>정렬:</span>
            {[
              { key: "score" as const, label: "점수" },
              { key: "grade" as const, label: "증거" },
              { key: "urgency" as const, label: "긴급" },
            ].map((opt) => (
              <button
                key={opt.key}
                onClick={() => setSortBy(opt.key)}
                className={`px-2 py-0.5 rounded ${
                  sortBy === opt.key
                    ? "bg-accent/20 text-accent"
                    : "hover:bg-panel-hover text-muted"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Candidate list */}
      <div className="flex-1 overflow-y-auto p-5">
        {!scanTriggered && (
          <div className="flex flex-col items-center justify-center h-full text-muted">
            <Zap className="w-12 h-12 mb-4 opacity-20" />
            <p className="text-sm mb-1">아직 스캔을 실행하지 않았습니다.</p>
            <p className="text-xs mb-4">Deep Scan을 실행하면 AI가 투자 가설 후보를 찾아냅니다.</p>
            <button
              onClick={() => scanMutation.mutate()}
              disabled={scanMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 rounded-md bg-accent hover:bg-accent/90 text-white text-sm font-semibold"
            >
              <Zap className="w-4 h-4" />
              Deep Scan 실행
            </button>
          </div>
        )}

        {scanMutation.isPending && (
          <div className="flex flex-col items-center justify-center h-full">
            <Loader2 className="w-10 h-10 text-accent animate-spin mb-3" />
            <p className="text-sm text-muted">
              이벤트를 스캔하고 투자 가설 후보를 분석 중입니다...
            </p>
            <p className="text-xs text-muted mt-1">최대 30초 소요될 수 있습니다.</p>
          </div>
        )}

        {scanTriggered && !scanMutation.isPending && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-muted">
            <CheckCircle2 className="w-10 h-10 mb-3 opacity-30" />
            <p className="text-sm">새로운 가설 후보가 없습니다.</p>
            <p className="text-xs mt-1">모든 이벤트가 이미 처리되었거나 조건에 맞는 후보가 없습니다.</p>
          </div>
        )}

        <div className="space-y-3">
          {filtered.map((c) => {
            const cid = c.motif_id;
            const isAccepted = c.events.some((e: any) => acceptedIds.has(e.event_id));
            const isExpanded = expandedId === cid;
            const isSelected = selectedIds.has(cid);

            return (
              <div
                key={c.motif_id}
                className={`border rounded-lg transition-all ${
                  isAccepted
                    ? "border-accent-green/30 bg-accent-green/5 opacity-70"
                    : isSelected
                    ? "border-accent/50 bg-accent/5"
                    : "border-border bg-panel"
                }`}
              >
                <div className="flex items-start gap-3 p-4">
                  {/* Checkbox */}
                  {!isAccepted && (
                    <button
                      onClick={() => toggleSelect(c.motif_id)}
                      className={`w-5 h-5 rounded border-2 flex-shrink-0 mt-0.5 flex items-center justify-center transition-colors ${
                        isSelected
                          ? "bg-accent border-accent"
                          : "border-border hover:border-accent/50"
                      }`}
                    >
                      {isSelected && <CheckCircle2 className="w-3.5 h-3.5 text-white" />}
                    </button>
                  )}

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-accent/15 text-accent">
                              {c.event_count} events
                            </span>
                          <span className="text-sm font-semibold text-foreground">
                            {c.root_title_ko || "Motif " + c.motif_id}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-[10px] text-muted">
                          <span>{c.events.map((e: any) => e.evidence_grade).filter((v: string, i: number, a: string[]) => a.indexOf(v) === i).join("+")}</span>
                          <span>·</span>
                          <span>{c.aggregated_sectors.slice(0, 2).join(", ")}</span>
                          <span>·</span>
                          <span className="text-accent-blue">
                            {c.aggregated_tickers.slice(0, 4).join(", ")}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <span className="text-[10px] text-muted">
                          점수 {c.combined_score.toFixed(2)}
                        </span>
                        {c.gate_status && (
                          <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium ${
                            c.gate_status === "active_scenario" ? "bg-accent-green/15 text-accent-green" :
                            c.gate_status === "high_conviction_research_candidate" ? "bg-accent/15 text-accent" :
                            "bg-panel-hover text-muted"
                          }`}>
                            {c.passed_gates != null ? `${c.passed_gates}/10` : c.gate_status}
                          </span>
                        )}
                        <button
                          onClick={() => setExpandedId(isExpanded ? null : c.motif_id)}
                          className="p-1 text-muted hover:text-foreground"
                        >
                          {isExpanded ? (
                            <ChevronUp className="w-3.5 h-3.5" />
                          ) : (
                            <ChevronDown className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </div>
                    </div>

                    {/* Mechanism preview */}
                    {c.narrative_ko && (
                      <div className="text-xs text-foreground mt-1.5 leading-relaxed line-clamp-2">
                        {c.narrative_ko}
                      </div>
                    )}


                    {/* Expanded detail */}
                    {isExpanded && (
                      <div className="mt-3 pt-3 border-t border-border space-y-3">
                        {/* Event list */}
                        <div>
                          <div className="text-[10px] font-semibold text-muted uppercase mb-1.5">구성 이벤트</div>
                          <div className="space-y-1">
                            {c.events.map((ev: any) => (
                              <div key={ev.event_id} className="flex items-center gap-2 text-[10px] border border-border rounded-md px-2 py-1">
                                <EvidenceBadge grade={ev.evidence_grade} />
                                <span className="text-foreground">{ev.title_ko}</span>
                                <span className="text-muted ml-auto">{ev.sector_ko}</span>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Scenario distribution */}
                        {c.scenario_distribution && Object.keys(c.scenario_distribution).length > 0 && (
                          <div>
                            <div className="text-[10px] font-semibold text-muted uppercase mb-1.5">시나리오 확률</div>
                            <div className="flex gap-2">
                              {Object.entries(c.scenario_distribution).map(([name, prob]: [string, any]) => (
                                <div key={name} className="flex-1 border border-border rounded-md px-2 py-1.5 text-center">
                                  <div className={`text-xs font-semibold ${name === "Bull" ? "text-accent-green" : name === "Bear" ? "text-accent-red" : "text-accent-amber"}`}>
                                    {name === "Bull" ? "강세" : name === "Bear" ? "약세" : "기본"}
                                  </div>
                                  <div className="text-sm font-bold text-foreground">{((prob || 0) * 100).toFixed(0)}%</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Scores */}
                        <div className="grid grid-cols-3 gap-1 text-[9px] text-muted">
                          <div>증거: {c.evidence_score?.toFixed(2)}</div>
                          <div>인과: {c.causal_score?.toFixed(2)}</div>
                          <div>다양성: {c.diversity_score?.toFixed(2)}</div>
                          <div>신규성: {c.novelty_score?.toFixed(2)}</div>
                          <div>백테스트: {c.backtest_score?.toFixed(2)}</div>
                          <div>포트폴리오: {c.portfolio_score?.toFixed(2)}</div>
                        </div>

                        {/* Risk flags */}
                        {c.risk_flags && c.risk_flags.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {c.risk_flags.map((flag: string, i: number) => (
                              <span key={i} className="px-1.5 py-0.5 rounded text-[9px] bg-accent-red/10 text-accent-red">{flag}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Action buttons */}
                {!isAccepted && (
                  <div className="flex gap-1.5 px-4 pb-3">
                    <button
                      onClick={() => handleAcceptMotif(c)}
                      disabled={acceptMutation.isPending}
                      className="flex items-center gap-1 px-3 py-1 rounded-md bg-accent-green/15 border border-accent-green/30 hover:bg-accent-green/25 text-accent-green text-xs font-medium disabled:opacity-50"
                    >
                      <CheckCircle2 className="w-3 h-3" />
                      수용
                    </button>
                    <button
                      onClick={() => handleRejectMotif(c)}
                      disabled={rejectMutation.isPending}
                      className="flex items-center gap-1 px-3 py-1 rounded-md border border-border hover:bg-panel-hover text-muted hover:text-foreground text-xs"
                    >
                      <XCircle className="w-3 h-3" />
                      거부
                    </button>
                  </div>
                )}

                {isAccepted && (
                  <div className="px-4 pb-3">
                    <span className="text-[10px] text-accent-green flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" /> 내 가설에 등록됨
                    </span>
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

function EvidenceBadge({ grade }: { grade: string }) {
  const c =
    grade === "E4" ? "#3fb950" : grade === "E3" ? "#58a6ff" : grade === "E2" ? "#d29922" : "#8b949e";
  return (
    <span className="inline-flex items-center px-1 py-0.5 rounded text-[10px] font-semibold" style={{ backgroundColor: `${c}22`, color: c }}>
      {grade}
    </span>
  );
}

function UrgencyBadge({ urgency }: { urgency: string }) {
  const labels: Record<string, string> = { Critical: "심각", High: "높음", Medium: "보통", Low: "낮음" };
  const c =
    urgency === "Critical" ? "#d73a49" : urgency === "High" ? "#e16a2e" : urgency === "Medium" ? "#d29922" : "#8b949e";
  return (
    <span className="inline-flex items-center px-1 py-0.5 rounded text-[10px] font-semibold" style={{ backgroundColor: `${c}22`, color: c }}>
      {labels[urgency] || urgency}
    </span>
  );
}
