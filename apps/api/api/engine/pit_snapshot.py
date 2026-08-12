"""
Point-in-Time Snapshot Engine (Spec XXXI-XXXII)

Reconstructs the information environment available at a specific historical
cutoff time. All nodes, edges, prices, and expectations used in a backtest
must satisfy:

    backtest_available_time <= cutoff_time

If backtest_available_time is not set, the engine falls back to a safe
ordering: published_at -> effective_date -> first_observed_at -> created_at.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session

from api.models import (
    Event,
    EventRelation,
    SourceDocument,
    MarketPrice,
    MarketInstrument,
    PortfolioPosition,
    Thesis,
    Scenario,
    CandidateEdge,
    Claim,
    Rumor,
    Exposure,
)


@dataclass
class PITSnapshot:
    """A complete point-in-time snapshot of the system state."""

    cutoff_time: datetime
    snapshot_version: str
    source_snapshot: dict[str, Any] = field(default_factory=dict)
    market_snapshot: dict[str, Any] = field(default_factory=dict)
    expectation_snapshot: dict[str, Any] = field(default_factory=dict)
    graph_snapshot: dict[str, Any] = field(default_factory=dict)
    fundamental_snapshot: dict[str, Any] = field(default_factory=dict)
    active_scenarios: list[dict[str, Any]] = field(default_factory=list)
    unresolved_uncertainties: list[dict[str, Any]] = field(default_factory=list)
    rumor_state: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cutoff_time": self.cutoff_time.isoformat(),
            "snapshot_version": self.snapshot_version,
            "source_snapshot": self.source_snapshot,
            "market_snapshot": self.market_snapshot,
            "expectation_snapshot": self.expectation_snapshot,
            "graph_snapshot": self.graph_snapshot,
            "fundamental_snapshot": self.fundamental_snapshot,
            "active_scenarios": self.active_scenarios,
            "unresolved_uncertainties": self.unresolved_uncertainties,
            "rumor_state": self.rumor_state,
            "metadata": self.metadata,
        }


class PITSnapshotBuilder:
    """Builds point-in-time snapshots for backtesting."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        cutoff_time: datetime,
        universe: Optional[dict[str, Any]] = None,
    ) -> PITSnapshot:
        """Build a full PIT snapshot at cutoff_time."""
        snapshot_version = f"pit-{cutoff_time.strftime('%Y%m%d%H%M%S')}"

        return PITSnapshot(
            cutoff_time=cutoff_time,
            snapshot_version=snapshot_version,
            source_snapshot=self._build_source_snapshot(cutoff_time),
            market_snapshot=self._build_market_snapshot(cutoff_time, universe),
            expectation_snapshot=self._build_expectation_snapshot(cutoff_time),
            graph_snapshot=self._build_graph_snapshot(cutoff_time),
            fundamental_snapshot=self._build_fundamental_snapshot(cutoff_time),
            active_scenarios=self._build_active_scenarios(cutoff_time),
            unresolved_uncertainties=self._build_unresolved_uncertainties(cutoff_time),
            rumor_state=self._build_rumor_state(cutoff_time),
            metadata={
                "universe": universe or {},
                "total_events_considered": self.db.query(Event).count(),
                "events_available_at_cutoff": self._available_query(
                    self.db.query(Event), Event, cutoff_time
                ).count(),
            },
        )

    # ------------------------------------------------------------------
    # Availability filter
    # ------------------------------------------------------------------

    @staticmethod
    def _available_time_expr(model):
        """Expression that yields the earliest safe availability time.

        Uses only columns that actually exist on the model.
        """
        candidates = [
            "backtest_available_time",
            "publish_time",
            "published_at",
            "observed_time",
            "first_observed_at",
            "first_seen_time",
            "effective_time",
            "effective_date",
            "timestamp",
            "ingested_time",
            "created_at",
        ]
        exprs = [getattr(model, attr) for attr in candidates if hasattr(model, attr)]
        return func.coalesce(*exprs)

    def _available_query(self, query, model, cutoff_time: datetime):
        """Filter a query to rows available at or before cutoff_time."""
        available = self._available_time_expr(model)
        # Also exclude rows that became invalid before cutoff_time
        filters = [available <= cutoff_time]
        if hasattr(model, "valid_to"):
            filters.append(
                or_(model.valid_to.is_(None), model.valid_to > cutoff_time)
            )
        return query.filter(and_(*filters))

    # ------------------------------------------------------------------
    # Snapshot builders
    # ------------------------------------------------------------------

    def _build_source_snapshot(self, cutoff_time: datetime) -> dict[str, Any]:
        docs = (
            self._available_query(
                self.db.query(SourceDocument).order_by(SourceDocument.publish_time.desc()),
                SourceDocument,
                cutoff_time,
            )
            .limit(500)
            .all()
        )
        return {
            "document_count": len(docs),
            "documents": [
                {
                    "id": str(d.id),
                    "source_name": (d.source.source_name if d.source else None),
                    "title": d.title,
                    "published_at": (
                        d.published_at.isoformat() if d.published_at else None
                    ),
                    "backtest_available_time": (
                        d.backtest_available_time.isoformat()
                        if d.backtest_available_time
                        else None
                    ),
                    "content_type": d.content_type,
                }
                for d in docs
            ],
        }

    def _build_market_snapshot(
        self,
        cutoff_time: datetime,
        universe: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        symbols = universe.get("symbols", []) if universe else []
        query = self.db.query(MarketPrice).join(MarketInstrument)
        if symbols:
            query = query.filter(MarketInstrument.symbol.in_(symbols))

        # Latest price per instrument at or before cutoff
        subq = (
            self._available_query(query, MarketPrice, cutoff_time)
            .with_entities(
                MarketPrice.instrument_id,
                func.max(self._available_time_expr(MarketPrice)).label("latest_time"),
            )
            .group_by(MarketPrice.instrument_id)
            .subquery()
        )

        latest = (
            self.db.query(MarketPrice, MarketInstrument.symbol)
            .join(MarketInstrument, MarketPrice.instrument_id == MarketInstrument.id)
            .join(
                subq,
                and_(
                    MarketPrice.instrument_id == subq.c.instrument_id,
                    self._available_time_expr(MarketPrice) == subq.c.latest_time,
                ),
            )
            .all()
        )

        return {
            "price_count": len(latest),
            "prices": [
                {
                    "symbol": sym,
                    "timestamp": (
                        mp.timestamp.isoformat() if mp.timestamp else None
                    ),
                    "open": mp.open,
                    "high": mp.high,
                    "low": mp.low,
                    "close": mp.close,
                    "volume": mp.volume,
                }
                for mp, sym in latest
            ],
        }

    def _build_expectation_snapshot(self, cutoff_time: datetime) -> dict[str, Any]:
        # Claims act as soft expectation / consensus proxies
        claims = (
            self._available_query(
                self.db.query(Claim).order_by(Claim.first_seen_time.desc()),
                Claim,
                cutoff_time,
            )
            .limit(200)
            .all()
        )
        rumors = (
            self._available_query(
                self.db.query(Rumor).order_by(Rumor.first_seen_time.desc()),
                Rumor,
                cutoff_time,
            )
            .limit(100)
            .all()
        )
        return {
            "claim_count": len(claims),
            "claims": [
                {
                    "id": str(c.id),
                    "claim_text_ko": c.claim_text_ko or c.claim_text,
                    "confirmation_status": c.confirmation_status,
                    "first_seen_time": (
                        c.first_seen_time.isoformat() if c.first_seen_time else None
                    ),
                }
                for c in claims
            ],
            "rumor_count": len(rumors),
            "rumors": [
                {
                    "id": str(r.id),
                    "claim_text_ko": r.claim_text_ko or r.claim_text,
                    "confirmation_status": r.confirmation_status,
                    "mention_volume": r.mention_volume,
                }
                for r in rumors
            ],
        }

    def _build_graph_snapshot(self, cutoff_time: datetime) -> dict[str, Any]:
        events = (
            self._available_query(
                self.db.query(Event).order_by(Event.published_at.desc()),
                Event,
                cutoff_time,
            )
            .limit(200)
            .all()
        )
        event_ids = {e.id for e in events}

        relations = (
            self._available_query(
                self.db.query(EventRelation),
                EventRelation,
                cutoff_time,
            )
            .filter(
                EventRelation.source_event_id.in_(event_ids),
                EventRelation.target_event_id.in_(event_ids),
            )
            .all()
        )

        candidate_edges = (
            self._available_query(
                self.db.query(CandidateEdge).filter(CandidateEdge.status == "proposed"),
                CandidateEdge,
                cutoff_time,
            )
            .limit(200)
            .all()
        )

        return {
            "event_count": len(events),
            "events": [
                {
                    "id": str(e.id),
                    "title_ko": e.title_ko or e.title,
                    "event_type": e.event_type,
                    "evidence_grade": e.evidence_grade,
                    "published_at": (
                        e.published_at.isoformat() if e.published_at else None
                    ),
                    "backtest_available_time": (
                        e.backtest_available_time.isoformat()
                        if e.backtest_available_time
                        else None
                    ),
                    "sector_ko": e.sector_ko or e.sector,
                }
                for e in events
            ],
            "relation_count": len(relations),
            "relations": [
                {
                    "source_id": str(r.source_event_id),
                    "target_id": str(r.target_event_id),
                    "edge_type": r.edge_type,
                    "strength": r.strength,
                    "causal_or_associative": r.causal_or_associative,
                }
                for r in relations
            ],
            "candidate_edge_count": len(candidate_edges),
            "candidate_edges": [
                {
                    "id": str(ce.id),
                    "from_node_id": str(ce.from_node_id),
                    "to_node_id": str(ce.to_node_id),
                    "edge_type": ce.edge_type,
                    "strength": ce.strength,
                    "confidence": ce.confidence,
                }
                for ce in candidate_edges
            ],
        }

    def _build_fundamental_snapshot(self, cutoff_time: datetime) -> dict[str, Any]:
        # Exposures are the closest proxy to fundamental linkages in MVP
        exposures = (
            self._available_query(
                self.db.query(Exposure).order_by(Exposure.created_at.desc()),
                Exposure,
                cutoff_time,
            )
            .limit(200)
            .all()
        )
        positions = self.db.query(PortfolioPosition).all()
        return {
            "exposure_count": len(exposures),
            "exposures": [
                {
                    "id": str(ex.id),
                    "ticker": ex.ticker,
                    "entity_name": ex.entity_name,
                    "relationship_type": ex.relationship_type,
                    "direction_of_impact": ex.direction_of_impact,
                    "estimated_materiality": ex.estimated_materiality,
                    "evidence_grade": ex.evidence_grade,
                }
                for ex in exposures
            ],
            "portfolio_positions": [
                {
                    "ticker": p.ticker,
                    "shares": p.shares,
                    "avg_cost": p.avg_cost,
                    "current_price": p.current_price,
                }
                for p in positions
            ],
        }

    def _build_active_scenarios(self, cutoff_time: datetime) -> list[dict[str, Any]]:
        scenarios = (
            self._available_query(
                self.db.query(Scenario).filter(Scenario.status == "active"),
                Scenario,
                cutoff_time,
            )
            .order_by(Scenario.created_at.desc())
            .limit(100)
            .all()
        )
        return [
            {
                "id": str(s.id),
                "scenario_name": s.scenario_name,
                "probability_estimate": s.probability_estimate,
                "time_horizon": s.time_horizon,
                "affected_assets": s.affected_assets,
            }
            for s in scenarios
        ]

    def _build_unresolved_uncertainties(self, cutoff_time: datetime) -> list[dict[str, Any]]:
        events = (
            self._available_query(
                self.db.query(Event).filter(
                    Event.official_confirmation_status != "confirmed"
                ),
                Event,
                cutoff_time,
            )
            .order_by(Event.published_at.desc())
            .limit(50)
            .all()
        )
        return [
            {
                "id": str(e.id),
                "title_ko": e.title_ko or e.title,
                "official_confirmation_status": e.official_confirmation_status,
                "next_events_ko": e.next_events_ko,
            }
            for e in events
        ]

    def _build_rumor_state(self, cutoff_time: datetime) -> list[dict[str, Any]]:
        rumors = (
            self._available_query(
                self.db.query(Rumor).filter(
                    Rumor.confirmation_status != "confirmed"
                ),
                Rumor,
                cutoff_time,
            )
            .order_by(Rumor.first_seen_time.desc())
            .limit(50)
            .all()
        )
        return [
            {
                "id": str(r.id),
                "claim_text_ko": r.claim_text_ko or r.claim_text,
                "confirmation_status": r.confirmation_status,
                "mention_volume": r.mention_volume,
                "manipulation_risk": r.manipulation_risk,
            }
            for r in rumors
        ]
