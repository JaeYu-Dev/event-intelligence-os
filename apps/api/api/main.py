import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Any

from api.database import get_db, engine, Base
from api.config import settings
from api.models import Event, PortfolioPosition, Thesis
from api.ingest.service import run_connector, ingest_prices
from api.graph.service import build_event_relations, get_event_relations
from api.schemas import IngestResponse, EventOut, PortfolioOut, RadarOut, orm_to_dict
from api.alerts.service import generate_alerts
from api.portfolio.service import import_positions, compute_exposure
from api.paper.service import list_paper_trades, create_paper_trade
from api.thesis.service import get_or_create_thesis_for_event, reassess_thesis, list_theses, get_thesis_detail


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "mode": settings.default_mode}


@app.post("/events/ingest/{source_name}", response_model=IngestResponse)
async def ingest(source_name: str, db: Session = Depends(get_db)):
    if source_name == "prices":
        raise HTTPException(400, "Use /prices/ingest/{symbol} for price ingestion")
    try:
        result = await run_connector(source_name)
        return IngestResponse(**result)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/prices/ingest/{symbol}")
async def ingest_price(symbol: str, period: str = "1mo", interval: str = "1d"):
    try:
        return await ingest_prices(symbol, period, interval)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)):
    events = db.query(Event).order_by(Event.published_at.desc()).all()
    return [EventOut(**orm_to_dict(e)) for e in events]


@app.get("/radar/opportunities", response_model=RadarOut)
def radar_opportunities(db: Session = Depends(get_db)):
    events = db.query(Event).order_by(Event.published_at.desc()).limit(100).all()
    positions = db.query(PortfolioPosition).all()
    event_dicts = [EventOut(**orm_to_dict(e)).model_dump() for e in events]
    edges = build_event_relations(event_dicts, db=db)
    return RadarOut(
        events=[EventOut(**orm_to_dict(e)) for e in events],
        positions=[PortfolioOut(**orm_to_dict(p)) for p in positions],
        edges=edges,
    )


@app.get("/alerts")
def list_alerts(db: Session = Depends(get_db)):
    return {"alerts": generate_alerts(db)}


@app.get("/theses/{thesis_id}")
def get_thesis(thesis_id: str, db: Session = Depends(get_db)):
    thesis = db.query(Thesis).filter(Thesis.id == thesis_id).first()
    if not thesis:
        raise HTTPException(404, "Thesis not found")
    return {"thesis": thesis}


@app.post("/extract/{doc_id}")
async def extract(doc_id: str):
    from api.extract.service import extract_from_document
    try:
        event = await extract_from_document(doc_id)
        if not event:
            raise HTTPException(404, "Document not found or extraction failed")
        return {"event_id": str(event.id), "title": event.title}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/extract")
async def extract_pending(limit: int = 10):
    from api.extract.service import extract_all_pending
    try:
        return await extract_all_pending(limit)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/relations")
def list_relations(db: Session = Depends(get_db)):
    return {"edges": get_event_relations(db)}


@app.post("/relations/generate")
def generate_relations(db: Session = Depends(get_db)):
    events = db.query(Event).order_by(Event.published_at.desc()).limit(100).all()
    event_dicts = [EventOut(**orm_to_dict(e)).model_dump() for e in events]
    edges = build_event_relations(event_dicts, db=db)
    return {"edges": edges}


@app.get("/theses")
def get_theses(db: Session = Depends(get_db)):
    return {"theses": [orm_to_dict(t) for t in list_theses(db)]}


