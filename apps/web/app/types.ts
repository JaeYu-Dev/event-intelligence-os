export type EvidenceGrade = "E0" | "E1" | "E2" | "E3" | "E4";
export type Urgency = "Low" | "Medium" | "High" | "Critical";
export type ThesisStatus = "Active" | "Strengthening" | "At Risk" | "Invalidated" | "Resolved" | "Watching";
export type ActionRequired = "Research Required" | "Watch" | "Paper Trade" | "Reduce" | "Hold";
export type EventType = "policy_announcement" | "filing" | "earnings" | "macro" | "supply_chain" | "regulatory" | "prediction_market";

export interface Scenario {
  name: "Bull" | "Base" | "Bear";
  probability: number;
  prevProbability?: number;
  conditions: string[];
  priceRange: string;
}

export interface Event {
  id: string;
  title: string;
  titleKo: string;
  eventType: EventType;
  actor: string;
  actorKo: string;
  action: string;
  object: string;
  magnitude?: { value: number; unit: string };
  effectiveDate?: string;
  publishedAt: string;
  sourceType: "official" | "filing" | "wire" | "analyst" | "social";
  sourceReliability: number;
  evidenceGrade: EvidenceGrade;
  urgency: Urgency;
  status: ThesisStatus;
  actionRequired: ActionRequired;
  lat: number;
  lng: number;
  count: number;
  sector: string;
  sectorKo: string;
  relatedTickers: string[];
  scenarios: Scenario[];
  mechanism: string;
  mechanismKo: string;
  counterevidence: string[];
  counterevidenceKo: string[];
  nextEvents: string[];
  nextEventsKo: string[];
}

export interface PortfolioPosition {
  ticker: string;
  name: string;
  shares: number;
  avgCost: number;
  currentPrice: number;
  plPercent: number;
  plUsd: number;
  exposureEvents: string[]; // event ids
  scenarioBias: "Bull" | "Base" | "Bear";
}

export interface CausalEdge {
  source: string;
  target: string;
  strength: number; // 1-10
  type: "causal" | "supply_chain" | "regulatory" | "market" | "latent";
  labelKo: string;
}

export interface ConfirmationAlert {
  eventId: string;
  scenario: string;
  whatToWatch: string;
  deadline: string;
  impactIfConfirmed: string;
}

export interface FilterState {
  keyword: string;
  eventType: string;
  evidenceGrade: string;
  urgency: string;
  status: string;
  sector: string;
}

export type ViewMode = "dashboard" | "graph" | "portfolio" | "thesislab" | "inbox" | "backtest";

export interface BacktestRun {
  backtest_run_id: string;
  run_name: string;
  status: string;
  created_at?: string;
  completed_at?: string;
  metrics?: any;
  result_summary?: any;
}

export interface BacktestDetail extends BacktestRun {
  config: any;
  windows: number;
  metrics: any;
  improvement_decision: any;
  failure_analysis: any;
  summaries: any[];
}
