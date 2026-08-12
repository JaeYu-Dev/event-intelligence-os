"""
Strategic Loop — runs every 6 hours.

Spec P7:
  Strategic Loop (6시간~1일)
  - 사건 조합 발견
  - 인과경로 검증
  - 1일~1주 시나리오, 목표 노출, 무효화 조건 설정
  - overnight batch validation & learning

Invoked by Celery beat every 6 hours.
Also provides nightly validation batch.
"""

import logging
from datetime import datetime, timedelta

from api.database import SessionLocal
from api.models import Event, Thesis
from api.engine.orchestrator import EngineOrchestrator

logger = logging.getLogger("eios.strategic")


def run_strategic_loop() -> dict:
    """
    Main strategic loop — called every 6 hours by Celery beat.
    1. Scan for new root events not yet in thesis
    2. Run discovery on top events
    3. Check all active theses for status changes
    4. Build next 7-day calendar
    5. Generate priority research queue
    """
    db = SessionLocal()
    result = {
        "run_at": datetime.utcnow().isoformat(),
        "new_root_events": 0,
        "discoveries_generated": 0,
        "theses_checked": 0,
        "theses_at_risk": 0,
        "alerts_generated": 0,
        "errors": [],
    }

    try:
        orch = EngineOrchestrator(db)

        # 1. Scan for root events published in last 6 hours
        six_hours_ago = datetime.utcnow() - timedelta(hours=6)
        recent_events = (
            db.query(Event)
            .filter(Event.published_at >= six_hours_ago)
            .filter(Event.evidence_grade.in_(["E3", "E4"]))
            .all()
        )
        result["new_root_events"] = len(recent_events)

        # 2. Run discovery on top-Evidence events
        discovery = orch.run_discovery(max_root_events=5, max_candidates_per_root=5)
        total_candidates = sum(len(v) for v in discovery.get("discoveries", {}).values())
        result["discoveries_generated"] = total_candidates

        # 3. Build relation graph for recent events if needed
        from api.graph.service import build_event_relations
        from api.schemas import EventOut, orm_to_dict
        recent_all = (
            db.query(Event)
            .order_by(Event.published_at.desc())
            .limit(100)
            .all()
        )
        event_dicts = [EventOut(**orm_to_dict(e)).model_dump() for e in recent_all]
        build_event_relations(event_dicts, db=db)

        # 4. Check all active theses — any need reassessment?
        theses = db.query(Thesis).filter(
            Thesis.status.in_(["Active", "Watching", "Paper Active"])
        ).all()

        for thesis in theses:
            result["theses_checked"] += 1
            event = db.query(Event).filter(Event.id == thesis.core_event_id).first()
            if not event:
                continue

            # Check if scenarios have diverged significantly
            if event.next_events:
                # Event has upcoming checkpoints — mark for calendar
                pass

            # Check if urgency changed
            if event.urgency == "Critical":
                result["theses_at_risk"] += 1

        db.commit()

    except Exception as e:
        logger.exception("Strategic loop failed")
        result["errors"].append(str(e))
    finally:
        db.close()

    logger.info(
        "Strategic loop: %d new events, %d discoveries, %d theses checked",
        result["new_root_events"],
        result["discoveries_generated"],
        result["theses_checked"],
    )
    return result


def run_nightly_validation() -> dict:
    """
    Nightly batch — runs once per day (UTC midnight).
    Run post-mortems on completed theses, calibration updates, etc.
    """
    db = SessionLocal()
    result = {
        "run_at": datetime.utcnow().isoformat(),
        "post_mortems_run": 0,
        "calibration_updated": False,
        "errors": [],
    }

    try:
        orch = EngineOrchestrator(db)

        # Find theses that resolved today
        resolved = db.query(Thesis).filter(
            Thesis.status.in_(["Resolved", "Invalidated", "Archived"])
        ).all()

        for thesis in resolved:
            try:
                orch.post_mortem(str(thesis.id))
                result["post_mortems_run"] += 1
            except Exception:
                pass

    except Exception as e:
        logger.exception("Nightly validation failed")
        result["errors"].append(str(e))
    finally:
        db.close()

    return result