@app.get("/theses/{thesis_id}/detail")
def thesis_detail(thesis_id: str, db: Session = Depends(get_db)):
    try:
        return get_thesis_detail(db, thesis_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/theses/{thesis_id}/reassess")
def reassess_thesis_endpoint(thesis_id: str, payload: dict[str, Any], db: Session = Depends(get_db)):
    try:
        thesis = reassess_thesis(db, thesis_id, payload)
        return {"thesis": orm_to_dict(thesis)}
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/events/{event_id}/thesis")
def create_thesis_from_event(event_id: str, db: Session = Depends(get_db)):
    try:
        thesis = get_or_create_thesis_for_event(db, event_id)
        return {"thesis": orm_to_dict(thesis)}
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/portfolio")
def get_portfolio(db: Session = Depends(get_db)):
    return compute_exposure(db)


@app.post("/portfolio/import")
def import_portfolio(payload: list[dict[str, Any]], db: Session = Depends(get_db)):
    try:
        positions = import_positions(db, payload)
        return {"imported": len(positions), "positions": [PortfolioOut(**orm_to_dict(p)).model_dump() for p in positions]}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/paper-trades")
def get_paper_trades(thesis_id: str | None = None, db: Session = Depends(get_db)):
    return {"trades": list_paper_trades(db, thesis_id)}


@app.post("/paper-trades")
def create_trade(payload: dict[str, Any], db: Session = Depends(get_db)):
    try:
        trade = create_paper_trade(db, payload)
        return {"trade": orm_to_dict(trade)}
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


# ============================================================================
# Engine API endpoints (v1.2 engines)
# ============================================================================

from api.engine.orchestrator import EngineOrchestrator


def _get_orch(db: Session) -> EngineOrchestrator:
    return EngineOrchestrator(db)




# -- Walk-Forward Backtest --

@app.post("/engine/backtest/walk-forward")
def run_walk_forward_backtest(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
):
    """Run a walk-forward backtest over a historical window."""
    orch = _get_orch(db)
    return orch.run_walk_forward_backtest(
        run_name=payload.get("run_name", "walk-forward-backtest"),
        cutoff_start=payload["cutoff_start"],
        cutoff_end=payload["cutoff_end"],
        train_window_days=payload.get("train_window_days", 365),
        val_window_days=payload.get("val_window_days", 90),
        test_window_days=payload.get("test_window_days", 90),
        step_days=payload.get("step_days", 30),
        universe=payload.get("universe"),
    )



@app.get("/engine/backtest/{run_id}/postmortem")
def get_backtest_postmortem(run_id: str, db: Session = Depends(get_db)):
    """Get aggregate postmortem for a backtest run."""
    from api.models import BacktestRun
    from uuid import UUID as _UUID

    run = db.query(BacktestRun).filter(BacktestRun.id == _UUID(run_id)).first()
    if not run:
        raise HTTPException(404, "Backtest run not found")
    return {
        "backtest_run_id": str(run.id),
        "run_name": run.run_name,
        "status": run.status,
        "failure_analysis": run.failure_analysis,
        "improvement_decision": run.improvement_decision,
    }

@app.get("/engine/backtest/{run_id}")
def get_backtest_result(run_id: str, db: Session = Depends(get_db)):
    """Get backtest run result."""
    from api.models import BacktestRun
    from uuid import UUID as _UUID

    run = db.query(BacktestRun).filter(BacktestRun.id == _UUID(run_id)).first()
    if not run:
        raise HTTPException(404, "Backtest run not found")
    return {
        "backtest_run_id": str(run.id),
        "run_name": run.run_name,
        "status": run.status,
        "config": run.config,
        "result_summary": run.result_summary,
        "predictions_generated": run.predictions_generated,
        "predictions_resolved": run.predictions_resolved,
        "brier_score": run.brier_score,
        "log_loss": run.log_loss,
        "improvement_decision": run.improvement_decision,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@app.get("/engine/backtests")
def list_backtest_runs(db: Session = Depends(get_db)):
    """List backtest runs."""
    from api.models import BacktestRun

    runs = db.query(BacktestRun).order_by(BacktestRun.created_at.desc()).all()
    return {
        "runs": [
            {
                "backtest_run_id": str(r.id),
                "run_name": r.run_name,
                "status": r.status,
                "predictions_generated": r.predictions_generated,
                "predictions_resolved": r.predictions_resolved,
                "brier_score": r.brier_score,
                "improvement_decision": r.improvement_decision,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ]
    }

# -- Point-in-Time Snapshot --

@app.post("/engine/pit-snapshot")
def build_pit_snapshot(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
):
    """Build a point-in-time snapshot at cutoff_time."""
    orch = _get_orch(db)
    cutoff_time = payload.get("cutoff_time")
    universe = payload.get("universe")
    if not cutoff_time:
        raise HTTPException(400, "cutoff_time is required")
    return orch.build_pit_snapshot(cutoff_time, universe=universe)

# -- Command Center --

@app.get("/engine/command-center")
def command_center(db: Session = Depends(get_db)):
    orch = _get_orch(db)
    return orch.command_center()


# -- Discovery Engine --

@app.get("/engine/discover")
def discover_opportunities(
    max_root_events: int = 5,
    max_candidates: int = 5,
    db: Session = Depends(get_db),
):
    orch = _get_orch(db)
    return orch.run_discovery(
        max_root_events=max_root_events,
        max_candidates_per_root=max_candidates,
    )


@app.get("/engine/expand/{event_id}")
def expand_event(
    event_id: str,
    max_candidates: int = 10,
    max_hops: int = 3,
    db: Session = Depends(get_db),
):
    orch = _get_orch(db)
    result = orch.expand_event(event_id, max_candidates=max_candidates, max_hops=max_hops)
    if not result and not db.query(Event).filter(Event.id == event_id).first():
        raise HTTPException(404, "Event not found")
    return {"event_id": event_id, "candidates": result}


# -- Assimilation Engine --

@app.get("/engine/assimilation/{event_id}")
def classify_assimilation(
    event_id: str,
    target_instrument: str | None = None,
    db: Session = Depends(get_db),
):
    orch = _get_orch(db)
    result = orch.classify_assimilation(event_id, target_instrument=target_instrument)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.get("/engine/event-study/{event_id}")
def event_study(
    event_id: str,
    instrument: str,
    db: Session = Depends(get_db),
):
    orch = _get_orch(db)
    result = orch.run_event_study(event_id, instrument)
    if not result:
        raise HTTPException(404, "Event or instrument data not found")
    return result


# -- Rebalance Engine --

@app.post("/engine/rebalance/arm/{event_id}")
def arm_rebalance(
    event_id: str,
    thesis_ids: list[str] | None = None,
    db: Session = Depends(get_db),
):
    orch = _get_orch(db)
    result = orch.arm_for_event(event_id, thesis_ids=thesis_ids)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.get("/engine/rebalance/state/{event_id}")
def get_rebalance_state(event_id: str, db: Session = Depends(get_db)):
    orch = _get_orch(db)
    return orch.get_rebalance_state(event_id)


@app.post("/engine/rebalance/transition/{event_id}")
def transition_rebalance(
    event_id: str,
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
):
    orch = _get_orch(db)
    actual_data = payload.get("actual_data") if payload else None
    result = orch.transition_rebalance(event_id, actual_data=actual_data)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


# -- Validation Engine --

@app.get("/engine/post-mortem/{thesis_id}")
def post_mortem(thesis_id: str, db: Session = Depends(get_db)):
    orch = _get_orch(db)
    result = orch.post_mortem(thesis_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.post("/engine/evaluate-overfitting")
def evaluate_overfitting(
    thesis_ids: list[str],
    db: Session = Depends(get_db),
):
    orch = _get_orch(db)
    return orch.evaluate_overfitting(thesis_ids)


# -- Calendar Engine --

@app.get("/engine/calendar")
def weekly_calendar(lookahead_days: int = 7, db: Session = Depends(get_db)):
    orch = _get_orch(db)
    return orch.weekly_calendar(lookahead_days=lookahead_days)


@app.get("/engine/calendar/sensitivity/{scheduled_id}")
def event_sensitivity(scheduled_id: str, db: Session = Depends(get_db)):
    orch = _get_orch(db)
    return {"scheduled_id": scheduled_id, "sensitivities": orch.event_sensitivity(scheduled_id)}


# -- Engine 5: Probability & Scenario --

@app.get("/engine/probability/{thesis_id}")
def compute_probabilities(thesis_id: str, db: Session = Depends(get_db)):
    orch = _get_orch(db)
    result = orch.compute_probabilities(thesis_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.post("/engine/probability/{thesis_id}/update")
def update_scenario_with_evidence(
    thesis_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
):
    orch = _get_orch(db)
    result = orch.update_scenario_with_evidence(
        thesis_id,
        price_data=payload.get("price_data"),
        polymarket_prob=payload.get("polymarket_prob"),
        official_confirmations=payload.get("official_confirmations", 0),
        analyst_views=payload.get("analyst_views", 0),
        counter_evidence_count=payload.get("counter_evidence_count", 0),
    )
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.post("/engine/calibrate")
def calibrate_against_market(
    thesis_ids: list[str],
    market_prices: list[float],
    outcomes: list[int],
    db: Session = Depends(get_db),
):
    orch = _get_orch(db)
    return orch.calibrate_against_market(thesis_ids, market_prices, outcomes)


# -- Engine 1-3: Fabric, Evidence, Ontology --


@app.post("/engine/deep-scan")
def deep_scan(db: Session = Depends(get_db)):
    """Manual deep scan — runs discovery, assimilation, graph, calendar."""
    orch = _get_orch(db)
    return orch.deep_scan()


# -- Thesis management (Inbox: accept/reject, My Theses: list/detail) --

@app.post("/engine/thesis/accept/{event_id}")
def accept_thesis(event_id: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db)):
    """Accept a candidate or motif — promotes all events to Thesis."""
    """Accept a candidate or motif."""
    orch = _get_orch(db)
    motif_events = payload.get("motif_events") if payload else None
    result = orch.accept_thesis(event_id, motif_events=motif_events)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result
def reject_thesis(event_id: str, db: Session = Depends(get_db)):
    """Reject/dismiss a candidate."""
    orch = _get_orch(db)
    result = orch.reject_thesis(event_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result

@app.get("/engine/theses")
def list_my_theses(db: Session = Depends(get_db)):
    """List all accepted theses."""
    orch = _get_orch(db)
    return orch.list_my_theses()


@app.get("/engine/causal-path/{thesis_id}")
def get_causal_path(thesis_id: str, db: Session = Depends(get_db)):
    """Build structured causal path for a thesis — 6-layer flow."""
    from api.engine.causal_path import CausalPathEngine
    engine = CausalPathEngine(db)
    result = engine.build_path(thesis_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result

@app.get("/engine/thesis/{thesis_id}")
def get_thesis_detail(thesis_id: str, db: Session = Depends(get_db)):
    """Full thesis detail with scenarios, narrative, graph, portfolio."""
    orch = _get_orch(db)
    result = orch.get_thesis_detail(thesis_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.get("/engine/fabric")
def fabric_summary(db: Session = Depends(get_db)):
    orch = _get_orch(db)
    return orch.fabric_summary()


@app.get("/engine/evidence/{event_id}")
def evidence_quality(event_id: str, db: Session = Depends(get_db)):
    orch = _get_orch(db)
    return orch.evidence_quality(event_id)


@app.get("/engine/ontology/{entity_id}")
def entity_graph(entity_id: str, db: Session = Depends(get_db)):
    orch = _get_orch(db)
    return orch.entity_graph(entity_id)


# ============================================================================
# Phase 5: Prediction Record & Standard Output
# ============================================================================

@app.post("/engine/prediction-record/{event_id}")
def create_prediction_record(
    event_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
):
    """Create a prediction record for post-hoc verification."""
    from api.models import PredictionRecord
    from uuid import UUID as _UUID

    event = db.query(Event).filter(Event.id == _UUID(event_id)).first()
    if not event:
        raise HTTPException(404, "Event not found")

    record = PredictionRecord(
        event_id=_UUID(event_id),
        thesis_id=_UUID(payload["thesis_id"]) if payload.get("thesis_id") else None,
        claim=payload.get("claim", ""),
        target_asset=payload.get("target_asset", ""),
        target_metric=payload.get("target_metric", "price_change"),
        forecast_horizon=payload.get("forecast_horizon", "7d"),
        expected_direction=payload.get("expected_direction", "unknown"),
        expected_range=payload.get("expected_range", ""),
        conditional_on=payload.get("conditional_on", []),
        confidence=payload.get("confidence", 0.5),
        probability_basis=payload.get("probability_basis", ""),
        evidence_at_creation=payload.get("evidence_at_creation", []),
        falsifiers=payload.get("falsifiers", []),
        confirmation_events=payload.get("confirmation_events", []),
        market_expectation_snapshot=payload.get("market_expectation_snapshot", {}),
        model_version="v2",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "prediction_id": str(record.id),
        "created_at": record.created_at.isoformat(),
        "status": "active",
    }


@app.post("/engine/prediction-record/{record_id}/resolve")
def resolve_prediction_record(
    record_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
):
    """Resolve a prediction record with actual outcome."""
    from api.models import PredictionRecord
    from uuid import UUID as _UUID
    from datetime import datetime

    record = db.query(PredictionRecord).filter(PredictionRecord.id == _UUID(record_id)).first()
    if not record:
        raise HTTPException(404, "Prediction record not found")

    record.actual_outcome = payload.get("actual_outcome", {})
    record.outcome_timestamp = datetime.utcnow()
    record.calibration_error = payload.get("calibration_error")
    record.postmortem = payload.get("postmortem", "")
    record.status = "resolved"
    db.commit()

    return {
        "record_id": record_id,
        "status": "resolved",
        "calibration_error": record.calibration_error,
    }


@app.get("/engine/prediction-records")
def list_prediction_records(
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """List all prediction records, optionally filtered by status."""
    from api.models import PredictionRecord

    q = db.query(PredictionRecord)
    if status:
        q = q.filter(PredictionRecord.status == status)
    records = q.order_by(PredictionRecord.created_at.desc()).limit(50).all()

    return {
        "records": [
            {
                "id": str(r.id),
                "target_asset": r.target_asset,
                "expected_direction": r.expected_direction,
                "confidence": r.confidence,
                "status": r.status,
                "calibration_error": r.calibration_error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]
    }
