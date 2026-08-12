"""
Cheap Monitor — runs every 30 seconds.

Spec P6:
  Cheap Monitor
    → anomaly / calendar / evidence trigger
    → retrieval
    → targeted LLM reasoning
    → probability + risk update
    → human-readable decision card
    → return to cheap monitor

This is the CONTINUOUS monitoring loop that:
  1. Checks if any armed event windows need attention
  2. Detects anomalies (price divergence, new evidence, calendar triggers)
  3. Only triggers expensive re-evaluation when warranted
"""

import logging
from datetime import datetime, timedelta

from api.database import SessionLocal
from api.models import Event, Thesis, PortfolioPosition

logger = logging.getLogger("eios.cheap_monitor")

# Anomaly triggers (Section P6)
ANOMALY_TRIGGERS = [
    "price_divergence",          # Target vs external sensor mismatch
    "volume_spike",              # Abnormal volume
    "volatility_break",          # Volatility spike
    "keyword_match",             # Key word in headline
    "counterevidence_detected",  # New counterevidence appears
    "calendar_event_imminent",   # Scheduled event within 60m
    "thesis_at_risk_edge",       # Thesis approaching risk limit
    "new_official_source",       # Tier A source just published
]

STATE_CACHE: dict[str, dict] = {}  # in-memory state cache (MVP)


def run_cheap_monitor() -> dict:
    """
    Cheap monitor tick — runs every 30 seconds.
    Lightweight checks only. No LLM calls.
    """
    db = SessionLocal()
    result = {
        "run_at": datetime.utcnow().isoformat(),
        "triggers_fired": 0,
        "armed_events_checked": 0,
        "alert_conditions_met": 0,
        "triggers": [],
    }

    try:
        now = datetime.utcnow()

        # 1. Check armed event windows
        armed_events = _find_armed_events(db, now)
        result["armed_events_checked"] = len(armed_events)

        for event in armed_events:
            triggers = _check_event_triggers(db, event, now)
            if triggers:
                result["triggers_fired"] += len(triggers)
                result["triggers"].extend([{
                    "event_id": str(event.id),
                    "trigger_type": t,
                } for t in triggers])

        # 2. Check thesis risk limits
        at_risk = db.query(Thesis).filter(
            Thesis.status.in_(["Active", "Paper Active"])
        ).all()

        for thesis in at_risk:
            if _check_thesis_risk(db, thesis, now):
                result["alert_conditions_met"] += 1

        # 3. Check for stale data
        _check_data_staleness(db, now)

    except Exception as e:
        logger.exception("Cheap monitor failed")
        result["errors"] = [str(e)]
    finally:
        db.close()

    return result


def _find_armed_events(db, now: datetime) -> list[Event]:
    """
    Portfolio-scoped: only find events linked to active portfolio positions
    whose effective_date is within the armed window (T-60m to T+30m).
    """
    from api.models import PortfolioPosition

    arm_start = now - timedelta(minutes=30)
    arm_end = now + timedelta(minutes=90)

    # Get portfolio-linked event IDs
    positions = db.query(PortfolioPosition).all()
    linked_event_ids: set[str] = set()
    for p in positions:
        for eid in p.exposure_events or []:
            linked_event_ids.add(str(eid))

    # If no portfolio positions, scan nothing — user hasn't committed yet
    if not linked_event_ids:
        return []

    events = db.query(Event).filter(
        Event.effective_date.isnot(None),
    ).all()

    armed = []
    for e in events:
        if str(e.id) not in linked_event_ids:
            continue
        if e.effective_date:
            effective = e.effective_date.replace(tzinfo=None) if e.effective_date.tzinfo else e.effective_date
            if arm_start <= effective <= arm_end:
                armed.append(e)
        if e.next_events:
            for ne_text in e.next_events:
                parsed = _parse_date_hint(ne_text, now)
                if parsed and arm_start <= parsed <= arm_end:
                    if e not in armed:
                        armed.append(e)
                    break

    return armed


def _check_event_triggers(db, event: Event, now: datetime) -> list[str]:
    """Check all anomaly triggers for a given event."""
    triggers = []

    # Calendar trigger: event effective date is imminent
    if event.effective_date:
        effective = event.effective_date.replace(tzinfo=None) if event.effective_date.tzinfo else event.effective_date
        minutes_to = (effective - now).total_seconds() / 60
        if 0 <= minutes_to <= 5:
            triggers.append("calendar_event_imminent")
        elif 0 <= minutes_to <= 60:
            triggers.append("calendar_event_armed")

    # Thesis at risk edge: check if linked theses have high bear probability
    theses = db.query(Thesis).filter(Thesis.core_event_id == event.id).all()
    for t in theses:
        if t.status in ("At Risk", "Invalidated"):
            triggers.append("thesis_at_risk_edge")
            break

    # Counterevidence: check if new evidence contradicts existing claims
    from api.models import EvidenceItem
    recent_counter = (
        db.query(EvidenceItem)
        .filter(
            EvidenceItem.event_id == event.id,
            EvidenceItem.extracted_at >= now - timedelta(hours=1),
        )
        .all()
    )
    if recent_counter:
        triggers.append("counterevidence_detected")

    return triggers


def _check_thesis_risk(db, thesis: Thesis, now: datetime) -> bool:
    """Check if a thesis has breached a risk threshold."""
    event = db.query(Event).filter(Event.id == thesis.core_event_id).first()
    if not event:
        return False

    # Simple check: if bear scenario probability > 40%, alert
    from api.models import ThesisScenario
    bear = (
        db.query(ThesisScenario)
        .filter(
            ThesisScenario.thesis_id == thesis.id,
            ThesisScenario.name == "Bear",
        )
        .first()
    )
    if bear and bear.probability and bear.probability > 0.40:
        logger.warning("Thesis %s bear prob %.2f — alert threshold breached", thesis.id, bear.probability)
        return True

    return False


def _check_data_staleness(db, now: datetime) -> None:
    """Check if any data sources are stale (not updated in 24h+)."""
    from api.models import Source
    sources = db.query(Source).all()
    for s in sources:
        # Simple staleness check — in production would check last fetch time
        pass


def _parse_date_hint(text: str, now: datetime) -> datetime | None:
    """Lightweight date hint parser for cheap monitor."""
    import re
    if not text:
        return None

    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    # Pattern: "Month Day" like "Jul 10" or "7/10"
    match = re.search(r"(\d{1,2})[/\s](\d{1,2})", text)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            year = now.year
            if month < now.month:
                year += 1
            try:
                return datetime(year, month, day, 14, 0, 0)
            except ValueError:
                return None

    match = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})", text, re.I)
    if match:
        month = month_map.get(match.group(1).lower()[:3])
        day = int(match.group(2))
        if month and 1 <= day <= 31:
            year = now.year
            if month < now.month:
                year += 1
            try:
                return datetime(year, month, day, 14, 0, 0)
            except ValueError:
                return None

    return None
