from typing import Any
from sqlalchemy.orm import Session
from api.models import PortfolioPosition, Event
from api.schemas import PortfolioOut, orm_to_dict


def import_positions(db: Session, items: list[dict[str, Any]]) -> list[PortfolioPosition]:
    """Import or update portfolio positions."""
    out: list[PortfolioPosition] = []
    for item in items:
        ticker = item["ticker"].upper().strip()
        existing = db.query(PortfolioPosition).filter(PortfolioPosition.ticker == ticker).first()
        if existing:
            existing.name = item.get("name") or existing.name
            existing.shares = float(item.get("shares", existing.shares or 0))
            existing.avg_cost = float(item.get("avg_cost", existing.avg_cost or 0))
            existing.current_price = float(item.get("current_price", existing.current_price or 0)) if item.get("current_price") is not None else existing.current_price
            existing.scenario_bias = item.get("scenario_bias") or existing.scenario_bias
            existing.exposure_events = item.get("exposure_events") or existing.exposure_events or []
            out.append(existing)
        else:
            pos = PortfolioPosition(
                ticker=ticker,
                name=item.get("name") or ticker,
                shares=float(item.get("shares", 0)),
                avg_cost=float(item.get("avg_cost", 0)),
                current_price=float(item.get("current_price", 0)) if item.get("current_price") is not None else None,
                scenario_bias=item.get("scenario_bias") or "Base",
                exposure_events=item.get("exposure_events") or [],
            )
            db.add(pos)
            out.append(pos)
    db.commit()
    for p in out:
        db.refresh(p)
    return out


def compute_exposure(db: Session) -> dict[str, Any]:
    """Compute causal factor exposure from positions and related events."""
    positions = db.query(PortfolioPosition).all()
    events = {str(e.id): e for e in db.query(Event).all()}

    factor_totals: dict[str, dict[str, Any]] = {}
    position_factors: list[dict[str, Any]] = []

    for p in positions:
        pos_value = (p.current_price or 0) * p.shares
        pos_factors: list[str] = []
        for event_id in p.exposure_events or []:
            ev = events.get(str(event_id))
            if not ev:
                continue
            factor = ev.sector_ko or ev.sector or "Unknown"
            pos_factors.append(factor)
            factor_totals.setdefault(factor, {"value": 0.0, "events": set(), "tickers": set()})
            factor_totals[factor]["value"] += pos_value
            factor_totals[factor]["events"].add(str(ev.id))
            factor_totals[factor]["tickers"].add(p.ticker)

        position_factors.append({
            "ticker": p.ticker,
            "name": p.name,
            "value": pos_value,
            "factors": pos_factors,
            "scenario_bias": p.scenario_bias or "Base",
        })

    total_value = sum((p.current_price or 0) * p.shares for p in positions)
    factors = []
    for name, data in sorted(factor_totals.items(), key=lambda x: x[1]["value"], reverse=True):
        factors.append({
            "name": name,
            "value": data["value"],
            "pct": (data["value"] / total_value * 100) if total_value else 0,
            "event_count": len(data["events"]),
            "tickers": sorted(data["tickers"]),
        })

    return {
        "total_value": total_value,
        "positions": [PortfolioOut(**orm_to_dict(p)).model_dump() for p in positions],
        "factors": factors,
        "position_factors": position_factors,
    }
