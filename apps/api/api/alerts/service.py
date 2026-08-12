from datetime import datetime, timedelta
from typing import Any
from sqlalchemy.orm import Session
from api.models import Event


def generate_alerts(db: Session, lookahead_days: int = 7) -> list[dict[str, Any]]:
    """Generate alerts for events with upcoming effective dates or next_events."""
    now = datetime.utcnow().replace(tzinfo=None)
    horizon = now + timedelta(days=lookahead_days)
    events = db.query(Event).order_by(Event.published_at.desc()).limit(200).all()
    alerts: list[dict[str, Any]] = []

    for e in events:
        conditions = e.conditions or []
        top_scenario = None
        if conditions:
            sorted_scenarios = sorted(
                conditions, key=lambda s: s.get("probability", 0), reverse=True
            )
            top_scenario = sorted_scenarios[0]

        if e.effective_date:
            effective_naive = e.effective_date.replace(tzinfo=None) if e.effective_date.tzinfo else e.effective_date
            if now <= effective_naive <= horizon:
                alerts.append(_make_alert(e, top_scenario, "effective_date"))

        next_events_ko = e.next_events_ko or []
        if next_events_ko:
            alerts.append(_make_alert(e, top_scenario, "next_event", next_events_ko[0]))

    urgency_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    grade_rank = {"E4": 0, "E3": 1, "E2": 2, "E1": 3, "E0": 4}
    alerts.sort(key=lambda a: (urgency_rank.get(a["urgency"], 99), grade_rank.get(a["evidence_grade"], 99)))
    return alerts


def _make_alert(event: Event, scenario: dict | None, trigger: str, what_to_watch: str | None = None) -> dict[str, Any]:
    scenario_name = scenario.get("name", "Base") if scenario else "Base"
    price_range = scenario.get("price_range", "가격 영역 확인") if scenario else "가격 영역 확인"
    deadline = event.effective_date.isoformat() if event.effective_date else "미정"
    return {
        "id": f"{event.id}:{trigger}",
        "event_id": str(event.id),
        "title_ko": event.title_ko or event.title or "",
        "scenario": scenario_name,
        "trigger": trigger,
        "what_to_watch": what_to_watch or (event.next_events_ko[0] if event.next_events_ko else "효력 발생일 확인"),
        "deadline": deadline,
        "impact_if_confirmed": price_range,
        "urgency": event.urgency,
        "evidence_grade": event.evidence_grade,
        "sector_ko": event.sector_ko or event.sector or "",
    }
