import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, Integer, Text, Boolean, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from api.database import Base


def uuid_str():
    return lambda: str(uuid.uuid4())


class Source(Base):
    __tablename__ = "sources"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_name = Column(String, unique=True, nullable=False)
    source_tier = Column(String, default="C")  # A/B/C/D
    base_url = Column(String)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class SourceDocument(Base):
    __tablename__ = "source_documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False)
    source_document_id = Column(String, nullable=False)
    content_hash = Column(String, nullable=False)
    raw_payload_ref = Column(String, nullable=False)  # s3 path
    published_at = Column(DateTime(timezone=True))
    first_observed_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    content_type = Column(String)
    title = Column(String)
    url = Column(String)
    metadata_json = Column(JSON, default=dict)
    source = relationship("Source")
    # Point-in-Time integrity fields (spec XXXI-XXXII)
    effective_time = Column(DateTime(timezone=True))
    publish_time = Column(DateTime(timezone=True))
    observed_time = Column(DateTime(timezone=True))
    ingested_time = Column(DateTime(timezone=True), default=datetime.utcnow)
    revision_time = Column(DateTime(timezone=True))
    valid_from = Column(DateTime(timezone=True))
    valid_to = Column(DateTime(timezone=True))
    backtest_available_time = Column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("source_id", "content_hash", name="uq_source_doc_hash"),)


class Event(Base):
    __tablename__ = "events"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_key = Column(String, unique=True, nullable=False)  # actor|action|object|published_at hash
    event_type = Column(String, nullable=False)
    actor = Column(String)
    actor_ko = Column(String)
    action = Column(String)
    object = Column(String)
    magnitude_value = Column(Float)
    magnitude_unit = Column(String)
    effective_date = Column(DateTime(timezone=True))
    published_at = Column(DateTime(timezone=True))
    first_observed_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    source_reliability = Column(Float, default=0.0)
    source_type = Column(String)
    evidence_grade = Column(String, default="E0")
    urgency = Column(String, default="Medium")
    status = Column(String, default="Watching")
    title = Column(String)
    title_ko = Column(String)
    sector = Column(String)
    sector_ko = Column(String)
    mechanism = Column(Text)
    mechanism_ko = Column(Text)
    related_tickers = Column(ARRAY(String), default=list)
    conditions = Column(JSON, default=list)
    counterevidence = Column(JSON, default=list)
    counterevidence_ko = Column(JSON, default=list)
    next_events = Column(JSON, default=list)
    next_events_ko = Column(JSON, default=list)
    # Phase 1: v2 schema additions
    event_subtype = Column(String)
    event_stage = Column(String, default="detected")
    expectedness = Column(String, default="unknown")
    novelty_score = Column(Float, default=0.5)
    materiality_score = Column(Float, default=0.5)
    reversibility = Column(String, default="unknown")
    recurrence_pattern = Column(String, default="unknown")
    causal_scope = Column(String, default="unknown")
    geographic_scope = Column(String, default="global")
    affected_time_horizon = Column(String, default="unknown")
    official_confirmation_status = Column(String, default="unconfirmed")
    fact_confidence = Column(Float, default=0.5)
    revision_risk = Column(String, default="low")
    market_expectation_score = Column(Float, default=0.5)
    linked_claim_ids = Column(JSON, default=list)

    source_document_ids = Column(ARRAY(UUID(as_uuid=True)), default=list)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    # Point-in-Time integrity fields (spec XXXI-XXXII)
    effective_time = Column(DateTime(timezone=True))
    publish_time = Column(DateTime(timezone=True))
    observed_time = Column(DateTime(timezone=True))
    ingested_time = Column(DateTime(timezone=True), default=datetime.utcnow)
    revision_time = Column(DateTime(timezone=True))
    valid_from = Column(DateTime(timezone=True))
    valid_to = Column(DateTime(timezone=True))
    backtest_available_time = Column(DateTime(timezone=True))
    # Point-in-Time integrity fields (spec XXXI-XXXII)
    effective_time = Column(DateTime(timezone=True))
    publish_time = Column(DateTime(timezone=True))
    observed_time = Column(DateTime(timezone=True))
    ingested_time = Column(DateTime(timezone=True), default=datetime.utcnow)
    revision_time = Column(DateTime(timezone=True))
    valid_from = Column(DateTime(timezone=True))
    valid_to = Column(DateTime(timezone=True))
    backtest_available_time = Column(DateTime(timezone=True))


