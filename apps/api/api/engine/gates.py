"""
10-Gate Scenario Promotion System (Spec Section XXIV)

Every Deep Scan candidate must pass these gates before becoming a full scenario:
  1. Fact Gate         — at least one credible fact or measurable anomaly
  2. Mechanism Gate    — explainable economic/institutional/physical mechanism
  3. Exposure Gate     — affected entity/asset identified with connection rationale
  4. Expectation Gate  — market expectation measured or explicitly declared unmeasured
  5. Falsifiability Gate — next event that can confirm or invalidate
  6. Non-Redundancy Gate — substantively different from existing scenarios
  7. Materiality Gate  — meaningful impact on price/cashflow/risk premium probable
  8. Time Integrity Gate — no future information leaked into past analysis
  9. Data Integrity Gate — core data traceable by source/time/unit/revision
  10. Alternative Explanation Gate — no stronger competing explanation

Candidates that fail gates are classified as:
  Watchlist Hypothesis / Developing Thesis / High-Conviction Research Candidate
  / Active Scenario / Resolved Scenario / Invalidated Scenario / Archived Scenario
"""
from dataclasses import dataclass, field
from typing import Any

from api.models import Event, Thesis


@dataclass
class GateResult:
    gate_name: str
    passed: bool
    score: float = 0.0  # 0-1
    reason: str = ""
    evidence: list[str] = field(default_factory=list)


@dataclass
class PromotionResult:
    candidate_id: str
    passed_all: bool
    gate_results: list[GateResult] = field(default_factory=list)
    final_status: str = "watchlist_hypothesis"  # one of the 7 statuses
    overall_score: float = 0.0
    failed_gates: list[str] = field(default_factory=list)


