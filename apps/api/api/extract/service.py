from datetime import datetime
import hashlib
from sqlalchemy.orm import Session
from api.database import SessionLocal
from api.models import SourceDocument, Event, EvidenceItem, Entity, Relation
from api.llm.extractor import extractor, EventExtraction
from api.storage import raw_storage
from api.connectors.sec_edgar import SECEdgarConnector
from api.connectors.polymarket import PolymarketConnector


CONNECTORS = {
    "sec_edgar": SECEdgarConnector(),
    "polymarket": PolymarketConnector(),
}


def build_event_key(extraction: EventExtraction, published_at: datetime | None) -> str:
    parts = [
        extraction.actor or "",
        extraction.action or "",
        extraction.object or "",
        str(published_at or ""),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


async def extract_from_document(doc_id: str) -> Event | None:
    db = SessionLocal()
    try:
        doc = db.query(SourceDocument).filter(SourceDocument.id == doc_id).first()
        if not doc:
            return None

        source = doc.source
        connector = CONNECTORS.get(source.source_name)
        if not connector:
            return None

        raw = type("Raw", (), {
            "source_document_id": doc.source_document_id,
            "published_at": doc.published_at,
            "title": doc.title,
            "url": doc.url,
            "content_type": doc.content_type,
            "raw_content": raw_storage.get(doc.raw_payload_ref),
            "metadata": doc.metadata_json,
        })()
        normalized = connector.normalize(raw)

        extraction = await extractor.extract(normalized)
        if not extraction:
            return None

        event_key = build_event_key(extraction, normalized.published_at)
        existing = db.query(Event).filter(Event.event_key == event_key).first()
        if existing:
            return existing

        event = Event(
            event_key=event_key,
            event_type=extraction.event_type,
            actor=extraction.actor,
            actor_ko=extraction.actor_ko,
            action=extraction.action,
            object=extraction.object,
            magnitude_value=extraction.magnitude_value,
            magnitude_unit=extraction.magnitude_unit,
            effective_date=datetime.fromisoformat(extraction.effective_date) if extraction.effective_date else None,
            published_at=normalized.published_at,
            source_reliability=0.95 if source.source_tier == "A" else 0.85,
            source_type=source.source_name,
            evidence_grade=extraction.evidence_grade,
            urgency=extraction.urgency,
            status="Watching",
            title=extraction.title,
            title_ko=extraction.title_ko,
            sector=extraction.sector,
            sector_ko=extraction.sector_ko,
            mechanism=extraction.mechanism,
            mechanism_ko=extraction.mechanism_ko,
            related_tickers=extraction.related_tickers,
            conditions=[s.model_dump() for s in extraction.scenarios],
            counterevidence=extraction.counterevidence,
            counterevidence_ko=extraction.counterevidence_ko,
            next_events=extraction.next_events,
            next_events_ko=extraction.next_events_ko,
            source_document_ids=[doc.id],
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        ev = EvidenceItem(
            event_id=event.id,
            source_document_id=doc.id,
            claim_text=extraction.mechanism,
            claim_text_ko=extraction.mechanism_ko,
            evidence_grade=extraction.evidence_grade,
        )
        db.add(ev)

        actor_entity = _get_or_create_entity(db, extraction.actor, "organization", extraction.sector, extraction.actor_ko)
        object_entity = _get_or_create_entity(db, extraction.object, "theme", extraction.sector)
        ticker_entities = []
        for ticker in extraction.related_tickers or []:
            ent = _get_or_create_entity(db, ticker, "security", extraction.sector)
            if ent:
                ticker_entities.append(ent)
                if actor_entity:
                    _link_entities(db, actor_entity, ent, "exposure", extraction.mechanism)
                if object_entity:
                    _link_entities(db, object_entity, ent, "affects", extraction.mechanism)
        db.commit()
        return event
    finally:
        db.close()



def _get_or_create_entity(db: Session, name: str | None, entity_type: str, sector: str | None = None, alias: str | None = None) -> Entity | None:
    if not name:
        return None
    entity = db.query(Entity).filter(Entity.canonical_name == name).first()
    if not entity:
        aliases = [alias] if alias else []
        entity = Entity(
            entity_type=entity_type,
            canonical_name=name,
            aliases=aliases,
            sector=sector,
        )
        db.add(entity)
        db.flush()
    return entity


def _link_entities(db: Session, source: Entity | None, target: Entity | None, edge_type: str, mechanism: str | None = None) -> None:
    if not source or not target or source.id == target.id:
        return
    existing = db.query(Relation).filter(
        Relation.source_id == source.id,
        Relation.target_id == target.id,
        Relation.edge_type == edge_type,
    ).first()
    if existing:
        return
    db.add(Relation(
        source_id=source.id,
        target_id=target.id,
        edge_type=edge_type,
        mechanism=mechanism,
        evidence_grade="E2",
    ))


async def extract_all_pending(limit: int = 10) -> dict:
    db = SessionLocal()
    try:
        docs = db.query(SourceDocument).order_by(SourceDocument.first_observed_at.desc()).limit(limit).all()
        created = 0
        for doc in docs:
            event = await extract_from_document(str(doc.id))
            if event:
                created += 1
        return {"processed": len(docs), "events_created": created}
    finally:
        db.close()