class EventRelation(Base):
    __tablename__ = "event_relations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)
    target_event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)
    edge_type = Column(String, nullable=False)
    strength = Column(Float, default=1.0)
    mechanism = Column(Text)
    mechanism_ko = Column(Text)
    source_refs = Column(ARRAY(UUID(as_uuid=True)), default=list)
    # Phase 1: v2 spec edge attributes
    direction = Column(String, default="positive")
    confidence = Column(Float, default=0.5)
    lag_distribution = Column(JSON, default=dict)
    valid_from = Column(DateTime(timezone=True))
    valid_to = Column(DateTime(timezone=True))
    supporting_source_ids = Column(JSON, default=list)
    contradicting_source_ids = Column(JSON, default=list)
    required_conditions = Column(JSON, default=list)
    alternative_paths = Column(JSON, default=list)
    causal_or_associative = Column(String, default="associative")
    connection_rationale = Column(Text)
    evidence_rationale = Column(Text)
    mechanism_rationale = Column(Text)
    time_rationale = Column(Text)
    alternative_explanation = Column(Text)
    uncertainty_note = Column(Text)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    # Point-in-Time integrity fields (spec XXXI-XXXII)
    effective_time = Column(DateTime(timezone=True))
    publish_time = Column(DateTime(timezone=True))
    observed_time = Column(DateTime(timezone=True))
    ingested_time = Column(DateTime(timezone=True), default=datetime.utcnow)
    revision_time = Column(DateTime(timezone=True))
    valid_from = Column(DateTime(timezone=True))
    valid_to = Column(DateTime(timezone=True))
    backtest_available_time = Column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("source_event_id", "target_event_id", "edge_type", name="uq_event_relation"),)


class Entity(Base):
    __tablename__ = "entities"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String, nullable=False)
    canonical_name = Column(String, nullable=False)
    aliases = Column(ARRAY(String), default=list)
    identifiers = Column(JSON, default=dict)  # {ticker, cik, etc}
    sector = Column(String)
    metadata_json = Column(JSON, default=dict)


class Relation(Base):
    __tablename__ = "relations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    target_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    edge_type = Column(String, nullable=False)
    direction = Column(String, default="positive")
    mechanism = Column(Text)
    mechanism_ko = Column(Text)
    lag_window_min_hours = Column(Integer, default=0)
    lag_window_max_hours = Column(Integer, default=168)
    evidence_grade = Column(String, default="E0")
    historical_stability = Column(Float)
    current_regime_fit = Column(Float)
    redundancy_group = Column(String)
    source_refs = Column(ARRAY(UUID(as_uuid=True)), default=list)


class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"))
    source_document_id = Column(UUID(as_uuid=True), ForeignKey("source_documents.id"))
    claim_text = Column(Text)
    claim_text_ko = Column(Text)
    evidence_grade = Column(String, default="E0")
    extracted_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class LatentFactor(Base):
    __tablename__ = "latent_factors"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text)
    sensors = Column(ARRAY(String), default=list)


class MarketInstrument(Base):
    __tablename__ = "market_instruments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String, unique=True, nullable=False)
    name = Column(String)
    asset_class = Column(String)
    exchange = Column(String)
    metadata_json = Column(JSON, default=dict)


