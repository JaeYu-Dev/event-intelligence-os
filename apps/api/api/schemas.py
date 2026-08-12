from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from typing import Any


class IngestResponse(BaseModel):
    source: str
    fetched: int
    ingested: int


def _convert(v: Any) -> Any:
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, list):
        return [_convert(x) for x in v]
    if isinstance(v, dict):
        return {k: _convert(x) for k, x in v.items()}
    return v


def orm_to_dict(obj: Any) -> dict:
    d = {}
    for k, v in obj.__dict__.items():
        if k.startswith("_"):
            continue
        d[k] = _convert(v)
    return d


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_key: str
    event_type: str
    actor: str | None
    actor_ko: str | None
    action: str | None
    object: str | None
    title: str | None
    title_ko: str | None
    sector: str | None
    sector_ko: str | None
    evidence_grade: str
    urgency: str
    status: str
    related_tickers: list[str] | None
    mechanism: str | None
    mechanism_ko: str | None
    counterevidence: list[str] | None
    counterevidence_ko: list[str] | None
    next_events: list[str] | None
    next_events_ko: list[str] | None
    conditions: list[dict] | None
    source_type: str | None
    source_reliability: float | None
    effective_date: datetime | None
    published_at: datetime | None
    created_at: datetime


class PortfolioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ticker: str
    name: str | None
    shares: float
    avg_cost: float
    current_price: float | None
    pl_percent: float | None
    pl_usd: float | None
    scenario_bias: str | None
    exposure_events: list[str] | None


class CausalEdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    target: str
    strength: float
    type: str
    label: str | None
    label_ko: str | None


class RadarOut(BaseModel):
    events: list[EventOut]
    positions: list[PortfolioOut]
    edges: list[CausalEdgeOut] = []
