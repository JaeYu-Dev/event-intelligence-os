"""
Engine Orchestrator

Coordinates all engines and provides a unified interface for the API layer.
Implements the cost-aware compute priority queue from the spec.
"""
from datetime import datetime

from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from api.models import Event, Thesis, PortfolioPosition
from api.engine.discovery import DiscoveryEngine
from api.engine.assimilation import AssimilationEngine
from api.engine.rebalance import RebalanceEngine, EventWindowPack, RebalanceState
from api.engine.validation import ValidationEngine
from api.engine.calendar import CalendarEngine
from api.engine.pit_snapshot import PITSnapshotBuilder
from api.engine.pit_backtest import WalkForwardEngine, BacktestConfig


@dataclass
class ComputePriority:
    """Cost-aware priority for compute resource allocation."""
    event_id: str
    priority: float
    reason: str
    estimated_cost_usd: float = 0.0


class EngineOrchestrator:
    """
    Central orchestrator for all Event Intelligence OS engines.

    Usage:
        orch = EngineOrchestrator(db_session)
        cmd_center = orch.command_center()
        discoveries = orch.run_discovery()
    """

    def __init__(self, db: Session):
        self.db = db
        self.discovery = DiscoveryEngine(db)
        self.assimilation = AssimilationEngine(db)
        self.rebalance = RebalanceEngine(db)
        self.validation = ValidationEngine(db)
        self.calendar = CalendarEngine(db)
        self.pit_snapshot = PITSnapshotBuilder(db)
        self.backtest = WalkForwardEngine(db)

    # ------------------------------------------------------------------
    # Command Center (Section 32.1)
    # ------------------------------------------------------------------

    def command_center(self) -> dict[str, Any]:
        """Build the full Command Center view."""
        events = (
            self.db.query(Event)
            .order_by(Event.published_at.desc())
            .limit(100)
            .all()
        )
        theses = self.db.query(Thesis).all()

        at_risk = [t for t in theses if t.status in ("At Risk", "Invalidated")]
        active = [t for t in theses if t.status not in ("Archived", "Resolved", "Invalidated")]

        # Find high-priority events
        high_priority_events = [
            e for e in events
            if e.urgency in ("Critical", "High") and e.evidence_grade in ("E3", "E4")
        ]

        # Compute research queue priority
        compute_queue = self._compute_priority_queue(events, theses)

        # Calendar
        calendar = self.calendar.get_cockpit_view()

        return {
            "as_of": "2026-07-02T00:00:00Z",
            "priority_actions": [
                {
                    "event_id": str(e.id),
                    "title_ko": e.title_ko or e.title or "",
                    "urgency": e.urgency,
                    "evidence_grade": e.evidence_grade,
                    "action_required": "Research Required" if e.urgency in ("Critical", "High") else "Watch",
                }
                for e in high_priority_events[:5]
            ],
            "armed_events": calendar.get("armed_events", []),
            "at_risk_theses": [
                {
                    "id": str(t.id),
                    "title": t.title or "",
                    "status": t.status,
                    "action": t.action,
                }
                for t in at_risk[:5]
            ],
            "root_events": [
                {
                    "id": str(e.id),
                    "title_ko": e.title_ko or e.title or "",
                    "event_type": e.event_type,
                    "evidence_grade": e.evidence_grade,
                    "urgency": e.urgency,
                    "sector_ko": e.sector_ko or e.sector or "",
                }
                for e in events[:10]
                if e.evidence_grade in ("E3", "E4")
            ],
            "research_queue": compute_queue,
            "active_theses_count": len(active),
            "at_risk_count": len(at_risk),
            "system_health": {
                "events_total": len(events),
                "theses_total": len(theses),
                "engine_status": "operational",
            },
        }

    def _compute_priority_queue(
        self,
        events: list[Event],
        theses: list[Thesis],
    ) -> list[dict[str, Any]]:
        """Compute cost-aware priority queue for compute allocation.

        ComputePriority = PortfolioImpact * EventImminence * EvidenceConfidence
                        * ThesisStateUrgency * ExpectedInformationGain
                        / EstimatedComputeCost
        """
        urgency_rank = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
        thesis_state_urgency = {
            "At Risk": 4, "Invalidated": 4, "Active": 2, "Watching": 1, "Resolved": 0, "Archived": 0,
        }
        grade_confidence = {"E4": 1.0, "E3": 0.85, "E2": 0.65, "E1": 0.35, "E0": 0.15}

        priorities: list[tuple[float, dict]] = []

        # Build thesis event map
        thesis_events: dict[str, set[str]] = {}
        for t in theses:
            if t.core_event_id:
                thesis_events.setdefault(str(t.core_event_id), set()).add(str(t.id))

        for e in events:
            linked_thesis_ids = thesis_events.get(str(e.id), set())

            portfolio_impact = min(1.0, len(linked_thesis_ids) * 0.3)
            event_imminence = 0.5  # default
            if e.effective_date:
                from datetime import datetime
                delta = (e.effective_date.replace(tzinfo=None) - datetime.utcnow()).total_seconds()
                if delta < 0:
                    event_imminence = 1.0  # past or now
                elif delta < 86400:
                    event_imminence = 0.9  # within 24h
                elif delta < 604800:
                    event_imminence = 0.6  # within 7d
                else:
                    event_imminence = 0.3

            evidence_conf = grade_confidence.get(e.evidence_grade or "E1", 0.35)
            urgency = urgency_rank.get(e.urgency or "Low", 1) / 4

            # Thesis state urgency: max across linked theses
            max_thesis_urgency = 0.0
            for tid in linked_thesis_ids:
                t = next((t for t in theses if str(t.id) == tid), None)
                if t:
                    max_thesis_urgency = max(max_thesis_urgency, thesis_state_urgency.get(t.status or "Watching", 1))
            thesis_urgency = max_thesis_urgency / 4 if max_thesis_urgency > 0 else 0.25

            info_gain = evidence_conf  # higher evidence means higher information value
            compute_cost = 0.01  # base cost

            priority = (
                portfolio_impact * event_imminence * evidence_conf
                * thesis_urgency * info_gain / (compute_cost + 0.001)
            )

            priorities.append((priority, {
                "event_id": str(e.id),
                "title_ko": e.title_ko or e.title or "",
                "priority": round(priority, 4),
                "linked_theses": len(linked_thesis_ids),
                "urgency": e.urgency,
                "evidence_grade": e.evidence_grade,
            }))

        priorities.sort(key=lambda x: x[0], reverse=True)
        return [p[1] for p in priorities[:20]]


    # ------------------------------------------------------------------
    # Point-in-Time Snapshot (Spec XXXI-XXXII)
    # ------------------------------------------------------------------

    def build_pit_snapshot(
        self,
        cutoff_time: datetime,
        universe: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a point-in-time snapshot for backtesting."""
        from datetime import timezone
        if isinstance(cutoff_time, str):
            cutoff_time = datetime.fromisoformat(cutoff_time.replace("Z", "+00:00"))
        if cutoff_time.tzinfo is None:
            cutoff_time = cutoff_time.replace(tzinfo=timezone.utc)
        snapshot = self.pit_snapshot.build(cutoff_time, universe=universe)
        return snapshot.to_dict()


    # ------------------------------------------------------------------
    # Walk-Forward Backtest (Spec XXXI-XLIII)
    # ------------------------------------------------------------------

    def run_walk_forward_backtest(
        self,
        run_name: str,
        cutoff_start: str,
        cutoff_end: str,
        train_window_days: int = 365,
        val_window_days: int = 90,
        test_window_days: int = 90,
        step_days: int = 30,
        universe: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a walk-forward backtest."""
        config = BacktestConfig(
            run_name=run_name,
            cutoff_start=datetime.fromisoformat(cutoff_start.replace("Z", "+00:00")),
            cutoff_end=datetime.fromisoformat(cutoff_end.replace("Z", "+00:00")),
            train_window_days=train_window_days,
            val_window_days=val_window_days,
            test_window_days=test_window_days,
            step_days=step_days,
            universe=universe or {},
        )
        return self.backtest.run(config)

    # ------------------------------------------------------------------
    # Discovery pipeline
    # ------------------------------------------------------------------

    def run_discovery(
        self,
        *,
        max_root_events: int = 5,
        max_candidates_per_root: int = 5,
    ) -> dict[str, Any]:
        """Run full discovery pipeline across top events."""
        return self.discovery.discover(
            max_root_events=max_root_events,
            max_candidates_per_root=max_candidates_per_root,
        )

    def expand_event(
        self,
        event_id: str,
        max_candidates: int = 10,
        max_hops: int = 3,
    ) -> list[dict[str, Any]]:
        """Run Budgeted Best-First expansion from a single event."""
        return self.discovery.expand(
            event_id, max_candidates=max_candidates, max_hops=max_hops,
        )

    # ------------------------------------------------------------------
    # Assimilation pipeline
    # ------------------------------------------------------------------

    def classify_assimilation(
        self,
        event_id: str,
        target_instrument: str | None = None,
    ) -> dict[str, Any]:
        """Classify assimilation state for an event."""
        event = self.db.query(Event).filter(Event.id == UUID(event_id)).first()
        if not event:
            return {"error": "Event not found"}
        return self.assimilation.classify(event, target_instrument=target_instrument)

    def run_event_study(
        self,
        event_id: str,
        instrument_symbol: str,
    ) -> dict[str, Any] | None:
        """Run event study for an event-instrument pair."""
        event = self.db.query(Event).filter(Event.id == UUID(event_id)).first()
        if not event:
            return None
        result = self.assimilation.event_study(event, instrument_symbol)
        if not result:
            return None
        return {
            "event_id": result.event_id,
            "instrument": result.instrument_symbol,
            "CAR": result.CAR,
            "abnormal_returns": result.abnormal_return,
            "window_start": result.window_start.isoformat(),
            "window_end": result.window_end.isoformat(),
        }

    # ------------------------------------------------------------------
    # Rebalance pipeline
    # ------------------------------------------------------------------

    def arm_for_event(
        self,
        event_id: str,
        thesis_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Arm a rebalance pack for an event."""
        event = self.db.query(Event).filter(Event.id == UUID(event_id)).first()
        if not event:
            return {"error": "Event not found"}
        pack = self.rebalance.arm_for_event(event, linked_thesis_ids=thesis_ids)
        return self.rebalance.get_state_report(pack)

    def get_rebalance_state(self, event_id: str) -> dict[str, Any]:
        """Get current rebalance state for an event."""
        pack = self.rebalance.active_packs.get(event_id)
        if not pack:
            return {"state": "not_armed", "state_ko": "무장되지 않음"}
        return self.rebalance.get_state_report(pack)

    def transition_rebalance(
        self,
        event_id: str,
        actual_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Transition rebalance state and get updated recommendations."""
        pack = self.rebalance.active_packs.get(event_id)
        if not pack:
            return {"error": "No active pack for this event"}
        recommendations = self.rebalance.transition(pack, actual_data=actual_data)
        return {
            "state_report": self.rebalance.get_state_report(pack),
            "recommendations": [
                {
                    "ticker": r.ticker,
                    "action": r.action.value,
                    "reason": r.reason,
                    "allowed": r.allowed,
                }
                for r in recommendations
            ],
        }

    # ------------------------------------------------------------------
    # Validation pipeline
    # ------------------------------------------------------------------

    def post_mortem(self, thesis_id: str) -> dict[str, Any]:
        """Run full post-mortem analysis on a thesis."""
        return self.validation.run_post_mortem(thesis_id)

    def evaluate_overfitting(
        self,
        thesis_ids: list[str],
    ) -> dict[str, Any]:
        """Estimate PBO across a set of theses."""
        return self.validation.compute_pbo_estimate(thesis_ids)

    # ------------------------------------------------------------------
    # Calendar
    # ------------------------------------------------------------------

    def weekly_calendar(self, lookahead_days: int = 7) -> dict[str, Any]:
        """Build the weekly event calendar cockpit view."""
        return self.calendar.get_cockpit_view(lookahead_days=lookahead_days)

    def event_sensitivity(
        self,
        scheduled_id: str,
    ) -> list[dict[str, Any]]:
        """Get thesis sensitivity to a scheduled event."""
        # Find the scheduled event from the calendar
        all_scheduled = self.calendar.build_weekly_calendar(lookahead_days=14)
        target = next((s for s in all_scheduled if s.scheduled_id == scheduled_id), None)
        if not target:
            return []

        sensitivities = self.calendar.compute_sensitivity(target)
        return [
            {
                "thesis_id": s.thesis_id,
                "thesis_title": s.thesis_title,
                "ticker": s.ticker,
                "sensitivity": s.sensitivity,
                "expected_direction": s.expected_direction,
                "scenario_if_beat": s.scenario_if_beat,
                "scenario_if_miss": s.scenario_if_miss,
                "scenario_if_inline": s.scenario_if_inline,
            }
            for s in sensitivities
        ]


# ============================================================================
# Engine 5 — Probability
# ============================================================================

    def compute_probabilities(
        self,
        thesis_id: str,
    ) -> dict[str, Any]:
        """Compute three-way probability split for a thesis."""
        from api.engine.probability import ProbabilityEngine

        thesis = self.db.query(Thesis).filter(Thesis.id == UUID(thesis_id)).first()
        if not thesis:
            return {"error": "Thesis not found"}

        eng = ProbabilityEngine(self.db)
        prob_set = eng.compute_probability_set(thesis)
        dist = eng.get_scenario_distribution(thesis)

        return {
            "thesis_id": thesis_id,
            "probabilities": prob_set.to_dict(),
            "scenario_distribution": dist.to_dict(),
        }

    def update_scenario_with_evidence(
        self,
        thesis_id: str,
        *,
        price_data: dict[str, float] | None = None,
        polymarket_prob: float | None = None,
        official_confirmations: int = 0,
        analyst_views: int = 0,
        counter_evidence_count: int = 0,
    ) -> dict[str, Any]:
        """Bayesian update of scenario probabilities with evidence clusters."""
        from api.engine.probability import ProbabilityEngine

        thesis = self.db.query(Thesis).filter(Thesis.id == UUID(thesis_id)).first()
        if not thesis:
            return {"error": "Thesis not found"}

        event = (
            self.db.query(Event).filter(Event.id == thesis.core_event_id).first()
        )

        eng = ProbabilityEngine(self.db)
        clusters = eng.build_evidence_clusters(
            event or Event(),
            price_data=price_data,
            polymarket_prob=polymarket_prob,
            official_confirmations=official_confirmations,
            analyst_views=analyst_views,
            counter_evidence_count=counter_evidence_count,
        )

        dist = eng.update_scenario(thesis, clusters)

        return {
            "thesis_id": thesis_id,
            "scenario_distribution": dist.to_dict(),
            "evidence_clusters_used": len([c for c in clusters if c.is_independent]),
        }

    def calibrate_against_market(
        self,
        thesis_ids: list[str],
        market_prices: list[float],
        outcomes: list[int],
    ) -> dict[str, Any]:
        """Compare model calibration against market baseline."""
        from api.engine.probability import ProbabilityEngine

        eng = ProbabilityEngine(self.db)
        model_probs: list[float] = []

        for tid in thesis_ids:
            thesis = self.db.query(Thesis).filter(Thesis.id == UUID(tid)).first()
            if thesis:
                prob_set = eng.compute_probability_set(thesis)
                model_probs.append(prob_set.outcome)

        n = min(len(model_probs), len(market_prices), len(outcomes))
        return eng.market_benchmark_comparison(
            model_probs[:n], market_prices[:n], outcomes[:n],
        )


# ============================================================================
# Engine 1-3 — Fabric, Evidence, Ontology
# ============================================================================

    def fabric_summary(self) -> dict[str, Any]:
        """Get Live Event Fabric summary."""
        from api.engine.fabric import LiveEventFabric
        return LiveEventFabric(self.db).build_summary()

    def evidence_quality(self, event_id: str) -> dict[str, Any]:
        """Get evidence quality summary for an event."""
        from api.engine.fabric import EvidenceEngine
        return EvidenceEngine(self.db).get_evidence_summary(event_id)

    def entity_graph(self, entity_id: str) -> dict[str, Any]:
        """Get entity-centric graph from ontology."""
        from api.engine.fabric import OntologyEngine
        return OntologyEngine(self.db).get_entity_graph(entity_id)


    # ------------------------------------------------------------------
    # Deep Scan — manual trigger
    def deep_scan(self) -> dict[str, Any]:
        """Full combinatorial scan — finds 3+ event motifs, scores, backtest-filters."""
        from api.engine.combinatorial import CombinatorialScanEngine
        engine = CombinatorialScanEngine(self.db)
        result = engine.run(max_motifs=80, min_events=3)
        # Also add calendar + existing theses
        result["calendar"] = self.calendar.get_cockpit_view()
        theses = self.db.query(Thesis).all()
        result["existing_thesis_count"] = len(theses)
        return result
    # ==================================================================
    # Thesis management — accept / reject / list / detail
    # ==================================================================

    def accept_thesis(self, event_id: str, motif_events: list[str] | None = None) -> dict[str, Any]:
        """
        Accept a candidate — if motif_events provided, creates a single thesis anchored
        at the first event and links the remaining events via EventRelation.
        """
        from api.models import ThesisScenario, EventRelation

        event_ids = motif_events if motif_events else [event_id]
        if not event_ids:
            return {"error": "No events provided"}

        events = []
        for eid in event_ids:
            ev = self.db.query(Event).filter(Event.id == UUID(eid)).first()
            if ev:
                events.append(ev)
        if not events:
            return {"error": "No valid events found"}

        core_event = events[0]
        existing = self.db.query(Thesis).filter(Thesis.core_event_id == core_event.id).first()
        if existing:
            return {"thesis_id": str(existing.id), "title": existing.title, "status": existing.status, "already_exists": True}

        # Create one thesis for the whole motif, anchored at the first event
        thesis = Thesis(
            title=core_event.title_ko or core_event.title or "Untitled thesis",
            status="Research Required",
            core_event_id=core_event.id,
            action="WATCH",
        )
        self.db.add(thesis)
        self.db.commit()
        self.db.refresh(thesis)

        # Link remaining events to the core event so the causal graph can traverse the motif
        for ev in events[1:]:
            rel_exists = self.db.query(EventRelation).filter(
                EventRelation.source_event_id == core_event.id,
                EventRelation.target_event_id == ev.id,
            ).first() or self.db.query(EventRelation).filter(
                EventRelation.source_event_id == ev.id,
                EventRelation.target_event_id == core_event.id,
            ).first()
            if not rel_exists:
                self.db.add(EventRelation(
                    source_event_id=core_event.id,
                    target_event_id=ev.id,
                    relation_type="motif_link",
                    strength=0.7,
                    evidence_grade="E2",
                    label_ko=f"motif 내 연결: {core_event.title_ko or ''} → {ev.title_ko or ''}",
                ))

        # Create scenarios from core event conditions, or default distribution
        conditions = core_event.conditions or []
        if not conditions:
            conditions = [
                {"name": "Bull", "probability": 0.38, "conditions": [], "price_range": ""},
                {"name": "Base", "probability": 0.40, "conditions": [], "price_range": ""},
                {"name": "Bear", "probability": 0.22, "conditions": [], "price_range": ""},
            ]

        for s in conditions:
            self.db.add(ThesisScenario(
                thesis_id=thesis.id,
                name=s.get("name", "Base"),
                probability=s.get("probability", 0),
                prev_probability=s.get("prev_probability"),
                conditions=s.get("conditions", []),
                price_range=s.get("price_range", ""),
            ))
        self.db.commit()

        return {
            "thesis_id": str(thesis.id),
            "title": thesis.title,
            "status": thesis.status,
            "created": True,
            "linked_events": [str(ev.id) for ev in events[1:]],
        }

    def reject_thesis(self, event_id: str) -> dict[str, Any]:
        """Mark a candidate as dismissed (soft reject)."""
        event = self.db.query(Event).filter(Event.id == UUID(event_id)).first()
        if not event:
            return {"error": "Event not found"}

        # Mark event as "Dismissed" status
        event.status = "Resolved"  # Using Resolved as a catch-all for dismissed
        self.db.commit()

        return {"event_id": event_id, "status": "dismissed"}

    def list_my_theses(self) -> dict[str, Any]:
        """List all theses created by the user (non-archived)."""
        theses = (
            self.db.query(Thesis)
            .filter(Thesis.status.notin_(["Archived"]))
            .order_by(Thesis.updated_at.desc())
            .all()
        )

        result = []
        for thesis in theses:
            event = (
                self.db.query(Event)
                .filter(Event.id == thesis.core_event_id)
                .first()
            )

            result.append({
                "thesis_id": str(thesis.id),
                "title": thesis.title,
                "status": thesis.status,
                "action": thesis.action,
                "event_id": str(thesis.core_event_id) if thesis.core_event_id else None,
                "event_title_ko": event.title_ko if event else None,
                "event_type": event.event_type if event else None,
                "evidence_grade": event.evidence_grade if event else None,
                "urgency": event.urgency if event else None,
                "sector_ko": event.sector_ko if event else None,
                "created_at": thesis.created_at.isoformat() if thesis.created_at else None,
                "updated_at": thesis.updated_at.isoformat() if thesis.updated_at else None,
            })

        return {"theses": result}

    def get_thesis_detail(self, thesis_id: str) -> dict[str, Any]:
        """Full thesis detail: scenarios, narrative, linked events, portfolio."""
        from api.models import ThesisScenario

        thesis = self.db.query(Thesis).filter(Thesis.id == UUID(thesis_id)).first()
        if not thesis:
            return {"error": "Thesis not found"}

        # Core event
        event = (
            self.db.query(Event)
            .filter(Event.id == thesis.core_event_id)
            .first()
        )

        # Scenarios
        scenarios = (
            self.db.query(ThesisScenario)
            .filter(ThesisScenario.thesis_id == thesis.id)
            .all()
        )

        # Related events (from event relations)
        from api.models import EventRelation
        related_event_ids: set[str] = set()
        if thesis.core_event_id:
            relations = self.db.query(EventRelation).filter(
                (EventRelation.source_event_id == thesis.core_event_id)
                | (EventRelation.target_event_id == thesis.core_event_id)
            ).all()
            for r in relations:
                if str(r.source_event_id) != str(thesis.core_event_id):
                    related_event_ids.add(str(r.source_event_id))
                if str(r.target_event_id) != str(thesis.core_event_id):
                    related_event_ids.add(str(r.target_event_id))

        related_events = []
        if related_event_ids:
            rel_evs = self.db.query(Event).filter(
                Event.id.in_([UUID(eid) for eid in related_event_ids])
            ).all()
            related_events = [
                {
                    "event_id": str(re.id),
                    "title_ko": re.title_ko or re.title or "",
                    "event_type": re.event_type,
                    "evidence_grade": re.evidence_grade,
                    "mechanism_ko": re.mechanism_ko or "",
                }
                for re in rel_evs
            ]

        # Portfolio positions linked to this thesis's core event
        positions = self.db.query(PortfolioPosition).all()
        linked_positions = []
        for p in positions:
            for eid in p.exposure_events or []:
                if str(eid) == str(thesis.core_event_id):
                    linked_positions.append({
                        "ticker": p.ticker,
                        "name": p.name,
                        "shares": p.shares,
                        "current_price": p.current_price,
                        "pl_percent": round(p.pl_percent or 0, 2),
                        "pl_usd": round(p.pl_usd or 0, 2),
                        "scenario_bias": p.scenario_bias or "Base",
                    })
                    break

        # Build causal narrative
        narrative_parts: list[str] = []
        if event:
            narrative_parts.append(f"핵심 사건: {event.title_ko or event.title}")
            if event.mechanism_ko:
                narrative_parts.append(f"\n인과 메커니즘: {event.mechanism_ko}")
            if event.counterevidence_ko:
                first_counter = event.counterevidence_ko[0] if event.counterevidence_ko else ""
                if first_counter:
                    narrative_parts.append(f"\n반대 증거: {first_counter}")
            if event.next_events_ko:
                first_next = event.next_events_ko[0] if event.next_events_ko else ""
                if first_next:
                    narrative_parts.append(f"\n다음 확인 이벤트: {first_next}")

        # Causal edges for this thesis
        from api.models import EventRelation as ER
        edges = []
        if thesis.core_event_id:
            rels = self.db.query(ER).filter(
                (ER.source_event_id == thesis.core_event_id)
                | (ER.target_event_id == thesis.core_event_id)
            ).all()
            edges = [
                {
                    "source": str(r.source_event_id),
                    "target": str(r.target_event_id),
                    "strength": r.strength or 1.0,
                    "type": r.edge_type or "market",
                    "label_ko": r.mechanism_ko or "",
                }
                for r in rels
            ]

        return {
            "thesis": {
                "id": str(thesis.id),
                "title": thesis.title,
                "status": thesis.status,
                "action": thesis.action,
            },
            "core_event": {
                "id": str(event.id) if event else None,
                "title_ko": event.title_ko if event else None,
                "event_type": event.event_type if event else None,
                "evidence_grade": event.evidence_grade if event else None,
                "urgency": event.urgency if event else None,
                "sector_ko": event.sector_ko if event else None,
                "mechanism_ko": event.mechanism_ko if event else None,
                "related_tickers": list(event.related_tickers or []) if event else [],
                "counterevidence_ko": list(event.counterevidence_ko or []) if event else [],
                "next_events_ko": list(event.next_events_ko or []) if event else [],
                "scenarios": [
                    {
                        "name": s.get("name", ""),
                        "probability": s.get("probability", 0),
                        "conditions": s.get("conditions", []),
                        "price_range": s.get("price_range", ""),
                    }
                    for s in (event.conditions or [])
                ] if event else [],
            },
            "scenarios": [
                {
                    "name": s.name,
                    "probability": s.probability or 0,
                    "prev_probability": s.prev_probability,
                    "conditions": s.conditions or [],
                    "price_range": s.price_range or "",
                }
                for s in scenarios
            ],
            "narrative": "".join(narrative_parts),
            "related_events": related_events,
            "edges": edges,
            "linked_positions": linked_positions,
        }
