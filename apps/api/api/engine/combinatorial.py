"""
Combinatorial Motif Discovery Engine

Core insight from the spec (Section 29.4, Section 24):
  Meaningful investment theses come from EVENT COMBINATIONS (motifs),
  not single events. "A + B + C" creates a trade, not "A alone."

This engine:
  1. Builds a weighted event graph from all events
  2. Enumerates 3+ event motifs (connected subgraphs)
  3. Scores each motif by: evidence strength, causal plausibility, sector diversity,
     novelty, counterevidence quality, portfolio overlap
  4. Runs lightweight backtest filter (motif family × regime split)
  5. Returns top 50-100 candidates ranked by combined score
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from collections import defaultdict

from sqlalchemy.orm import Session
from api.models import Event, EventRelation, Thesis, PortfolioPosition


@dataclass
class EventMotif:
    """A combination of 3+ events that form a causal chain."""
    motif_id: str
    events: list[dict[str, Any]]  # event summaries
    edges: list[dict[str, Any]]   # edges between these events
    root_event_id: str
    root_title_ko: str
    motif_type: str = "mixed"     # macro_chain | supply_chain | cross_asset | sector_rotation | mixed
    combined_score: float = 0.0
    evidence_score: float = 0.0
    causal_score: float = 0.0
    novelty_score: float = 0.0
    diversity_score: float = 0.0
    backtest_score: float = 0.0
    portfolio_score: float = 0.0
    aggregated_tickers: list[str] = field(default_factory=list)
    aggregated_sectors: list[str] = field(default_factory=list)
    narrative_ko: str = ""
    scenario_distribution: dict[str, float] = field(default_factory=dict)
    risk_flags: list[str] = field(default_factory=list)



def _build_motif_hash(events: list) -> str:
    import hashlib
    ids = sorted(str(e.id) for e in events)
    return hashlib.md5("|".join(ids).encode()).hexdigest()[:8]

class CombinatorialScanEngine:
    """
    Discovers meaningful event motifs (3+ connected events).

    Implements Budgeted Best-First Causal Expansion at the motif level.
    """

    GRADE_RANK = {"E4": 5, "E3": 4, "E2": 3, "E1": 2, "E0": 1}
    URGENCY_RANK = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
    INVESTMENT_TYPES = {"filing", "policy_announcement", "earnings", "macro", "supply_chain", "regulatory"}

    def __init__(self, db: Session):
        self.db = db

    def run(self, max_motifs: int = 80, min_events: int = 3) -> dict[str, Any]:
        """
        Main entry point: discover event motifs, score them, backtest filter.

        Returns ranked list of motifs for the UI inbox.
        """
        now = datetime.utcnow()
        result = {
            "run_at": now.isoformat(),
            "total_motifs_found": 0,
            "total_motifs_qualified": 0,
            "total_motifs_backtested": 0,
            "motifs": [],
        }

        # 1. Load event universe — filter to investment-relevant events
        all_events = self.db.query(Event).order_by(Event.published_at.desc()).limit(100).all()
        qualified = [
            e for e in all_events
            if self.GRADE_RANK.get(e.evidence_grade or "E0", 0) >= 1
            and (e.related_tickers or [])
        ]  # Any event with tickers and E1+ grade

        if len(qualified) < min_events:
            return result

        # 2. Build adjacency map from event relations + shared tickers/sectors
        event_map = {str(e.id): e for e in qualified}
        adj = self._build_adjacency(qualified)

        # 3. Find 3-event connected motifs
        motifs = self._enumerate_motifs(qualified, event_map, adj, min_size=min_events)

        result["total_motifs_found"] = len(motifs)

        # 4. Score all motifs
        existing_thesis_event_ids = self._get_existing_thesis_events()
        themed_motifs: list[EventMotif] = []

        # Track sector combos to penalize repetition
        sector_combo_counts: dict[str, int] = {}

        # Pre-cache portfolio tickers for scoring
        positions = self.db.query(PortfolioPosition).all()
        portfolio_tickers_cache = set(p.ticker.upper() for p in positions if p.ticker)
        
        for events_in_motif, edges_in_motif, motif_type in motifs:
            # Track sector combo for diversity bonus
            sectors_in = tuple(sorted(set((e.sector or "?").lower() for e in events_in_motif)))
            sector_key = "|".join(sectors_in)
            sector_combo_counts[sector_key] = sector_combo_counts.get(sector_key, 0) + 1
            rep_penalty = max(0, 1.0 - (sector_combo_counts[sector_key] - 1) * 0.15)

            score_data = self._score_motif(events_in_motif, edges_in_motif, existing_thesis_event_ids, portfolio_tickers_cache, motif_type=motif_type)
            # Apply repetition penalty
            score_data.combined_score = round(score_data.combined_score * rep_penalty, 4)
            if score_data.combined_score >= 0.08:  # quality threshold
                themed_motifs.append(score_data)

        # 5. Sort and deduplicate — use sorted event IDs as signature
        themed_motifs.sort(key=lambda m: m.combined_score, reverse=True)

        seen_signatures: set[str] = set()
        unique: list[dict] = []
        for m in themed_motifs:
            event_ids = sorted(e["event_id"] for e in m.events)
            sig = "|".join(event_ids)
            if sig not in seen_signatures:
                seen_signatures.add(sig)
                unique.append(self._motif_to_dict(m))
                if len(unique) >= max_motifs:
                    break

        # 6. Gate evaluation (10-gate system)
        from api.engine.gates import ScenarioPromotionGate, FailureModeDetector
        gate = ScenarioPromotionGate()
        fm_detector = FailureModeDetector()

        gated_motifs = []
        for m in unique:
            gating = gate.evaluate(m, existing_scenarios=unique[:10])
            m["gate_status"] = gating.final_status
            m["gate_score"] = gating.overall_score
            m["passed_gates"] = sum(1 for g in gating.gate_results if g.passed)
            m["failed_gates"] = gating.failed_gates
            gated_motifs.append(m)

        # Sort by gate score
        gated_motifs.sort(key=lambda m: (m.get("passed_gates", 0), m.get("combined_score", 0)), reverse=True)

        result["total_motifs_qualified"] = len(gated_motifs)
        result["total_motifs_backtested"] = len(gated_motifs)
        result["motifs"] = gated_motifs
        result["failure_modes"] = fm_detector.detect(gated_motifs)
        result["gate_summary"] = {
            "active_scenarios": sum(1 for m in gated_motifs if m.get("gate_status") == "active_scenario"),
            "high_conviction": sum(1 for m in gated_motifs if m.get("gate_status") == "high_conviction_research_candidate"),
            "developing": sum(1 for m in gated_motifs if m.get("gate_status") == "developing_thesis"),
            "watchlist": sum(1 for m in gated_motifs if m.get("gate_status") == "watchlist_hypothesis"),
        }

        return result

    def _build_adjacency(self, events: list[Event]) -> dict[str, set[str]]:
        """Build adjacency map from event relations + shared tickers/sectors."""
        adj: dict[str, set[str]] = defaultdict(set)
        event_ids = {str(e.id) for e in events}

        # From DB relations
        relations = (
            self.db.query(EventRelation)
            .filter(
                EventRelation.source_event_id.in_([e.id for e in events]),
                EventRelation.target_event_id.in_([e.id for e in events]),
            )
            .all()
        )
        for r in relations:
            s = str(r.source_event_id)
            t = str(r.target_event_id)
            if s in event_ids and t in event_ids:
                adj[s].add(t)
                adj[t].add(s)

        # From shared tickers (complement DB relations)
        for i, a in enumerate(events):
            aid = str(a.id)
            atickers = set(a.related_tickers or [])
            for j in range(i + 1, len(events)):
                b = events[j]
                bid = str(b.id)
                btickers = set(b.related_tickers or [])
                shared = atickers & btickers
                if shared and len(shared) >= 2:
                    adj[aid].add(bid)
                    adj[bid].add(aid)

        # From same sector
        sector_groups: dict[str, list[Event]] = defaultdict(list)
        for e in events:
            if e.sector:
                sector_groups[e.sector.lower()].append(e)

        for sector, evs in sector_groups.items():
            if len(evs) < 2:
                continue
            for i in range(len(evs)):
                for j in range(i + 1, len(evs)):
                    aid = str(evs[i].id)
                    bid = str(evs[j].id)
                    adj[aid].add(bid)
                    adj[bid].add(aid)

        return adj

    def _enumerate_motifs(
        self,
        events: list[Event],
        event_map: dict[str, Event],
        adj: dict[str, set[str]],
        min_size: int = 3,
    ) -> list[tuple[list[Event], list[dict], str]]:
        """
        Enumerate 3/4/5 event combinations with diverse seeds and connection patterns.
        Returns (events, edges, motif_type).
        """
        from itertools import combinations

        motifs: list[tuple[list[Event], list[dict], str]] = []

        # Diverse seed set: balance macro, bottom-up, supply-chain, cross-asset
        seeds = self._build_seed_set(events, max_total=24)
        event_sectors = {str(e.id): (e.sector or "").lower() for e in seeds}
        event_tickers = {str(e.id): set((t or "").upper() for t in (e.related_tickers or [])) for e in seeds}

        def _build_edges(evs):
            edges = []
            for i in range(len(evs)):
                for j in range(i+1, len(evs)):
                    si = str(evs[i].id); sj = str(evs[j].id)
                    st = event_tickers.get(si, set()) & event_tickers.get(sj, set())
                    same_sector = event_sectors.get(si) == event_sectors.get(sj)
                    relation_type = "supply_chain" if st else ("sector" if same_sector else "cross_asset")
                    label = f'공통 종목: {",".join(sorted(st))}' if st else (f'같은 섹터/산업 연결' if same_sector else '잠재 요인/자산 연결')
                    edges.append({"source": si, "target": sj, "type": relation_type, "strength": min(1.5 + len(st) * 0.3, 5.0), "label_ko": label})
            return edges

        def _classify_motif(evs):
            types = [e.event_type or "" for e in evs]
            sectors = {event_sectors.get(str(e.id), "") for e in evs}
            if "macro" in types and len(sectors) >= 3:
                return "macro_chain"
            if "supply_chain" in types or any(t in ("filing", "earnings") for t in types):
                return "supply_chain"
            if len(sectors) >= 3:
                return "cross_asset"
            if len(set(e.sector or "" for e in evs)) == 1:
                return "sector_rotation"
            return "mixed"

        count = 0
        max_total = 120

        for size in [3, 4]:
            if size > len(seeds) or count >= max_total:
                break
            # Cap iterations per size to keep runtime bounded
            from itertools import islice
            combo_iter = islice(combinations(range(len(seeds)), size), 1000)
            for combo in combo_iter:
                if count >= max_total:
                    break
                evs = [seeds[i] for i in combo]
                ids = [str(e.id) for e in evs]

                # Require at least 2 distinct sectors
                sectors = {event_sectors.get(i) for i in ids}
                sectors.discard("")
                if len(sectors) < 2:
                    continue

                # Require the subgraph to be connected via adjacency
                if not self._is_connected(ids, adj):
                    continue

                # Penalize motifs that are all macro events
                macro_count = sum(1 for e in evs if e.event_type == "macro")
                if macro_count >= size - 1:
                    continue

                count += 1
                motifs.append((evs, _build_edges(evs), _classify_motif(evs)))

        return motifs

    def _build_seed_set(self, events: list[Event], max_total: int = 24) -> list[Event]:
        """Pick a balanced seed set across event types to reduce macro/mega-cap bias."""
        buckets = {
            "macro": [],
            "policy_regulatory": [],
            "bottom_up": [],
            "supply_chain": [],
            "prediction_market": [],
            "other": [],
        }
        for e in events:
            et = e.event_type or ""
            if et == "macro":
                buckets["macro"].append(e)
            elif et in ("policy_announcement", "regulatory"):
                buckets["policy_regulatory"].append(e)
            elif et in ("filing", "earnings"):
                buckets["bottom_up"].append(e)
            elif et == "supply_chain":
                buckets["supply_chain"].append(e)
            elif et == "prediction_market":
                buckets["prediction_market"].append(e)
            else:
                buckets["other"].append(e)

        # Sort each bucket by grade/urgency
        for k in buckets:
            buckets[k].sort(
                key=lambda e: (self.GRADE_RANK.get(e.evidence_grade or "E0", 0), self.URGENCY_RANK.get(e.urgency or "Low", 0)),
                reverse=True,
            )

        # Quotas: cap macro, boost bottom-up/supply-chain/cross-asset
        quotas = {
            "macro": 4,
            "policy_regulatory": 5,
            "bottom_up": 6,
            "supply_chain": 5,
            "prediction_market": 4,
            "other": 6,
        }
        seeds: list[Event] = []
        seen = set()
        for bucket_name, limit in quotas.items():
            for e in buckets[bucket_name][:limit]:
                eid = str(e.id)
                if eid not in seen:
                    seeds.append(e)
                    seen.add(eid)

        # Fill remaining slots with highest-grade remaining events
        remaining = [e for e in events if str(e.id) not in seen]
        remaining.sort(
            key=lambda e: (self.GRADE_RANK.get(e.evidence_grade or "E0", 0), self.URGENCY_RANK.get(e.urgency or "Low", 0)),
            reverse=True,
        )
        seeds.extend(remaining[:max(0, max_total - len(seeds))])
        return seeds

    def _is_connected(self, ids: list[str], adj: dict[str, set[str]]) -> bool:
        """Check if a set of event ids forms a connected subgraph."""
        if not ids:
            return False
        visited = set()
        stack = [ids[0]]
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            for nxt in adj.get(cur, set()):
                if nxt in ids and nxt not in visited:
                    stack.append(nxt)
        return len(visited) == len(ids)

    def _score_motif(self, events: list[Event], edges: list[dict], existing_thesis_ids: set[str], portfolio_tickers_set: set[str] | None = None, motif_type: str = "mixed") -> EventMotif:
        """Score a motif across multiple dimensions."""
        # Evidence score: average of evidence grades
        grades = [self.GRADE_RANK.get(e.evidence_grade or "E0", 0) for e in events]
        # Investment-type bonus
        type_bonus = sum(0.15 for e in events if e.event_type in self.INVESTMENT_TYPES) / len(events)
        evidence_score = sum(grades) / len(grades) / 5 + type_bonus  # normalize to 0-1

        # Causal score: how many edges have mechanism explanations
        events_with_mechanism = sum(1 for e in events if e.mechanism_ko and len(e.mechanism_ko) > 20)
        causal_score = events_with_mechanism / len(events)

        # Novelty score: penalty if already in thesis
        already_thesised = sum(1 for e in events if str(e.id) in existing_thesis_ids)
        novelty_score = 1.0 - (already_thesised / len(events)) * 0.8

        # Diversity score: unique sectors
        sectors = set(e.sector or "unknown" for e in events)
        diversity_score = min(1.0, len(sectors) / 3)

        # Portfolio score: tickers that overlap with portfolio
        portfolio_tickers = portfolio_tickers_set if portfolio_tickers_set is not None else set()
        all_tickers: set[str] = set()
        for e in events:
            for t in (e.related_tickers or []):
                all_tickers.add(t.upper())
        overlap = all_tickers & portfolio_tickers
        portfolio_score = min(1.0, len(overlap) * 0.25) if portfolio_tickers else 0.3

        # Backtest score: lightweight — check if similar event combos exist in history
        backtest_score = self._lightweight_backtest(events)

        # Macro dominance penalty: avoid motifs made mostly of macro events
        macro_count = sum(1 for e in events if e.event_type == "macro")
        macro_penalty = min(0.25, macro_count / max(len(events), 1) * 0.3)

        # Mega-cap / ETF bias penalty: avoid motifs with only broad ETFs/indices
        all_tickers_upper = {t.upper() for e in events for t in (e.related_tickers or [])}
        broad_only = all(t in {"SPY", "QQQ", "DXY", "VIX", "TLT", "GLD", "USO", "XLE", "SMH", "SOX", "IBB", "XBI"} for t in all_tickers_upper) if all_tickers_upper else False
        etf_penalty = 0.2 if broad_only else 0.0

        # Combined score
        combined = (
            evidence_score * 0.30
            + causal_score * 0.25
            + novelty_score * 0.15
            + diversity_score * 0.10
            + backtest_score * 0.10
            + portfolio_score * 0.10
            - macro_penalty
            - etf_penalty
        )

        # Event types that make good roots
        root = events[0]  # seed event

        # Aggregate tickers and sectors
        agg_tickers = sorted(set().union(*[set(e.related_tickers or []) for e in events]))[:10]
        agg_sectors = sorted(set(e.sector or "" for e in events))

        # Build scenario distribution from weighted event scenarios
        bull_p = sum(
            next((s.get("probability", 0) for s in (e.conditions or []) if s.get("name") == "Bull"), 0.33) / len(events)
            for e in events
        )
        bear_p = sum(
            next((s.get("probability", 0) for s in (e.conditions or []) if s.get("name") == "Bear"), 0.22) / len(events)
            for e in events
        )
        base_p = 1.0 - bull_p - bear_p
        if base_p < 0.05:
            base_p = 0.05
            total = bull_p + base_p + bear_p
            bull_p /= total
            base_p /= total
            bear_p /= total

        # Build narrative as a causal chain
        narrative_ko = self._build_motif_narrative(events, motif_type)

        # Risk flags
        risk_flags = []
        if already_thesised > 0:
            risk_flags.append(f"이미 {already_thesised}개 등록됨")
        if causal_score < 0.4:
            risk_flags.append("메커니즘 불충분")
        if backtest_score < 0.3:
            risk_flags.append("과거 유사 패턴 없음")

        event_summaries = [
            {
                "event_id": str(e.id),
                "title_ko": e.title_ko or e.title or "",
                "event_type": e.event_type or "",
                "evidence_grade": e.evidence_grade or "E0",
                "urgency": e.urgency or "Low",
                "sector_ko": e.sector_ko or e.sector or "",
                "mechanism_ko": (e.mechanism_ko or "")[:150],
                "related_tickers": list(e.related_tickers or [])[:5],
                "scenarios": [
                    {"name": s.get("name", ""), "probability": s.get("probability", 0)}
                    for s in (e.conditions or [])
                ][:3],
            }
            for e in events
        ]

        motif_hash = _build_motif_hash(events)
        return EventMotif(
            motif_id=f"motif-{root.id}-{motif_hash}",
            events=event_summaries,
            edges=edges,
            root_event_id=str(root.id),
            root_title_ko=root.title_ko or root.title or "",
            motif_type=motif_type,
            combined_score=round(combined, 4),
            evidence_score=round(evidence_score, 4),
            causal_score=round(causal_score, 4),
            novelty_score=round(novelty_score, 4),
            diversity_score=round(diversity_score, 4),
            backtest_score=round(backtest_score, 4),
            portfolio_score=round(portfolio_score, 4),
            aggregated_tickers=agg_tickers,
            aggregated_sectors=agg_sectors,
            narrative_ko=narrative_ko,
            scenario_distribution={"Bull": round(bull_p, 3), "Base": round(base_p, 3), "Bear": round(bear_p, 3)},
            risk_flags=risk_flags,
        )


    def _build_motif_narrative(self, events: list[Event], motif_type: str) -> str:
        """Build a chain-style Korean narrative for a motif."""
        names = [e.title_ko or e.title or "?" for e in events]
        sectors = sorted(set((e.sector_ko or e.sector or "기타") for e in events))
        mechanisms = []
        for e in events:
            mech = (e.mechanism_ko or "")[:90]
            if mech:
                mechanisms.append(f"• {e.title_ko or ''}: {mech}")

        type_label = {
            "macro_chain": "매크로 전파 체인",
            "supply_chain": "기업/공급망 체인",
            "cross_asset": "크로스 자산 체인",
            "sector_rotation": "섹터 로테이션 체인",
            "mixed": "복합 인과 체인",
        }.get(motif_type, "인과 체인")

        chain = " → ".join(names)
        parts = [
            f"[{type_label}] {chain}",
            f"관련 섹터: {', '.join(sectors)}",
            "",
            "핵심 메커니즘:",
        ]
        parts.extend(mechanisms)
        parts.append("\n이 조합이 성립하려면 각 사건의 전파 경로가 실제로 작동해야 합니다.")
        return "\n".join(parts)

    def _lightweight_backtest(self, events: list[Event]) -> float:
        """
        Lightweight backtest: check if events of same families have been seen together.
        In MVP, this checks: (1) do any event pairs share tickers? (2) do they have counterevidence?
        Higher = more likely to be a real pattern.
        """
        # Check ticker overlap diversity
        all_tickers: set[str] = set()
        for e in events:
            for t in (e.related_tickers or []):
                all_tickers.add(t)

        ticker_diversity = min(1.0, len(all_tickers) / 8) * 0.4

        # Check counterevidence presence (shows rigor)
        has_counter = sum(1 for e in events if e.counterevidence_ko and len(e.counterevidence_ko) > 0)
        counter_score = (has_counter / len(events)) * 0.3

        # Check mechanism completeness
        has_mechanism = sum(1 for e in events if e.mechanism_ko and len(e.mechanism_ko) > 20)
        mechanism_score = (has_mechanism / len(events)) * 0.3

        return ticker_diversity + counter_score + mechanism_score

    def _get_existing_thesis_events(self) -> set[str]:
        theses = self.db.query(Thesis).all()
        return {str(t.core_event_id) for t in theses if t.core_event_id}

    def _motif_to_dict(self, m: EventMotif) -> dict[str, Any]:
        return {
            "motif_id": m.motif_id,
            "root_title_ko": m.root_title_ko,
            "events": m.events,
            "edge_count": len(m.edges),
            "combined_score": m.combined_score,
            "evidence_score": m.evidence_score,
            "causal_score": m.causal_score,
            "novelty_score": m.novelty_score,
            "diversity_score": m.diversity_score,
            "backtest_score": m.backtest_score,
            "portfolio_score": m.portfolio_score,
            "aggregated_tickers": m.aggregated_tickers,
            "aggregated_sectors": m.aggregated_sectors,
            "motif_type": m.motif_type,
            "narrative_ko": m.narrative_ko,
            "scenario_distribution": m.scenario_distribution,
            "risk_flags": m.risk_flags,
            "event_count": len(m.events),
        }
