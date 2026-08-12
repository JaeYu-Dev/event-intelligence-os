from datetime import datetime
from typing import Any
from uuid import UUID
from sqlalchemy.orm import Session
from api.models import Thesis, ThesisScenario, ThesisCondition, Event

VALID_STATUSES = {"Watching", "Research Required", "Validating", "Paper Active", "Live Candidate", "Live Active", "Reduce", "Invalidated", "Resolved", "Archived"}
VALID_ACTIONS = {"WATCH", "RESEARCH", "PAPER_TRADE", "REDUCE", "HOLD"}


def get_or_create_thesis_for_event(db: Session, event_id: str) -> Thesis:
    thesis = db.query(Thesis).filter(Thesis.core_event_id == UUID(event_id)).first()
    if thesis:
        return thesis
    event = db.query(Event).filter(Event.id == UUID(event_id)).first()
    if not event:
        raise ValueError("Event not found")
    thesis = Thesis(
        title=event.title_ko or event.title or "Untitled thesis",
        status="Watching",
        core_event_id=UUID(event_id),
        action="WATCH",
    )
    db.add(thesis)
    db.commit()
    db.refresh(thesis)
    # Mirror event scenarios into thesis scenarios
    for s in event.conditions or []:
        db.add(ThesisScenario(
            thesis_id=thesis.id,
            name=s.get("name", "Base"),
            probability=s.get("probability", 0),
            conditions=s.get("conditions", []),
            price_range=s.get("price_range", ""),
        ))
    db.commit()
    return thesis


def reassess_thesis(db: Session, thesis_id: str, payload: dict[str, Any] | None = None) -> Thesis:
    thesis = db.query(Thesis).filter(Thesis.id == UUID(thesis_id)).first()
    if not thesis:
        raise ValueError("Thesis not found")
    payload = payload or {}
    new_status = payload.get("status")
    if new_status and new_status in VALID_STATUSES:
        thesis.status = new_status
    new_action = payload.get("action")
    if new_action and new_action in VALID_ACTIONS:
        thesis.action = new_action
    thesis.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(thesis)
    return thesis


def list_theses(db: Session) -> list[Thesis]:
    return db.query(Thesis).order_by(Thesis.updated_at.desc()).all()


def get_thesis_detail(db: Session, thesis_id: str) -> dict[str, Any]:
    thesis = db.query(Thesis).filter(Thesis.id == UUID(thesis_id)).first()
    if not thesis:
        raise ValueError("Thesis not found")
    scenarios = db.query(ThesisScenario).filter(ThesisScenario.thesis_id == thesis.id).all()
    conditions = db.query(ThesisCondition).filter(ThesisCondition.thesis_id == thesis.id).all()
    return {
        "thesis": thesis,
        "scenarios": scenarios,
        "conditions": conditions,
    }
