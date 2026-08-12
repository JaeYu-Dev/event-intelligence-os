const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

export interface ApiEvent {
  id: string;
  event_key: string;
  event_type: string;
  actor: string | null;
  actor_ko: string | null;
  action: string | null;
  object: string | null;
  title: string | null;
  title_ko: string | null;
  sector: string | null;
  sector_ko: string | null;
  evidence_grade: string;
  urgency: string;
  status: string;
  related_tickers: string[] | null;
  mechanism: string | null;
  mechanism_ko: string | null;
  published_at: string | null;
  created_at: string;
  conditions?: any[];
  counterevidence?: string[];
  counterevidence_ko?: string[];
  next_events?: string[];
  next_events_ko?: string[];
}

export interface ApiPosition {
  id: string;
  ticker: string;
  name: string | null;
  shares: number;
  avg_cost: number;
  current_price: number | null;
  pl_percent: number | null;
  pl_usd: number | null;
  scenario_bias: string | null;
  exposure_events?: string[];
}

export interface ApiEdge {
  source: string;
  target: string;
  strength: number;
  type: string;
  label: string | null;
  label_ko: string | null;
}

export interface RadarData {
  events: ApiEvent[];
  positions: ApiPosition[];
  edges: ApiEdge[];
}

export interface ApiAlert {
  id: string;
  event_id: string;
  title_ko: string;
  scenario: string;
  trigger: string;
  what_to_watch: string;
  deadline: string;
  impact_if_confirmed: string;
  urgency: string;
  evidence_grade: string;
  sector_ko: string;
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function fetchRadar(): Promise<RadarData> {
  return fetchJson("/radar/opportunities");
}

export async function fetchEvents(): Promise<ApiEvent[]> {
  return fetchJson("/events");
}

export async function fetchAlerts(): Promise<ApiAlert[]> {
  const data = await fetchJson<{ alerts: ApiAlert[] }>("/alerts");
  return data.alerts;
}

export async function createThesisFromEvent(eventId: string): Promise<{ thesis: any }> {
  const res = await fetch(`${API_BASE}/events/${eventId}/thesis`, { method: "POST" });
  if (!res.ok) throw new Error(`Thesis creation error: ${res.status}`);
  return res.json();
}

export async function reassessThesis(thesisId: string, payload: object): Promise<{ thesis: any }> {
  const res = await fetch(`${API_BASE}/theses/${thesisId}/reassess`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Reassess error: ${res.status}`);
  return res.json();
}

export async function createPaperTrade(payload: object): Promise<{ trade: any }> {
  const res = await fetch(`${API_BASE}/paper-trades`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Paper trade error: ${res.status}`);
  return res.json();
}

export async function fetchPaperTrades(thesisId?: string): Promise<any[]> {
  const qs = thesisId ? `?thesis_id=${thesisId}` : "";
  const data = await fetchJson<{ trades: any[] }>(`/paper-trades${qs}`);
  return data.trades;
}

export async function importPortfolio(payload: object[]): Promise<{ imported: number; positions: ApiPosition[] }> {
  const res = await fetch(`${API_BASE}/portfolio/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Portfolio import error: ${res.status}`);
  return res.json();
}

export async function ingestSource(source: string): Promise<{ source: string; fetched: number; ingested: number }> {
  const res = await fetch(`${API_BASE}/events/ingest/${source}`, { method: "POST" });
  if (!res.ok) throw new Error(`Ingest error: ${res.status}`);
  return res.json();
}