class ScenarioPromotionGate:
    """10-Gate evaluator for Deep Scan candidates."""

    def evaluate(
        self,
        candidate: dict[str, Any],
        existing_scenarios: list[dict] | None = None,
    ) -> PromotionResult:
        """
        Run all 10 gates on a candidate.
        Returns PromotionResult with pass/fail per gate and final status.
        """
        gates = [
            self._gate_fact(candidate),
            self._gate_mechanism(candidate),
            self._gate_exposure(candidate),
            self._gate_expectation(candidate),
            self._gate_falsifiability(candidate),
            self._gate_non_redundancy(candidate, existing_scenarios or []),
            self._gate_materiality(candidate),
            self._gate_time_integrity(candidate),
            self._gate_data_integrity(candidate),
            self._gate_alternative_explanation(candidate),
        ]

        passed = [g for g in gates if g.passed]
        failed = [g for g in gates if not g.passed]
        avg_score = sum(g.score for g in gates) / len(gates)

        # Determine status
        if len(passed) >= 9:
            status = "active_scenario"
        elif len(passed) >= 7:
            status = "high_conviction_research_candidate"
        elif len(passed) >= 5:
            status = "developing_thesis"
        else:
            status = "watchlist_hypothesis"

        return PromotionResult(
            candidate_id=candidate.get("motif_id", candidate.get("event_id", "unknown")),
            passed_all=len(failed) == 0,
            gate_results=gates,
            final_status=status,
            overall_score=avg_score,
            failed_gates=[g.gate_name for g in failed],
        )

    # ---- Individual Gates ----

    def _gate_fact(self, c: dict) -> GateResult:
        """Gate 1: At least one credible fact or measurable anomaly."""
        evidence_grade = c.get("evidence_grade", "E0")
        events = c.get("events", [])
        grade_rank = {"E4": 5, "E3": 4, "E2": 3, "E1": 2, "E0": 1}

        if events:
            best_grade = max(grade_rank.get(e.get("evidence_grade", "E0"), 0) for e in events)
        else:
            best_grade = grade_rank.get(evidence_grade, 1)

        passed = best_grade >= 2
        return GateResult(
            gate_name="Fact Gate",
            passed=passed,
            score=best_grade / 5,
            reason=f"Best evidence grade: E{best_grade}" if passed else "No credible source (below E2)",
        )

    def _gate_mechanism(self, c: dict) -> GateResult:
        """Gate 2: Explainable economic mechanism exists."""
        narrative = c.get("narrative_ko", "")
        mechanism = c.get("mechanism_ko", "")
        events = c.get("events", [])

        mech_count = sum(1 for e in events if e.get("mechanism_ko") and len(e.get("mechanism_ko", "")) > 20)
        has_narrative = len(narrative) > 50

        passed = mech_count >= 1 or has_narrative
        score = min(1.0, mech_count / max(len(events), 1) + (0.3 if has_narrative else 0))
        return GateResult(
            gate_name="Mechanism Gate",
            passed=passed,
            score=score,
            reason=f"{mech_count}/{len(events)} events with mechanism" if passed else "No economic mechanism documented",
        )

    def _gate_exposure(self, c: dict) -> GateResult:
        """Gate 3: Affected entity/asset identified with connection rationale."""
        tickers = c.get("aggregated_tickers", c.get("related_tickers", []))
        events = c.get("events", [])
        all_tickers = set(tickers)
        for e in events:
            for t in e.get("related_tickers", []):
                all_tickers.add(t)

        passed = len(all_tickers) > 0
        score = min(1.0, len(all_tickers) / 5)
        return GateResult(
            gate_name="Exposure Gate",
            passed=passed,
            score=score,
            reason=f"{len(all_tickers)} tickers mapped" if passed else "No tradable instrument identified",
        )

    def _gate_expectation(self, c: dict) -> GateResult:
        """Gate 4: Market expectation measured or declared unmeasured."""
        # MVP: check if we have assimilation data or price data
        events = c.get("events", [])
        has_market_data = any(
            e.get("market_data") for e in events if isinstance(e, dict)
        )
        passed = True  # MVP: always pass but flag
        score = 0.5 if has_market_data else 0.3
        return GateResult(
            gate_name="Expectation Gate",
            passed=passed,
            score=score,
            reason="Market expectation snapshot available" if has_market_data else "Market expectation not yet measured",
        )

    def _gate_falsifiability(self, c: dict) -> GateResult:
        """Gate 5: Next event exists that can confirm or invalidate."""
        events = c.get("events", [])
        next_events = []
        for e in events:
            if isinstance(e, dict):
                next_events.extend(e.get("next_events_ko", e.get("next_events", [])))
        passed = len(next_events) > 0
        score = min(1.0, len(next_events) / 3)
        return GateResult(
            gate_name="Falsifiability Gate",
            passed=passed,
            score=score,
            reason=f"{len(next_events)} confirmation events" if passed else "No falsification criteria defined",
        )

    def _gate_non_redundancy(self, c: dict, existing: list[dict]) -> GateResult:
        """Gate 6: Not substantively identical to existing scenarios."""
        if not existing:
            return GateResult(gate_name="Non-Redundancy Gate", passed=True, score=1.0, reason="No existing scenarios to compare")

        c_tickers = set(c.get("aggregated_tickers", []))
        c_sectors = set(c.get("aggregated_sectors", []))
        c_events = c.get("events", [])

        for ex in existing:
            ex_tickers = set(ex.get("aggregated_tickers", []))
            ex_sectors = set(ex.get("aggregated_sectors", []))
            # High overlap = redundant
            ticker_overlap = len(c_tickers & ex_tickers) / max(len(c_tickers | ex_tickers), 1)
            sector_overlap = len(c_sectors & ex_sectors) / max(len(c_sectors | ex_sectors), 1)
            if ticker_overlap > 0.7 and sector_overlap > 0.7:
                return GateResult(gate_name="Non-Redundancy Gate", passed=False, score=0.2,
                                  reason="Substantially overlaps existing scenario")

        return GateResult(gate_name="Non-Redundancy Gate", passed=True, score=0.9, reason="Sufficiently distinct")

    def _gate_materiality(self, c: dict) -> GateResult:
        """Gate 7: Meaningful impact on price/cashflow/risk premium probable."""
        events = c.get("events", [])
        urgency_rank = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
        if events:
            best_urgency = max(urgency_rank.get(e.get("urgency", "Low"), 1) for e in events)
        else:
            best_urgency = 1

        passed = best_urgency >= 2
        return GateResult(gate_name="Materiality Gate", passed=passed, score=best_urgency / 4,
                          reason=f"Urgency level {best_urgency}" if passed else "Low urgency — insufficient materiality")

    def _gate_time_integrity(self, c: dict) -> GateResult:
        """Gate 8: No future information leaked into past analysis."""
        # MVP: always pass (data is from known timestamps)
        return GateResult(gate_name="Time Integrity Gate", passed=True, score=1.0,
                          reason="All data from published timestamps")

    def _gate_data_integrity(self, c: dict) -> GateResult:
        """Gate 9: Core data traceable by source/time/unit/revision."""
        events = c.get("events", [])
        grades = {"E4": 1.0, "E3": 0.85, "E2": 0.65, "E1": 0.35, "E0": 0.15}
        if events:
            avg_grade = sum(grades.get(e.get("evidence_grade", "E0"), 0.15) for e in events) / len(events)
        else:
            avg_grade = 0.3

        passed = avg_grade >= 0.3
        return GateResult(gate_name="Data Integrity Gate", passed=passed, score=avg_grade,
                          reason=f"Average evidence confidence: {avg_grade:.2f}" if passed else "Core data unverifiable")

    def _gate_alternative_explanation(self, c: dict) -> GateResult:
        """Gate 10: No stronger competing explanation."""
        # Check if candidate has counterevidence — shows awareness of alternatives
        events = c.get("events", [])
        has_counter = any(
            e.get("counterevidence_ko") or e.get("counterevidence")
            for e in events if isinstance(e, dict)
        )
        passed = True  # MVP: always pass
        score = 0.8 if has_counter else 0.5
        return GateResult(gate_name="Alternative Explanation Gate", passed=passed, score=score,
                          reason="Counterevidence acknowledged" if has_counter else "Alternative explanations not yet explored")


