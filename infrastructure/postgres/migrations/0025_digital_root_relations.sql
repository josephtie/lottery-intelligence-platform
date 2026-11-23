-- Digital Root Relations Storage
-- Stores temporary digital root relation patterns discovered by the analyzer
-- Relations are time-limited and must be continuously validated

-- Extension for UUIDs (if not already present)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Relation types enum
CREATE TYPE digital_root_relation_type AS ENUM (
    'SAME_GAME_SUCCESSIVE',
    'CROSS_GAME_SAME_DAY',
    'TIME_SLOT',
    'ROOT_TRANSITION',
    'POSITION_ASSOCIATION'
);

-- Relation status enum
CREATE TYPE digital_root_relation_status AS ENUM (
    'CANDIDATE',
    'OBSERVING',
    'WEAKENING',
    'EXPIRED',
    'CONFIRMED_TEMPORARY',
    'REJECTED'
);

-- Digital root relations table
CREATE TABLE research.digital_root_relations (
    relation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    relation_type digital_root_relation_type NOT NULL,
    source_game_id UUID REFERENCES catalog.draw_types(draw_type_id),
    target_game_id UUID REFERENCES catalog.draw_types(draw_type_id),
    source_root INTEGER NOT NULL CHECK (source_root >= 0 AND source_root <= 8),
    target_root INTEGER NOT NULL CHECK (target_root >= 0 AND target_root <= 8),
    position INTEGER CHECK (position >= 1 AND position <= 5),
    time_slot VARCHAR(50),

    -- Status and lifecycle
    status digital_root_relation_status NOT NULL DEFAULT 'CANDIDATE',
    discovery_date DATE NOT NULL DEFAULT CURRENT_DATE,
    last_validation_date DATE,
    observation_window_days INTEGER NOT NULL DEFAULT 3,

    -- Evidence
    total_observations INTEGER NOT NULL DEFAULT 0,
    successful_predictions INTEGER NOT NULL DEFAULT 0,
    last_observed_at TIMESTAMP,

    -- Statistical metrics
    baseline_success_rate NUMERIC(5,4) NOT NULL DEFAULT 0.0,
    current_success_rate NUMERIC(5,4) GENERATED ALWAYS AS (
        CASE WHEN total_observations > 0
             THEN successful_predictions::NUMERIC / total_observations
             ELSE 0.0::NUMERIC
        END
    ) STORED,
    statistical_significance NUMERIC(5,4),

    -- Metadata
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT valid_root_range CHECK (source_root BETWEEN 0 AND 8 AND target_root BETWEEN 0 AND 8),
    CONSTRAINT positive_observations CHECK (total_observations >= 0 AND successful_predictions >= 0),
    CONSTRAINT successful_not_exceed_total CHECK (successful_predictions <= total_observations)
);

-- Indexes for efficient queries
CREATE INDEX idx_drr_target_game ON research.digital_root_relations(target_game_id);
CREATE INDEX idx_drr_status ON research.digital_root_relations(status);
CREATE INDEX idx_drr_discovery_date ON research.digital_root_relations(discovery_date);
CREATE INDEX idx_drr_relation_type ON research.digital_root_relations(relation_type);
CREATE INDEX idx_drr_source_target_root ON research.digital_root_relations(source_root, target_root);
CREATE INDEX idx_drr_active ON research.digital_root_relations(target_game_id, status)
    WHERE status IN ('OBSERVING', 'CONFIRMED_TEMPORARY');

