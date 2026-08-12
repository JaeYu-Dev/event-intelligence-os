from datetime import datetime
from typing import Any
from uuid import UUID
from sqlalchemy.orm import Session
from api.models import PaperTrade, Thesis
from api.schemas import orm_to_dict


def list_paper_trades(db: Session, thesis_id: str | None = None) -> list[dict[str, Any]]:
    q = db.query(PaperTrade)
    if thesis_id:
        q = q.filter(PaperTrade.thesis_id == UUID(thesis_id))
    rows = q.order_by(PaperTrade.executed_at.desc()).all()
    return [orm_to_dict(r) for r in rows]


def create_paper_trade(db: Session, payload: dict[str, Any]) -> PaperTrade:
    thesis_id = payload.get("thesis_id")
    if thesis_id:
        thesis = db.query(Thesis).filter(Thesis.id == UUID(thesis_id)).first()
        if not thesis:
            raise ValueError("Thesis not found")

    trade = PaperTrade(
        thesis_id=UUID(thesis_id) if thesis_id else None,
        ticker=payload["ticker"].upper().strip(),
        action=payload["action"],
        shares=float(payload["shares"]),
        price=float(payload["price"]),
        costs=float(payload.get("costs", 0)),
        executed_at=datetime.fromisoformat(payload["executed_at"]) if payload.get("executed_at") else datetime.utcnow(),
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade
