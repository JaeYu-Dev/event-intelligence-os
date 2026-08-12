"""
Cross-Asset Assimilation Engine (Engine 6)

Tracks what expectation change has been priced where.

Key concepts:
  - LatentExpectation: common cause across multiple market sensors
  - SensorReading: an observation from one market (price, volume, etc.)
  - AssimilationState: Under-reflected / Overreaction / Broadly Priced / Unresolved
  - Event Study: abnormal return, CAR, volume, volatility analysis
  - AssimilationGap: how much of the expected move is NOT yet priced
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from api.models import Event, EventRelation, MarketPrice, MarketInstrument, LatentFactor


# ---------------------------------------------------------------------------
# Enums and data classes
# ---------------------------------------------------------------------------

class AssimilationState(str, Enum):
    CONFIRMED_UNDER_REFLECTED = "A"  # sensors agree, target hasn't moved
    HEADLINE_OVERREACTION = "B"      # target moved, sensors don't confirm
    BROADLY_PRICED = "C"             # all sensors and target aligned
    UNRESOLVED = "D"                 # sensors conflict, evidence incomplete


@dataclass
class SensorReading:
    """A single observation from one market sensor."""
    sensor_name: str
    sensor_type: str  # yield, futures, equity, etf, prediction_market, fx, commodity
    instrument_symbol: str
    value: float
    previous_value: float | None = None
    timestamp: datetime | None = None
    abnormal_change: float | None = None  # deviation from expected
    is_aligned: bool = True  # whether this sensor agrees with latent factor direction


@dataclass
class LatentExpectation:
    """
    A common cause (latent factor) observed through multiple sensors.

    Example: rate_cut_expectation
      sensors: 2Y yield, Fed funds futures, DXY, QQQ, Polymarket rate-cut
    """
    factor_id: str
    factor_name: str
    factor_name_ko: str
    description: str
    sensors: list[str] = field(default_factory=list)  # instrument symbols
    sensor_readings: list[SensorReading] = field(default_factory=list)
    direction: str = "positive"  # positive / negative / neutral
    consensus_strength: float = 0.0  # 0-1, how aligned the sensors are
    regime: str = "normal"  # normal / high_vol / low_liquidity / pre_event


@dataclass
class EventStudyResult:
    """Abnormal return analysis for a single event window."""
    event_id: str
    instrument_symbol: str
    event_timestamp: datetime
    window_start: datetime
    window_end: datetime
    abnormal_return: list[float] = field(default_factory=list)
    CAR: float = 0.0  # Cumulative Abnormal Return
    abnormal_volume: float | None = None
    abnormal_volatility: float | None = None
    benchmark_return: list[float] = field(default_factory=list)
    relative_reaction_lag: float | None = None  # hours until max reaction


# ---------------------------------------------------------------------------
# Factor definitions (pre-configured latent factors)
# ---------------------------------------------------------------------------

PREDEFINED_FACTORS: dict[str, dict[str, Any]] = {
    "rate_cut_expectation": {
        "name": "Rate Cut Expectation",
        "name_ko": "금리 인하 기대",
        "description": "Expected timing and magnitude of Fed rate cuts",
        "sensors": ["TLT", "DXY", "QQQ"],  # 2Y yield proxy, dollar, growth
        "direction": "positive",
    },
    "ai_capex_expectation": {
        "name": "AI Capex Expectation",
        "name_ko": "AI 투자 기대",
        "description": "Expected hyperscaler and enterprise AI infrastructure spend",
        "sensors": ["NVDA", "SOXL", "SMH"],
        "direction": "positive",
    },
    "energy_supply_tightness": {
        "name": "Energy Supply Tightness",
        "name_ko": "에너지 공급 타이트니스",
        "description": "Crude oil and natural gas supply-demand balance",
        "sensors": ["XLE", "USO", "XOM"],
        "direction": "positive",
    },
    "regulatory_approval_probability": {
        "name": "Regulatory Approval Probability",
        "name_ko": "규제 승인 확률",
        "description": "FDA/regulatory approval odds for key drugs/devices",
        "sensors": ["XBI", "IBB"],
        "direction": "positive",
    },
    "supply_chain_disruption_severity": {
        "name": "Supply Chain Disruption Severity",
        "name_ko": "공급망 차질 심각도",
        "description": "How severe and widespread supply chain issues are",
        "sensors": ["FCX", "COPX", "XME"],
        "direction": "negative",
    },
    "risk_appetite": {
        "name": "Risk Appetite",
        "name_ko": "위험 선호도",
        "description": "Broad market risk appetite / risk-off sentiment",
        "sensors": ["SPY", "VIX", "HYG"],
        "direction": "positive",
    },
    "recession_probability": {
        "name": "Recession Probability",
        "name_ko": "경기침체 확률",
        "description": "Market-implied recession odds",
        "sensors": ["TLT", "GLD", "SPY"],
        "direction": "negative",
    },
}


# ---------------------------------------------------------------------------
# Assimilation Engine
# ---------------------------------------------------------------------------

class AssimilationEngine:
    """
    Cross-Asset Assimilation Engine.

    For a given event or thesis:
      1. Identify the relevant latent factor
      2. Read all sensor readings
      3. Classify assimilation state
      4. Compute assimilation gap
    """

    def __init__(self, db: Session):
        self.db = db
        self.factors = self._load_factors()

    def _load_factors(self) -> dict[str, LatentExpectation]:
        """Load pre-configured latent factors from DB or defaults."""
        factors: dict[str, LatentExpectation] = {}
        for fid, spec in PREDEFINED_FACTORS.items():
            # Check DB for stored factor
            db_factor = self.db.query(LatentFactor).filter(LatentFactor.name == spec["name"]).first()
            if db_factor:
                sensors = db_factor.sensors or spec["sensors"]
            else:
                sensors = spec["sensors"]

            factors[fid] = LatentExpectation(
                factor_id=fid,
                factor_name=spec["name"],
                factor_name_ko=spec["name_ko"],
                description=spec["description"],
                sensors=sensors,
                direction=spec["direction"],
            )
        return factors

    def get_latent_factor_for_event(self, event: Event) -> LatentExpectation | None:
        """Map an event to its most relevant latent factor."""
        sector = (event.sector or "").lower()
        event_type = (event.event_type or "").lower()

        mapping: dict[str, str] = {
            "macro / rates": "rate_cut_expectation",
            "semiconductors": "ai_capex_expectation",
            "energy": "energy_supply_tightness",
            "biotech": "regulatory_approval_probability",
            "cleantech / battery": "energy_supply_tightness",
            "materials": "supply_chain_disruption_severity",
            "cybersecurity": "risk_appetite",
        }

        # Direct sector match
        for key, factor_id in mapping.items():
            if key in sector:
                return self.factors.get(factor_id)

        # Event-type based fallback
        if "macro" in event_type or "prediction" in event_type:
            return self.factors.get("rate_cut_expectation")
        if "regulatory" in event_type:
            return self.factors.get("regulatory_approval_probability")
        if "supply_chain" in event_type:
            return self.factors.get("supply_chain_disruption_severity")

        return self.factors.get("risk_appetite")  # default

    def read_sensors(
        self,
        factor: LatentExpectation,
        lookback_hours: int = 24,
    ) -> list[SensorReading]:
        """Read recent market data for a factor's sensor instruments."""
        readings: list[SensorReading] = []
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=lookback_hours)

        for symbol in factor.sensors:
            instr = (
                self.db.query(MarketInstrument)
                .filter(MarketInstrument.symbol == symbol)
                .first()
            )
            if not instr:
                continue

            prices = (
                self.db.query(MarketPrice)
                .filter(
                    MarketPrice.instrument_id == instr.id,
                    MarketPrice.timestamp >= cutoff,
                )
                .order_by(MarketPrice.timestamp.desc())
                .limit(100)
                .all()
            )

            if not prices:
                continue

            latest = prices[0]
            prev = prices[-1] if len(prices) > 1 else None

            change = None
            if prev and prev.close and latest.close:
                change = (latest.close - prev.close) / prev.close

            readings.append(SensorReading(
                sensor_name=symbol,
                sensor_type=_infer_sensor_type(symbol),
                instrument_symbol=symbol,
                value=latest.close or 0,
                previous_value=prev.close if prev else None,
                timestamp=latest.timestamp,
                abnormal_change=change,
                is_aligned=True,  # calibrated below
            ))

        return readings

    def classify(
        self,
        event: Event,
        *,
        target_instrument: str | None = None,
    ) -> dict[str, Any]:
        """
        Classify the assimilation state for an event relative to a target instrument.

        Returns:
            state: A/B/C/D
            confidence: 0-1
            reason: human-readable explanation
            gap: estimated assimilation gap
        """
        factor = self.get_latent_factor_for_event(event)
        if not factor:
            return {
                "state": AssimilationState.UNRESOLVED.value,
                "state_ko": "미해결",
                "confidence": 0.3,
                "reason_ko": "잠재 요인을 식별할 수 없습니다.",
                "gap": None,
                "factor": None,
            }

        readings = self.read_sensors(factor)
        factor.sensor_readings = readings

        # Determine sensor consensus
        if readings:
            aligned = sum(1 for r in readings if r.is_aligned)
            factor.consensus_strength = aligned / len(readings)
        else:
            factor.consensus_strength = 0.5  # no data

        # Read target instrument if provided
        target_reading = None
        if target_instrument:
            target_instr = (
                self.db.query(MarketInstrument)
                .filter(MarketInstrument.symbol == target_instrument)
                .first()
            )
            if target_instr:
                target_prices = (
                    self.db.query(MarketPrice)
                    .filter(
                        MarketPrice.instrument_id == target_instr.id,
                    )
                    .order_by(MarketPrice.timestamp.desc())
                    .limit(2)
                    .all()
                )
                if target_prices and len(target_prices) >= 2:
                    target_change = (
                        (target_prices[0].close - target_prices[1].close)
                        / target_prices[1].close
                        if target_prices[1].close
                        else 0
                    )
                    target_reading = SensorReading(
                        sensor_name=target_instrument,
                        sensor_type="equity",
                        instrument_symbol=target_instrument,
                        value=target_prices[0].close or 0,
                        previous_value=target_prices[1].close,
                        abnormal_change=target_change,
                        timestamp=target_prices[0].timestamp,
                    )

        # Classify assimilation state
        event_grades = {"E4": 1.0, "E3": 0.85, "E2": 0.6, "E1": 0.35, "E0": 0.15}
        evidence_confidence = event_grades.get(event.evidence_grade or "E1", 0.35)

        sensor_align = factor.consensus_strength

        if sensor_align >= 0.7 and evidence_confidence >= 0.6 and target_reading and abs(target_reading.abnormal_change or 0) < 0.02:
            state = AssimilationState.CONFIRMED_UNDER_REFLECTED
            state_ko = "확인됨 / 덜 반영됨"
        elif sensor_align < 0.4 and target_reading and abs(target_reading.abnormal_change or 0) > 0.03:
            state = AssimilationState.HEADLINE_OVERREACTION
            state_ko = "헤드라인 과잉 반응"
        elif sensor_align >= 0.6 and target_reading and abs(target_reading.abnormal_change or 0) > 0.02:
            state = AssimilationState.BROADLY_PRICED
            state_ko = "광범위 반영 완료"
        else:
            state = AssimilationState.UNRESOLVED
            state_ko = "미해결"

        # Compute assimilation gap
        gap = self._compute_gap(
            factor,
            event,
            target_reading,
            evidence_confidence,
        )

        return {
            "state": state.value,
            "state_ko": state_ko,
            "confidence": round((evidence_confidence + sensor_align) / 2, 3),
            "reason_ko": _state_reason_ko(state, factor, sensor_align),
            "gap": gap,
            "factor": {
                "id": factor.factor_id,
                "name_ko": factor.factor_name_ko,
                "sensor_count": len(readings),
                "consensus_strength": round(sensor_align, 3),
                "sensors": [
                    {
                        "symbol": r.instrument_symbol,
                        "change": round(r.abnormal_change, 4) if r.abnormal_change else None,
                    }
                    for r in readings
                ],
            },
        }

    def _compute_gap(
        self,
        factor: LatentExpectation,
        event: Event,
        target_reading: SensorReading | None,
        evidence_confidence: float,
    ) -> dict[str, Any] | None:
        """
        AssimilationGap = ExpectedTargetMoveGivenFactorState
                        - ObservedExecutableMove
                        - EstimatedExecutionCost
                        - UncertaintyBuffer
        """
        if not target_reading or not target_reading.abnormal_change:
            return None

        # Estimate expected move from factor consensus and evidence
        expected_move_pct = (
            evidence_confidence
            * factor.consensus_strength
            * _impact_to_move(event)
        ) / 100

        observed_move_pct = target_reading.abnormal_change
        execution_cost = 0.003  # 30 bps estimate
        uncertainty_buffer = (1 - evidence_confidence) * 0.02

        gap = expected_move_pct - abs(observed_move_pct) - execution_cost - uncertainty_buffer

        return {
            "expected_move_pct": round(expected_move_pct, 5),
            "observed_move_pct": round(observed_move_pct, 5),
            "execution_cost_pct": round(execution_cost, 5),
            "uncertainty_buffer_pct": round(uncertainty_buffer, 5),
            "net_gap_pct": round(gap, 5),
            "is_actionable": gap > 0.01,
        }

    def event_study(
        self,
        event: Event,
        instrument_symbol: str,
        *,
        pre_window_hours: int = 24,
        post_window_hours: int = 72,
    ) -> EventStudyResult | None:
        """
        Compute abnormal returns around an event's published time.
        """
        instr = (
            self.db.query(MarketInstrument)
            .filter(MarketInstrument.symbol == instrument_symbol)
            .first()
        )
        if not instr or not event.published_at:
            return None

        window_start = event.published_at - timedelta(hours=pre_window_hours)
        window_end = event.published_at + timedelta(hours=post_window_hours)

        prices = (
            self.db.query(MarketPrice)
            .filter(
                MarketPrice.instrument_id == instr.id,
                MarketPrice.timestamp >= window_start,
                MarketPrice.timestamp <= window_end,
            )
            .order_by(MarketPrice.timestamp.asc())
            .all()
        )

        if len(prices) < 2:
            return None

        # Simple abnormal return: actual - average pre-event return
        event_idx = next(
            (i for i, p in enumerate(prices) if p.timestamp >= event.published_at),
            len(prices) // 2,
        )

        pre_prices = prices[:event_idx]
        post_prices = prices[event_idx:]

        if not pre_prices or not post_prices:
            return None

        # Benchmark: average pre-event daily return
        pre_returns: list[float] = []
        for i in range(1, len(pre_prices)):
            if pre_prices[i - 1].close and pre_prices[i - 1].close > 0:
                r = (pre_prices[i].close - pre_prices[i - 1].close) / pre_prices[i - 1].close
                pre_returns.append(r)

        avg_pre_return = sum(pre_returns) / len(pre_returns) if pre_returns else 0

        # Abnormal returns post-event
        post_base = pre_prices[-1].close or post_prices[0].close or 1
        abnormal_returns: list[float] = []
        for p in post_prices:
            if p.close and post_base > 0:
                raw_return = (p.close - post_base) / post_base
                abnormal = raw_return - avg_pre_return
                abnormal_returns.append(abnormal)

        CAR = sum(abnormal_returns)

        return EventStudyResult(
            event_id=str(event.id),
            instrument_symbol=instrument_symbol,
            event_timestamp=event.published_at,
            window_start=window_start,
            window_end=window_end,
            abnormal_return=[round(x, 5) for x in abnormal_returns],
            CAR=round(CAR, 5),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_sensor_type(symbol: str) -> str:
    if symbol in ("TLT", "IEF", "SHY"):
        return "yield"
    if symbol in ("DXY", "UUP"):
        return "fx"
    if symbol in ("VIX", "VXX"):
        return "volatility"
    if symbol in ("GLD", "USO", "UNG"):
        return "commodity"
    if symbol in ("SPY", "QQQ", "IWM"):
        return "index"
    return "equity"


def _impact_to_move(event: Event) -> float:
    """Estimate percentage price move from event magnitude."""
    base = 2.0  # default 2%
    if event.magnitude_value:
        base = abs(event.magnitude_value)
    if event.event_type in ("earnings", "filing"):
        base = min(base, 15.0)
    elif event.event_type in ("policy_announcement", "regulatory"):
        base = max(base, 3.0)
    return base


def _state_reason_ko(
    state: AssimilationState,
    factor: LatentExpectation,
    sensor_align: float,
) -> str:
    reasons = {
        AssimilationState.CONFIRMED_UNDER_REFLECTED: (
            f"센서 {len(factor.sensors)}개 중 {int(sensor_align * len(factor.sensors))}개가 "
            f"{factor.factor_name_ko} 방향을 확인했지만, 대상 자산은 아직 충분히 반응하지 않았습니다."
        ),
        AssimilationState.HEADLINE_OVERREACTION: (
            f"대상 자산만 급격히 움직였으나, {factor.factor_name_ko} 연관 센서들은 "
            f"일관된 신호를 보이지 않습니다."
        ),
        AssimilationState.BROADLY_PRICED: (
            f"{factor.factor_name_ko}의 변화가 이미 여러 시장에 폭넓게 반영되었습니다."
        ),
        AssimilationState.UNRESOLVED: (
            f"{factor.factor_name_ko} 센서들의 신호가 엇갈리고 있어 명확한 판단이 어렵습니다. "
            f"추가 확인 이벤트를 기다리는 것이 좋습니다."
        ),
    }
    return reasons.get(state, "분석 불가")
