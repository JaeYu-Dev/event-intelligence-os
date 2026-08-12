from typing import Any
from sqlalchemy.orm import Session
from api.models import EventRelation
from uuid import UUID


def _make_pair_key(a: str, b: str, edge_type: str) -> str:
    return f"{a}:{b}:{edge_type}"


def build_event_relations(events: list[dict[str, Any]], db: Session | None = None) -> list[dict[str, Any]]:
    """Build simple event-to-event edges from shared tickers and sector."""
    edges: list[dict[str, Any]] = []
    n = len(events)
    for i in range(n):
        a = events[i]
        a_tickers = set(a.get("related_tickers") or [])
        a_sector = a.get("sector") or ""
        a_sector_ko = a.get("sector_ko") or a_sector
        a_event_type = a.get("event_type") or ""
        for j in range(i + 1, n):
            b = events[j]
            b_tickers = set(b.get("related_tickers") or [])
            b_sector = b.get("sector") or ""
            shared = a_tickers & b_tickers
            same_sector = bool(a_sector and b_sector and a_sector.lower() == b_sector.lower())
            if not shared and not same_sector:
                continue

            strength = 1.0
            edge_type = "market"
            label = ""
            if shared:
                strength += min(len(shared), 4) * 1.5
                edge_type = "supply_chain" if a_event_type in ("supply_chain", "macro") or b.get("event_type") in ("supply_chain", "macro") else "market"
                label = f"공통 종목: {', '.join(sorted(shared))}"
            if same_sector:
                strength += 1.0
                edge_type = "regulatory" if a_event_type == "regulatory" or b.get("event_type") == "regulatory" else edge_type
                label = label + (" · " if label else "") + f"같은 섹터 ({a_sector_ko})"

            edges.append({
                "source": str(a["id"]),
                "target": str(b["id"]),
                "strength": min(strength, 8.0),
                "type": edge_type,
                "label": label,
                "label_ko": label,
            })

    if db is not None:
        _persist_edges(db, edges)

    return edges


def _persist_edges(db: Session, edges: list[dict[str, Any]]) -> None:
    """Upsert generated edges into event_relations."""
    if not edges:
        return
    # Build lookup of existing edges for the involved event ids
    event_ids = set()
    for e in edges:
        event_ids.add(e["source"])
        event_ids.add(e["target"])
    existing = db.query(EventRelation).filter(
        EventRelation.source_event_id.in_(event_ids) | EventRelation.target_event_id.in_(event_ids)
    ).all()
    existing_keys = {_make_pair_key(str(r.source_event_id), str(r.target_event_id), r.edge_type) for r in existing}

    new_rows = []
    for e in edges:
        key = _make_pair_key(e["source"], e["target"], e["type"])
        if key in existing_keys:
            continue
        new_rows.append(EventRelation(
            source_event_id=UUID(e["source"]),
            target_event_id=UUID(e["target"]),
            edge_type=e["type"],
            strength=e["strength"],
            mechanism=e.get("label"),
            mechanism_ko=e.get("label_ko"),
        ))
    if new_rows:
        db.bulk_save_objects(new_rows)
        db.commit()


def get_event_relations(db: Session) -> list[dict[str, Any]]:
    rows = db.query(EventRelation).order_by(EventRelation.strength.desc()).all()
    return [
        {
            "source": str(r.source_event_id),
            "target": str(r.target_event_id),
            "strength": r.strength,
            "type": r.edge_type,
            "label": r.mechanism,
            "label_ko": r.mechanism_ko,
        }
        for r in rows
    ]
