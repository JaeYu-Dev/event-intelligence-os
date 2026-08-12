import hashlib
from datetime import datetime
from sqlalchemy.orm import Session
from api.database import SessionLocal
from api.models import Source, SourceDocument
from api.storage import raw_storage
from api.connectors.sec_edgar import SECEdgarConnector
from api.connectors.polymarket import PolymarketConnector
from api.connectors.yahoo import YahooPriceConnector
from api.connectors.base import SourceConnector


CONNECTORS: dict[str, SourceConnector] = {
    "sec_edgar": SECEdgarConnector(),
    "polymarket": PolymarketConnector(),
    "yahoo_finance": YahooPriceConnector(),
}


def get_or_create_source(db: Session, name: str, tier: str = "C") -> Source:
    source = db.query(Source).filter(Source.source_name == name).first()
    if not source:
        source = Source(source_name=name, source_tier=tier)
        db.add(source)
        db.commit()
        db.refresh(source)
    return source


def ingest_document(db: Session, source: Source, raw: object) -> SourceDocument | None:
    content_hash = hashlib.sha256(raw.raw_content).hexdigest()
    existing = db.query(SourceDocument).filter(
        SourceDocument.source_id == source.id,
        SourceDocument.content_hash == content_hash,
    ).first()
    if existing:
        return existing

    ref = raw_storage.put(raw.raw_content, key_prefix=f"sources/{source.source_name}")
    doc = SourceDocument(
        source_id=source.id,
        source_document_id=raw.source_document_id,
        content_hash=content_hash,
        raw_payload_ref=ref,
        published_at=raw.published_at,
        content_type=raw.content_type,
        title=raw.title,
        url=raw.url,
        metadata_json=raw.metadata,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


async def run_connector(source_name: str) -> dict:
    connector = CONNECTORS.get(source_name)
    if not connector:
        raise ValueError(f"Unknown connector: {source_name}")

    db = SessionLocal()
    try:
        source = get_or_create_source(db, source_name, connector.source_tier)
        raws = await connector.fetch_incremental(cursor=None)
        ingested = 0
        for raw in raws:
            doc = ingest_document(db, source, raw)
            if doc:
                ingested += 1
        return {"source": source_name, "fetched": len(raws), "ingested": ingested}
    finally:
        db.close()


async def ingest_prices(symbol: str, period: str = "1mo", interval: str = "1d") -> dict:
    from api.models import MarketInstrument, MarketPrice
    connector = CONNECTORS["yahoo_finance"]
    records = await connector.fetch_prices(symbol, period, interval)

    db = SessionLocal()
    try:
        instr = db.query(MarketInstrument).filter(MarketInstrument.symbol == symbol).first()
        if not instr:
            instr = MarketInstrument(symbol=symbol, name=symbol, asset_class="equity")
            db.add(instr)
            db.commit()
            db.refresh(instr)

        inserted = 0
        for r in records:
            existing = db.query(MarketPrice).filter(
                MarketPrice.instrument_id == instr.id,
                MarketPrice.timestamp == r["timestamp"],
            ).first()
            if existing:
                continue
            db.add(MarketPrice(
                instrument_id=instr.id,
                timestamp=r["timestamp"],
                open=r["open"],
                high=r["high"],
                low=r["low"],
                close=r["close"],
                volume=r["volume"],
                source="yahoo_finance",
            ))
            inserted += 1
        db.commit()
        return {"symbol": symbol, "records": len(records), "inserted": inserted}
    finally:
        db.close()