class MarketPrice(Base):
    __tablename__ = "market_prices"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instrument_id = Column(UUID(as_uuid=True), ForeignKey("market_instruments.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    source = Column(String)
    # Point-in-Time integrity fields (spec XXXI-XXXII)
    effective_time = Column(DateTime(timezone=True))
    publish_time = Column(DateTime(timezone=True))
    observed_time = Column(DateTime(timezone=True))
    ingested_time = Column(DateTime(timezone=True), default=datetime.utcnow)
    revision_time = Column(DateTime(timezone=True))
    valid_from = Column(DateTime(timezone=True))
    valid_to = Column(DateTime(timezone=True))
    backtest_available_time = Column(DateTime(timezone=True))


class PortfolioPosition(Base):
    __tablename__ = "portfolio_positions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String, nullable=False)
    name = Column(String)
    shares = Column(Float, default=0)
    avg_cost = Column(Float, default=0)
    current_price = Column(Float)
    pl_percent = Column(Float)
    pl_usd = Column(Float)
    exposure_events = Column(ARRAY(UUID(as_uuid=True)), default=list)
    scenario_bias = Column(String)


class Thesis(Base):
    __tablename__ = "theses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String)
    status = Column(String, default="Watching")
    core_event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"))
    action = Column(String, default="WATCH")
    time_window = Column(String)
    portfolio_overlap = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class ThesisScenario(Base):
    __tablename__ = "thesis_scenarios"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thesis_id = Column(UUID(as_uuid=True), ForeignKey("theses.id"), nullable=False)
    name = Column(String, nullable=False)
    probability = Column(Float)
    prev_probability = Column(Float)
    conditions = Column(JSON, default=list)
    price_range = Column(String)


class ThesisCondition(Base):
    __tablename__ = "thesis_conditions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thesis_id = Column(UUID(as_uuid=True), ForeignKey("theses.id"), nullable=False)
    condition_type = Column(String, nullable=False)  # required / invalidating
    description = Column(Text)


class PaperTrade(Base):
    __tablename__ = "paper_trades"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thesis_id = Column(UUID(as_uuid=True), ForeignKey("theses.id"))
    ticker = Column(String)
    action = Column(String)
    shares = Column(Float)
    price = Column(Float)
    costs = Column(Float, default=0)
    executed_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class DecisionLog(Base):
    __tablename__ = "decision_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thesis_id = Column(UUID(as_uuid=True), ForeignKey("theses.id"))
    decision = Column(String)
    reason_summary = Column(Text)
    counterevidence_summary = Column(Text)
    input_data_cutoff_time = Column(DateTime(timezone=True))
    # Phase 1: v2 schema additions
    event_subtype = Column(String)
    event_stage = Column(String, default="detected")
    expectedness = Column(String, default="unknown")
    novelty_score = Column(Float, default=0.5)
    materiality_score = Column(Float, default=0.5)
    reversibility = Column(String, default="unknown")
    recurrence_pattern = Column(String, default="unknown")
    causal_scope = Column(String, default="unknown")
    geographic_scope = Column(String, default="global")
    affected_time_horizon = Column(String, default="unknown")
    official_confirmation_status = Column(String, default="unconfirmed")
    fact_confidence = Column(Float, default=0.5)
    revision_risk = Column(String, default="low")
    market_expectation_score = Column(Float, default=0.5)
    linked_claim_ids = Column(JSON, default=list)

    source_document_ids = Column(ARRAY(UUID(as_uuid=True)), default=list)
    evidence_ids = Column(ARRAY(UUID(as_uuid=True)), default=list)
    ontology_version = Column(String)
    prompt_version = Column(String)
    model_version = Column(String)
    human_approval_state = Column(String, default="pending")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ModelRun(Base):
    __tablename__ = "model_runs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_type = Column(String)
    model_name = Column(String)
    prompt_version = Column(String)
    input_hash = Column(String)
    output_json = Column(JSON)
    cost_usd = Column(Float)
    latency_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_name = Column(String)
    version = Column(String)
    prompt_text = Column(Text)
    model = Column(String)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_name = Column(String, nullable=False)
    status = Column(String, default="running")  # running | completed | failed
    config = Column(JSON, default=dict)
    result_summary = Column(JSON, default=dict)
    snapshot_summary = Column(JSON, default=dict)
    predictions_generated = Column(Integer, default=0)
    predictions_resolved = Column(Integer, default=0)
    brier_score = Column(Float)
    log_loss = Column(Float)
    calibration_curve = Column(JSON, default=list)
    failure_analysis = Column(JSON, default=list)
    improvement_decision = Column(String, default="No Change")
    model_version = Column(String, default="")
    prompt_version = Column(String, default="")
    schema_version = Column(String, default="")
    started_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)



class Claim(Base):
    __tablename__ = "claims"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_text = Column(Text)
    claim_text_ko = Column(Text)
    claim_type = Column(String)
    claimant = Column(String)
    target_entities = Column(JSON, default=list)
    first_seen_time = Column(DateTime(timezone=True), default=datetime.utcnow)
    source_cluster = Column(JSON, default=list)
    propagation_speed = Column(Float, default=0)
    mention_volume = Column(Integer, default=0)
    confirmation_status = Column(String, default="unverified")
    official_response = Column(Text)
    historical_source_accuracy = Column(Float, default=0)
    manipulation_risk = Column(String, default="low")
    linked_event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"))
    source_document_ids = Column(JSON, default=list)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Rumor(Base):
    __tablename__ = "rumors"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_text = Column(Text)
    claim_text_ko = Column(Text)
    origin = Column(String)
    first_seen_time = Column(DateTime(timezone=True), default=datetime.utcnow)
    propagation_speed = Column(Float, default=0)
    mention_volume = Column(Integer, default=0)
    source_cluster = Column(JSON, default=list)
    associated_entities = Column(JSON, default=list)
    confirmation_status = Column(String, default="unverified")
    official_response = Column(Text)
    price_reaction_after_spread = Column(Float)
    historical_source_accuracy = Column(Float, default=0)
    manipulation_risk = Column(String, default="low")
    linked_event_ids = Column(JSON, default=list)
    linked_claim_ids = Column(JSON, default=list)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    # Point-in-Time integrity fields (spec XXXI-XXXII)
    effective_time = Column(DateTime(timezone=True))
    publish_time = Column(DateTime(timezone=True))
    observed_time = Column(DateTime(timezone=True))
    ingested_time = Column(DateTime(timezone=True), default=datetime.utcnow)
    revision_time = Column(DateTime(timezone=True))
    valid_from = Column(DateTime(timezone=True))
    valid_to = Column(DateTime(timezone=True))
    backtest_available_time = Column(DateTime(timezone=True))


class Scenario(Base):
    __tablename__ = "scenarios"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thesis_id = Column(UUID(as_uuid=True), ForeignKey("theses.id", ondelete="CASCADE"))
    scenario_name = Column(String, nullable=False)
    scenario_type = Column(String, default="system")
    source = Column(String, default="")
    conditions = Column(JSON, default=list)
    trigger_chain = Column(JSON, default=list)
    expected_market_response = Column(Text)
    affected_assets = Column(JSON, default=list)
    probability_estimate = Column(Float, default=0)
    probability_basis = Column(String, default="")
    upside_case = Column(Text)
    downside_case = Column(Text)
    invalidating_evidence = Column(JSON, default=list)
    confirmation_events = Column(JSON, default=list)
    expected_value_range = Column(String, default="")
    confidence_level = Column(String, default="low")
    time_horizon = Column(String, default="unknown")
    status = Column(String, default="active")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    # Point-in-Time integrity fields (spec XXXI-XXXII)
    effective_time = Column(DateTime(timezone=True))
    publish_time = Column(DateTime(timezone=True))
    observed_time = Column(DateTime(timezone=True))
    ingested_time = Column(DateTime(timezone=True), default=datetime.utcnow)
    revision_time = Column(DateTime(timezone=True))
    valid_from = Column(DateTime(timezone=True))
    valid_to = Column(DateTime(timezone=True))
    backtest_available_time = Column(DateTime(timezone=True))


class Exposure(Base):
    __tablename__ = "exposures"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thesis_id = Column(UUID(as_uuid=True), ForeignKey("theses.id", ondelete="CASCADE"))
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"))
    entity_name = Column(String)
    ticker = Column(String)
    exposure_tier = Column(String)
    relationship_type = Column(String)
    direction_of_impact = Column(String)
    economic_mechanism = Column(Text)
    estimated_materiality = Column(Float)
    time_horizon = Column(String)
    source_of_relationship = Column(Text)
    relationship_confidence = Column(Float, default=0.5)
    alternative_explanations = Column(Text)
    evidence_grade = Column(String, default="E1")
    status = Column(String, default="proposed")
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class CandidateEdge(Base):
    __tablename__ = "candidate_edges"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_node_id = Column(UUID(as_uuid=True), nullable=False)
    from_node_type = Column(String, nullable=False)
    to_node_id = Column(UUID(as_uuid=True), nullable=False)
    to_node_type = Column(String, nullable=False)
    edge_type = Column(String, nullable=False)
    direction = Column(String, default="positive")
    strength = Column(Float, default=0.5)
    confidence = Column(Float, default=0.5)
    status = Column(String, default="proposed")
    evidence_grade = Column(String, default="C0")
    supporting_source_ids = Column(JSON, default=list)
    contradicting_source_ids = Column(JSON, default=list)
    required_conditions = Column(JSON, default=list)
    alternative_paths = Column(JSON, default=list)
    causal_or_associative = Column(String, default="associative")
    connection_rationale = Column(Text)
    evidence_rationale = Column(Text)
    mechanism_rationale = Column(Text)
    time_rationale = Column(Text)
    alternative_explanation = Column(Text)
    uncertainty_note = Column(Text)
    lag_distribution = Column(JSON, default=dict)
    valid_from = Column(DateTime(timezone=True))
    valid_to = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    model_version = Column(String, default="")
    # Point-in-Time integrity fields (spec XXXI-XXXII)
    effective_time = Column(DateTime(timezone=True))
    publish_time = Column(DateTime(timezone=True))
    observed_time = Column(DateTime(timezone=True))
    ingested_time = Column(DateTime(timezone=True), default=datetime.utcnow)
    revision_time = Column(DateTime(timezone=True))
    valid_from = Column(DateTime(timezone=True))
    valid_to = Column(DateTime(timezone=True))
    backtest_available_time = Column(DateTime(timezone=True))


class PredictionRecord(Base):
    __tablename__ = "prediction_records"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thesis_id = Column(UUID(as_uuid=True), ForeignKey("theses.id"))
    scenario_id = Column(UUID(as_uuid=True), ForeignKey("scenarios.id"))
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"))
    claim = Column(Text)
    target_asset = Column(String)
    target_metric = Column(String)
    forecast_horizon = Column(String)
    expected_direction = Column(String)
    expected_range = Column(String)
    conditional_on = Column(JSON, default=list)
    confidence = Column(Float, default=0.5)
    probability_basis = Column(String)
    evidence_at_creation = Column(JSON, default=list)
    falsifiers = Column(JSON, default=list)
    confirmation_events = Column(JSON, default=list)
    market_expectation_snapshot = Column(JSON, default=dict)
    actual_outcome = Column(JSON, nullable=True)
    outcome_timestamp = Column(DateTime(timezone=True))
    calibration_error = Column(Float)
    postmortem = Column(Text)
    model_version = Column(String, default="")
    cutoff_time = Column(DateTime(timezone=True))
    snapshot_version = Column(String, default="")
    backtest_run_id = Column(UUID(as_uuid=True), ForeignKey("backtest_runs.id", ondelete="SET NULL"), nullable=True)
    # Point-in-Time integrity fields (spec XXXI-XXXII)
    effective_time = Column(DateTime(timezone=True))
    publish_time = Column(DateTime(timezone=True))
    observed_time = Column(DateTime(timezone=True))
    ingested_time = Column(DateTime(timezone=True), default=datetime.utcnow)
    revision_time = Column(DateTime(timezone=True))
    valid_from = Column(DateTime(timezone=True))
    valid_to = Column(DateTime(timezone=True))
    backtest_available_time = Column(DateTime(timezone=True))
    status = Column(String, default="active")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
