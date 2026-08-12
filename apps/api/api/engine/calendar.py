"""
Calendar Engine — ScheduledEvent vs ObservedEvent

Key insight from spec Section 5:
  "Who will announce what" and "what actually arrived" are different objects.

ScheduledEvent: a future event we expect (macro release, earnings, filing, etc.)
ObservedEvent: the actual document/value/announcement that arrived

They are linked by REALIZES edges. Expected time and actual time may differ.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from api.models import Event, Thesis, PortfolioPosition


# ---------------------------------------------------------------------------
# Enums and data structures
# ---------------------------------------------------------------------------

class EventClass(str, Enum):
    MACRO_RELEASE = "macro_release"
    EARNINGS = "earnings"
    FILING = "filing"
    POLICY = "policy"
    COURT = "court"
    PRODUCT = "product"
    RESOLUTION = "resolution"  # Polymarket resolution
    FED_SPEAK = "fed_speak"
    OPEC_MEETING = "opec_meeting"
    OTHER = "other"


class TimeConfidence(str, Enum):
    EXACT = "exact"          # precise time known
    WINDOW = "window"        # within a known time window
    DATE_ONLY = "date_only"  # only date known, not time
    ESTIMATED = "estimated"  # approximate


class ActivationPolicy(str, Enum):
    ARM_60M_BEFORE = "arm_60m_before"
    ARM_24H_BEFORE = "arm_24h_before"
    ARM_5M_BEFORE = "arm_5m_before"
    PASSIVE = "passive"  # no rebalancing, just watch


@dataclass
class ScheduledEvent:
    """
    An event we EXPECT to happen in the future.

    Not stored in DB for MVP — computed from event.next_events and static calendars.
    """
    scheduled_id: str
    event_class: EventClass
    expected_at: datetime
    time_confidence: TimeConfidence = TimeConfidence.EXACT
    title: str = ""
    title_ko: str = ""
    expected_metric: str | None = None  # e.g., "CPI YoY"
    consensus: float | None = None       # market consensus
    actual_value: float | None = None    # filled when ObservedEvent arrives
    surprise: float | None = None        # actual - consensus (if applicable)
    affected_factors: list[str] = field(default_factory=list)
    linked_theses: list[str] = field(default_factory=list)
    linked_events: list[str] = field(default_factory=list)
    activation_policy: ActivationPolicy = ActivationPolicy.PASSIVE
    realized_by: str | None = None  # observed_event_id
    realized_at: datetime | None = None
    is_armed: bool = False


@dataclass
class EventSensitivity:
    """How sensitive a thesis/position is to a scheduled event."""
    thesis_id: str
    thesis_title: str
    ticker: str | None = None
    sensitivity: float = 0.5  # 0-1
    expected_direction: str = "neutral"
    pre_event_position: str | None = None
    scenario_if_beat: str | None = None    # e.g., "bull"
    scenario_if_miss: str | None = None     # e.g., "bear"
    scenario_if_inline: str | None = None   # e.g., "base"


# ---------------------------------------------------------------------------
# Pre-configured calendars
# ---------------------------------------------------------------------------

def _build_macro_calendar() -> list[dict[str, Any]]:
    """Build a static calendar of recurring macro events."""
    now = datetime.utcnow()
    # Approximate next occurrences based on known schedules
    return [
        {
            "event_class": "macro_release",
            "title": "Nonfarm Payrolls",
            "title_ko": "비농업 고용",
            "expected_metric": "NFP Change",
            "frequency": "monthly",
            "typical_day": "first_friday",
        },
        {
            "event_class": "macro_release",
            "title": "CPI MoM",
            "title_ko": "소비자물가지수",
            "expected_metric": "CPI MoM",
            "frequency": "monthly",
            "typical_day": "mid_month",
        },
        {
            "event_class": "macro_release",
            "title": "FOMC Decision",
            "title_ko": "FOMC 금리 결정",
            "expected_metric": "Fed Funds Rate",
            "frequency": "6_weeks",
            "typical_day": "wednesday",
        },
        {
            "event_class": "macro_release",
            "title": "GDP QoQ",
            "title_ko": "GDP 분기 성장률",
            "expected_metric": "GDP QoQ",
            "frequency": "quarterly",
            "typical_day": "end_of_month",
        },
        {
            "event_class": "macro_release",
            "title": "ISM Manufacturing PMI",
            "title_ko": "ISM 제조업 PMI",
            "expected_metric": "ISM Manufacturing",
            "frequency": "monthly",
            "typical_day": "first_business_day",
        },
        {
            "event_class": "macro_release",
            "title": "Retail Sales MoM",
            "title_ko": "소매 판매",
            "expected_metric": "Retail Sales MoM",
            "frequency": "monthly",
            "typical_day": "mid_month",
        },
    ]


# ---------------------------------------------------------------------------
# Calendar Engine
# ---------------------------------------------------------------------------

class CalendarEngine:
    """
    Calendar / Event Fabric engine.

    Builds the weekly calendar from:
      - Static macro calendar
      - Event.next_events fields
      - Thesis checkpoints
      - Polymarket resolution deadlines
    """

    def __init__(self, db: Session):
        self.db = db

    def build_weekly_calendar(
        self,
        *,
        lookahead_days: int = 7,
    ) -> list[ScheduledEvent]:
        """Build the 7-day event calendar with scheduled events."""
        now = datetime.utcnow()
        horizon = now + timedelta(days=lookahead_days)
        scheduled: list[ScheduledEvent] = []

        # 1. From event.next_events fields
        events = (
            self.db.query(Event)
            .order_by(Event.published_at.desc())
            .limit(200)
            .all()
        )

        for ev in events:
            next_events = ev.next_events or []
            next_events_ko = ev.next_events_ko or []

            for idx, ne in enumerate(next_events):
                parsed_date = self._parse_date_hint(ne)
                if not parsed_date or not (now <= parsed_date <= horizon):
                    continue

                ko_label = next_events_ko[idx] if idx < len(next_events_ko) else ne
                scheduled.append(ScheduledEvent(
                    scheduled_id=f"sched_next_{ev.id}_{idx}",
                    event_class=self._infer_event_class(ne),
                    expected_at=parsed_date,
                    time_confidence=TimeConfidence.DATE_ONLY,
                    title=f"Next event for: {ev.title or ev.event_key}",
                    title_ko=ko_label,
                    linked_events=[str(ev.id)],
                    activation_policy=self._activation_for_event(ev),
                ))

            # Also check effective dates
            if ev.effective_date:
                eff_naive = ev.effective_date.replace(tzinfo=None) if ev.effective_date.tzinfo else ev.effective_date
                if now <= eff_naive <= horizon:
                    scheduled.append(ScheduledEvent(
                        scheduled_id=f"sched_eff_{ev.id}",
                        event_class=EventClass.POLICY if ev.event_type == "policy_announcement" else EventClass.OTHER,
                        expected_at=eff_naive,
                        time_confidence=TimeConfidence.EXACT,
                        title=f"Effective date: {ev.title or ''}",
                        title_ko=f"효력 발생: {ev.title_ko or ev.title or ''}",
                        linked_events=[str(ev.id)],
                        activation_policy=ActivationPolicy.ARM_60M_BEFORE,
                    ))

        # 2. From thesis-linked checkpoints
        theses = self.db.query(Thesis).all()
        for thesis in theses:
            if not thesis.core_event_id:
                continue
            ev = self.db.query(Event).filter(Event.id == thesis.core_event_id).first()
            if not ev or not ev.next_events_ko:
                continue
            for idx, ne_ko in enumerate(ev.next_events_ko):
                parsed_date = self._parse_date_hint(ev.next_events[idx] if idx < len(ev.next_events or []) else "")
                if not parsed_date or not (now <= parsed_date <= horizon):
                    continue
                scheduled.append(ScheduledEvent(
                    scheduled_id=f"sched_thesis_{thesis.id}_{idx}",
                    event_class=EventClass.OTHER,
                    expected_at=parsed_date,
                    time_confidence=TimeConfidence.DATE_ONLY,
                    title=f"Thesis checkpoint: {thesis.title or ''}",
                    title_ko=ne_ko,
                    linked_theses=[str(thesis.id)],
                    activation_policy=ActivationPolicy.ARM_60M_BEFORE,
                ))

        # Sort by time
        scheduled.sort(key=lambda s: s.expected_at)
        return scheduled

    def compute_sensitivity(
        self,
        scheduled: ScheduledEvent,
    ) -> list[EventSensitivity]:
        """Compute which theses/positions are sensitive to a scheduled event."""
        sensitivities: list[EventSensitivity] = []

        # Find theses linked to this event (directly or via latent factors)
        linked_thesis_ids = set(scheduled.linked_theses)

        # Also find from linked events
        for event_id in scheduled.linked_events:
            theses = (
                self.db.query(Thesis)
                .filter(Thesis.core_event_id == UUID(event_id))
                .all()
            )
            for t in theses:
                linked_thesis_ids.add(str(t.id))

        # Build sensitivity for each thesis
        for tid in linked_thesis_ids:
            thesis = self.db.query(Thesis).filter(Thesis.id == UUID(tid)).first()
            if not thesis:
                continue

            # Find positions linked through exposure_events
            positions = (
                self.db.query(PortfolioPosition)
                .filter(PortfolioPosition.exposure_events.any(str(thesis.core_event_id)))
                .all()
            )

            ticker = positions[0].ticker if positions else None
            sensitivity = EventSensitivity(
                thesis_id=str(thesis.id),
                thesis_title=thesis.title or "",
                ticker=ticker,
                sensitivity=0.7 if scheduled.activation_policy != ActivationPolicy.PASSIVE else 0.3,
                expected_direction="neutral",
                scenario_if_beat="bull",
                scenario_if_miss="bear",
                scenario_if_inline="base",
            )
            sensitivities.append(sensitivity)

        return sensitivities

    def get_cockpit_view(
        self,
        lookahead_days: int = 7,
    ) -> dict[str, Any]:
        """Build the full Event Fabric / Rebalance Cockpit view."""
        scheduled = self.build_weekly_calendar(lookahead_days=lookahead_days)

        armed_events: list[dict[str, Any]] = []
        upcoming: list[dict[str, Any]] = []

        for se in scheduled:
            entry = {
                "scheduled_id": se.scheduled_id,
                "event_class": se.event_class.value,
                "expected_at": se.expected_at.isoformat(),
                "time_confidence": se.time_confidence.value,
                "title": se.title,
                "title_ko": se.title_ko,
                "expected_metric": se.expected_metric,
                "consensus": se.consensus,
                "linked_theses": len(se.linked_theses),
                "linked_events": len(se.linked_events),
                "activation_policy": se.activation_policy.value,
                "is_armed": se.is_armed,
            }

            sensitivities = self.compute_sensitivity(se)
            entry["sensitivity_count"] = len(sensitivities)

            if se.activation_policy in (
                ActivationPolicy.ARM_60M_BEFORE,
                ActivationPolicy.ARM_5M_BEFORE,
            ):
                # Check if within arm window
                now = datetime.utcnow()
                seconds_to_event = (se.expected_at - now).total_seconds()
                arm_seconds = {
                    ActivationPolicy.ARM_60M_BEFORE: 3600,
                    ActivationPolicy.ARM_24H_BEFORE: 86400,
                    ActivationPolicy.ARM_5M_BEFORE: 300,
                    ActivationPolicy.PASSIVE: 0,
                }
                threshold = arm_seconds.get(se.activation_policy, 0)
                if 0 <= seconds_to_event <= threshold + 300:  # within arm window + buffer
                    se.is_armed = True
                    entry["is_armed"] = True
                    entry["seconds_until"] = int(seconds_to_event)
                    armed_events.append(entry)
                else:
                    upcoming.append(entry)
            else:
                upcoming.append(entry)

        return {
            "as_of": datetime.utcnow().isoformat(),
            "armed_events": armed_events,
            "upcoming_events": upcoming,
            "total_scheduled": len(scheduled),
            "total_armed": len(armed_events),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_date_hint(self, text: str) -> datetime | None:
        """Try to parse a date hint from text like 'Jul 10' or '7/10'."""
        import re

        if not text:
            return None

        now = datetime.utcnow()
        current_year = now.year

        # Pattern: "Month Day" or "M/D"
        patterns = [
            (r"(\d{1,2})[/\-\s](\d{1,2})", None),  # 7/10, 7-10
            (r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})", {
                "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
            }),
        ]

        for pattern_str, month_map in patterns:
            match = re.search(pattern_str, text, re.IGNORECASE)
            if match:
                if month_map:
                    month_name = match.group(1).lower()[:3]
                    month = month_map.get(month_name)
                    day = int(match.group(2))
                else:
                    month = int(match.group(1))
                    day = int(match.group(2))

                if month and 1 <= month <= 12 and 1 <= day <= 31:
                    # Guess year: if month < current month, assume next year
                    year = current_year
                    if month < now.month:
                        year = current_year + 1
                    try:
                        return datetime(year, month, day, 14, 0, 0)  # default to 2PM UTC
                    except ValueError:
                        return None

        return None

    def _infer_event_class(self, text: str) -> EventClass:
        text_lower = text.lower()
        if any(w in text_lower for w in ("cpi", "gdp", "nfp", "payroll", "ism", "fomc", "fed", "retail")):
            return EventClass.MACRO_RELEASE
        if any(w in text_lower for w in ("earnings", "call", "q2", "q3", "q4", "q1", "실적")):
            return EventClass.EARNINGS
        if any(w in text_lower for w in ("court", "ruling", "판결")):
            return EventClass.COURT
        if any(w in text_lower for w in ("filing", "8k", "10q", "10k", "공시")):
            return EventClass.FILING
        if any(w in text_lower for w in ("opec", "eia")):
            return EventClass.OPEC_MEETING
        if any(w in text_lower for w in ("resolve", "resolution")):
            return EventClass.RESOLUTION
        return EventClass.OTHER

    def _activation_for_event(self, event: Event) -> ActivationPolicy:
        """Determine activation policy based on event urgency and type."""
        if event.urgency == "Critical":
            return ActivationPolicy.ARM_5M_BEFORE
        if event.urgency == "High":
            return ActivationPolicy.ARM_60M_BEFORE
        if event.event_type in ("earnings", "macro"):
            return ActivationPolicy.ARM_60M_BEFORE
        return ActivationPolicy.PASSIVE