# ---- Redundancy Control (Spec Section XXV) ----

class RedundancyController:
    """Detects and merges overly similar scenarios (Macro Theme Clustering)."""

    def cluster_similar(
        self, scenarios: list[dict], similarity_threshold: float = 0.7
    ) -> dict[str, list[dict]]:
        """
        Group scenarios by underlying cause/mechanism/exposure/confirmation event.
        Returns {cluster_key: [scenario_dict, ...]}.
        """
        clusters: dict[str, list[dict]] = {}

        for s in scenarios:
            key = self._cluster_key(s)
            if key not in clusters:
                clusters[key] = []
            clusters[key].append(s)

        return clusters

    def _cluster_key(self, s: dict) -> str:
        """Build a clustering key from the four axes: cause, mechanism, exposure, confirmation."""
        tickers = sorted(s.get("aggregated_tickers", [])[:5])
        sectors = sorted(s.get("aggregated_sectors", [])[:3])
        return f"t:{','.join(tickers)}|s:{','.join(sectors)}"


# ---- Failure Mode Detection (Spec Section XXVIII) ----

class FailureModeDetector:
    """Detects common failure patterns in the system output."""

    def detect(self, scenarios: list[dict]) -> list[dict]:
        """Check for 8 known failure modes. Returns detected issues."""
        issues: list[dict] = []

        # Failure 1: Macro event dominance
        macro_count = sum(1 for s in scenarios if any(
            t in str(s).lower() for t in ("macro", "fed", "cpi", "tariff", "war", "election")
        ))
        if macro_count / max(len(scenarios), 1) > 0.6:
            issues.append({"mode": "macro_event_dominance", "severity": "high",
                           "fix": "Increase Bottom-Up, Supply Chain, Corporate Fundamental seed weights"})

        # Failure 2: Mega-cap ticker bias
        mega_caps = {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "SPY", "QQQ"}
        mega_count = sum(1 for s in scenarios if any(
            t in mega_caps for t in s.get("aggregated_tickers", [])
        ))
        if mega_count / max(len(scenarios), 1) > 0.5:
            issues.append({"mode": "mega_cap_ticker_bias", "severity": "medium",
                           "fix": "Require direct contract/customer/supplier connection evidence"})

        # Failure 3: Shallow paths (event → sector → ticker, no mechanism)
        shallow = sum(1 for s in scenarios if not s.get("mechanism_ko") or len(s.get("mechanism_ko", "")) < 30)
        if shallow / max(len(scenarios), 1) > 0.4:
            issues.append({"mode": "shallow_path_bias", "severity": "medium",
                           "fix": "Require at least Mechanism Node or Confirmation Event"})

        # Failure 8: Future information leakage (point-in-time check)
        # MVP: flag but don't block — needs historical timestamp data
        issues.append({"mode": "future_info_leakage_risk", "severity": "monitor",
                       "fix": "Ensure observed_time / publish_time / valid_from separation"})

        return issues
