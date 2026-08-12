"""
Multi-Layer Graph Builder (Spec Section V)

Builds typed edges across layers:
  Layer 1: Source Layer
  Layer 2: Claim Layer  
  Layer 3: Event Layer
  Layer 4: Entity Layer
  Layer 5: Economic Mechanism Layer
  Layer 6: Market Expectation Layer
  Layer 7: Exposure Layer
  Layer 8: Scenario Layer

Key difference from v1: edges are NOT just "market" type. They use the full
causal taxonomy with direction, mechanism_rationale, and evidence_grade.
"""
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from api.models import (
    Event, EventRelation, CandidateEdge, Entity, Relation,
    Exposure, Scenario, Thesis, PortfolioPosition,
)


# Causal edge taxonomy (Spec Section VIII)
CAUSAL_EDGES = {
    "increases", "decreases", "constrains", "enables",
    "delays", "accelerates", "transfers_demand_to", "shifts_market_share_to",
    "raises_cost_of", "lowers_cost_of", "expands_multiple_of", "compresses_multiple_of",
    "increases_risk_premium_of", "reduces_risk_premium_of",
}

EXPOSURE_EDGES = {
    "direct_revenue_exposure", "direct_cost_exposure", "regulatory_exposure",
    "competitive_exposure", "supply_chain_exposure", "financing_exposure",
    "macro_beta_exposure", "sentiment_exposure", "index_or_etf_exposure",
}

MARKET_EXPECTATION_EDGES = {
    "priced_into", "surprises_upside", "surprises_downside",
    "confirms_expectation", "invalidates_expectation",
    "increases_implied_probability", "decreases_implied_probability",
    "increases_implied_volatility", "decreases_implied_volatility",
}

EVIDENCE_EDGES = {
    "sourced_from", "supports", "contradicts", "confirms", "denies", "corrects",
}

ENTITY_RELATION_EDGES = {
    "owns", "regulates", "competes_with", "supplies", "purchases_from",
    "licenses_to", "partners_with", "invests_in", "depends_on",
    "substitutes_for", "belongs_to_industry",
}

EVENT_PROGRESSION_EDGES = {
    "precedes", "follows", "escalates_to", "resolves_into",
    "delays", "cancels", "supersedes", "extends",
}