-- Digital root predictions table (for audit and analysis)
CREATE TABLE research.digital_root_predictions (
    prediction_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    draw_id UUID NOT NULL REFERENCES core.draws(draw_id),
    draw_type_id UUID NOT NULL REFERENCES catalog.draw_types(draw_type_id),
    scheduled_date DATE NOT NULL,

    -- Prediction details
    predicted_roots JSONB NOT NULL,  -- Array of {root, confidence, uncertainty}
    turbo_variant VARCHAR(20) NOT NULL,
    predicted_numbers INTEGER[] NOT NULL,
    used_relations_count INTEGER NOT NULL DEFAULT 0,

    -- Settlement (nullable until settled)
    winning_numbers INTEGER[],
    hit_count INTEGER,
    turbo_hit BOOLEAN,
    stake NUMERIC(10,2) DEFAULT 100.0,
    payout NUMERIC(10,2) DEFAULT 0.0,
    net_profit NUMERIC(10,2) DEFAULT 0.0,
    roi NUMERIC(10,2),

    -- Metadata
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    settled_at TIMESTAMP,

    -- Constraints
    CONSTRAINT valid_turbo_variant CHECK (turbo_variant IN ('turbo_2', 'turbo_3', 'turbo_4', 'turbo_5')),
    CONSTRAINT non_negative_stake CHECK (stake >= 0),
    CONSTRAINT hit_count_valid CHECK (hit_count >= 0 AND hit_count <= array_length(predicted_numbers, 1))
);

-- Indexes for predictions
CREATE INDEX idx_drp_draw_id ON research.digital_root_predictions(draw_id);
CREATE INDEX idx_drp_draw_type_date ON research.digital_root_predictions(draw_type_id, scheduled_date);
CREATE INDEX idx_drp_created_at ON research.digital_root_predictions(created_at);
CREATE INDEX idx_drp_settled_at ON research.digital_root_predictions(settled_at)
    WHERE settled_at IS NOT NULL;

-- Walk-forward validation results table
CREATE TABLE research.digital_root_validation (
    validation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    validation_run_id UUID NOT NULL,
    draw_type_id UUID NOT NULL REFERENCES catalog.draw_types(draw_type_id),

    -- Validation parameters
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    training_window_days INTEGER NOT NULL,
    test_window_days INTEGER NOT NULL,
    turbo_variant VARCHAR(20) NOT NULL,

    -- Aggregated metrics
    total_predictions INTEGER NOT NULL,
    total_hits INTEGER NOT NULL,
    hit_rate NUMERIC(5,4) NOT NULL,
    turbo_hits INTEGER NOT NULL,
    turbo_hit_rate NUMERIC(5,4) NOT NULL,
    total_stake NUMERIC(12,2) NOT NULL,
    total_payout NUMERIC(12,2) NOT NULL,
    total_net_profit NUMERIC(12,2) NOT NULL,
    average_roi NUMERIC(10,2) NOT NULL,

    -- Baseline comparison
    baseline_hit_rate NUMERIC(5,4) NOT NULL,
    baseline_turbo_hit_rate NUMERIC(5,4) NOT NULL,
    baseline_roi NUMERIC(10,2) NOT NULL,
    hit_rate_improvement_percent NUMERIC(10,2),
    turbo_improvement_percent NUMERIC(10,2),
    roi_improvement NUMERIC(10,2),
    statistically_significant BOOLEAN NOT NULL,

    -- Metadata
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT valid_date_range CHECK (end_date >= start_date),
    CONSTRAINT positive_windows CHECK (training_window_days > 0 AND test_window_days > 0),
    CONSTRAINT valid_rates CHECK (
        hit_rate BETWEEN 0 AND 1 AND
        turbo_hit_rate BETWEEN 0 AND 1 AND
        baseline_hit_rate BETWEEN 0 AND 1 AND
        baseline_turbo_hit_rate BETWEEN 0 AND 1
    )
);

-- Indexes for validation
CREATE INDEX idx_drv_validation_run ON research.digital_root_validation(validation_run_id);
CREATE INDEX idx_drv_draw_type ON research.digital_root_validation(draw_type_id);
CREATE INDEX idx_drv_created_at ON research.digital_root_validation(created_at);

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_digital_root_relations_updated_at
    BEFORE UPDATE ON research.digital_root_relations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Comment on tables
COMMENT ON TABLE research.digital_root_relations IS 'Stores temporary digital root relation patterns discovered by the analyzer';
COMMENT ON TABLE research.digital_root_predictions IS 'Stores digital root predictions for audit and analysis';
COMMENT ON TABLE research.digital_root_validation IS 'Stores walk-forward validation results for digital root predictions';
