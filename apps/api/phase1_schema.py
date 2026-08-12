from api.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# 1. ADD COLUMNS to events
event_cols = [
    ("event_subtype", "VARCHAR"), ("event_stage", "VARCHAR DEFAULT 'detected'"),
    ("expectedness", "VARCHAR DEFAULT 'unknown'"), ("novelty_score", "FLOAT DEFAULT 0.5"),
    ("materiality_score", "FLOAT DEFAULT 0.5"), ("reversibility", "VARCHAR DEFAULT 'unknown'"),
    ("recurrence_pattern", "VARCHAR DEFAULT 'unknown'"), ("causal_scope", "VARCHAR DEFAULT 'unknown'"),
    ("geographic_scope", "VARCHAR DEFAULT 'global'"), ("affected_time_horizon", "VARCHAR DEFAULT 'unknown'"),
    ("official_confirmation_status", "VARCHAR DEFAULT 'unconfirmed'"), ("fact_confidence", "FLOAT DEFAULT 0.5"),
    ("revision_risk", "VARCHAR DEFAULT 'low'"), ("market_expectation_score", "FLOAT DEFAULT 0.5"),
    ("linked_claim_ids", "JSON DEFAULT '[]'"),
]
for cn, ct in event_cols:
    try: db.execute(text(f"ALTER TABLE events ADD COLUMN IF NOT EXISTS {cn} {ct}")); print(f"  + {cn}")
    except Exception as e: print(f"  skip {cn}: {e}")
db.commit()
print("1. events extended")

# 2. Claim table
db.execute(text("""CREATE TABLE IF NOT EXISTS claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), claim_text TEXT, claim_text_ko TEXT,
    claim_type VARCHAR, claimant VARCHAR, target_entities JSON DEFAULT '[]',
    first_seen_time TIMESTAMPTZ DEFAULT NOW(), source_cluster JSON DEFAULT '[]',
    propagation_speed FLOAT DEFAULT 0, mention_volume INT DEFAULT 0,
    confirmation_status VARCHAR DEFAULT 'unverified', official_response TEXT,
    historical_source_accuracy FLOAT DEFAULT 0, manipulation_risk VARCHAR DEFAULT 'low',
    linked_event_id UUID REFERENCES events(id), source_document_ids JSON DEFAULT '[]',
    metadata_json JSON DEFAULT '{}', created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
)"""))
db.commit(); print("2. claims created")

# 3. Rumor table
db.execute(text("""CREATE TABLE IF NOT EXISTS rumors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), claim_text TEXT, claim_text_ko TEXT,
    origin VARCHAR, first_seen_time TIMESTAMPTZ DEFAULT NOW(), propagation_speed FLOAT DEFAULT 0,
    mention_volume INT DEFAULT 0, source_cluster JSON DEFAULT '[]', associated_entities JSON DEFAULT '[]',
    confirmation_status VARCHAR DEFAULT 'unverified', official_response TEXT,
    price_reaction_after_spread FLOAT, historical_source_accuracy FLOAT DEFAULT 0,
    manipulation_risk VARCHAR DEFAULT 'low', linked_event_ids JSON DEFAULT '[]',
    linked_claim_ids JSON DEFAULT '[]', metadata_json JSON DEFAULT '{}', created_at TIMESTAMPTZ DEFAULT NOW()
)"""))
db.commit(); print("3. rumors created")

# 4. Scenario table (v2)
db.execute(text("""CREATE TABLE IF NOT EXISTS scenarios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), thesis_id UUID REFERENCES theses(id) ON DELETE CASCADE,
    scenario_name VARCHAR NOT NULL, scenario_type VARCHAR DEFAULT 'system', source VARCHAR DEFAULT '',
    conditions JSON DEFAULT '[]', trigger_chain JSON DEFAULT '[]', expected_market_response TEXT,
    affected_assets JSON DEFAULT '[]', probability_estimate FLOAT DEFAULT 0, probability_basis VARCHAR DEFAULT '',
    upside_case TEXT, downside_case TEXT, invalidating_evidence JSON DEFAULT '[]',
    confirmation_events JSON DEFAULT '[]', expected_value_range VARCHAR DEFAULT '',
    confidence_level VARCHAR DEFAULT 'low', time_horizon VARCHAR DEFAULT 'unknown',
    status VARCHAR DEFAULT 'active', created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
)"""))
db.commit(); print("4. scenarios created")

