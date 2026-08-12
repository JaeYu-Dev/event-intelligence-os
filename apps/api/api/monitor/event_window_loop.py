"""
Event-Window Loop — runs every 1 minute when armed events exist.

Spec Section 13A:
  1-minute loop that ONLY activates during armed event windows.
  Does NOT run continuously.

  Dormant → Armed (T-60~30min) → Event Pending → Evidence Received
  → Fast Reassess (1min) → Hold/Trim/Hedge/Rotate/Exit
  → Cooldown → Deep Research or Dormant

Key constraint: NO LLM in the 1-min loop. Only structured rule evaluation.
"""

import logging
from datetime import datetime, timedelta

from api.database import SessionLocal
from api.models import Event, Thesis, ThesisScenario
from api.engine.rebalance import RebalanceEngine, RebalanceState

logger = logging.getLogger("eios.event_window")

# In-memory state — in production this would be Redis-backed
_ARMED_PACKS: dict[str, dict] = {}


def run_event_window_loop() -> dict:
    """
    Event-window loop — runs every 1 minute.
    Only active when armed events exist.
    """
    db = SessionLocal()
    result = {
        "run_at": datetime.utcnow().isoformat(),
        "armed_events": 0,
        "fast_reassesses": 0,
        "actions_recommended": 0,
        "cooldown_events": 0,
    }

    try:
        now = datetime.utcnow()

        # 1. Scan for events in the impact window (T0 to T+30m)
        impact_start = now - timedelta(minutes=30)
        impact_end = now + timedelta(minutes=5)

        events = db.query(Event).filter(
            Event.effective_date.isnot(None),
            Event.urgency.in_(["High", "Critical"]),
        ).all()

        armed = []
        for e in events:
            if e.effective_date:
                effective = e.effective_date.replace(tzinfo=None) if e.effective_date.tzinfo else e.effective_date
                # Event just happened or is imminent
                if impact_start <= effective <= impact_end:
                    armed.append(e)

        result["armed_events"] = len(armed)

        if not armed:
            return result

        # 2. For each armed event, run fast reassess
        rebalance = RebalanceEngine(db)

        for event in armed:
            eid = str(event.id)

            # Initialize pack if not already armed
            if eid not in _ARMED_PACKS:
                linked_theses = [
                    str(t.id) for t in db.query(Thesis)
                    .filter(Thesis.core_event_id == event.id)
                    .all()
                ]
                pack = rebalance.arm_for_event(event, linked_thesis_ids=linked_theses)
                _ARMED_PACKS[eid] = {"pack": pack, "armed_at": now}

            pack_data = _ARMED_PACKS[eid]
            pack = pack_data["pack"]

            # Transition state machine
            if pack.current_state == RebalanceState.ARMED:
                # Check if in impact window
                elapsed = (now - pack.scheduled_at).total_seconds()
                if elapsed >= 0:
                    rebalance.transition(pack)

            elif pack.current_state == RebalanceState.IMPACT_LOCK:
                # Fast reassess: check if we have price data
                prices = _get_recent_prices(db, event.related_tickers or [], 1)
                if prices:
                    rebalance.transition(pack, actual_data={"prices": prices})

            elif pack.current_state == RebalanceState.FACT_CLASSIFIED:
                elapsed = (now - pack.scheduled_at).total_seconds()
                if elapsed > 120:  # 2 minutes after impact
                    rebalance.transition(pack)
                    result["fast_reassesses"] += 1
                    # Count actions
                    for rec in pack.recommendations:
                        if rec.action.value != "MAINTAIN":
                            result["actions_recommended"] += 1

            elif pack.current_state == RebalanceState.COOLDOWN:
                cooldown_elapsed = (now - pack_data["armed_at"]).total_seconds()
                if cooldown_elapsed > 3600:  # 1 hour cooldown
                    rebalance.transition(pack, force_state=RebalanceState.NORMAL)
                    result["cooldown_events"] += 1

    except Exception as e:
        logger.exception("Event window loop failed")
        result["errors"] = [str(e)]
    finally:
        db.close()

    return result


def _get_recent_prices(db, tickers: list[str], minutes: int) -> dict[str, float]:
    """Get the most recent price changes for tickers — lightweight check."""
    from api.models import MarketPrice, MarketInstrument

    prices: dict[str, float] = {}
    if not tickers:
        return prices

    cutoff = datetime.utcnow() - timedelta(minutes=minutes + 5)

    for ticker in tickers[:5]:  # limit to 5
        instr = db.query(MarketInstrument).filter(
            MarketInstrument.symbol == ticker
        ).first()
        if not instr:
            continue

        latest = (
            db.query(MarketPrice)
            .filter(
                MarketPrice.instrument_id == instr.id,
                MarketPrice.timestamp >= cutoff,
            )
            .order_by(MarketPrice.timestamp.desc())
            .limit(2)
            .all()
        )

        if len(latest) >= 2 and latest[0].close and latest[1].close and latest[1].close > 0:
            change = (latest[0].close - latest[1].close) / latest[1].close
            prices[ticker] = round(change, 5)

    return prices
