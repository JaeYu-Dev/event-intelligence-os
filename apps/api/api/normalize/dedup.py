"""
Event Deduplication Service (Spec Section VII)

Deduplicates events based on entity/action/object/time proximity.
Uses multi-field similarity scoring with official identifier matching.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID
import hashlib

from sqlalchemy.orm import Session
from api.models import Event


@dataclass
class DedupScore:
    entity_similarity: float = 0.0
    action_similarity: float = 0.0
    object_similarity: float = 0.0
    time_proximity: float = 0.0
    jurisdiction_similarity: float = 0.0
    semantic_claim_similarity: float = 0.0
    document_reference_overlap: float = 0.0
    official_identifier_match: float = 0.0  # 0 or 1

    @property
    def total(self) -> float:
        return (
            self.entity_similarity * 0.25
            + self.action_similarity * 0.15
            + self.object_similarity * 0.15
            + self.time_proximity * 0.15
            + self.jurisdiction_similarity * 0.05
            + self.semantic_claim_similarity * 0.10
            + self.document_reference_overlap * 0.05
            + self.official_identifier_match * 0.10
        )


DUPLICATE_THRESHOLD = 0.75
HIGH_IMPACT_TYPES = {"merger_acquisition", "regulatory_approval", "regulatory_rejection",
                     "capital_raise", "bankruptcy", "war_escalation", "central_bank_decision",
                     "earnings_surprise", "management_change"}


class EventDedupService:
    """Deduplicates events: finds clusters of reports about the same event."""

    def __init__(self, db: Session):
        self.db = db

    def find_duplicates(self, event: Event, candidate_window_days: int = 3) -> list[tuple[Event, DedupScore]]:
        """
        Find duplicate events within a time window.
        Returns list of (candidate_event, score).
        """
        if not event.published_at:
            return []

        window_start = event.published_at - timedelta(days=candidate_window_days)
        window_end = event.published_at + timedelta(days=candidate_window_days)

        candidates = (
            self.db.query(Event)
            .filter(
                Event.id != event.id,
                Event.published_at >= window_start,
                Event.published_at <= window_end,
            )
            .all()
        )

        results: list[tuple[Event, DedupScore]] = []
        for candidate in candidates:
            score = self._compute_similarity(event, candidate)
            if score.total >= DUPLICATE_THRESHOLD:
                results.append((candidate, score))

        return sorted(results, key=lambda x: x[1].total, reverse=True)

    def _compute_similarity(self, a: Event, b: Event) -> DedupScore:
        """Compute multi-field deduplication similarity score."""
        s = DedupScore()

        # Entity similarity: actor match
        a_actor = (a.actor or "").lower()
        b_actor = (b.actor or "").lower()
        if a_actor and b_actor:
            s.entity_similarity = 1.0 if a_actor == b_actor else (
                0.7 if a_actor in b_actor or b_actor in a_actor else 0.0)

        # Action similarity
        a_action = (a.action or "").lower()
        b_action = (b.action or "").lower()
        s.action_similarity = 1.0 if a_action == b_action else (
            0.6 if _action_group(a_action) == _action_group(b_action) else 0.0)

        # Object similarity
        a_obj = (a.object or "").lower()
        b_obj = (b.object or "").lower()
        s.object_similarity = 1.0 if a_obj == b_obj else (
            0.5 if a_obj and b_obj and (a_obj in b_obj or b_obj in a_obj) else 0.0)

        # Time proximity: exponential decay
        if a.published_at and b.published_at:
            delta_hours = abs((a.published_at - b.published_at).total_seconds()) / 3600
            s.time_proximity = max(0.0, 1.0 - delta_hours / 48)  # decay over 48h

        # Jurisdiction: same sector proxy
        s.jurisdiction_similarity = 1.0 if (a.sector == b.sector) else 0.5

        # Official identifier match: event_key
        if a.event_key and b.event_key:
            s.official_identifier_match = 1.0 if a.event_key == b.event_key else 0.0

        # Semantic claim: title overlap
        a_title = (a.title_ko or a.title or "").lower()
        b_title = (b.title_ko or b.title or "").lower()
        if a_title and b_title:
            a_words = set(a_title.split())
            b_words = set(b_title.split())
            overlap = len(a_words & b_words)
            s.semantic_claim_similarity = min(1.0, overlap / max(len(a_words | b_words), 1))

        return s

    def should_auto_merge(self, event_a: Event, event_b: Event) -> bool:
        """Check if two events should be auto-merged. High-impact events get manual review."""
        score = self._compute_similarity(event_a, event_b)
        if score.total < DUPLICATE_THRESHOLD:
            return False

        # High-impact events: require manual verification
        if (event_a.event_type in HIGH_IMPACT_TYPES or event_b.event_type in HIGH_IMPACT_TYPES):
            return False

        return score.total >= 0.85


def _action_group(action: str) -> str:
    """Map similar actions into groups."""
    groups = {
        "announce": {"announced", "announces", "announcement", "announce", "reveals", "unveils"},
        "approve": {"approved", "approves", "approval", "grants", "granted"},
        "reject": {"rejected", "rejects", "denied", "denies", "rejection"},
        "file": {"filed", "files", "filing", "submitted", "submits", "submission"},
        "cut": {"cut", "cuts", "reduced", "reduces", "lowered", "lowers"},
        "raise": {"raised", "raises", "increased", "increases", "hiked", "hikes"},
        "report": {"reported", "reports", "released", "publishes", "published"},
        "acquire": {"acquired", "acquires", "acquisition", "bought", "purchased"},
        "sell": {"sold", "sells", "divested", "divests"},
    }
    for group_name, words in groups.items():
        if action in words:
            return group_name
    return action