# 5. Exposure table
db.execute(text("""CREATE TABLE IF NOT EXISTS exposures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), thesis_id UUID REFERENCES theses(id) ON DELETE CASCADE,
    event_id UUID REFERENCES events(id), entity_name VARCHAR, ticker VARCHAR,
    exposure_tier VARCHAR, relationship_type VARCHAR, direction_of_impact VARCHAR,
    economic_mechanism TEXT, estimated_materiality FLOAT, time_horizon VARCHAR,
    source_of_relationship TEXT, relationship_confidence FLOAT DEFAULT 0.5,
    alternative_explanations TEXT, evidence_grade VARCHAR DEFAULT 'E1',
    status VARCHAR DEFAULT 'proposed', metadata_json JSON DEFAULT '{}', created_at TIMESTAMPTZ DEFAULT NOW()
)"""))
db.commit(); print("5. exposures created")

# 6. CandidateEdge
db.execute(text("""CREATE TABLE IF NOT EXISTS candidate_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), from_node_id UUID NOT NULL,
    from_node_type VARCHAR NOT NULL, to_node_id UUID NOT NULL, to_node_type VARCHAR NOT NULL,
    edge_type VARCHAR NOT NULL, direction VARCHAR DEFAULT 'positive', strength FLOAT DEFAULT 0.5,
    confidence FLOAT DEFAULT 0.5, status VARCHAR DEFAULT 'proposed', evidence_grade VARCHAR DEFAULT 'C0',
    supporting_source_ids JSON DEFAULT '[]', contradicting_source_ids JSON DEFAULT '[]',
    required_conditions JSON DEFAULT '[]', alternative_paths JSON DEFAULT '[]',
    causal_or_associative VARCHAR DEFAULT 'associative', connection_rationale TEXT,
    evidence_rationale TEXT, mechanism_rationale TEXT, time_rationale TEXT,
    alternative_explanation TEXT, uncertainty_note TEXT, lag_distribution JSON DEFAULT '{}',
    valid_from TIMESTAMPTZ, valid_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), model_version VARCHAR DEFAULT ''
)"""))
db.commit(); print("6. candidate_edges created")

# 7. PredictionRecord
db.execute(text("""CREATE TABLE IF NOT EXISTS prediction_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), thesis_id UUID REFERENCES theses(id),
    scenario_id UUID REFERENCES scenarios(id), event_id UUID REFERENCES events(id),
    claim TEXT, target_asset VARCHAR, target_metric VARCHAR, forecast_horizon VARCHAR,
    expected_direction VARCHAR, expected_range VARCHAR, conditional_on JSON DEFAULT '[]',
    confidence FLOAT DEFAULT 0.5, probability_basis VARCHAR, evidence_at_creation JSON DEFAULT '[]',
    falsifiers JSON DEFAULT '[]', confirmation_events JSON DEFAULT '[]',
    market_expectation_snapshot JSON DEFAULT '{}', actual_outcome JSON DEFAULT NULL,
    outcome_timestamp TIMESTAMPTZ, calibration_error FLOAT, postmortem TEXT,
    model_version VARCHAR DEFAULT '', status VARCHAR DEFAULT 'active', created_at TIMESTAMPTZ DEFAULT NOW()
)"""))
db.commit(); print("7. prediction_records created")

# 8. Enrich event_relations
er_cols = [
    ("direction", "VARCHAR DEFAULT 'positive'"), ("confidence", "FLOAT DEFAULT 0.5"),
    ("lag_distribution", "JSON DEFAULT '{}'"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"),
    ("supporting_source_ids", "JSON DEFAULT '[]'"), ("contradicting_source_ids", "JSON DEFAULT '[]'"),
    ("required_conditions", "JSON DEFAULT '[]'"), ("alternative_paths", "JSON DEFAULT '[]'"),
    ("causal_or_associative", "VARCHAR DEFAULT 'associative'"), ("connection_rationale", "TEXT"),
    ("evidence_rationale", "TEXT"), ("mechanism_rationale", "TEXT"), ("time_rationale", "TEXT"),
    ("alternative_explanation", "TEXT"), ("uncertainty_note", "TEXT"),
    ("updated_at", "TIMESTAMPTZ DEFAULT NOW()"),
]
for cn, ct in er_cols:
    try: db.execute(text(f"ALTER TABLE event_relations ADD COLUMN IF NOT EXISTS {cn} {ct}")); print(f"  + {cn}")
    except Exception as e: print(f"  skip {cn}: {e}")
db.commit(); print("8. event_relations enriched")

# Verify
result = db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"))
for r in result: print(f"  {r[0]}")
db.close()
print("\nPhase 1 complete")
