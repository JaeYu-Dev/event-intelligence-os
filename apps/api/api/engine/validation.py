"""
Validation & Learning Engine (Engine 8)

Implements replay, post-mortem analysis, error classification, and statistical
validation to separate "plausible AI research" from "reproducible decisions."

Section 29.8 of the spec.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID
import math

from sqlalchemy.orm import Session

from api.models import (
    Event,
    EventRelation,
    Thesis,
    ThesisScenario,
    PaperTrade,
    PortfolioPosition,
    DecisionLog,
    ModelRun,
    PromptVersion,
    MarketPrice,
    MarketInstrument,
)


# ---------------------------------------------------------------------------
# Enums and data classes
# ---------------------------------------------------------------------------

class FailureType(str, Enum):
    EVIDENCE_ERROR = "EVIDENCE_ERROR"       # Misread source text / numbers / conditions
    ENTITY_ERROR = "ENTITY_ERROR"           # Wrong company / product / market mapping
    MECHANISM_ERROR = "MECHANISM_ERROR"     # Economic propagation path was wrong
    TIMING_ERROR = "TIMING_ERROR"           # Right path but already priced / too early or late
    REGIME_ERROR = "REGIME_ERROR"           # Past pattern doesn't fit current regime
    EXECUTION_ERROR = "EXECUTION_ERROR"     # Spread / slippage / liquidity / excessive turnover
    CONTRACT_ERROR = "CONTRACT_ERROR"       # Polymarket settlement rules or market definition
    UNKNOWN = "UNKNOWN"                     # Could not identify cause


@dataclass
class FailureClassification:
    """Classification of why a thesis/decision was wrong."""
    failure_type: FailureType
    description: str
    description_ko: str
    confidence: float  # how sure we are about this classification
    evidence: list[str] = field(default_factory=list)
    preventable: bool = False


@dataclass
class ReplaySnapshot:
    """A point-in-time capture of the system state for replay."""
    timestamp: datetime
    event_id: str
    thesis_id: str | None = None
    scenario_probs: dict[str, float] = field(default_factory=dict)
    position_values: dict[str, float] = field(default_factory=dict)
    market_prices: dict[str, float] = field(default_factory=dict)
    decisions_made: list[dict[str, Any]] = field(default_factory=list)
    model_version: str | None = None
    prompt_version: str | None = None
    ontology_version: str | None = None


@dataclass
class PerformanceMetrics:
    """Tracked performance metrics for a thesis."""
    thesis_id: str
    total_pnl_usd: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float | None = None
    deflated_sharpe: float | None = None  # DSR
    pbo_estimate: float | None = None     # Probability of Backtest Overfitting
    trade_count: int = 0
    win_rate: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0


# ---------------------------------------------------------------------------
# Validation Engine
# ---------------------------------------------------------------------------

class ValidationEngine:
    """
    Post-mortem and learning engine.

    For each completed (or failed) thesis:
      1. Capture replay snapshot
      2. Classify errors
      3. Update performance metrics
      4. Check for overfitting signals
    """

    def __init__(self, db: Session):
        self.db = db

    def run_post_mortem(self, thesis_id: str) -> dict[str, Any]:
        """
        Run a full post-mortem analysis on a thesis.

        Examines:
          - What the system believed at decision time
          - What actually happened
          - Why the gap existed
          - What can be learned
        """
        thesis = self.db.query(Thesis).filter(Thesis.id == UUID(thesis_id)).first()
        if not thesis:
            return {"error": "Thesis not found"}

        # Gather decisions
        decisions = (
            self.db.query(DecisionLog)
            .filter(DecisionLog.thesis_id == UUID(thesis_id))
            .order_by(DecisionLog.created_at.asc())
            .all()
        )

        # Gather trades for PnL
        trades = (
            self.db.query(PaperTrade)
            .filter(PaperTrade.thesis_id == UUID(thesis_id))
            .order_by(PaperTrade.executed_at.asc())
            .all()
        )

        # Classify outcome
        outcome = self._classify_outcome(thesis)

        # Compute performance
        metrics = self._compute_performance(thesis_id, trades)

        # Classify errors if applicable
        failures: list[dict[str, Any]] = []
        if outcome.get("error"):
            failures = self._classify_failures(thesis, decisions, outcome)

        # Build replay snapshot
        snapshots = self._build_replay_snapshots(thesis, decisions, trades)

        return {
            "thesis_id": thesis_id,
            "thesis_title": thesis.title or "",
            "current_status": thesis.status,
            "outcome": outcome,
            "metrics": {
                "total_pnl_usd": round(metrics.total_pnl_usd, 2),
                "total_return_pct": round(metrics.total_return_pct, 4),
                "max_drawdown_pct": round(metrics.max_drawdown_pct, 4),
                "trade_count": metrics.trade_count,
                "win_rate": round(metrics.win_rate, 4),
                "avg_win_pct": round(metrics.avg_win_pct, 4),
                "avg_loss_pct": round(metrics.avg_loss_pct, 4),
            },
            "failures": [vars(f) if hasattr(f, '__dict__') else f for f in failures],
            "learnings": self._generate_learnings(failures, outcome),
            "snapshots": snapshots,
        }

    def _classify_outcome(self, thesis: Thesis) -> dict[str, Any]:
        """Classify the outcome of a thesis."""
        if thesis.status in ("Resolved", "Watching", "Archived"):
            scenarios = (
                self.db.query(ThesisScenario)
                .filter(ThesisScenario.thesis_id == thesis.id)
                .all()
            )

            bull_prob = next(
                (s.probability for s in scenarios if s.name and s.name.lower() == "bull"),
                None,
            )
            bear_prob = next(
                (s.probability for s in scenarios if s.name and s.name.lower() == "bear"),
                None,
            )

            # Check if probabilities shifted significantly
            if bull_prob and bear_prob:
                if bear_prob > bull_prob + 0.2:
                    return {
                        "outcome": "bearish",
                        "outcome_ko": "약세 전환",
                        "confidence": bear_prob,
                        "error": bear_prob > 0.3,
                    }
                elif bull_prob > bear_prob + 0.2:
                    return {
                        "outcome": "bullish",
                        "outcome_ko": "강세 유지",
                        "confidence": bull_prob,
                        "error": False,
                    }
                else:
                    return {
                        "outcome": "neutral",
                        "outcome_ko": "중립",
                        "confidence": 0.5,
                        "error": False,
                    }

        if thesis.status == "Invalidated":
            return {
                "outcome": "invalidated",
                "outcome_ko": "무효화됨",
                "confidence": 0.9,
                "error": True,
            }

        return {
            "outcome": "pending",
            "outcome_ko": "진행 중",
            "confidence": 0.5,
            "error": False,
        }

    def _compute_performance(
        self,
        thesis_id: str,
        trades: list[PaperTrade],
    ) -> PerformanceMetrics:
        """Compute performance metrics from paper trades."""
        metrics = PerformanceMetrics(thesis_id=thesis_id, trade_count=len(trades))

        if not trades:
            return metrics

        # Sort by execution time
        sorted_trades = sorted(trades, key=lambda t: t.executed_at or datetime.min)

        buy_trades = [t for t in sorted_trades if t.action and t.action.upper() == "BUY"]
        sell_trades = [t for t in sorted_trades if t.action and t.action.upper() == "SELL"]

        # Simple PnL: match buys with sells FIFO
        pnl = 0.0
        buy_queue: list[tuple[float, float]] = []  # (price, shares)
        wins = 0
        losses = 0
        win_pcts: list[float] = []
        loss_pcts: list[float] = []
        running_equity: list[float] = [0.0]

        for t in sorted_trades:
            price = t.price or 0
            shares = t.shares or 0
            action = (t.action or "").upper()

            if action == "BUY":
                buy_queue.append((price, shares))
                running_equity.append(running_equity[-1] - price * shares - (t.costs or 0))
            elif action == "SELL" and buy_queue:
                buy_price, buy_shares = buy_queue.pop(0)
                trade_pnl = (price - buy_price) * min(shares, buy_shares) - (t.costs or 0)
                pnl += trade_pnl
                running_equity.append(running_equity[-1] + price * shares)

                pct_return = (price - buy_price) / buy_price if buy_price > 0 else 0
                if pct_return >= 0:
                    wins += 1
                    win_pcts.append(pct_return)
                else:
                    losses += 1
                    loss_pcts.append(abs(pct_return))

        metrics.total_pnl_usd = pnl
        metrics.win_rate = wins / max(wins + losses, 1)

        if win_pcts:
            metrics.avg_win_pct = sum(win_pcts) / len(win_pcts)
        if loss_pcts:
            metrics.avg_loss_pct = sum(loss_pcts) / len(loss_pcts)

        # Total return
        if running_equity[0] != 0:
            metrics.total_return_pct = abs(running_equity[-1] / running_equity[0]) - 1 if running_equity[0] > 0 else 0

        # Max drawdown
        peak = running_equity[0]
        max_dd = 0.0
        for val in running_equity:
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        metrics.max_drawdown_pct = max_dd

        # Deflated Sharpe Ratio (simplified)
        if trades:
            returns = []
            for i in range(1, len(running_equity)):
                if running_equity[i - 1] > 0:
                    returns.append(
                        (running_equity[i] - running_equity[i - 1]) / running_equity[i - 1]
                    )
            if returns and len(returns) > 1:
                avg_ret = sum(returns) / len(returns)
                std_ret = math.sqrt(
                    sum((r - avg_ret) ** 2 for r in returns) / (len(returns) - 1)
                ) if len(returns) > 1 else 1e-10
                metrics.sharpe_ratio = avg_ret / std_ret if std_ret > 0 else 0
                # DSR: adjusts for multiple testing
                N = len(returns)
                metrics.deflated_sharpe = (
                    metrics.sharpe_ratio * math.sqrt(N / (N + 10))
                    if metrics.sharpe_ratio else 0
                )

        return metrics

    def _classify_failures(
        self,
        thesis: Thesis,
        decisions: list[DecisionLog],
        outcome: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Classify failure reasons based on decision logs and outcome."""
        failures: list[dict[str, Any]] = []

        # Simple heuristic classification based on available data
        if thesis.status == "Invalidated":
            # Check if there was counterevidence
            event = (
                self.db.query(Event)
                .filter(Event.id == thesis.core_event_id)
                .first()
            )
            if event:
                if event.counterevidence_ko:
                    failures.append({
                        "failure_type": FailureType.EVIDENCE_ERROR.value,
                        "description": "Counterevidence was present but not weighted enough",
                        "description_ko": "반대 증거가 존재했으나 충분히 반영되지 않음",
                        "confidence": 0.7,
                        "evidence": list(event.counterevidence_ko or []),
                        "preventable": True,
                    })

                if event.mechanism_ko and len(decisions) == 0:
                    failures.append({
                        "failure_type": FailureType.TIMING_ERROR.value,
                        "description": "No reassessment was triggered after key checkpoint",
                        "description_ko": "주요 확인 시점 이후 재평가가 트리거되지 않음",
                        "confidence": 0.5,
                        "evidence": [],
                        "preventable": True,
                    })

        if not failures:
            failures.append({
                "failure_type": FailureType.UNKNOWN.value,
                "description": "Unable to determine exact failure cause",
                "description_ko": "정확한 실패 원인을 식별할 수 없음",
                "confidence": 0.3,
                "evidence": [],
                "preventable": False,
            })

        return failures

    def _build_replay_snapshots(
        self,
        thesis: Thesis,
        decisions: list[DecisionLog],
        trades: list[PaperTrade],
    ) -> list[dict[str, Any]]:
        """Build replay snapshots from existing data."""
        snapshots: list[dict[str, Any]] = []

        # Build one snapshot per decision event
        for d in decisions:
            scenarios = (
                self.db.query(ThesisScenario)
                .filter(ThesisScenario.thesis_id == thesis.id)
                .all()
            )
            scenario_probs = {
                s.name or "base": s.probability or 0 for s in scenarios
            }

            snapshot = {
                "timestamp": d.created_at.isoformat() if d.created_at else None,
                "decision": d.decision,
                "reason_summary": d.reason_summary,
                "counterevidence_summary": d.counterevidence_summary,
                "scenario_probs": scenario_probs,
                "model_version": d.model_version,
                "prompt_version": d.prompt_version,
                "ontology_version": d.ontology_version,
                "human_approval_state": d.human_approval_state,
            }
            snapshots.append(snapshot)

        return snapshots

    def _generate_learnings(
        self,
        failures: list[dict[str, Any]],
        outcome: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Generate human-readable learning items."""
        learnings: list[dict[str, str]] = []

        for f in failures:
            ftype = f.get("failure_type", "")
            if ftype == FailureType.EVIDENCE_ERROR.value:
                learnings.append({
                    "ko": "향후 유사 가설에서는 반대 증거를 더 높은 가중치로 반영하세요.",
                    "en": "Weight counterevidence more heavily in similar future theses.",
                })
            elif ftype == FailureType.TIMING_ERROR.value:
                learnings.append({
                    "ko": "다음 확인 이벤트 이후 재평가 자동화를 검토하세요.",
                    "en": "Consider automating reassessment after key checkpoints.",
                })
            elif ftype == FailureType.MECHANISM_ERROR.value:
                learnings.append({
                    "ko": "인과 경로의 중간 메커니즘을 더 구체적으로 검증하세요.",
                    "en": "Validate intermediate causal mechanisms more rigorously.",
                })
            else:
                learnings.append({
                    "ko": "실패 원인을 식별하지 못했습니다. 추가 데이터 수집이 필요합니다.",
                    "en": "Could not identify failure cause. More data needed.",
                })

        return learnings

    def compute_pbo_estimate(
        self,
        thesis_ids: list[str],
        *,
        num_trials: int = 100,
    ) -> dict[str, Any]:
        """
        Compute a simplified Probability of Backtest Overfitting estimate.

        Based on Combinatorially Symmetric Cross-Validation (CSCV) approach.
        """
        if len(thesis_ids) < 3:
            return {
                "pbo_estimate": None,
                "warning": "Need at least 3 theses for reliable PBO estimation",
            }

        # Gather performance for each thesis
        performances: list[float] = []
        for tid in thesis_ids:
            trades = (
                self.db.query(PaperTrade)
                .filter(PaperTrade.thesis_id == UUID(tid))
                .all()
            )
            _, returns = self._simple_returns_from_trades(trades)
            if returns:
                avg_ret = sum(returns) / len(returns)
                performances.append(avg_ret)

        if len(performances) < 3:
            return {"pbo_estimate": None, "warning": "Insufficient data"}

        # Simple PBO: ratio of in-sample best to out-of-sample performance
        midpoint = len(performances) // 2
        in_sample = performances[:midpoint]
        out_sample = performances[midpoint:]

        if not in_sample or not out_sample:
            return {"pbo_estimate": None, "warning": "Cannot split sample"}

        is_best = max(in_sample)
        os_rank = sum(1 for x in out_sample if x >= is_best) / len(out_sample)
        pbo = 1.0 - os_rank

        return {
            "pbo_estimate": round(pbo, 4),
            "interpretation": (
                "Likely overfit" if pbo > 0.5 else "Acceptable"
            ),
            "in_sample_theses": len(in_sample),
            "out_sample_theses": len(out_sample),
        }

    def _simple_returns_from_trades(
        self, trades: list[PaperTrade]
    ) -> tuple[float, list[float]]:
        """Compute simple PnL and returns from a list of trades."""
        sorted_trades = sorted(trades, key=lambda t: t.executed_at or datetime.min)
        pnl = 0.0
        returns: list[float] = []
        buy_queue: list[tuple[float, float]] = []

        for t in sorted_trades:
            price = t.price or 0
            shares = t.shares or 0
            action = (t.action or "").upper()

            if action == "BUY":
                buy_queue.append((price, shares))
            elif action == "SELL" and buy_queue:
                buy_price, buy_shares = buy_queue.pop(0)
                trade_pnl = (price - buy_price) * min(shares, buy_shares)
                pnl += trade_pnl
                if buy_price > 0:
                    returns.append((price - buy_price) / buy_price)

        return pnl, returns
