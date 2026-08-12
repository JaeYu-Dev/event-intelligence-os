"""
Celery task definitions for the monitor loops.

Wire the strategic loop, cheap monitor, and event-window loop
as periodic tasks via Celery Beat.
"""

from celery import Celery
from celery.schedules import crontab
from api.config import settings

celery_app = Celery(
    "eios_monitor",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Beat schedule — periodic tasks
    beat_schedule={
        # Strategic Loop — every 6 hours
        "strategic-loop": {
            "task": "api.monitor.tasks.strategic_loop",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        # Cheap Monitor — every 30 seconds
        "cheap-monitor": {
            "task": "api.monitor.tasks.cheap_monitor",
            "schedule": 30.0,
        },
        # Event-Window Loop — every 60 seconds
        "event-window-loop": {
            "task": "api.monitor.tasks.event_window_loop",
            "schedule": 60.0,
        },
        # Nightly Validation — UTC midnight
        "nightly-validation": {
            "task": "api.monitor.tasks.nightly_validation",
            "schedule": crontab(minute=0, hour=0),
        },
        # Hourly Calendar Refresh
        "calendar-refresh": {
            "task": "api.monitor.tasks.refresh_calendar",
            "schedule": crontab(minute=0, hour="*"),
        },
    },
    task_routes={
        "api.monitor.tasks.*": {"queue": "monitor"},
    },
)


@celery_app.task(name="api.monitor.tasks.strategic_loop")
def strategic_loop() -> dict:
    """Strategic loop: discovery, thesis maintenance, graph building."""
    from api.monitor.strategic_loop import run_strategic_loop
    return run_strategic_loop()


@celery_app.task(name="api.monitor.tasks.cheap_monitor")
def cheap_monitor() -> dict:
    """Cheap monitor: anomaly detection, trigger evaluation."""
    from api.monitor.cheap_monitor import run_cheap_monitor
    return run_cheap_monitor()


@celery_app.task(name="api.monitor.tasks.event_window_loop")
def event_window_loop() -> dict:
    """Event-window loop: 1-min rebalancing for armed events."""
    from api.monitor.event_window_loop import run_event_window_loop
    return run_event_window_loop()


@celery_app.task(name="api.monitor.tasks.nightly_validation")
def nightly_validation() -> dict:
    """Nightly: post-mortems, calibration, learning batch."""
    from api.monitor.strategic_loop import run_nightly_validation
    return run_nightly_validation()


@celery_app.task(name="api.monitor.tasks.refresh_calendar")
def refresh_calendar() -> dict:
    """Hourly: refresh event calendar from next_events fields."""
    from api.database import SessionLocal
    from api.engine.calendar import CalendarEngine

    db = SessionLocal()
    try:
        engine = CalendarEngine(db)
        cockpit = engine.get_cockpit_view(lookahead_days=7)
        return {
            "run_at": cockpit["as_of"],
            "total_scheduled": cockpit["total_scheduled"],
            "total_armed": cockpit["total_armed"],
        }
    finally:
        db.close()
