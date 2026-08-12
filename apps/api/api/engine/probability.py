"""
Probability & Scenario Engine (Engine 5)

Implements Section 29.5 of the spec. Key principles:

1. Never let LLM declare "73% probability" — probability is computed from structured
   evidence and scenario conditions using calibrated models.

2. Three separate probabilities:
   - P(outcome | evidence): real-world event/contract outcome probability
   - P(assimilation within horizon | evidence): market prices it within time window
   - P(net positive PnL | execution, costs, portfolio): actual post-execution profit

3. Conditional Bayesian update via log-odds, with sensor clustering to avoid
   double-counting correlated signals.

4. Uncertainty rules: E0/E1 = interval only, E2 = low-confidence weights, E3/E4 = point+interval

5. Calibration: Brier score, log loss, reliability curves per event family/source tier/horizon
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID
import math

from sqlalchemy.orm import Session

from api.models import Event, Thesis, ThesisScenario, EvidenceItem


# ---------------------------------------------------------------------------
# Enums and data types
# ---------------------------------------------------------------------------

class ScenarioName(str, Enum):
    BULL = "Bull"
    BASE = "Base"
    BEAR = "Bear"
    TAIL = "Tail"


@dataclass
class ProbabilitySet:
    """Three decoupled probabilities as required by the spec."""
    outcome: float = 0.5              # P(outcome | evidence)
    assimilation: float = 0.5          # P(market prices it within horizon)
    pnl_positive: float = 0.5          # P(net positive PnL | execution)

    outcome_interval: tuple[float, float] | None = None
    assimilation_interval: tuple[float, float] | None = None
    pnl_interval: tuple[float, float] | None = None

    evidence_grade: str = "E0"    # determines interval vs point
    horizon_days: int = 7

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": round(self.outcome, 4),
            "outcome_interval": (
                [round(self.outcome_interval[0], 4), round(self.outcome_interval[1], 4)]
                if self.outcome_interval else None
            ),
            "assimilation": round(self.assimilation, 4),
            "assimilation_interval": (
                [round(self.assimilation_interval[0], 4), round(self.assimilation_interval[1], 4)]
                if self.assimilation_interval else None
            ),
            "pnl_positive": round(self.pnl_positive, 4),
            "pnl_interval": (
                [round(self.pnl_interval[0], 4), round(self.pnl_interval[1], 4)]
                if self.pnl_interval else None
            ),
            "evidence_grade": self.evidence_grade,
            "horizon_days": self.horizon_days,
        }


@dataclass
class ScenarioDistribution:
    """Full scenario probability distribution for a thesis."""
    thesis_id: str
    bull: float = 0.33
    base: float = 0.34
    bear: float = 0.25
    tail: float = 0.08

    # Point vs interval control
    use_intervals: bool = False  # True when evidence < E2

    # History
    prev_bull: float | None = None
    prev_base: float | None = None
    prev_bear: float | None = None
    prev_tail: float | None = None

    updated_at: str | None = None

    @property
    def total(self) -> float:
        return self.bull + self.base + self.bear + self.tail

    def normalize(self) -> "ScenarioDistribution":
        t = self.total
        if t <= 0:
            self.bull = self.base = self.bear = 0.25
            self.tail = 0.25
        else:
            self.bull /= t
            self.base /= t
            self.bear /= t
            self.tail /= t
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "bull": round(self.bull, 4),
            "base": round(self.base, 4),
            "bear": round(self.bear, 4),
            "tail": round(self.tail, 4),
            "bull_prev": round(self.prev_bull, 4) if self.prev_bull is not None else None,
            "bear_prev": round(self.prev_bear, 4) if self.prev_bear is not None else None,
            "use_intervals": self.use_intervals,
            "updated_at": self.updated_at,
        }


@dataclass
class EvidenceCluster:
    """A group of correlated sensors that should be treated as ONE signal."""
    cluster_id: str
    sensors: list[str] = field(default_factory=list)
    likelihood_ratio: float = 1.0       # how much this evidence shifts odds
    confidence_weight: float = 0.5       # 0-1, quality of this cluster
    is_independent: bool = False          # truly independent from other clusters


@dataclass
class CalibrationMetrics:
    """Calibration metrics for a model/family."""
    brier_score: float = 0.0
    log_loss: float = 0.0
    reliability_curve: list[dict[str, float]] = field(default_factory=list)
    num_predictions: int = 0
    event_family: str = ""
    source_tier: str = ""
    time_horizon: int = 7


# ---------------------------------------------------------------------------
# Probability Engine
# ---------------------------------------------------------------------------

class ProbabilityEngine:
    """
    Probability & Scenario Engine.

    For each thesis:
      1. Maintain Bull/Base/Bear/Tail scenario distribution
      2. Update probabilities via structured Bayesian inference (NOT LLM guess)
      3. Keep three probabilities separate (outcome / assimilation / PnL)
      4. Apply uncertainty rules based on evidence grade
      5. Track calibration metrics
    """

    # Calibration storage (in-memory for MVP; would be DB-backed in production)
    _calibration_store: dict[str, list[dict[str, Any]]] = {}
    _predictions_store: dict[str, list[dict[str, Any]]] = {}

    def __init__(self, db: Session | None = None):
        self.db = db
        self.default_prior = ScenarioDistribution(thesis_id="prior")

    # ------------------------------------------------------------------
    # Probability separation (3-way split)
    # ------------------------------------------------------------------

    def compute_probability_set(
        self,
        thesis: Thesis,
        *,
        event: Event | None = None,
        execution_costs_pct: float = 0.003,
        portfolio_overlap: float = 0.0,
    ) -> ProbabilitySet:
        """
        Compute the three decoupled probabilities for a thesis.

        This is the key function that prevents the common error of blending
        different probability types into one misleading "win rate."
        """
        if event is None and thesis.core_event_id:
            event = self.db.query(Event).filter(Event.id == thesis.core_event_id).first()

        dist = self.get_scenario_distribution(thesis)
        evidence_grade = event.evidence_grade if event else "E1"
        grade_rank = {"E4": 4, "E3": 3, "E2": 2, "E1": 1, "E0": 0}
        grank = grade_rank.get(evidence_grade or "E1", 1)

        # --- P(outcome | evidence) ---
        # How likely the real-world event resolves bullishly
        outcome_p = dist.bull + dist.base * 0.5

        # --- P(assimilation | evidence) ---
        # How likely the market prices this in within the horizon
        # Depends on evidence grade (higher = faster assimilation)
        assimilation_base = 0.3 + grank * 0.15  # 0.45-0.90
        # Adjust for event type
        event_type = event.event_type if event else ""
        fast_assimilation = {"earnings", "macro", "prediction_market"}
        slow_assimilation = {"regulatory", "policy_announcement", "supply_chain"}
        if event_type in fast_assimilation:
            assimilation_base = min(0.95, assimilation_base * 1.3)
        elif event_type in slow_assimilation:
            assimilation_base *= 0.8

        # Scale by outcome direction
        if outcome_p > 0.6:
            assimilation_score = assimilation_base * 1.2
        elif outcome_p < 0.4:
            assimilation_score = assimilation_base * 0.8
        else:
            assimilation_score = assimilation_base

        # --- P(net positive PnL | execution) ---
        # Edge - costs - portfolio drag
        scenario_edge = (dist.bull - dist.bear) * 0.05  # rough edge in pct
        raw_pnl_prob = 0.5 + scenario_edge  # center at 0.5
        raw_pnl_prob -= execution_costs_pct * 5       # 30bps costs ~1.5% off
        raw_pnl_prob -= portfolio_overlap * 0.1
        raw_pnl_prob = max(0.15, min(0.85, raw_pnl_prob))

        # Apply uncertainty rules
        if grank <= 1:  # E0/E1: intervals only
            width = 0.15 if grank == 1 else 0.25
            outcome_interval = (max(0.05, outcome_p - width), min(0.95, outcome_p + width))
            assim_interval = (max(0.05, assimilation_score - width), min(0.95, assimilation_score + width))
            pnl_interval = (max(0.05, raw_pnl_prob - width), min(0.95, raw_pnl_prob + width))
        elif grank == 2:  # E2: point + interval
            width = 0.10
            outcome_interval = (max(0.1, outcome_p - width), min(0.9, outcome_p + width))
            assim_interval = (max(0.1, assimilation_score - width), min(0.9, assimilation_score + width))
            pnl_interval = (max(0.1, raw_pnl_prob - width), min(0.9, raw_pnl_prob + width))
        else:  # E3/E4: point estimate
            outcome_interval = None
            assim_interval = None
            pnl_interval = None

        return ProbabilitySet(
            outcome=outcome_p,
            outcome_interval=outcome_interval,
            assimilation=assimilation_score,
            assimilation_interval=assim_interval,
            pnl_positive=raw_pnl_prob,
            pnl_interval=pnl_interval,
            evidence_grade=evidence_grade or "E1",
            horizon_days=7,
        )

    # ------------------------------------------------------------------
    # Scenario distribution
    # ------------------------------------------------------------------

    def get_scenario_distribution(self, thesis: Thesis) -> ScenarioDistribution:
        """Get the current scenario distribution for a thesis."""
        scenarios = (
            self.db.query(ThesisScenario)
            .filter(ThesisScenario.thesis_id == thesis.id)
            .all()
        )

        dist = ScenarioDistribution(thesis_id=str(thesis.id))

        for s in scenarios:
            name = (s.name or "").lower()
            prob = s.probability or 0
            prev = s.prev_probability
            if name == "bull":
                dist.bull = prob
                dist.prev_bull = prev
            elif name == "base":
                dist.base = prob
                dist.prev_base = prev
            elif name == "bear":
                dist.bear = prob
                dist.prev_bear = prev
            elif name == "tail":
                dist.tail = prob
                dist.prev_tail = prev

        dist.normalize()

        # Determine if intervals needed
        event = self.db.query(Event).filter(Event.id == thesis.core_event_id).first()
        grade = (event.evidence_grade or "E1") if event else "E1"
        dist.use_intervals = grade in ("E0", "E1")

        return dist

    def initial_distribution(
        self,
        event: Event,
        *,
        thesis_id: str = "",
    ) -> ScenarioDistribution:
        """
        Initialize scenario distribution from event conditions.
        Uses event.conditions (JSON list of scenarios) as the seed.
        """
        dist = ScenarioDistribution(thesis_id=thesis_id)

        if event.conditions:
            for s in event.conditions:
                name = (s.get("name") or "").lower()
                prob = s.get("probability", 0)
                if name == "bull":
                    dist.bull = prob
                elif name == "base":
                    dist.base = prob
                elif name == "bear":
                    dist.bear = prob
                elif name == "tail":
                    dist.tail = prob

        # If no tail defined, allocate from residual
        if dist.tail == 0:
            remaining = 1.0 - (dist.bull + dist.base + dist.bear)
            if remaining > 0:
                dist.tail = remaining
                dist.bear = max(0, dist.bear - 0.02)
                dist.bull = max(0, dist.bull - 0.02)

        dist.normalize()
        dist.use_intervals = (event.evidence_grade or "E1") in ("E0", "E1")
        return dist

    # ------------------------------------------------------------------
    # Bayesian update via log-odds
    # ------------------------------------------------------------------

    def update_scenario(
        self,
        thesis: Thesis,
        evidence_clusters: list[EvidenceCluster],
    ) -> ScenarioDistribution:
        """
        Bayesian update of scenario probabilities using evidence clusters.

        Uses log-odds to properly combine independent evidence,
        avoiding the common error of treating correlated signals as independent.

        prior_logit = logit(prior)
        for each independent cluster:
            prior_logit += weight * log(likelihood_ratio)
        posterior = sigmoid(prior_logit)
        posterior = shrink_toward_prior_if_small_sample(posterior)
        """
        dist = self.get_scenario_distribution(thesis)

        # Store previous values
        dist.prev_bull = dist.bull
        dist.prev_base = dist.base
        dist.prev_bear = dist.bear
        dist.prev_tail = dist.tail

        # Only update if we have independent evidence
        independent_clusters = [c for c in evidence_clusters if c.is_independent]
        if not independent_clusters:
            dist.updated_at = datetime.utcnow().isoformat()
            return dist

        # For each scenario, update via log-odds
        for scenario_name, current_prob in [
            ("bull", dist.bull),
            ("bear", dist.bear),
        ]:
            prior_logit = _logit(current_prob)

            for cluster in independent_clusters:
                lr = cluster.likelihood_ratio
                weight = cluster.confidence_weight

                if scenario_name == "bull":
                    # Bull-beneficial evidence: LR > 1 = good
                    pass
                else:
                    # Bear-beneficial evidence: invert LR
                    lr = 1.0 / max(lr, 0.01)

                prior_logit += weight * math.log(max(lr, 0.01))

            posterior = _sigmoid(prior_logit)
            posterior = _shrink_toward_prior(
                posterior, current_prob, len(independent_clusters)
            )

            if scenario_name == "bull":
                dist.bull = posterior
            else:
                dist.bear = posterior

        # Base = residual after bull and bear, then normalize
        dist.base = max(0.05, 1.0 - dist.bull - dist.bear - dist.tail)
        dist.normalize()

        # Persist to DB
        self._persist_scenario_update(thesis, dist)

        dist.updated_at = datetime.utcnow().isoformat()
        return dist

    def _persist_scenario_update(
        self,
        thesis: Thesis,
        dist: ScenarioDistribution,
    ) -> None:
        """Write updated probabilities back to ThesisScenario rows."""
        scenarios = (
            self.db.query(ThesisScenario)
            .filter(ThesisScenario.thesis_id == thesis.id)
            .all()
        )
        scenario_map = {(s.name or "").lower(): s for s in scenarios}

        updates = {
            "bull": dist.bull,
            "base": dist.base,
            "bear": dist.bear,
            "tail": dist.tail,
        }
        prevs = {
            "bull": dist.prev_bull,
            "base": dist.prev_base,
            "bear": dist.prev_bear,
            "tail": dist.prev_tail,
        }

        for name, prob in updates.items():
            existing = scenario_map.get(name)
            if existing:
                existing.prev_probability = existing.probability
                existing.probability = prob
            else:
                self.db.add(ThesisScenario(
                    thesis_id=thesis.id,
                    name=name.capitalize(),
                    probability=prob,
                    prev_probability=prevs.get(name),
                ))

        self.db.commit()

    # ------------------------------------------------------------------
    # Evidence clustering
    # ------------------------------------------------------------------

    def build_evidence_clusters(
        self,
        event: Event,
        *,
        price_data: dict[str, float] | None = None,
        polymarket_prob: float | None = None,
        official_confirmations: int = 0,
        analyst_views: int = 0,
        counter_evidence_count: int = 0,
    ) -> list[EvidenceCluster]:
        """
        Build evidence clusters from available data, grouping correlated
        sensors together to avoid double-counting.

        Returns clusters with independence flags set.
        """
        clusters: list[EvidenceCluster] = []

        # Cluster 1: Official / filing evidence (independent)
        if official_confirmations > 0 or (event.evidence_grade or "E0") in ("E3", "E4"):
            lr = 2.0 + official_confirmations * 0.5
            confidence = 0.85 if event.evidence_grade == "E4" else 0.7
            clusters.append(EvidenceCluster(
                cluster_id="official_evidence",
                sensors=["sec_edgar", "official_release", "filing"],
                likelihood_ratio=min(lr, 5.0),
                confidence_weight=confidence,
                is_independent=True,
            ))

        # Cluster 2: Market price sensors (correlated, one cluster)
        if price_data:
            price_signals = []
            lr_product = 1.0
            for symbol, change_pct in price_data.items():
                price_signals.append(symbol)
                if event.event_type in ("policy_announcement", "filing"):
                    # For these types, price movement confirms hypothesis
                    lr_product *= 1.0 + abs(change_pct) * 5
                else:
                    lr_product *= 1.0 + abs(change_pct) * 2

            if price_signals:
                clusters.append(EvidenceCluster(
                    cluster_id="price_sensors",
                    sensors=price_signals,
                    likelihood_ratio=min(lr_product, 3.0),
                    confidence_weight=0.5,
                    is_independent=True,
                ))

        # Cluster 3: Polymarket (independent sensor)
        if polymarket_prob is not None:
            lr = max(0.5, polymarket_prob / max(1 - polymarket_prob, 0.01))
            clusters.append(EvidenceCluster(
                cluster_id="polymarket",
                sensors=["polymarket"],
                likelihood_ratio=min(lr, 4.0),
                confidence_weight=0.55,
                is_independent=True,
            ))

        # Cluster 4: Analyst consensus (correlated, lower weight)
        if analyst_views > 0:
            lr = 1.0 + max(0, analyst_views - 2) * 0.2
            clusters.append(EvidenceCluster(
                cluster_id="analyst_views",
                sensors=[f"analyst_{i}" for i in range(analyst_views)],
                likelihood_ratio=min(lr, 2.0),
                confidence_weight=0.3,
                is_independent=True,
            ))

        # Cluster 5: Counterevidence (negative signal)
        if counter_evidence_count > 0:
            lr = max(0.2, 1.0 - counter_evidence_count * 0.3)
            clusters.append(EvidenceCluster(
                cluster_id="counterevidence",
                sensors=["counterevidence"],
                likelihood_ratio=lr,
                confidence_weight=0.6,
                is_independent=True,
            ))

        return clusters

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------

    def brier_score(
        self,
        predictions: list[float],
        outcomes: list[int],
    ) -> float:
        """Brier score = mean squared error between predicted prob and outcome."""
        if not predictions or len(predictions) != len(outcomes):
            return 0.0
        errors = [(p - o) ** 2 for p, o in zip(predictions, outcomes)]
        return sum(errors) / len(errors)

    def log_loss_score(
        self,
        predictions: list[float],
        outcomes: list[int],
    ) -> float:
        """Log loss = -mean(o * log(p) + (1-o) * log(1-p))."""
        if not predictions or len(predictions) != len(outcomes):
            return 0.0
        total = 0.0
        eps = 1e-15
        for p, o in zip(predictions, outcomes):
            p_clipped = max(eps, min(1 - eps, p))
            total += -(o * math.log(p_clipped) + (1 - o) * math.log(1 - p_clipped))
        return total / len(predictions)

    def reliability_curve(
        self,
        predictions: list[float],
        outcomes: list[int],
        num_bins: int = 10,
    ) -> list[dict[str, float]]:
        """
        Build a reliability curve to assess calibration quality.

        Groups predictions into bins, computse mean predicted vs actual fraction.
        A perfectly calibrated model has them equal.
        """
        if not predictions or len(predictions) != len(outcomes):
            return []

        paired = sorted(zip(predictions, outcomes), key=lambda x: x[0])
        bin_size = max(1, len(paired) // num_bins)
        curve: list[dict[str, float]] = []

        for i in range(0, len(paired), bin_size):
            batch = paired[i : i + bin_size]
            if not batch:
                continue
            mean_pred = sum(p for p, _ in batch) / len(batch)
            actual_freq = sum(o for _, o in batch) / len(batch)
            curve.append({
                "mean_predicted": round(mean_pred, 4),
                "actual_frequency": round(actual_freq, 4),
                "bin_size": len(batch),
            })

        return curve

    def calibrate(
        self,
        event_family: str,
        predictions: list[float],
        outcomes: list[int],
    ) -> CalibrationMetrics:
        """Run full calibration evaluation for an event family."""
        brier = self.brier_score(predictions, outcomes)
        logloss = self.log_loss_score(predictions, outcomes)
        relcurve = self.reliability_curve(predictions, outcomes)

        return CalibrationMetrics(
            brier_score=round(brier, 4),
            log_loss=round(logloss, 4),
            reliability_curve=relcurve,
            num_predictions=len(predictions),
            event_family=event_family,
        )

    def store_prediction(
        self,
        thesis_id: str,
        event_family: str,
        predicted_prob: float,
        timestamp: datetime | None = None,
    ) -> None:
        """Store a prediction for later calibration."""
        key = event_family
        if key not in self._predictions_store:
            self._predictions_store[key] = []
        self._predictions_store[key].append({
            "thesis_id": thesis_id,
            "predicted": predicted_prob,
            "timestamp": (timestamp or datetime.utcnow()).isoformat(),
        })

    def resolve_prediction(
        self,
        thesis_id: str,
        event_family: str,
        actual_outcome: int,  # 0 or 1
    ) -> None:
        """Resolve a previously stored prediction with its actual outcome."""
        key = event_family
        if key not in self._predictions_store:
            return
        for pred in self._predictions_store[key]:
            if pred["thesis_id"] == thesis_id and "outcome" not in pred:
                pred["outcome"] = actual_outcome
                break

    def get_calibration_for_family(self, event_family: str) -> CalibrationMetrics:
        """Get calibration metrics for an event family."""
        key = event_family
        predictions_raw = self._predictions_store.get(key, [])
        resolved = [p for p in predictions_raw if "outcome" in p]
        if not resolved:
            return CalibrationMetrics(event_family=event_family)

        probs = [p["predicted"] for p in resolved]
        outcomes = [p["outcome"] for p in resolved]
        return self.calibrate(event_family, probs, outcomes)

    def market_benchmark_comparison(
        self,
        model_predictions: list[float],
        market_prices: list[float],
        outcomes: list[int],
    ) -> dict[str, Any]:
        """
        Compare model calibration vs Polymarket/market baseline.

        Returns whether the model is outperforming the market as a probability source.
        """
        model_brier = self.brier_score(model_predictions, outcomes)
        market_brier = self.brier_score(market_prices, outcomes)
        model_logloss = self.log_loss_score(model_predictions, outcomes)
        market_logloss = self.log_loss_score(market_prices, outcomes)

        beats_market = model_brier < market_brier

        return {
            "model_brier": round(model_brier, 4),
            "market_brier": round(market_brier, 4),
            "model_log_loss": round(model_logloss, 4),
            "market_log_loss": round(market_logloss, 4),
            "beats_market_on_brier": beats_market,
            "brier_difference": round(market_brier - model_brier, 4),
            "sample_size": len(model_predictions),
            "note": "Market price is a strong baseline; compare PnL separately",
        }


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _logit(p: float) -> float:
    """logit(p) = log(p / (1-p)). Clamped for numerical stability."""
    p = max(0.001, min(0.999, p))
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    """sigmoid(x) = 1 / (1 + exp(-x))."""
    if x > 20:
        return 1.0
    if x < -20:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def _shrink_toward_prior(
    posterior: float,
    prior: float,
    num_independent_signals: int,
) -> float:
    """
    Shrink posterior toward prior when sample size (independent signals) is small.

    Shrinkage factor = num_signals / (num_signals + k), where k is regularization.
    """
    k = 3.0  # regularization strength
    shrinkage = num_independent_signals / (num_independent_signals + k)
    return prior + shrinkage * (posterior - prior)
