"use client";

import { Search, Filter, Menu, Settings, BarChart3, Share2, LayoutDashboard, Target, Zap, Activity } from "lucide-react";
import { FilterState, ViewMode } from "../types";
import { filters } from "../lib/mockData";
import { Fragment } from "react";

interface SidebarProps {
  filter: FilterState;
  setFilter: (f: FilterState) => void;
  totalCount: number;
  filteredCount: number;
  view: ViewMode;
  setView: (v: ViewMode) => void;
  alertCount?: number;
}

const NAV_ITEMS: Array<{ icon: any; label: string; view?: ViewMode } | null> = [
  { icon: LayoutDashboard, label: "이벤트 대시보드", view: "dashboard" },
  { icon: Share2, label: "인과 그래프", view: "graph" },
  { icon: BarChart3, label: "포트폴리오", view: "portfolio" },
  { icon: Activity, label: "백테스트", view: "backtest" },
  null,
  { icon: Target, label: "Thesis Lab", view: "thesislab" },
  { icon: Zap, label: "가설 인박스", view: "inbox" },
  { icon: Settings, label: "설정" },
];

export default function Sidebar({ filter, setFilter, totalCount, filteredCount, view, setView, alertCount = 0 }: SidebarProps) {
  const update = (key: keyof FilterState, value: string) => setFilter({ ...filter, [key]: value });

  return (
    <aside className="w-72 flex-shrink-0 bg-panel border-r border-border flex flex-col h-full">
      <div className="h-14 flex items-center gap-3 px-4 border-b border-border">
        <Menu className="w-5 h-5 text-muted" />
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-sm bg-accent flex items-center justify-center text-[10px] font-bold text-white">EI</div>
          <span className="font-semibold tracking-tight">이벤트 인텔리전스 OS</span>
        </div>
      </div>

      <nav className="flex flex-col gap-0.5 p-2 border-b border-border">
        {NAV_ITEMS.map((item, idx) => {
          if (!item) return <div key={`sep-${idx}`} className="border-t border-border my-1" />;
          const isActive = item.view === view;
          return (
            <button
              key={item.label}
              onClick={() => item.view && setView(item.view)}
              className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm ${
                isActive ? "bg-panel-hover text-foreground" : "text-muted hover:text-foreground hover:bg-panel-hover"
              }`}
            >
              <item.icon className="w-4 h-4" />
              {item.label}
              {item.label === "가설 인박스" && alertCount > 0 && (
                <span className="ml-auto px-1.5 py-0.5 rounded text-[10px] font-semibold bg-accent-red text-white">{alertCount}</span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="flex-1 overflow-y-auto p-4">
        <div className="flex items-center gap-2 mb-4">
          <Filter className="w-4 h-4 text-muted" />
          <span className="text-xs font-medium text-muted uppercase tracking-wider">필터</span>
        </div>
        <div className="space-y-4">
          <FilterGroup label="키워드 검색">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted" />
              <input type="text" value={filter.keyword} onChange={(e) => update("keyword", e.target.value)} placeholder="종목, 사건, 섹터 검색..." className="w-full bg-background border border-border rounded-md py-1.5 pl-7 pr-2 text-sm text-foreground placeholder:text-muted focus:outline-none focus:border-accent" />
            </div>
          </FilterGroup>
          <FilterGroup label="이벤트 유형">
            <select value={filter.eventType} onChange={(e) => update("eventType", e.target.value)} className="w-full bg-background border border-border rounded-md py-1.5 px-2 text-sm text-foreground focus:outline-none focus:border-accent">
              {filters.eventTypes.map((t) => (<option key={t} value={t}>{t === "All" ? "전체" : t}</option>))}
            </select>
          </FilterGroup>
          <FilterGroup label="증거 등급">
            <select value={filter.evidenceGrade} onChange={(e) => update("evidenceGrade", e.target.value)} className="w-full bg-background border border-border rounded-md py-1.5 px-2 text-sm text-foreground focus:outline-none focus:border-accent">
              {filters.evidenceGrades.map((g) => (<option key={g} value={g}>{g === "All" ? "전체" : g}</option>))}
            </select>
          </FilterGroup>
          <FilterGroup label="긴급도">
            <select value={filter.urgency} onChange={(e) => update("urgency", e.target.value)} className="w-full bg-background border border-border rounded-md py-1.5 px-2 text-sm text-foreground focus:outline-none focus:border-accent">
              {filters.urgencies.map((u) => (<option key={u} value={u}>{u === "All" ? "전체" : u}</option>))}
            </select>
          </FilterGroup>
          <FilterGroup label="상태">
            <select value={filter.status} onChange={(e) => update("status", e.target.value)} className="w-full bg-background border border-border rounded-md py-1.5 px-2 text-sm text-foreground focus:outline-none focus:border-accent">
              {filters.statuses.map((s) => (<option key={s} value={s}>{s === "All" ? "전체" : s}</option>))}
            </select>
          </FilterGroup>
          <FilterGroup label="섹터">
            <select value={filter.sector} onChange={(e) => update("sector", e.target.value)} className="w-full bg-background border border-border rounded-md py-1.5 px-2 text-sm text-foreground focus:outline-none focus:border-accent">
              {filters.sectors.map((s) => (<option key={s} value={s}>{s === "All" ? "전체" : s}</option>))}
            </select>
          </FilterGroup>
        </div>
      </div>

      <div className="p-3 border-t border-border">
        <button onClick={() => setFilter({ keyword: "", eventType: "All", evidenceGrade: "All", urgency: "All", status: "All", sector: "All" })} className="w-full py-1.5 text-xs font-medium text-muted hover:text-foreground border border-border rounded-md hover:bg-panel-hover">
          필터 초기화
        </button>
      </div>
    </aside>
  );
}

function FilterGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[10px] font-medium text-muted uppercase tracking-wider mb-1.5">{label}</label>
      {children}
    </div>
  );
}