class MultiLayerGraphBuilder:
    """Builds the multi-layer graph from existing data."""

    def __init__(self, db: Session):
        self.db = db

    def build_all(self) -> dict[str, int]:
        """Build all layers. Returns count of edges created per layer."""
        return {
            "causal_edges": self._build_causal_edges(),
            "exposure_edges": self._build_exposure_edges(),
            "progression_edges": self._build_progression_edges(),
            "candidate_edges": self._build_candidate_edges_from_relations(),
        }

    def _build_causal_edges(self) -> int:
        """
        Build causal edges between events using proper taxonomy.
        Replaces old 'market' edges with typed causal relationships.
        """
        created = 0
        events = self.db.query(Event).order_by(Event.published_at.desc()).limit(100).all()

        for i, a in enumerate(events):
            a_tickers = set(t.upper() for t in (a.related_tickers or []))
            a_sector = (a.sector or "").lower()
            a_type = a.event_type or ""

            for b in events[i + 1:]:
                b_tickers = set(t.upper() for t in (b.related_tickers or []))
                b_sector = (b.sector or "").lower()
                b_type = b.event_type or ""

                shared = a_tickers & b_tickers
                same_sector = a_sector and b_sector and a_sector == b_sector

                if not shared and not same_sector:
                    continue

                # Determine proper causal edge type
                edge_type, mechanism = self._infer_causal_type(a, b, shared, same_sector)

                # Check not already exists
                existing = self._find_event_edge(a.id, b.id, edge_type)
                if existing:
                    continue

                strength = 1.5 + (len(shared) * 0.5)

                self.db.add(EventRelation(
                    source_event_id=a.id, target_event_id=b.id,
                    edge_type=edge_type, strength=strength,
                    mechanism_ko=mechanism, mechanism=mechanism,
                    causal_or_associative="causal" if shared else "associative",
                    connection_rationale=mechanism,
                    mechanism_rationale=f"Shared tickers: {','.join(sorted(shared))}" if shared else f"Same sector: {a_sector}",
                    direction="positive" if strength > 0 else "negative",
                    confidence=min(0.9, 0.4 + strength * 0.1),
                    evidence_rationale="Grade E2" if shared else "Grade E1",
                ))
                created += 1

                if created % 10 == 0:
                    self.db.flush()

        self.db.commit()
        return created

    def _infer_causal_type(
        self, a: Event, b: Event, shared_tickers: set, same_sector: bool,
    ) -> tuple[str, str]:
        """Infer the proper causal edge type based on event characteristics."""
        a_type = a.event_type or ""
        b_type = b.event_type or ""

        if a_type == "policy_announcement" or b_type == "policy_announcement":
            return "enables", "정책 변경이 공급/수요 조건을 변화시킴"
        if a_type == "supply_chain" or b_type == "supply_chain":
            return "constrains", "공급망 차질이 생산/가격에 영향"
        if a_type == "regulatory" or b_type == "regulatory":
            return "constrains", "규제 변경이 시장 접근 조건을 변화시킴"
        if a_type == "filing" or b_type == "filing":
            if "capex" in (a.action or "").lower() or "capex" in (b.action or "").lower():
                return "decreases", "투자 감소가 공급망 수요를 줄임"
            return "increases", "공시 정보가 시장 기대를 업데이트"
        if a_type == "macro" or b_type == "macro":
            return "increases_risk_premium_of", "거시 변수가 위험 프리미엄에 영향"
        if a_type == "earnings" or b_type == "earnings":
            return "increases", "실적 데이터가 밸류에이션 기대를 변화시킴"

        return "increases", "경제적 연결"

    def _find_event_edge(self, src_id: UUID, tgt_id: UUID, edge_type: str) -> EventRelation | None:
        return self.db.query(EventRelation).filter(
            EventRelation.source_event_id == src_id,
            EventRelation.target_event_id == tgt_id,
            EventRelation.edge_type == edge_type,
        ).first()

    def _build_exposure_edges(self) -> int:
        """
        Build exposure edges: which tickers are exposed to which events,
        and through what mechanism.
        """
        created = 0
        events = self.db.query(Event).order_by(Event.published_at.desc()).limit(100).all()

        for event in events:
            tickers = event.related_tickers or []
            event_id = event.id
            sector = event.sector_ko or event.sector or ""

            for ticker in tickers:
                # Determine exposure type
                exp_type = self._determine_exposure_type(event, ticker)

                existing = self.db.query(Exposure).filter(
                    Exposure.event_id == event_id,
                    Exposure.ticker == ticker,
                ).first()
                if existing:
                    continue

                self.db.add(Exposure(
                    event_id=event_id,
                    ticker=ticker,
                    entity_name=ticker,
                    exposure_tier="direct",
                    relationship_type=exp_type,
                    direction_of_impact="positive",
                    economic_mechanism=event.mechanism_ko or "",
                    estimated_materiality=0.5,
                    source_of_relationship=f"Event: {event.title_ko or event.title}",
                    relationship_confidence=0.7,
                    evidence_grade=event.evidence_grade or "E1",
                    status="proposed",
                ))
                created += 1

                if created % 20 == 0:
                    self.db.flush()

        self.db.commit()
        return created

    def _determine_exposure_type(self, event: Event, ticker: str) -> str:
        etype = event.event_type or ""
        if etype in ("policy_announcement", "regulatory"):
            return "regulatory_exposure"
        if etype == "supply_chain":
            return "supply_chain_exposure"
        if etype == "macro":
            return "macro_beta_exposure"
        if etype == "earnings":
            return "direct_revenue_exposure" if ticker in (event.related_tickers or [])[:2] else "competitive_exposure"
        if etype == "filing":
            return "direct_cost_exposure"
        return "sentiment_exposure"

    def _build_progression_edges(self) -> int:
        """
        Build event progression edges: detect Application → Review → Approval chains.
        """
        created = 0
        events = self.db.query(Event).filter(
            Event.event_stage.isnot(None),
            Event.event_stage != "detected",
        ).order_by(Event.published_at.asc()).all()

        # Group by actor
        by_actor: dict[str, list[Event]] = {}
        for e in events:
            actor = (e.actor or "").lower().strip()
            if actor:
                by_actor.setdefault(actor, []).append(e)

        for actor, evs in by_actor.items():
            if len(evs) < 2:
                continue
            for i in range(len(evs)):
                for j in range(i + 1, len(evs)):
                    a_stage = evs[i].event_stage or ""
                    b_stage = evs[j].event_stage or ""

                    # Check if stages form a progression
                    if self._stages_are_sequential(a_stage, b_stage):
                        existing = self._find_event_edge(evs[i].id, evs[j].id, "precedes")
                        if not existing:
                            self.db.add(EventRelation(
                                source_event_id=evs[i].id, target_event_id=evs[j].id,
                                edge_type="precedes", strength=2.0,
                                mechanism_ko=f"{a_stage} → {b_stage}",
                                causal_or_associative="causal",
                                connection_rationale=f"Event progression: {a_stage} → {b_stage}",
                                evidence_grade="E2",
                                direction="positive",
                            ))
                            created += 1

        self.db.commit()
        return created

    def _stages_are_sequential(self, a: str, b: str) -> bool:
        chain = [
            "rumor", "announcement", "application_submitted", "application_accepted",
            "review_started", "deadline_scheduled", "committee_review",
            "approval", "conditional_approval", "rejection", "commercial_launch",
            "revenue_confirmation",
        ]
        if a in chain and b in chain:
            return chain.index(a) < chain.index(b)
        return False

    def _build_candidate_edges_from_relations(self) -> int:
        """
        Convert weak EventRelations into CandidateEdges with proper status tracking.
        """
        created = 0
        weak_relations = self.db.query(EventRelation).filter(
            EventRelation.strength < 1.5,
            EventRelation.edge_type == "market",
        ).all()

        for rel in weak_relations[:50]:  # Limit batch size
            self.db.add(CandidateEdge(
                from_node_id=rel.source_event_id,
                from_node_type="event",
                to_node_id=rel.target_event_id,
                to_node_type="event",
                edge_type=rel.edge_type,
                strength=rel.strength or 1.0,
                confidence=0.3,
                status="proposed",
                evidence_grade="C0",
                connection_rationale=rel.mechanism_ko or "",
                mechanism_rationale=rel.mechanism or "",
                valid_from=rel.created_at,
            ))
            created += 1

        self.db.commit()
        return created
