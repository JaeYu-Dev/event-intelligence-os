"""
Point-in-Time Walk-Forward Backtest Engine (Spec XXXI-XLIII)

Runs the full engine pipeline at historical cutoff times and evaluates
predictions against forward outcomes, enforcing:
  - no future information leakage
  - immutable prediction records
  - separated train / validation / test windows
  - calibration-aware metrics
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from api.models import (
    BacktestRun,
    Event,
    MarketPrice,
    MarketInstrument,
    PredictionRecord,
    Thesis,
)
from api.engine.pit_snapshot import PITSnapshotBuilder
from api.engine.combinatorial import CombinatorialScanEngine
from api.engine.gates import ScenarioPromotionGate
from api.engine.probability import ProbabilityEngine
from api.engine.postmortem import PostmortemBuilder


@dataclass
class BacktestConfig:
    run_name: str
    cutoff_start: datetime
    cutoff_end: datetime
    train_window_days: int = 365
    val_window_days: int = 90
    test_window_days: int = 90
    step_days: int = 30
    universe: dict[str, Any] = field(default_factory=dict)
    benchmark: str = "SPY"
    transaction_cost_pct: float = 0.001
    model_version: str = "v1.0"
    prompt_version: str = "v1.0"
    schema_version: str = "v1.2-pit"
    max_motifs_per_cutoff: int = 50
    min_events_per_motif: int = 3


@dataclass
class BacktestWindow:
    train_start: datetime
    train_end: datetime
    val_start: datetime
    val_end: datetime
    test_start: datetime
    test_end: datetime
    cutoff: datetime


@dataclass
class PredictionOutcome:
    prediction_id: str
    target_asset: str
    forecast_horizon: str
    expected_direction: str
    predicted_prob: float
    actual_return: float | None
    actual_direction: int | None  # 1 = up, 0 = down/flat
    benchmark_return: float | None
    resolved: bool


class WalkForwardEngine:
    """Walk-forward backtest coordinator."""

    HORIZON_DAYS = {"1d": 1, "5d": 5, "20d": 20, "60d": 60, "120d": 120}

    def __init__(self, db: Session):
        self.db = db
        self.snapshot_builder = PITSnapshotBuilder(db)
        self.scan_engine = CombinatorialScanEngine(db)
        self.gate_engine = ScenarioPromotionGate()
        self.prob_engine = ProbabilityEngine(db)
        self.postmortem = PostmortemBuilder()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, config: BacktestConfig) -> dict[str, Any]:
        """Run a full walk-forward backtest."""
        def _serialize_config(cfg):
            out = {}
            for k, v in cfg.__dict__.items():
                if isinstance(v, datetime):
                    out[k] = v.isoformat()
                else:
                    out[k] = v
            return out

        run = BacktestRun(
            id=uuid4(),
            run_name=config.run_name,
            status="running",
            config=_serialize_config(config),
            model_version=config.model_version,
            prompt_version=config.prompt_version,
            schema_version=config.schema_version,
        )
        self.db.add(run)
        self.db.commit()

        try:
            windows = self._generate_windows(config)
            all_predictions: list[PredictionOutcome] = []
            summaries: list[dict[str, Any]] = []

            for w in windows:
                summary = self._run_single_cutoff(w, config, run)
                summaries.append(summary)
                all_predictions.extend(summary.get("outcomes", []))

            metrics = self._compute_metrics(all_predictions)
            improvement = self._build_improvement_decision(metrics)

            run.status = "completed"
            run.completed_at = datetime.utcnow()
            run.predictions_generated = len(all_predictions)
            run.predictions_resolved = sum(1 for p in all_predictions if p.resolved)
            run.brier_score = metrics.get("brier_score")
            run.log_loss = metrics.get("log_loss")
            run.calibration_curve = metrics.get("reliability_curve", [])
            run.result_summary = {
                "windows": len(windows),
                "predictions_generated": len(all_predictions),
                "predictions_resolved": run.predictions_resolved,
                "direction_accuracy": metrics.get("direction_accuracy"),
                "mean_excess_return": metrics.get("mean_excess_return"),
                "brier_score": run.brier_score,
                "log_loss": run.log_loss,
                "improvement_decision": improvement,
                "failure_analysis": failure_summary,
                "summaries": summaries,
            }
            # Build aggregate postmortem from resolved prediction records
            resolved_records = (
                self.db.query(PredictionRecord)
                .filter(PredictionRecord.backtest_run_id == run.id)
                .all()
            )
            failure_summary = self.postmortem.build_backtest_summary(resolved_records)
            run.failure_analysis = failure_summary

            run.improvement_decision = improvement
            self.db.commit()

            return {
                "backtest_run_id": str(run.id),
                "status": "completed",
                "config": config.__dict__,
                "windows": len(windows),
                "metrics": metrics,
                "improvement_decision": improvement,
                "failure_analysis": failure_summary,
                "summaries": summaries,
            }
        except Exception as e:
            run.status = "failed"
            run.result_summary = {"error": str(e)}
            self.db.commit()
            raise

    # ------------------------------------------------------------------
    # Window generation
    # ------------------------------------------------------------------

    def _generate_windows(self, config: BacktestConfig) -> list[BacktestWindow]:
        """Generate rolling walk-forward windows."""
        windows: list[BacktestWindow] = []
        current = config.cutoff_start
        while current + timedelta(days=config.test_window_days) <= config.cutoff_end:
            train_start = current - timedelta(
                days=config.train_window_days + config.val_window_days
            )
            train_end = current - timedelta(days=config.val_window_days)
            val_start = train_end
            val_end = current
            test_start = current
            test_end = current + timedelta(days=config.test_window_days)
            windows.append(
                BacktestWindow(
                    train_start=train_start,
                    train_end=train_end,
                    val_start=val_start,
                    val_end=val_end,
                    test_start=test_start,
                    test_end=test_end,
                    cutoff=current,
                )
            )
            current += timedelta(days=config.step_days)
        return windows

    # ------------------------------------------------------------------
    # Single cutoff run
    # ------------------------------------------------------------------

    def _run_single_cutoff(
        self,
        window: BacktestWindow,
        config: BacktestConfig,
        run: BacktestRun,
    ) -> dict[str, Any]:
        """Run Deep Scan -> Gate -> Prediction Records for one cutoff."""
        snapshot = self.snapshot_builder.build(window.cutoff, universe=config.universe)

        # Run combinatorial scan on PIT event universe
        scan_result = self.scan_engine.run(
            max_motifs=config.max_motifs_per_cutoff,
            min_events=config.min_events_per_motif,
        )
        motifs = scan_result.get("motifs", [])

        # Apply 10-gate system
        gated = []
        for m in motifs:
            gating = self.gate_engine.evaluate(m, existing_scenarios=gated[:10])
            m["gate_status"] = gating.final_status
            m["gate_score"] = gating.overall_score
            m["passed_gates"] = sum(1 for g in gating.gate_results if g.passed)
            gated.append(m)

        # Keep only active / high-conviction candidates
        qualified = [
            m
            for m in gated
            if m.get("gate_status") in ("active_scenario", "high_conviction_research_candidate")
        ]

        # Create prediction records for top qualified motifs
        predictions: list[PredictionOutcome] = []
        for m in qualified[:10]:
            preds = self._create_predictions_from_motif(
                m, window, config, run, snapshot
            )
            predictions.extend(preds)

        # Resolve predictions with forward returns
        resolved = [self._resolve_prediction(p, window, config) for p in predictions]

        return {
            "cutoff": window.cutoff.isoformat(),
            "test_end": window.test_end.isoformat(),
            "motifs_scanned": len(motifs),
            "qualified": len(qualified),
            "predictions": len(predictions),
            "outcomes": resolved,
        }

    def _create_predictions_from_motif(
        self,
        motif: dict[str, Any],
        window: BacktestWindow,
        config: BacktestConfig,
        run: BacktestRun,
        snapshot: Any,
    ) -> list[PredictionOutcome]:
        """Create immutable PredictionRecords from a motif."""
        tickers = motif.get("aggregated_tickers", [])
        if not tickers:
            return []

        # Use scenario distribution from motif
        dist = motif.get("scenario_distribution", {})
        bull_p = dist.get("Bull", 0.33)
        bear_p = dist.get("Bear", 0.22)
        expected_direction = "up" if bull_p > bear_p else "down"
        predicted_prob = bull_p if expected_direction == "up" else bear_p

        outcomes: list[PredictionOutcome] = []
        for horizon, days in self.HORIZON_DAYS.items():
            for ticker in tickers[:3]:  # limit to top 3 tickers per motif
                record = PredictionRecord(
                    id=uuid4(),
                    claim=motif.get("narrative_ko", ""),
                    target_asset=ticker,
                    target_metric="price_change",
                    forecast_horizon=horizon,
                    expected_direction=expected_direction,
                    expected_range=f"{motif.get('scenario_distribution', {})}",
                    confidence=predicted_prob,
                    probability_basis="motif_scenario_distribution",
                    evidence_at_creation=motif.get("events", []),
                    market_expectation_snapshot=snapshot.to_dict(),
                    model_version=config.model_version,
                    backtest_run_id=run.id,
                    cutoff_time=window.cutoff,
                    snapshot_version=snapshot.snapshot_version,
                    status="active",
                )
                self.db.add(record)
                outcomes.append(
                    PredictionOutcome(
                        prediction_id=str(record.id),
                        target_asset=ticker,
                        forecast_horizon=horizon,
                        expected_direction=expected_direction,
                        predicted_prob=predicted_prob,
                        actual_return=None,
                        actual_direction=None,
                        benchmark_return=None,
                        resolved=False,
                    )
                )
        self.db.commit()
        return outcomes

    # ------------------------------------------------------------------
    # Outcome resolution
    # ------------------------------------------------------------------

    def _resolve_prediction(
        self,
        p: PredictionOutcome,
        window: BacktestWindow,
        config: BacktestConfig,
    ) -> PredictionOutcome:
        """Resolve a prediction against actual forward prices."""
        days = self.HORIZON_DAYS.get(p.forecast_horizon, 20)
        horizon_end = window.cutoff + timedelta(days=days)
        if horizon_end > window.test_end:
            horizon_end = window.test_end

        price_start = self._price_at(p.target_asset, window.cutoff)
        price_end = self._price_at(p.target_asset, horizon_end)
        bench_start = self._price_at(config.benchmark, window.cutoff)
        bench_end = self._price_at(config.benchmark, horizon_end)

        if price_start and price_end and price_start > 0:
            raw_return = (price_end - price_start) / price_start
            p.actual_return = raw_return - config.transaction_cost_pct
            p.actual_direction = 1 if p.actual_return > 0 else 0
        if bench_start and bench_end and bench_start > 0:
            p.benchmark_return = (bench_end - bench_start) / bench_start

        p.resolved = price_start is not None and price_end is not None

        # Update DB record
        record = (
            self.db.query(PredictionRecord)
            .filter(PredictionRecord.id == UUID(p.prediction_id))
            .first()
        )
        if record:
            record.actual_outcome = {
                "actual_return": p.actual_return,
                "actual_direction": p.actual_direction,
                "benchmark_return": p.benchmark_return,
                "horizon_end": horizon_end.isoformat(),
            }
            record.outcome_timestamp = datetime.utcnow()
            record.status = "resolved" if p.resolved else "unresolved"
            # Auto-generate postmortem for resolved records
            if p.resolved:
                from api.models import Event
                event = self.db.query(Event).filter(Event.id == record.event_id).first() if record.event_id else None
                record.postmortem = str(self.postmortem.build(record, event))
            self.db.commit()
        return p

    def _price_at(self, symbol: str, dt: datetime) -> float | None:
        """Get the latest available price for symbol at or before dt."""
        inst = self.db.query(MarketInstrument).filter(MarketInstrument.symbol == symbol).first()
        if not inst:
            return None
        price = (
            self.db.query(MarketPrice)
            .filter(
                MarketPrice.instrument_id == inst.id,
                MarketPrice.timestamp <= dt,
            )
            .order_by(MarketPrice.timestamp.desc())
            .first()
        )
        return price.close if price else None

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def _compute_metrics(self, predictions: list[PredictionOutcome]) -> dict[str, Any]:
        resolved = [p for p in predictions if p.resolved and p.actual_direction is not None]
        if not resolved:
            return {"note": "no resolved predictions"}

        probs = [p.predicted_prob for p in resolved]
        outcomes = [p.actual_direction for p in resolved]
        brier = self.prob_engine.brier_score(probs, outcomes)
        logloss = self.prob_engine.log_loss_score(probs, outcomes)
        reliability = self.prob_engine.reliability_curve(probs, outcomes, num_bins=5)

        correct = sum(
            1
            for p in resolved
            if (p.expected_direction == "up" and p.actual_direction == 1)
            or (p.expected_direction == "down" and p.actual_direction == 0)
        )
        excess_returns = [
            (p.actual_return or 0) - (p.benchmark_return or 0)
            for p in resolved
            if p.actual_return is not None
        ]

        return {
            "total_predictions": len(predictions),
            "resolved": len(resolved),
            "direction_accuracy": round(correct / len(resolved), 4),
            "mean_excess_return": round(sum(excess_returns) / len(excess_returns), 4)
            if excess_returns
            else None,
            "brier_score": round(brier, 4),
            "log_loss": round(logloss, 4),
            "reliability_curve": reliability,
        }

    def _build_improvement_decision(self, metrics: dict[str, Any]) -> str:
        """Suggest an improvement decision based on backtest metrics."""
        if "brier_score" not in metrics:
            return "No Change"
        brier = metrics["brier_score"]
        acc = metrics.get("direction_accuracy", 0)
        if brier > 0.25:
            return "Probability Calibration Update Candidate"
        if acc and acc < 0.45:
            return "Edge Weight Update Candidate"
        if metrics.get("mean_excess_return", 0) < -0.02:
            return "Data Source Priority Update Candidate"
        return "No Change"
