"""
Portfolio & Rebalance Engine (Engine 7)

Implements the Event Window rebalancing logic from Section 29.7.

Key principles:
  - Discovery and Rebalancing are separate: this engine only adjusts EXISTING positions
  - 1-minute event window activation only
  - State machine: NORMAL -> ARMED -> IMPACT_LOCK -> FACT_CLASSIFIED -> CROSS_CONFIRMED -> REBALANCE_WINDOW -> COOLDOWN -> NORMAL
  - Reduce/Hedge: lower evidence bar; Increase: requires gates; New Entry: forbidden in impact window
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from api.models import Event, PortfolioPosition, Thesis, ThesisScenario
from api.config import settings


# ---------------------------------------------------------------------------
# Enums and data structures
# ---------------------------------------------------------------------------

class RebalanceState(str, Enum):
    NORMAL = "NORMAL"
    ARMED = "ARMED"                    # Event imminent (T-24h to T-5m)
    IMPACT_LOCK = "IMPACT_LOCK"        # T0 to T+2m: no new entries, only reduce/hedge
    FACT_CLASSIFIED = "FACT_CLASSIFIED" # Actual data classified
    CROSS_CONFIRMED = "CROSS_CONFIRMED" # External sensors confirm
    REBALANCE_WINDOW = "REBALANCE_WINDOW"  # Pre-approved adjustments
    COOLDOWN = "COOLDOWN"              # Prevent excessive chatter
    THESIS_REASSESS = "THESIS_REASSESS" # Requires deep re-evaluation


class ActionDecision(str, Enum):
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    HEDGE = "HEDGE"
    MAINTAIN = "MAINTAIN"
    INCREASE = "INCREASE"
    NEW_ENTRY = "NEW_ENTRY"


@dataclass
class TargetExposure:
    """Rule-based exposure recommendation."""
    ticker: str
    current_shares: float
    current_value: float
    target_shares: float | None = None
    target_value: float | None = None
    action: ActionDecision = ActionDecision.MAINTAIN
    reason: str = ""
    allowed: bool = True


@dataclass
class EventWindowPack:
    """
    A pre-computed playbook for a scheduled event.
    Created before the event, used during the event window.
    """
    event_id: str
    event_title: str
    scheduled_at: datetime
    armed_theses: list[str] = field(default_factory=list)
    time_windows: dict[str, tuple[float, float]] = field(default_factory=lambda: {
        "pre": (-24 * 3600, -300),       # T-24h to T-5m
        "impact": (0, 120),               # T0 to T+2m
        "stabilization": (120, 1800),     # T+2m to T+30m
        "interpretation": (1800, 86400),  # T+30m to T+1d
    })
    scenario_triggers: dict[str, list[str]] = field(default_factory=dict)
    allowed_actions: dict[str, bool] = field(default_factory=lambda: {
        "reduce": True,
        "hedge": True,
        "increase": False,
        "new_entry": False,
    })
    max_turnover: float = 0.20
    cooldown_seconds: int = 120

    # Runtime state
    current_state: RebalanceState = RebalanceState.NORMAL
    state_entered_at: datetime | None = None
    fact_classified_at: datetime | None = None
    last_rebalance_at: datetime | None = None
    actual_outcome: dict[str, Any] | None = None
    recommendations: list[TargetExposure] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Rebalance Engine
# ---------------------------------------------------------------------------

class RebalanceEngine:
    """
    Event Window Rebalancing engine.

    Operates only on EXISTING thesis/positions. Does not invent new alpha.
    """

    def __init__(self, db: Session):
        self.db = db
        self.active_packs: dict[str, EventWindowPack] = {}
        self.rebalance_deadband: float = 0.02  # 2% minimum move to act
        self.max_position_fraction: float = 0.25  # max 25% of portfolio per position

    def arm_for_event(
        self,
        event: Event,
        *,
        linked_thesis_ids: list[str] | None = None,
    ) -> EventWindowPack:
        """Prepare an Event Window Pack before a scheduled event."""
        pack = EventWindowPack(
            event_id=str(event.id),
            event_title=event.title_ko or event.title or "",
            scheduled_at=event.effective_date or event.published_at or datetime.utcnow(),
            armed_theses=linked_thesis_ids or [],
        )

        # Build scenario triggers from event conditions
        triggers: dict[str, list[str]] = {}
        for scenario in event.conditions or []:
            name = scenario.get("name", "base")
            if name not in triggers:
                triggers[name] = []
            conditions = scenario.get("conditions", [])
            triggers[name].extend(conditions)

        pack.scenario_triggers = triggers
        pack.current_state = RebalanceState.ARMED
        pack.state_entered_at = datetime.utcnow()

        # Compute initial recommendations
        if linked_thesis_ids:
            pack.recommendations = self._compute_exposure_recommendations(
                linked_thesis_ids, pack
            )

        self.active_packs[str(event.id)] = pack
        return pack

    def transition(
        self,
        pack: EventWindowPack,
        *,
        actual_data: dict[str, Any] | None = None,
        force_state: RebalanceState | None = None,
    ) -> list[TargetExposure]:
        """
        Transition the state machine based on time or data arrival.

        Returns updated exposure recommendations.
        """
        now = datetime.utcnow()
        elapsed = (now - pack.scheduled_at).total_seconds()

        # Time-based transitions
        if pack.current_state == RebalanceState.ARMED:
            if 0 <= elapsed <= 120:
                pack.current_state = RebalanceState.IMPACT_LOCK
                pack.state_entered_at = now

        elif pack.current_state == RebalanceState.IMPACT_LOCK:
            if actual_data:
                pack.actual_outcome = actual_data
                pack.current_state = RebalanceState.FACT_CLASSIFIED
                pack.fact_classified_at = now
            elif elapsed > 120:
                pack.current_state = RebalanceState.FACT_CLASSIFIED
                pack.fact_classified_at = now

        elif pack.current_state == RebalanceState.FACT_CLASSIFIED:
            if elapsed > 1800:
                pack.current_state = RebalanceState.REBALANCE_WINDOW
                pack.state_entered_at = now

        elif pack.current_state == RebalanceState.REBALANCE_WINDOW:
            if pack.last_rebalance_at:
                cooldown_elapsed = (now - pack.last_rebalance_at).total_seconds()
                if cooldown_elapsed >= pack.cooldown_seconds:
                    pack.current_state = RebalanceState.COOLDOWN
                    pack.state_entered_at = now
            elif elapsed > 86400:
                pack.current_state = RebalanceState.NORMAL

        elif pack.current_state == RebalanceState.COOLDOWN:
            if elapsed > 86400:
                pack.current_state = RebalanceState.NORMAL

        # Force state override
        if force_state:
            pack.current_state = force_state
            pack.state_entered_at = now

        # Regenerate recommendations
        pack.recommendations = self._compute_exposure_recommendations(
            pack.armed_theses, pack
        )
        return pack.recommendations

    def _compute_exposure_recommendations(
        self,
        thesis_ids: list[str],
        pack: EventWindowPack,
    ) -> list[TargetExposure]:
        """Compute target exposure for positions linked to these theses."""
        recommendations: list[TargetExposure] = []

        for tid in thesis_ids:
            thesis = self.db.query(Thesis).filter(Thesis.id == UUID(tid)).first()
            if not thesis:
                continue

            positions = (
                self.db.query(PortfolioPosition)
                .filter(PortfolioPosition.exposure_events.any(str(thesis.core_event_id)))
                .all()
            )

            for pos in positions:
                current_value = (pos.current_price or 0) * (pos.shares or 0)
                exposure = TargetExposure(
                    ticker=pos.ticker or "",
                    current_shares=pos.shares or 0,
                    current_value=current_value,
                    target_shares=pos.shares,
                    action=ActionDecision.MAINTAIN,
                )

                # Determine action based on state
                if pack.current_state == RebalanceState.IMPACT_LOCK:
                    # Only reduce or hedge allowed
                    if self._is_thesis_at_risk(thesis, pack):
                        exposure.action = ActionDecision.REDUCE
                        exposure.target_shares = pos.shares * 0.5 if pos.shares else 0
                        exposure.reason = "Impact lock: thesis at risk, reducing exposure"
                    else:
                        exposure.action = ActionDecision.MAINTAIN
                        exposure.reason = "Impact lock: no action until facts classified"

                elif pack.current_state == RebalanceState.FACT_CLASSIFIED:
                    outcome = pack.actual_outcome
                    if outcome:
                        scenario = self._match_scenario(outcome, pack)
                        if scenario == "bear":
                            if pack.allowed_actions.get("hedge", True):
                                exposure.action = ActionDecision.HEDGE
                                exposure.reason = "Bear scenario confirmed, hedging recommended"
                            exposure.allowed = pack.allowed_actions.get("reduce", True)
                        elif scenario == "bull" and pack.allowed_actions.get("increase", False):
                            exposure.action = ActionDecision.MAINTAIN  # increase needs gates
                            exposure.reason = "Bull scenario detected but increase requires human approval"

                elif pack.current_state == RebalanceState.REBALANCE_WINDOW:
                    # Apply hysteresis deadband
                    if pack.last_rebalance_at:
                        seconds_since = (datetime.utcnow() - pack.last_rebalance_at).total_seconds()
                        if seconds_since < pack.cooldown_seconds:
                            exposure.action = ActionDecision.HOLD
                            exposure.reason = f"Cooldown: {seconds_since:.0f}s since last rebalance"
                            exposure.allowed = False

                    # Apply deadband check
                    if exposure.action != ActionDecision.HOLD:
                        target_change = abs(
                            (exposure.target_shares or pos.shares or 0) - (pos.shares or 0)
                        ) / max(abs(pos.shares or 1), 1)
                        if target_change < self.rebalance_deadband:
                            exposure.action = ActionDecision.HOLD
                            exposure.reason = "Below rebalance deadband threshold"

                recommendations.append(exposure)

        return recommendations

    def _is_thesis_at_risk(self, thesis: Thesis, pack: EventWindowPack) -> bool:
        """Check if thesis status or evidence suggests risk."""
        if thesis.status in ("At Risk", "Invalidated"):
            return True

        scenarios = (
            self.db.query(ThesisScenario)
            .filter(ThesisScenario.thesis_id == thesis.id)
            .all()
        )

        bear_scenario = next(
            (s for s in scenarios if s.name and s.name.lower() == "bear"),
            None,
        )
        if bear_scenario and bear_scenario.probability and bear_scenario.probability > 0.35:
            return True

        return False

    def _match_scenario(
        self, outcome: dict[str, Any], pack: EventWindowPack
    ) -> str:
        """Match actual outcome to pre-defined scenario triggers."""
        for scenario_name, triggers in pack.scenario_triggers.items():
            for trigger in triggers:
                trigger_lower = trigger.lower()
                outcome_str = str(outcome).lower()
                for condition_word in trigger_lower.split():
                    if condition_word in outcome_str:
                        return scenario_name
        return "base"

    def get_state_report(self, pack: EventWindowPack) -> dict[str, Any]:
        """Human-readable state report for the cockpit UI."""
        state_labels: dict[RebalanceState, str] = {
            RebalanceState.NORMAL: "정상",
            RebalanceState.ARMED: "무장 완료",
            RebalanceState.IMPACT_LOCK: "영향 구간 잠김",
            RebalanceState.FACT_CLASSIFIED: "팩트 분류 완료",
            RebalanceState.CROSS_CONFIRMED: "교차 확인 완료",
            RebalanceState.REBALANCE_WINDOW: "리밸런싱 가능",
            RebalanceState.COOLDOWN: "쿨다운",
            RebalanceState.THESIS_REASSESS: "가설 재평가 필요",
        }

        return {
            "event_id": pack.event_id,
            "event_title": pack.event_title,
            "scheduled_at": pack.scheduled_at.isoformat() if pack.scheduled_at else None,
            "current_state": pack.current_state.value,
            "current_state_ko": state_labels.get(pack.current_state, pack.current_state.value),
            "state_entered_at": pack.state_entered_at.isoformat() if pack.state_entered_at else None,
            "elapsed_seconds": (
                (datetime.utcnow() - pack.scheduled_at).total_seconds()
                if pack.scheduled_at else None
            ),
            "allowed_actions": pack.allowed_actions,
            "recommendations": [
                {
                    "ticker": r.ticker,
                    "action": r.action.value,
                    "reason": r.reason,
                    "current_shares": r.current_shares,
                    "target_shares": r.target_shares,
                    "allowed": r.allowed,
                }
                for r in pack.recommendations
            ],
            "max_turnover": pack.max_turnover,
        }


# ---------------------------------------------------------------------------
# Exposure computation helper
# ---------------------------------------------------------------------------

def compute_target_exposure_rating(
    thesis: Thesis,
    event: Event | None = None,
    *,
    thesis_risk_budget: float = 0.05,
    evidence_confidence: float = 0.5,
    mechanism_completeness: float = 0.6,
    regime_fit: float = 0.7,
    execution_quality: float = 0.8,
    portfolio_overlap_penalty: float = 0.0,
    scenario_edge_scale: float = 1.0,
) -> dict[str, Any]:
    """
    Compute a conservative rule-based target exposure rating.

    Returns a rating (zero / small / normal / capped) rather than exact share count.
    """
    target_risk = (
        thesis_risk_budget
        * evidence_confidence
        * mechanism_completeness
        * regime_fit
        * execution_quality
        * (1 - min(portfolio_overlap_penalty, 0.5))
        * max(scenario_edge_scale, 0.1)
    )

    if target_risk <= 0.005:
        rating = "zero"
    elif target_risk <= 0.015:
        rating = "small"
    elif target_risk <= 0.04:
        rating = "normal"
    else:
        rating = "capped"

    return {
        "rating": rating,
        "target_risk": round(target_risk, 5),
        "components": {
            "thesis_risk_budget": round(thesis_risk_budget, 4),
            "evidence_confidence": round(evidence_confidence, 4),
            "mechanism_completeness": round(mechanism_completeness, 4),
            "regime_fit": round(regime_fit, 4),
            "execution_quality": round(execution_quality, 4),
            "portfolio_overlap_penalty": round(portfolio_overlap_penalty, 4),
            "scenario_edge_scale": round(scenario_edge_scale, 4),
        },
    }
