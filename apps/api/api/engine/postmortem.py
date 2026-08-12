"""
Postmortem Builder (Spec XL)

Generates structured postmortem analysis for each prediction record,
covering the 11 required dimensions.
"""

from typing import Any

from api.models import PredictionRecord, Event


class PostmortemBuilder:
    """Build postmortem analysis for a prediction record."""

    def build(self, record: PredictionRecord, event: Event | None = None) -> dict[str, Any]:
        actual = record.actual_outcome or {}
        actual_return = actual.get("actual_return")
        actual_direction = actual.get("actual_direction")
        benchmark_return = actual.get("benchmark_return")

        expected_dir = record.expected_direction or "unknown"
        predicted_prob = record.confidence or 0.5
        outcome_correct = self._direction_correct(expected_dir, actual_direction)

        # 1. Fact Quality
        fact_quality = self._evaluate_fact_quality(record, event)

        # 2. Event Stage Accuracy
        stage_accuracy = self._evaluate_stage(record, event)

        # 3. Mechanism Accuracy
        mechanism_accuracy = self._evaluate_mechanism(record, actual_return)

        # 4. Exposure Accuracy
        exposure_accuracy = self._evaluate_exposure(record, actual_return)

        # 5. Expectation Accuracy
        expectation_accuracy = self._evaluate_expectation(record, benchmark_return)

        # 6. Timing Accuracy
        timing_accuracy = self._evaluate_timing(record, actual)

        # 7. Probability Calibration
        calibration = self._evaluate_calibration(predicted_prob, actual_direction)

        # 8. Falsifier Quality
        falsifier_quality = self._evaluate_falsifier(record, actual)

        # 9. Alternative Explanation
        alternative = self._evaluate_alternative(record, actual)

        # 10. Data Gap
        data_gap = self._evaluate_data_gap(record, actual)

        # 11. Corrective Action
        corrective_action = self._recommend_action(
            fact_quality, mechanism_accuracy, exposure_accuracy, calibration
        )

        return {
            "prediction_id": str(record.id),
            "target_asset": record.target_asset,
            "forecast_horizon": record.forecast_horizon,
            "expected_direction": expected_dir,
            "predicted_probability": predicted_prob,
            "actual_return": actual_return,
            "actual_direction": actual_direction,
            "outcome_correct": outcome_correct,
            "fact_quality": fact_quality,
            "event_stage_accuracy": stage_accuracy,
            "mechanism_accuracy": mechanism_accuracy,
            "exposure_accuracy": exposure_accuracy,
            "expectation_accuracy": expectation_accuracy,
            "timing_accuracy": timing_accuracy,
            "probability_calibration": calibration,
            "falsifier_quality": falsifier_quality,
            "alternative_explanation": alternative,
            "data_gap": data_gap,
            "corrective_action": corrective_action,
        }

    def build_backtest_summary(
        self,
        records: list[PredictionRecord],
    ) -> dict[str, Any]:
        """Aggregate postmortem across a backtest run."""
        postmortems = []
        for r in records:
            pm = self.build(r)
            postmortems.append(pm)

        if not postmortems:
            return {"note": "no records"}

        correct = sum(1 for p in postmortems if p["outcome_correct"])
        total = len(postmortems)
        mechanisms_ok = sum(1 for p in postmortems if p["mechanism_accuracy"]["score"] >= 0.5)
        exposures_ok = sum(1 for p in postmortems if p["exposure_accuracy"]["score"] >= 0.5)

        action_counts: dict[str, int] = {}
        for p in postmortems:
            action = p["corrective_action"]
            action_counts[action] = action_counts.get(action, 0) + 1

        return {
            "total": total,
            "direction_accuracy": round(correct / total, 4),
            "mechanism_accuracy_rate": round(mechanisms_ok / total, 4),
            "exposure_accuracy_rate": round(exposures_ok / total, 4),
            "action_recommendations": action_counts,
            "common_data_gaps": self._common_data_gaps(postmortems),
            "sample_postmortems": postmortems[:5],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _direction_correct(expected: str, actual: int | None) -> bool | None:
        if actual is None:
            return None
        if expected == "up":
            return actual == 1
        if expected == "down":
            return actual == 0
        return None

    def _evaluate_fact_quality(self, record: PredictionRecord, event: Event | None) -> dict[str, Any]:
        evidence = record.evidence_at_creation or []
        has_evidence = len(evidence) > 0
        grade = event.evidence_grade if event else "E0"
        return {
            "score": 0.7 if has_evidence else 0.3,
            "evidence_count": len(evidence),
            "evidence_grade": grade,
            "note": "Evidence existed at prediction time" if has_evidence else "Sparse evidence",
        }

    def _evaluate_stage(self, record: PredictionRecord, event: Event | None) -> dict[str, Any]:
        stage = event.event_stage if event else "unknown"
        confirmed = stage in ("confirmed", "executed", "priced")
        return {
            "score": 0.8 if confirmed else 0.4,
            "stage": stage,
            "note": f"Event stage was {stage}",
        }

    def _evaluate_mechanism(self, record: PredictionRecord, actual_return: float | None) -> dict[str, Any]:
        if actual_return is None:
            return {"score": 0.0, "note": "No outcome observed"}
        claim = record.claim or ""
        has_mechanism = len(claim) > 30
        direction_ok = (record.expected_direction == "up" and actual_return > 0) or (
            record.expected_direction == "down" and actual_return < 0
        )
        return {
            "score": 0.7 if (has_mechanism and direction_ok) else 0.3,
            "has_mechanism": has_mechanism,
            "direction_ok": direction_ok,
            "note": "Mechanism and direction aligned" if direction_ok else "Direction mismatch",
        }

    def _evaluate_exposure(self, record: PredictionRecord, actual_return: float | None) -> dict[str, Any]:
        if actual_return is None or not record.target_asset:
            return {"score": 0.0, "note": "No exposure outcome"}
        moved = abs(actual_return) > 0.005
        return {
            "score": 0.8 if moved else 0.4,
            "ticker": record.target_asset,
            "absolute_return": round(abs(actual_return), 4),
            "note": "Asset showed meaningful move" if moved else "Asset barely moved",
        }

    def _evaluate_expectation(self, record: PredictionRecord, benchmark_return: float | None) -> dict[str, Any]:
        if benchmark_return is None:
            return {"score": 0.0, "note": "No benchmark data"}
        actual = (record.actual_outcome or {}).get("actual_return")
        if actual is None:
            return {"score": 0.0, "note": "No actual return"}
        excess = actual - benchmark_return
        return {
            "score": 0.7 if abs(excess) > 0.01 else 0.4,
            "excess_return": round(excess, 4),
            "note": f"Excess return vs benchmark: {excess:.4f}",
        }

    def _evaluate_timing(self, record: PredictionRecord, actual: dict[str, Any]) -> dict[str, Any]:
        if not actual:
            return {"score": 0.0, "note": "No timing data"}
        return {
            "score": 0.6,
            "horizon_end": actual.get("horizon_end"),
            "note": "Outcome observed within declared horizon",
        }

    def _evaluate_calibration(self, predicted_prob: float, actual_direction: int | None) -> dict[str, Any]:
        if actual_direction is None:
            return {"score": 0.0, "note": "Outcome unresolved"}
        outcome = actual_direction
        error = abs(predicted_prob - outcome)
        return {
            "score": round(1 - error, 4),
            "predicted": predicted_prob,
            "outcome": outcome,
            "error": round(error, 4),
            "note": f"Predicted {predicted_prob:.2f}, outcome {outcome}",
        }

    def _evaluate_falsifier(self, record: PredictionRecord, actual: dict[str, Any]) -> dict[str, Any]:
        falsifiers = record.falsifiers or []
        return {
            "score": 0.7 if falsifiers else 0.3,
            "falsifier_count": len(falsifiers),
            "note": "Falsifiers documented" if falsifiers else "No falsifiers recorded",
        }

    def _evaluate_alternative(self, record: PredictionRecord, actual: dict[str, Any]) -> dict[str, Any]:
        snapshot = record.market_expectation_snapshot or {}
        has_alternatives = bool(snapshot.get("unresolved_uncertainties"))
        return {
            "score": 0.6 if has_alternatives else 0.3,
            "note": "Alternative scenarios considered" if has_alternatives else "Limited alternative review",
        }

    def _evaluate_data_gap(self, record: PredictionRecord, actual: dict[str, Any]) -> dict[str, Any]:
        gaps = []
        snapshot = record.market_expectation_snapshot or {}
        if not snapshot.get("market_snapshot", {}).get("prices"):
            gaps.append("market_prices")
        if not record.falsifiers:
            gaps.append("falsifiers")
        if not record.confirmation_events:
            gaps.append("confirmation_events")
        return {
            "score": 0.8 if not gaps else 0.4,
            "gaps": gaps,
            "note": "Key data available" if not gaps else f"Missing: {', '.join(gaps)}",
        }

    def _recommend_action(
        self,
        fact_quality: dict,
        mechanism_accuracy: dict,
        exposure_accuracy: dict,
        calibration: dict,
    ) -> str:
        if fact_quality["score"] < 0.5:
            return "Prompt Update Candidate"
        if mechanism_accuracy["score"] < 0.5:
            return "Edge Weight Update Candidate"
        if exposure_accuracy["score"] < 0.5:
            return "Data Source Priority Update Candidate"
        if calibration.get("score", 1.0) < 0.5:
            return "Probability Calibration Update Candidate"
        return "No Change"

    def _common_data_gaps(self, postmortems: list[dict]) -> list[str]:
        gap_counts: dict[str, int] = {}
        for p in postmortems:
            for gap in p["data_gap"].get("gaps", []):
                gap_counts[gap] = gap_counts.get(gap, 0) + 1
        sorted_gaps = sorted(gap_counts.items(), key=lambda x: x[1], reverse=True)
        return [g for g, _ in sorted_gaps[:3]]
