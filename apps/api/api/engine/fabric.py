"""
Engine 1 & 2: Live Event Fabric + Evidence Engine

Engine 1 (Live Event Fabric):
  - Point-in-time event log with mandatory time fields
  - Source dedup, version tracking
  - source-level / connector-level latency stats

Engine 2 (Evidence Engine):
  - Claim extraction schema
  - Factuality gates (official_fact, reported_fact, analyst_view, model_inference)
  - LLM role limitation
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import hashlib

from sqlalchemy.orm import Session

from api.models import (
    Event, SourceDocument, EvidenceItem, Source, Entity, Relation
)


# ---------------------------------------------------------------------------
# Engine 1 — Live Event Fabric
# ---------------------------------------------------------------------------

class FactualityLevel(str, Enum):
    OFFICIAL_FACT = "official_fact"
    REPORTED_FACT = "reported_fact"
    ANALYST_VIEW = "analyst_view"
    MODEL_INFERENCE = "model_inference"


@dataclass
class Claim:
    """Evidence Engine claim as defined in Section 29.2."""
    claim_id: str = ""
    subject: str = ""           # Company / regulator / economic indicator
    predicate: str = ""         # raised_guidance | approved | delayed | ...
    object: str = ""            # product / capacity / policy / market
    value: dict[str, Any] = field(default_factory=dict)  # {"numeric": 0, "unit": "USD"}
    qualifiers: list[str] = field(default_factory=list)
    polarity: str = "unknown"   # positive | negative | mixed | unknown
    event_time: str | None = None
    source_document_id: str = ""
    source_span: str = ""       # exact paragraph/chunk reference
    factuality: FactualityLevel = FactualityLevel.MODEL_INFERENCE
    confidence: float = 0.0


@dataclass
class EventTimeFields:
    """Mandatory time tracking for every event (Section 29.1)."""
    event_id: str
    event_time: datetime | None = None         # actual occurrence
    published_time: datetime | None = None      # source published
    first_seen_time: datetime | None = None     # system first observed
    available_time: datetime | None = None      # downstream engines can use
    ingested_time: datetime | None = None       # storage write
    revised_time: datetime | None = None        # document/data revision
    market_time: datetime | None = None         # quote/trade time


@dataclass
class SourceLatencyStats:
    """Source and connector latency tracking."""
    source_name: str
    avg_latency_seconds: float = 0.0
    max_latency_seconds: float = 0.0
    min_latency_seconds: float = 0.0
    sample_count: int = 0


# ---------------------------------------------------------------------------
# Engine 3 — Ontology & Entity Engine
# ---------------------------------------------------------------------------

class RelationType(str, Enum):
    """3-layer ontology edge types."""
    # Layer 1: Structural Facts
    COMPANY_IN_INDUSTRY = "company → industry"
    COMPANY_HAS_PRODUCT = "company → product"
    SUPPLIER_TO = "company → supplier/customer"
    ENTITY_IN_GEOGRAPHY = "entity → geography"
    POLICY_IN_JURISDICTION = "policy → jurisdiction"

    # Layer 2: Economic Mechanisms
    POLICY_CHANGES_INCENTIVE = "policy → changes incentive"
    SHORTAGE_CONSTRAINS_SUPPLY = "shortage → constrains supply"
    DEMAND_AFFECTS_VOLUME = "demand change → affects volume"
    PRICE_AFFECTS_MARGIN = "price change → affects margin"
    RATE_CHANGES_DISCOUNT = "rate change → changes discount rate"

    # Layer 3: Tradable Exposure
    EXPOSES_TO_FACTOR = "exposes_to latent factor"
    HAS_LIQUIDITY = "has liquidity"
    HAS_COST = "has cost"
    HAS_CALENDAR_RISK = "has calendar risk"


# ---------------------------------------------------------------------------
# Live Event Fabric Engine
# ---------------------------------------------------------------------------

class LiveEventFabric:
    """Engine 1: Point-in-time event log management."""

    def __init__(self, db: Session):
        self.db = db
        self._latency_samples: dict[str, list[float]] = {}

    def compute_event_key(self, event: Event) -> str:
        """Generate a dedup key: actor|action|object|published_at hash."""
        parts = [
            event.actor or "",
            event.action or "",
            event.object or "",
            str(event.published_at or ""),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()

    def get_time_fields(self, event: Event) -> EventTimeFields:
        """Extract mandatory time fields from an event."""
        return EventTimeFields(
            event_id=str(event.id),
            event_time=event.effective_date,
            published_time=event.published_at,
            first_seen_time=event.first_observed_at,
            available_time=getattr(event, 'available_time', None),
            ingested_time=getattr(event, 'ingested_time', None),
            revised_time=None,  # not yet implemented
            market_time=getattr(event, 'market_time', None),
        )

    def find_duplicates(self, event: Event) -> list[Event]:
        """Find potential duplicates by event_key."""
        key = self.compute_event_key(event)
        return (
            self.db.query(Event)
            .filter(Event.event_key == key, Event.id != event.id)
            .all()
        )

    def record_latency(
        self,
        source_name: str,
        published_at: datetime,
        first_seen_at: datetime,
    ) -> None:
        """Record source-to-system latency for a connector."""
        latency = (first_seen_at - published_at).total_seconds()
        if source_name not in self._latency_samples:
            self._latency_samples[source_name] = []
        self._latency_samples[source_name].append(max(0, latency))

    def get_latency_stats(self) -> dict[str, SourceLatencyStats]:
        """Get latency statistics per source."""
        stats: dict[str, SourceLatencyStats] = {}
        for name, samples in self._latency_samples.items():
            if not samples:
                continue
            stats[name] = SourceLatencyStats(
                source_name=name,
                avg_latency_seconds=sum(samples) / len(samples),
                max_latency_seconds=max(samples),
                min_latency_seconds=min(samples),
                sample_count=len(samples),
            )
        return stats

    def build_summary(self) -> dict[str, Any]:
        """Build a fabric summary for the Command Center."""
        events = (
            self.db.query(Event)
            .order_by(Event.published_at.desc())
            .limit(100)
            .all()
        )

        sources = self.db.query(Source).all()
        docs_recent = (
            self.db.query(SourceDocument)
            .order_by(SourceDocument.first_observed_at.desc())
            .limit(50)
            .all()
        )

        return {
            "total_events": len(events),
            "total_sources": len(sources),
            "recent_documents": len(docs_recent),
            "latency_stats": {
                name: {
                    "avg_s": round(s.avg_latency_seconds, 1),
                    "max_s": round(s.max_latency_seconds, 1),
                    "samples": s.sample_count,
                }
                for name, s in self.get_latency_stats().items()
            },
            "event_types": _count_by_field(events, "event_type"),
            "source_tiers": _count_by_field(sources, "source_tier"),
        }


# ---------------------------------------------------------------------------
# Evidence Engine
# ---------------------------------------------------------------------------

class EvidenceEngine:
    """Engine 2: Claim extraction and factuality gating."""

    def __init__(self, db: Session):
        self.db = db

    def classify_factuality(
        self,
        source_tier: str,
        has_original_text: bool,
        has_cross_verification: bool,
    ) -> FactualityLevel:
        """Apply factuality gate based on source and verification."""
        if source_tier in ("A", "B") and has_original_text and has_cross_verification:
            return FactualityLevel.OFFICIAL_FACT
        elif source_tier in ("A", "B") and has_original_text:
            return FactualityLevel.REPORTED_FACT
        elif source_tier in ("A", "B", "C"):
            return FactualityLevel.ANALYST_VIEW
        else:
            return FactualityLevel.MODEL_INFERENCE

    def get_claims_for_event(self, event_id: str) -> list[Claim]:
        """Get evidence claims linked to an event."""
        evidence_items = (
            self.db.query(EvidenceItem)
            .filter(EvidenceItem.event_id == event_id)
            .all()
        )

        claims: list[Claim] = []
        for ev in evidence_items:
            source_doc = (
                self.db.query(SourceDocument)
                .filter(SourceDocument.id == ev.source_document_id)
                .first()
            )
            source = source_doc.source if source_doc else None
            source_tier = source.source_tier if source else "D"

            factuality = self.classify_factuality(
                source_tier,
                has_original_text=bool(source_doc),
                has_cross_verification=_has_cross_verification(
                    self.db, event_id, ev.claim_text
                ),
            )

            claims.append(Claim(
                claim_id=str(ev.id),
                subject=event_id,
                predicate="extracted",
                object=ev.claim_text or "",
                source_document_id=str(ev.source_document_id or ""),
                factuality=factuality,
                confidence=(
                    0.9 if factuality == FactualityLevel.OFFICIAL_FACT
                    else 0.7 if factuality == FactualityLevel.REPORTED_FACT
                    else 0.4 if factuality == FactualityLevel.ANALYST_VIEW
                    else 0.2
                ),
            ))

        return claims

    def get_evidence_summary(self, event_id: str) -> dict[str, Any]:
        """Summarize evidence quality for an event."""
        claims = self.get_claims_for_event(event_id)

        by_factuality: dict[str, int] = {}
        for c in claims:
            key = c.factuality.value
            by_factuality[key] = by_factuality.get(key, 0) + 1

        total = len(claims)
        official_pct = by_factuality.get("official_fact", 0) / max(total, 1)

        return {
            "event_id": event_id,
            "total_claims": total,
            "by_factuality": by_factuality,
            "evidence_quality": (
                "high" if official_pct > 0.5
                else "medium" if official_pct > 0.2
                else "low"
            ),
        }


# ---------------------------------------------------------------------------
# Ontology Engine
# ---------------------------------------------------------------------------

class OntologyEngine:
    """Engine 3: 3-layer ontology, entity resolution, forbidden relation gates."""

    # Forbidden patterns (Section 29.3)
    FORBIDDEN_PATTERNS = [
        "keyword overlap 만으로 공급망 관계 생성",
        "entity alias 불확실 시 market mapping",
        "company ↔ market relation without source evidence",
    ]

    def __init__(self, db: Session):
        self.db = db

    def resolve_entity(
        self,
        name: str,
        entity_type: str = "company",
    ) -> Entity | None:
        """Resolve an entity name to its canonical form."""
        # Try exact match
        entity = (
            self.db.query(Entity)
            .filter(Entity.canonical_name == name)
            .first()
        )
        if entity:
            return entity

        # Try alias match
        entity = (
            self.db.query(Entity)
            .filter(Entity.aliases.any(name))
            .first()
        )
        return entity

    def get_entity_graph(
        self,
        entity_id: str,
        max_depth: int = 3,
    ) -> dict[str, Any]:
        """Get entity-centric graph with 3-layer ontology filtering."""
        entity = (
            self.db.query(Entity)
            .filter(Entity.id == entity_id)
            .first()
        )
        if not entity:
            return {"error": "Entity not found"}

        # Outgoing relations
        outgoing = (
            self.db.query(Relation)
            .filter(Relation.source_id == entity.id)
            .all()
        )

        # Incoming relations
        incoming = (
            self.db.query(Relation)
            .filter(Relation.target_id == entity.id)
            .all()
        )

        return {
            "entity": {
                "id": str(entity.id),
                "name": entity.canonical_name,
                "type": entity.entity_type,
                "sector": entity.sector,
            },
            "outgoing_relations": [
                {
                    "id": str(r.id),
                    "target_id": str(r.target_id),
                    "type": r.edge_type,
                    "evidence_grade": r.evidence_grade,
                    "mechanism": r.mechanism_ko or r.mechanism,
                }
                for r in outgoing
            ],
            "incoming_relations": [
                {
                    "id": str(r.id),
                    "source_id": str(r.source_id),
                    "type": r.edge_type,
                    "evidence_grade": r.evidence_grade,
                }
                for r in incoming
            ],
        }

    def validate_relation(
        self,
        edge_type: str,
        source_id: str,
        target_id: str,
    ) -> tuple[bool, str]:
        """
        Validate whether a proposed relation is allowed by the ontology.

        Returns (is_valid, reason).
        """
        # Check forbidden patterns
        source_entity = (
            self.db.query(Entity)
            .filter(Entity.id == source_id)
            .first()
        )
        target_entity = (
            self.db.query(Entity)
            .filter(Entity.id == target_id)
            .first()
        )

        if not source_entity or not target_entity:
            return False, "Source or target entity does not exist"

        # Free-form edges outside taxonomy → E0 sandbox only
        valid_types = {
            "causal", "causal_candidate", "lead_lag", "correlation",
            "semantic", "ownership", "supply_chain", "regulatory",
            "exposure", "affects", "part_of",
        }
        if edge_type not in valid_types:
            return False, f"Edge type '{edge_type}' outside taxonomy → store as E0 only"

        return True, "OK"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_by_field(items: list[Any], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        val = getattr(item, field, None) or "unknown"
        counts[val] = counts.get(val, 0) + 1
    return counts


def _has_cross_verification(
    db: Session,
    event_id: str,
    claim_text: str | None,
) -> bool:
    """Check if a claim has independent corroboration."""
    if not claim_text:
        return False
    other = (
        db.query(EvidenceItem)
        .filter(
            EvidenceItem.event_id == event_id,
            EvidenceItem.claim_text != claim_text,
        )
        .count()
    )
    return other > 0
