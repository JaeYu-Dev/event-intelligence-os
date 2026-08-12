"""
Discovery Engine: Budgeted Best-First Causal Expansion

Implements Section 29.4 of the spec. Instead of full BFS over all event relations,
we score each candidate path and only expand the top-k.

Core formula:
  ExpandScore = relevance * evidence_strength * mechanism_plausibility
              * novelty * expected_impact * under_reflection_likelihood
              * data_observability
              / (speculation_risk + redundancy + compute_cost)
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID
import heapq

from sqlalchemy.orm import Session

from api.models import Event, EventRelation, Entity, Relation, Thesis


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ExpandScore:
    """
    Normalized score components for a candidate expansion path.
    Each component is in [0, 1].
    """
    relevance: float = 0.5
    evidence_strength: float = 0.5
    mechanism_plausibility: float = 0.5
    novelty: float = 0.5
    expected_impact: float = 0.5
    under_reflection_likelihood: float = 0.5
    data_observability: float = 0.5
    speculation_risk: float = 0.5
    redundancy: float = 0.3
    compute_cost: float = 0.3

    @property
    def score(self) -> float:
        """Computes the ExpandScore as defined in the spec."""
        numerator = (
            self.relevance
            * self.evidence_strength
            * self.mechanism_plausibility
            * self.novelty
            * self.expected_impact
            * max(self.under_reflection_likelihood, 0.1)
            * max(self.data_observability, 0.1)
        )
        denominator = (
            self.speculation_risk + self.redundancy + self.compute_cost + 0.001
        )
        return numerator / denominator

    def to_dict(self) -> dict[str, float]:
        return {
            "relevance": round(self.relevance, 3),
            "evidence_strength": round(self.evidence_strength, 3),
            "mechanism_plausibility": round(self.mechanism_plausibility, 3),
            "novelty": round(self.novelty, 3),
            "expected_impact": round(self.expected_impact, 3),
            "under_reflection_likelihood": round(self.under_reflection_likelihood, 3),
            "data_observability": round(self.data_observability, 3),
            "speculation_risk": round(self.speculation_risk, 3),
            "redundancy": round(self.redundancy, 3),
            "compute_cost": round(self.compute_cost, 3),
            "score": round(self.score, 4),
        }


@dataclass
class ExpansionCandidate:
    """
    A node + path that could be expanded from the current frontier.
    """
    event_id: str
    event_title: str
    event_title_ko: str
    event_type: str
    sector: str
    sector_ko: str
    evidence_grade: str
    urgency: str
    related_tickers: list[str]
    mechanism_ko: str

    path_from_root: list[str] = field(default_factory=list)  # event id chain
    parent_id: Optional[str] = None
    edge_type: Optional[str] = None
    edge_label: Optional[str] = None
    edge_strength: float = 1.0

    expand_score: ExpandScore = field(default_factory=ExpandScore)

    @property
    def total_score(self) -> float:
        return self.expand_score.score


def compute_expand_score(
    event: Event,
    *,
    parent_event: Optional[Event] = None,
    existing_theses: set[str] | None = None,
    edge_strength: float = 1.0,
    evidence_grade: str = "E0",
    novelty_factor: float = 0.5,
    under_reflection: float = 0.5,
    expected_impact_factor: float = 0.5,
    data_observability_factor: float = 0.5,
    speculation_factor: float = 0.5,
    compute_cost_factor: float = 0.1,
) -> ExpandScore:
    """Compute ExpandScore for an event relative to its parent in the expansion tree."""

    # Relevance: how strongly connected to parent via shared tickers/sector
    relevance = 0.3
    if parent_event:
        ptickers = set(parent_event.related_tickers or [])
        etickers = set(event.related_tickers or [])
        shared = ptickers & etickers
        if shared:
            relevance = 0.5 + min(len(shared) * 0.15, 0.5)
        elif parent_event.sector and event.sector and parent_event.sector.lower() == event.sector.lower():
            relevance = 0.65
        else:
            relevance = 0.35

    # Evidence strength: from the existing evidence grade
    grade_map = {"E4": 1.0, "E3": 0.85, "E2": 0.65, "E1": 0.40, "E0": 0.20}
    evidence_strength = grade_map.get(evidence_grade, 0.3)

    # Mechanism plausibility: events with explicit mechanism get higher score
    mechanism_plausibility = 0.6
    if event.mechanism or event.mechanism_ko:
        mechanism_plausibility = 0.75
    if event.mechanism_ko and len(event.mechanism_ko) > 80:
        mechanism_plausibility = 0.85
    if event.counterevidence_ko and len(event.counterevidence_ko) > 0:
        mechanism_plausibility *= 0.85  # tempered by acknowledged counterevidence

    # Speculation risk inversely proportional to evidence and source reliability
    source_rel = event.source_reliability or 0.7
    speculation_risk = max(0.1, 1.0 - source_rel * 0.8)

    # Redundancy: penalize if parent's sector/tickers overlap too much
    redundancy = 0.1
    if parent_event:
        ptickers = set(parent_event.related_tickers or [])
        etickers = set(event.related_tickers or [])
        overlap = len(ptickers & etickers) / max(len(etickers | ptickers), 1)
        same_sector = bool(parent_event.sector and event.sector and parent_event.sector.lower() == event.sector.lower())
        redundancy = min(0.8, max(0.1, 0.3 * overlap + (0.2 if same_sector else 0)))

    # Thesis redundancy: if already has a thesis, higher redundancy
    if existing_theses and str(event.id) in existing_theses:
        redundancy = min(0.95, redundancy + 0.4)

    return ExpandScore(
        relevance=round(relevance, 3),
        evidence_strength=round(evidence_strength, 3),
        mechanism_plausibility=round(mechanism_plausibility, 3),
        novelty=round(novelty_factor, 3),
        expected_impact=round(expected_impact_factor, 3),
        under_reflection_likelihood=round(under_reflection, 3),
        data_observability=round(data_observability_factor, 3),
        speculation_risk=round(speculation_risk, 3),
        redundancy=round(redundancy, 3),
        compute_cost=round(compute_cost_factor, 3),
    )


# ---------------------------------------------------------------------------
# Discovery Engine
# ---------------------------------------------------------------------------

class DiscoveryEngine:
    """
    Budgeted Best-First Causal Expansion engine.

    Usage:
        engine = DiscoveryEngine(db)
        candidates = engine.expand(event_id="...", max_candidates=10, max_hops=3)
    """

    def __init__(self, db: Session):
        self.db = db

    def expand(
        self,
        event_id: str,
        *,
        max_candidates: int = 10,
        max_hops: int = 3,
        min_score: float = 0.3,
    ) -> list[dict[str, Any]]:
        """
        Expand from a root event.

        Returns a ranked list of expansion candidates as dictionaries.
        """
        root = self.db.query(Event).filter(Event.id == UUID(event_id)).first()
        if not root:
            return []

        # Track existing theses to avoid redundant expansion
        existing_theses = {
            str(t.core_event_id)
            for t in self.db.query(Thesis).all()
            if t.core_event_id
        }

        # Priority queue: (-score, counter, candidate)
        pq: list[tuple[float, int, ExpansionCandidate]] = []
        counter = 0
        visited: set[str] = {str(root.id)}
        result: list[dict[str, Any]] = []

        # Seed from direct relations
        relations = (
            self.db.query(EventRelation)
            .filter(
                (EventRelation.source_event_id == UUID(event_id))
                | (EventRelation.target_event_id == UUID(event_id))
            )
            .all()
        )

        related_event_ids: set[str] = set()
        for r in relations:
            if str(r.source_event_id) == event_id:
                related_event_ids.add(str(r.target_event_id))
            else:
                related_event_ids.add(str(r.source_event_id))

        related_events = (
            self.db.query(Event)
            .filter(Event.id.in_([UUID(eid) for eid in related_event_ids]))
            .all()
        )
        event_map = {str(e.id): e for e in related_events}

        # Also seed from sector/ticker overlap
        sector_events = (
            self.db.query(Event)
            .filter(
                Event.sector == root.sector,
                Event.id != root.id,
            )
            .limit(30)
            .all()
        )

        for ev in sector_events:
            if str(ev.id) not in visited and str(ev.id) not in related_event_ids:
                related_event_ids.add(str(ev.id))
                if str(ev.id) not in event_map:
                    event_map[str(ev.id)] = ev

        # Build initial candidates
        for rid, rel in [(str(r.target_event_id), r) for r in relations] + [
            (str(r.source_event_id), r) for r in relations
        ]:
            if rid == event_id or rid not in event_map:
                continue
            ev = event_map[rid]
            edge_strength = 1.0
            edge_type = "market"
            edge_label = ""
            if isinstance(rel, EventRelation):
                edge_strength = rel.strength or 1.0
                edge_type = rel.edge_type or "market"
                edge_label = rel.mechanism_ko or ""

            score = compute_expand_score(
                ev,
                parent_event=root,
                existing_theses=existing_theses,
                edge_strength=edge_strength,
                evidence_grade=ev.evidence_grade or "E1",
                expected_impact_factor=_estimate_impact(ev),
                under_reflection=0.5,
                speculation_factor=max(0.1, 1.0 - (ev.source_reliability or 0.7)),
            )

            visited.add(rid)
            counter += 1
            heapq.heappush(
                pq,
                (
                    -score.score,
                    counter,
                    ExpansionCandidate(
                        event_id=rid,
                        event_title=ev.title or "",
                        event_title_ko=ev.title_ko or ev.title or "",
                        event_type=ev.event_type or "",
                        sector=ev.sector or "",
                        sector_ko=ev.sector_ko or ev.sector or "",
                        evidence_grade=ev.evidence_grade or "E1",
                        urgency=ev.urgency or "Medium",
                        related_tickers=list(ev.related_tickers or []),
                        mechanism_ko=ev.mechanism_ko or "",
                        path_from_root=[event_id],
                        parent_id=event_id,
                        edge_type=edge_type,
                        edge_label=edge_label,
                        edge_strength=edge_strength,
                        expand_score=score,
                    ),
                ),
            )

        # Add ticker-based candidates (events with shared tickers but different sector)
        root_tickers = set(root.related_tickers or [])
        if root_tickers:
            ticker_events = _find_events_by_tickers(self.db, root_tickers, exclude=list(visited))
            for ev in ticker_events:
                if str(ev.id) in visited:
                    continue
                score = compute_expand_score(
                    ev,
                    parent_event=root,
                    existing_theses=existing_theses,
                    edge_strength=2.0,
                    evidence_grade=ev.evidence_grade or "E1",
                    novelty=0.6,
                    expected_impact_factor=_estimate_impact(ev),
                    under_reflection=0.55,
                )
                visited.add(str(ev.id))
                counter += 1
                heapq.heappush(
                    pq,
                    (
                        -score.score,
                        counter,
                        ExpansionCandidate(
                            event_id=str(ev.id),
                            event_title=ev.title or "",
                            event_title_ko=ev.title_ko or ev.title or "",
                            event_type=ev.event_type or "",
                            sector=ev.sector or "",
                            sector_ko=ev.sector_ko or ev.sector or "",
                            evidence_grade=ev.evidence_grade or "E1",
                            urgency=ev.urgency or "Medium",
                            related_tickers=list(ev.related_tickers or []),
                            mechanism_ko=ev.mechanism_ko or "",
                            path_from_root=[event_id],
                            parent_id=event_id,
                            edge_type="market",
                            edge_label=f"common tickers: {', '.join(sorted(root_tickers & set(ev.related_tickers or [])))}",
                            edge_strength=2.0,
                            expand_score=score,
                        ),
                    ),
                )

        # Extract top candidates
        while pq and len(result) < max_candidates:
            neg_score, _, candidate = heapq.heappop(pq)
            if -neg_score < min_score:
                continue
            result.append(_candidate_to_dict(candidate))

        return result

    def discover(
        self,
        *,
        max_root_events: int = 5,
        max_candidates_per_root: int = 5,
        min_evidence_grade: str = "E2",
    ) -> dict[str, Any]:
        """
        Run discovery across the top N root events (highest evidence grade, recent).

        Returns a dict with root_events and their expansion candidates.
        """
        grade_rank = {"E4": 5, "E3": 4, "E2": 3, "E1": 2, "E0": 1}
        min_rank = grade_rank.get(min_evidence_grade, 2)

        events = (
            self.db.query(Event)
            .order_by(Event.published_at.desc())
            .limit(100)
            .all()
        )

        # Filter and sort by evidence grade + urgency
        qualified = [
            e for e in events
            if grade_rank.get(e.evidence_grade or "E0", 0) >= min_rank
        ]
        urgency_rank = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
        qualified.sort(
            key=lambda e: (
                grade_rank.get(e.evidence_grade or "E0", 0),
                urgency_rank.get(e.urgency or "Low", 0),
            ),
            reverse=True,
        )

        discovery_map: dict[str, list[dict]] = {}
        for root in qualified[:max_root_events]:
            candidates = self.expand(
                str(root.id),
                max_candidates=max_candidates_per_root,
                min_score=0.25,
            )
            if candidates:
                discovery_map[str(root.id)] = candidates

        return {
            "roots": [
                {
                    "id": str(e.id),
                    "title_ko": e.title_ko or e.title or "",
                    "event_type": e.event_type,
                    "evidence_grade": e.evidence_grade,
                    "urgency": e.urgency,
                    "sector_ko": e.sector_ko or e.sector or "",
                }
                for e in qualified[:max_root_events]
            ],
            "discoveries": discovery_map,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _estimate_impact(event: Event) -> float:
    """Estimate expected impact based on magnitude and event type."""
    base = 0.5
    if event.magnitude_value:
        if event.magnitude_value > 1:
            base = min(0.9, 0.5 + abs(event.magnitude_value) * 0.05)
    high_impact_types = {"policy_announcement", "regulatory", "filing", "earnings"}
    if event.event_type in high_impact_types:
        base = min(0.95, base * 1.3)
    return base


def _find_events_by_tickers(db: Session, tickers: set[str], exclude: list[str]) -> list[Event]:
    """Find events that share at least one ticker."""
    from sqlalchemy import or_
    events = (
        db.query(Event)
        .filter(
            Event.id.notin_([UUID(x) for x in exclude if x]),
            or_(*[Event.related_tickers.any(t) for t in tickers]),
        )
        .order_by(Event.published_at.desc())
        .limit(20)
        .all()
    )
    return events


def _candidate_to_dict(c: ExpansionCandidate) -> dict[str, Any]:
    return {
        "event_id": c.event_id,
        "event_title": c.event_title,
        "event_title_ko": c.event_title_ko,
        "event_type": c.event_type,
        "sector": c.sector,
        "sector_ko": c.sector_ko,
        "evidence_grade": c.evidence_grade,
        "urgency": c.urgency,
        "related_tickers": c.related_tickers,
        "mechanism_ko": c.mechanism_ko,
        "path_from_root": c.path_from_root,
        "parent_id": c.parent_id,
        "edge_type": c.edge_type,
        "edge_label": c.edge_label,
        "edge_strength": c.edge_strength,
        "expand_score": c.expand_score.to_dict(),
        "total_score": round(c.total_score, 4),
    }
