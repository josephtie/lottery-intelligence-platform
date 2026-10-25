-- AGENT SYSTEM - Autonomous Agents with Individual Persistent Memory
-- LOTTERY EDGE LAB
-- This migration creates the database schema for ten autonomous agents
-- with individual persistent memory, virtual capital, and decision-making capabilities.

CREATE SCHEMA IF NOT EXISTS edge_lab;

-- ============================================================================
-- 1. AGENT IDENTITY AND CONFIGURATION
-- ============================================================================

CREATE TABLE edge_lab.agents (
    agent_id UUID PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 1 CHECK (generation > 0),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'PAUSED', 'RETIRED', 'SUSPENDED')),
    mission TEXT NOT NULL,
    specialties JSONB NOT NULL DEFAULT '[]'::JSONB,
    objectives JSONB NOT NULL DEFAULT '[]'::JSONB,
    preferred_methods JSONB NOT NULL DEFAULT '[]'::JSONB,
    operational_level TEXT NOT NULL DEFAULT 'DECISION' CHECK (operational_level IN ('DECISION', 'RESEARCH', 'EVOLUTION')),
    autonomy_config JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(code)) > 0),
    CHECK (length(trim(display_name)) > 0),
    CHECK (length(trim(mission)) > 0),
    CHECK (jsonb_typeof(specialties) = 'array'),
    CHECK (jsonb_typeof(objectives) = 'array'),
    CHECK (jsonb_typeof(preferred_methods) = 'array'),
    CHECK (jsonb_typeof(autonomy_config) = 'object')
);

CREATE INDEX agents_status_idx ON edge_lab.agents (status);
CREATE INDEX agents_generation_idx ON edge_lab.agents (generation);
CREATE INDEX agents_operational_level_idx ON edge_lab.agents (operational_level);

-- Agent versions for evolution tracking
CREATE TABLE edge_lab.agent_versions (
    agent_version_id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES edge_lab.agents(agent_id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    previous_version_id UUID REFERENCES edge_lab.agent_versions(agent_version_id),
    change_reason TEXT NOT NULL,
    configuration_changes JSONB NOT NULL DEFAULT '{}'::JSONB,
    performance_before JSONB,
    performance_after JSONB,
    validation_criteria JSONB NOT NULL DEFAULT '{}'::JSONB,
    validation_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (validation_status IN ('PENDING', 'VALIDATED', 'REJECTED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (agent_id, version_number),
    CHECK (length(trim(change_reason)) > 0),
    CHECK (jsonb_typeof(configuration_changes) = 'object'),
    CHECK (jsonb_typeof(validation_criteria) = 'object')
);

CREATE INDEX agent_versions_agent_idx ON edge_lab.agent_versions (agent_id, version_number);
CREATE INDEX agent_versions_status_idx ON edge_lab.agent_versions (validation_status);

-- ============================================================================
-- 2. MEMORY COMPARTMENT 1: IDENTITY MEMORY
-- ============================================================================

CREATE TABLE edge_lab.memory_identity (
    memory_id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES edge_lab.agents(agent_id) ON DELETE CASCADE,
    agent_version_id UUID REFERENCES edge_lab.agent_versions(agent_version_id),
    mission TEXT NOT NULL,
    specialties JSONB NOT NULL DEFAULT '[]'::JSONB,
    objectives JSONB NOT NULL DEFAULT '[]'::JSONB,
    preferred_methods JSONB NOT NULL DEFAULT '[]'::JSONB,
    constraints JSONB NOT NULL DEFAULT '{}'::JSONB,
    version_summary TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(mission)) > 0),
    CHECK (jsonb_typeof(specialties) = 'array'),
    CHECK (jsonb_typeof(objectives) = 'array'),
    CHECK (jsonb_typeof(preferred_methods) = 'array'),
    CHECK (jsonb_typeof(constraints) = 'object'),
    CHECK (length(trim(version_summary)) > 0)
);

CREATE INDEX memory_identity_agent_idx ON edge_lab.memory_identity (agent_id, recorded_at DESC);

-- ============================================================================
-- 3. MEMORY COMPARTMENT 2: HYPOTHESES MEMORY
-- ============================================================================

CREATE TABLE edge_lab.memory_hypotheses (
    hypothesis_id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES edge_lab.agents(agent_id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    title TEXT NOT NULL,
    statement TEXT NOT NULL,
    justification TEXT NOT NULL,
    predicted_outcome JSONB NOT NULL DEFAULT '{}'::JSONB,
    counter_hypothesis TEXT,
    refutation_criteria JSONB NOT NULL DEFAULT '[]'::JSONB,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'TESTING', 'SUPPORTED', 'REJECTED', 'INCONCLUSIVE', 'ABANDONED')),
    confidence_level NUMERIC(5,4) CHECK (confidence_level BETWEEN 0 AND 1),
    origin TEXT NOT NULL DEFAULT 'SELF' CHECK (origin IN ('SELF', 'COLLECTIVE', 'EXTERNAL')),
    origin_agent_id UUID REFERENCES edge_lab.agents(agent_id),
    origin_knowledge_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(code)) > 0),
    CHECK (length(trim(title)) > 0),
    CHECK (length(trim(statement)) > 0),
    CHECK (length(trim(justification)) > 0),
    CHECK (jsonb_typeof(predicted_outcome) = 'object'),
    CHECK (jsonb_typeof(refutation_criteria) = 'array')
);

CREATE INDEX memory_hypotheses_agent_idx ON edge_lab.memory_hypotheses (agent_id, status, created_at DESC);
CREATE INDEX memory_hypotheses_code_idx ON edge_lab.memory_hypotheses (agent_id, code);
CREATE INDEX memory_hypotheses_origin_idx ON edge_lab.memory_hypotheses (origin, origin_agent_id, origin_knowledge_id);

-- ============================================================================
-- 4. MEMORY COMPARTMENT 3: EXPERIMENTS MEMORY
-- ============================================================================

CREATE TABLE edge_lab.memory_experiments (
    experiment_id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES edge_lab.agents(agent_id) ON DELETE CASCADE,
    hypothesis_id UUID REFERENCES edge_lab.memory_hypotheses(hypothesis_id),
    dataset_version_id UUID REFERENCES datasets.dataset_versions(dataset_version_id),
    model_version_id UUID REFERENCES research.model_versions(model_version_id),
    strategy_version_id UUID REFERENCES research.strategy_versions(strategy_version_id),
    test_period_start DATE NOT NULL,
    test_period_end DATE NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::JSONB,
    results JSONB NOT NULL DEFAULT '{}'::JSONB,
    comparative_reference JSONB,
    validation_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (validation_status IN ('PENDING', 'VALIDATED', 'REJECTED', 'INCONCLUSIVE')),
    scope TEXT NOT NULL CHECK (scope IN ('HISTORICAL', 'OUT_OF_SAMPLE', 'PROSPECTIVE', 'WALK_FORWARD')),
    reproducible BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    CHECK (jsonb_typeof(parameters) = 'object'),
    CHECK (jsonb_typeof(results) = 'object'),
    CHECK (test_period_start <= test_period_end)
);

CREATE INDEX memory_experiments_agent_idx ON edge_lab.memory_experiments (agent_id, created_at DESC);
CREATE INDEX memory_experiments_hypothesis_idx ON edge_lab.memory_experiments (hypothesis_id);
CREATE INDEX memory_experiments_status_idx ON edge_lab.memory_experiments (validation_status);
CREATE INDEX memory_experiments_scope_idx ON edge_lab.memory_experiments (scope);

-- ============================================================================
-- 5. MEMORY COMPARTMENT 4: SUCCESSES MEMORY
-- ============================================================================

CREATE TABLE edge_lab.memory_successes (
    success_id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES edge_lab.agents(agent_id) ON DELETE CASCADE,
    experiment_id UUID REFERENCES edge_lab.memory_experiments(experiment_id),
    hypothesis_id UUID REFERENCES edge_lab.memory_hypotheses(hypothesis_id),
    strategy_description TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    metrics JSONB NOT NULL DEFAULT '{}'::JSONB,
    uncertainty_estimate NUMERIC(5,4) CHECK (uncertainty_estimate BETWEEN 0 AND 1),
    out_of_sample_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    prospective_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    replication_count INTEGER NOT NULL DEFAULT 0 CHECK (replication_count >= 0),
    notes TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(strategy_description)) > 0),
    CHECK (jsonb_typeof(metrics) = 'object'),
    CHECK (period_start <= period_end)
);

CREATE INDEX memory_successes_agent_idx ON edge_lab.memory_successes (agent_id, recorded_at DESC);
CREATE INDEX memory_successes_experiment_idx ON edge_lab.memory_successes (experiment_id);
CREATE INDEX memory_successes_confirmed_idx ON edge_lab.memory_successes (out_of_sample_confirmed, prospective_confirmed);

-- ============================================================================
-- 6. MEMORY COMPARTMENT 5: FAILURES MEMORY
-- ============================================================================

CREATE TABLE edge_lab.memory_failures (
    failure_id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES edge_lab.agents(agent_id) ON DELETE CASCADE,
    experiment_id UUID REFERENCES edge_lab.memory_experiments(experiment_id),
    hypothesis_id UUID REFERENCES edge_lab.memory_hypotheses(hypothesis_id),
    failure_type TEXT NOT NULL CHECK (failure_type IN ('HYPOTHESIS_REFUTED', 'STRATEGY_DEFICIT', 'CALIBRATION_ERROR', 'CAPITAL_LOSS', 'DATA_ISSUE', 'OTHER')),
    description TEXT NOT NULL,
    conditions JSONB NOT NULL DEFAULT '{}'::JSONB,
    loss_amount NUMERIC(15,2),
    conditions_of_failure TEXT NOT NULL,
    abandonment_reason TEXT NOT NULL,
    lessons_learned TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(description)) > 0),
    CHECK (jsonb_typeof(conditions) = 'object'),
    CHECK (length(trim(conditions_of_failure)) > 0),
    CHECK (length(trim(abandonment_reason)) > 0)
);

CREATE INDEX memory_failures_agent_idx ON edge_lab.memory_failures (agent_id, recorded_at DESC);
CREATE INDEX memory_failures_type_idx ON edge_lab.memory_failures (failure_type);
CREATE INDEX memory_failures_experiment_idx ON edge_lab.memory_failures (experiment_id);

-- ============================================================================
-- 7. MEMORY COMPARTMENT 6: CHANGES MEMORY
-- ============================================================================

CREATE TABLE edge_lab.memory_changes (
    change_id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES edge_lab.agents(agent_id) ON DELETE CASCADE,
    agent_version_id UUID REFERENCES edge_lab.agent_versions(agent_version_id),
    change_type TEXT NOT NULL CHECK (change_type IN ('PARAMETER_ADJUSTMENT', 'MODEL_REPLACEMENT', 'STRATEGY_REPLACEMENT', 'GENERATION_PROMOTION', 'NEW_AGENT_PROPOSAL', 'CAPITAL_REALLOCATION', 'OTHER')),
    reason TEXT NOT NULL,
    before_state JSONB NOT NULL DEFAULT '{}'::JSONB,
    after_state JSONB NOT NULL DEFAULT '{}'::JSONB,
    comparison_metrics JSONB NOT NULL DEFAULT '{}'::JSONB,
    decision_rationale TEXT NOT NULL,
    expected_impact TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(reason)) > 0),
    CHECK (jsonb_typeof(before_state) = 'object'),
    CHECK (jsonb_typeof(after_state) = 'object'),
    CHECK (jsonb_typeof(comparison_metrics) = 'object'),
    CHECK (length(trim(decision_rationale)) > 0)
);

CREATE INDEX memory_changes_agent_idx ON edge_lab.memory_changes (agent_id, recorded_at DESC);
CREATE INDEX memory_changes_type_idx ON edge_lab.memory_changes (change_type);
CREATE INDEX memory_changes_version_idx ON edge_lab.memory_changes (agent_version_id);

-- ============================================================================
-- 8. MEMORY COMPARTMENT 7: CALIBRATION MEMORY
-- ============================================================================

CREATE TABLE edge_lab.memory_calibration (
    calibration_id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES edge_lab.agents(agent_id) ON DELETE CASCADE,
    model_version_id UUID REFERENCES research.model_versions(model_version_id),
    strategy_version_id UUID REFERENCES research.strategy_versions(strategy_version_id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    estimated_probabilities JSONB NOT NULL DEFAULT '{}'::JSONB,
    observed_outcomes JSONB NOT NULL DEFAULT '{}'::JSONB,
    calibration_error NUMERIC(10,6),
    signal_reliability NUMERIC(5,4) CHECK (signal_reliability BETWEEN 0 AND 1),
    uncertainty_degree TEXT NOT NULL CHECK (uncertainty_degree IN ('LOW', 'MEDIUM', 'HIGH', 'UNKNOWN')),
    brier_score NUMERIC(10,6),
    reliability_curve JSONB,
    notes TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (jsonb_typeof(estimated_probabilities) = 'object'),
    CHECK (jsonb_typeof(observed_outcomes) = 'object'),
    CHECK (period_start <= period_end)
);

CREATE INDEX memory_calibration_agent_idx ON edge_lab.memory_calibration (agent_id, recorded_at DESC);
CREATE INDEX memory_calibration_model_idx ON edge_lab.memory_calibration (model_version_id);
CREATE INDEX memory_calibration_uncertainty_idx ON edge_lab.memory_calibration (uncertainty_degree);

-- ============================================================================
-- 9. MEMORY COMPARTMENT 8: RISK MEMORY
-- ============================================================================

CREATE TABLE edge_lab.memory_risk (
    risk_record_id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES edge_lab.agents(agent_id) ON DELETE CASCADE,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    drawdown_max NUMERIC(15,2),
    drawdown_current NUMERIC(15,2),
    volatility NUMERIC(10,6),
    exposure_by_market JSONB NOT NULL DEFAULT '{}'::JSONB,
    average_stake_size NUMERIC(15,2),
    max_stake_size NUMERIC(15,2),
    stop_threshold_triggered BOOLEAN NOT NULL DEFAULT FALSE,
    stop_threshold_value NUMERIC(15,2),
    losing_streak_max INTEGER,
    losing_streak_current INTEGER,
    risk_limit_encountered TEXT,
    capital_at_risk NUMERIC(5,4) CHECK (capital_at_risk BETWEEN 0 AND 1),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (jsonb_typeof(exposure_by_market) = 'object'),
    CHECK (period_start <= period_end)
);

CREATE INDEX memory_risk_agent_idx ON edge_lab.memory_risk (agent_id, recorded_at DESC);
CREATE INDEX memory_risk_drawdown_idx ON edge_lab.memory_risk (drawdown_max DESC);

-- ============================================================================
-- 10. VIRTUAL CAPITAL MANAGEMENT
-- ============================================================================

CREATE TABLE edge_lab.agent_capital (
    capital_id UUID PRIMARY KEY,
    agent_id UUID NOT NULL UNIQUE REFERENCES edge_lab.agents(agent_id) ON DELETE CASCADE,
    initial_capital NUMERIC(15,2) NOT NULL DEFAULT 100000.00,
    current_capital NUMERIC(15,2) NOT NULL DEFAULT 100000.00,
    total_profit NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    total_loss NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    net_profit NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    roi NUMERIC(10,6) NOT NULL DEFAULT 0.00,
    total_bets INTEGER NOT NULL DEFAULT 0 CHECK (total_bets >= 0),
    winning_bets INTEGER NOT NULL DEFAULT 0 CHECK (winning_bets >= 0),
    losing_bets INTEGER NOT NULL DEFAULT 0 CHECK (losing_bets >= 0),
    no_bet_count INTEGER NOT NULL DEFAULT 0 CHECK (no_bet_count >= 0),
    max_drawdown NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    max_drawdown_date DATE,
    peak_capital NUMERIC(15,2) NOT NULL DEFAULT 100000.00,
    peak_capital_date DATE,
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (initial_capital > 0),
    CHECK (current_capital >= 0)
);

CREATE INDEX agent_capital_roi_idx ON edge_lab.agent_capital (roi DESC);

-- ============================================================================
-- 11. DECISION SYSTEM (SEALED DECISIONS)
-- ============================================================================

CREATE TABLE edge_lab.agent_decisions (
    decision_id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES edge_lab.agents(agent_id) ON DELETE CASCADE,
    draw_id UUID NOT NULL REFERENCES core.draws(draw_id),
    draw_type_id UUID NOT NULL REFERENCES catalog.draw_types(draw_type_id),
    decision_type TEXT NOT NULL CHECK (decision_type IN ('BET', 'NO_BET')),
    selected_numbers INTEGER[] NOT NULL,
    stake_amount NUMERIC(15,2) NOT NULL,
    reasoning TEXT NOT NULL,
    confidence_score NUMERIC(5,4) CHECK (confidence_score BETWEEN 0 AND 1),
    hypothesis_ids UUID[] NOT NULL DEFAULT '{}',
    model_version_ids UUID[] NOT NULL DEFAULT '{}',
    strategy_version_ids UUID[] NOT NULL DEFAULT '{}',
    expected_outcome JSONB NOT NULL DEFAULT '{}'::JSONB,
    risk_assessment JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sealed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_sealed BOOLEAN NOT NULL DEFAULT TRUE,
    cutoff_respected BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (jsonb_typeof(expected_outcome) = 'object'),
    CHECK (jsonb_typeof(risk_assessment) = 'object'),
    CHECK (cardinality(selected_numbers) > 0 OR decision_type = 'NO_BET'),
    CHECK (stake_amount >= 0)
);

CREATE INDEX agent_decisions_agent_idx ON edge_lab.agent_decisions (agent_id, sealed_at DESC);
CREATE INDEX agent_decisions_draw_idx ON edge_lab.agent_decisions (draw_id);
CREATE INDEX agent_decisions_sealed_idx ON edge_lab.agent_decisions (is_sealed, sealed_at);

-- Decision outcomes (settlement)
CREATE TABLE edge_lab.decision_outcomes (
    outcome_id UUID PRIMARY KEY,
    decision_id UUID NOT NULL UNIQUE REFERENCES edge_lab.agent_decisions(decision_id),
    draw_version_id UUID NOT NULL REFERENCES core.draw_versions(draw_version_id),
    winning_numbers INTEGER[] NOT NULL,
    hit_count INTEGER NOT NULL CHECK (hit_count >= 0),
    positional_hits JSONB NOT NULL DEFAULT '{}'::JSONB,
    stake_returned NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    payout NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    net_result NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    outcome_type TEXT NOT NULL CHECK (outcome_type IN ('WIN', 'LOSS', 'NO_BET')),
    settlement_details JSONB NOT NULL DEFAULT '{}'::JSONB,
    settled_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (jsonb_typeof(positional_hits) = 'object'),
    CHECK (jsonb_typeof(settlement_details) = 'object')
);

CREATE INDEX decision_outcomes_decision_idx ON edge_lab.decision_outcomes (decision_id);
CREATE INDEX decision_outcomes_settled_idx ON edge_lab.decision_outcomes (settled_at DESC);

-- ============================================================================
-- 12. COLLECTIVE MEMORY (SHARED KNOWLEDGE)
-- ============================================================================

CREATE TABLE edge_lab.collective_knowledge (
    knowledge_id UUID PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    knowledge_type TEXT NOT NULL CHECK (knowledge_type IN ('REPRODUCIBLE_EXPERIMENT', 'REFUTED_STRATEGY', 'STATISTICAL_TRAP', 'VALIDATED_METHOD', 'BEST_PRACTICE', 'WARNING')),
    content TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::JSONB,
    proof_level TEXT NOT NULL DEFAULT 'UNVERIFIED' CHECK (proof_level IN ('UNVERIFIED', 'REPRODUCED', 'VALIDATED', 'CONFIRMED')),
    originating_agent_id UUID NOT NULL REFERENCES edge_lab.agents(agent_id),
    originating_experiment_id UUID,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    parent_knowledge_id UUID REFERENCES edge_lab.collective_knowledge(knowledge_id),
    validation_count INTEGER NOT NULL DEFAULT 0 CHECK (validation_count >= 0),
    rejection_count INTEGER NOT NULL DEFAULT 0 CHECK (rejection_count >= 0),
    last_validated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(code)) > 0),
    CHECK (length(trim(title)) > 0),
    CHECK (length(trim(content)) > 0),
    CHECK (jsonb_typeof(evidence) = 'object')
);

CREATE INDEX collective_knowledge_type_idx ON edge_lab.collective_knowledge (knowledge_type, proof_level);
CREATE INDEX collective_knowledge_agent_idx ON edge_lab.collective_knowledge (originating_agent_id);
CREATE INDEX collective_knowledge_proof_idx ON edge_lab.collective_knowledge (proof_level, validation_count DESC);

-- Knowledge adoption by agents
CREATE TABLE edge_lab.knowledge_adoption (
    adoption_id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES edge_lab.agents(agent_id) ON DELETE CASCADE,
    knowledge_id UUID NOT NULL REFERENCES edge_lab.collective_knowledge(knowledge_id) ON DELETE CASCADE,
    adoption_reason TEXT NOT NULL,
    validation_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (validation_status IN ('PENDING', 'VALIDATED', 'REJECTED', 'INCONCLUSIVE')),
    validation_results JSONB NOT NULL DEFAULT '{}'::JSONB,
    adopted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    validated_at TIMESTAMPTZ,
    UNIQUE (agent_id, knowledge_id),
    CHECK (length(trim(adoption_reason)) > 0),
    CHECK (jsonb_typeof(validation_results) = 'object')
);

CREATE INDEX knowledge_adoption_agent_idx ON edge_lab.knowledge_adoption (agent_id, validation_status);
CREATE INDEX knowledge_adoption_knowledge_idx ON edge_lab.knowledge_adoption (knowledge_id);

-- ============================================================================
-- 13. AGENT REFLECTION LOG
-- ============================================================================

CREATE TABLE edge_lab.agent_reflections (
    reflection_id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES edge_lab.agents(agent_id) ON DELETE CASCADE,
    reflection_type TEXT NOT NULL CHECK (reflection_type IN ('PRE_DECISION', 'POST_SETTLEMENT', 'PERIOD_REVIEW', 'STRATEGY_REVIEW', 'SELF_CRITIQUE')),
    content TEXT NOT NULL,
    context JSONB NOT NULL DEFAULT '{}'::JSONB,
    action_taken TEXT,
    next_steps JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(content)) > 0),
    CHECK (jsonb_typeof(context) = 'object'),
    CHECK (jsonb_typeof(next_steps) = 'array')
);

CREATE INDEX agent_reflections_agent_idx ON edge_lab.agent_reflections (agent_id, created_at DESC);
CREATE INDEX agent_reflections_type_idx ON edge_lab.agent_reflections (reflection_type);

-- ============================================================================
-- 14. TRIGGERS AND CONSTRAINTS
-- ============================================================================

-- Prevent modification of sealed decisions
CREATE FUNCTION edge_lab.reject_sealed_decision_mutation()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.is_sealed = true AND (OLD.decision_type IS DISTINCT FROM NEW.decision_type
        OR OLD.selected_numbers IS DISTINCT FROM NEW.selected_numbers
        OR OLD.stake_amount IS DISTINCT FROM NEW.stake_amount) THEN
        RAISE EXCEPTION 'Cannot modify a sealed decision';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sealed_decision_guard
BEFORE UPDATE ON edge_lab.agent_decisions
FOR EACH ROW EXECUTE FUNCTION edge_lab.reject_sealed_decision_mutation();

-- Prevent deletion of sealed decisions
CREATE TRIGGER sealed_decision_no_delete
BEFORE DELETE ON edge_lab.agent_decisions
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

-- Prevent deletion of memory records (append-only)
CREATE TRIGGER memory_identity_append_only
BEFORE UPDATE OR DELETE ON edge_lab.memory_identity
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER memory_hypotheses_append_only
BEFORE UPDATE OR DELETE ON edge_lab.memory_hypotheses
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER memory_experiments_append_only
BEFORE UPDATE OR DELETE ON edge_lab.memory_experiments
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER memory_successes_append_only
BEFORE UPDATE OR DELETE ON edge_lab.memory_successes
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER memory_failures_append_only
BEFORE UPDATE OR DELETE ON edge_lab.memory_failures
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER memory_changes_append_only
BEFORE UPDATE OR DELETE ON edge_lab.memory_changes
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER memory_calibration_append_only
BEFORE UPDATE OR DELETE ON edge_lab.memory_calibration
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER memory_risk_append_only
BEFORE UPDATE OR DELETE ON edge_lab.memory_risk
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER decision_outcomes_append_only
BEFORE UPDATE OR DELETE ON edge_lab.decision_outcomes
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER agent_reflections_append_only
BEFORE UPDATE OR DELETE ON edge_lab.agent_reflections
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

-- Auto-update updated_at timestamp
CREATE FUNCTION edge_lab.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agents_update_updated_at
BEFORE UPDATE ON edge_lab.agents
FOR EACH ROW EXECUTE FUNCTION edge_lab.update_updated_at();

CREATE TRIGGER memory_hypotheses_update_updated_at
BEFORE UPDATE ON edge_lab.memory_hypotheses
FOR EACH ROW EXECUTE FUNCTION edge_lab.update_updated_at();

CREATE TRIGGER collective_knowledge_update_updated_at
BEFORE UPDATE ON edge_lab.collective_knowledge
FOR EACH ROW EXECUTE FUNCTION edge_lab.update_updated_at();

-- ============================================================================
-- 15. VIEWS FOR AGENT DASHBOARD
-- ============================================================================

-- Agent summary view for dashboard
CREATE VIEW edge_lab.agent_summary AS
SELECT
    a.agent_id,
    a.code,
    a.display_name,
    a.generation,
    a.status,
    a.operational_level,
    a.mission,
    ac.initial_capital,
    ac.current_capital,
    ac.net_profit,
    ac.roi,
    ac.total_bets,
    ac.winning_bets,
    ac.losing_bets,
    ac.no_bet_count,
    ac.max_drawdown,
    (SELECT COUNT(*) FROM edge_lab.memory_experiments WHERE agent_id = a.agent_id) AS experiments_count,
    (SELECT COUNT(*) FROM edge_lab.memory_hypotheses WHERE agent_id = a.agent_id) AS hypotheses_count,
    (SELECT COUNT(*) FROM edge_lab.memory_successes WHERE agent_id = a.agent_id) AS successes_count,
    (SELECT COUNT(*) FROM edge_lab.memory_failures WHERE agent_id = a.agent_id) AS failures_count,
    (SELECT content FROM edge_lab.agent_reflections WHERE agent_id = a.agent_id AND reflection_type = 'POST_SETTLEMENT' ORDER BY created_at DESC LIMIT 1) AS last_reflection,
    a.created_at AS agent_created_at,
    ac.last_updated_at AS capital_updated_at
FROM edge_lab.agents a
LEFT JOIN edge_lab.agent_capital ac ON ac.agent_id = a.agent_id;

-- Agent performance by market
CREATE VIEW edge_lab.agent_market_performance AS
SELECT
    a.agent_id,
    a.code AS agent_code,
    dt.display_name AS draw_type,
    COUNT(ad.decision_id) AS total_decisions,
    COUNT(CASE WHEN ad.decision_type = 'BET' THEN 1 END) AS total_bets,
    COUNT(CASE WHEN o.outcome_type = 'WIN' THEN 1 END) AS winning_bets,
    SUM(CASE WHEN o.outcome_type = 'WIN' THEN o.net_result ELSE 0 END) AS total_profit,
    SUM(CASE WHEN o.outcome_type = 'LOSS' THEN o.net_result ELSE 0 END) AS total_loss,
    SUM(o.net_result) AS net_profit,
    AVG(CASE WHEN ad.decision_type = 'BET' THEN ad.stake_amount END) AS avg_stake
FROM edge_lab.agents a
JOIN edge_lab.agent_decisions ad ON ad.agent_id = a.agent_id
JOIN catalog.draw_types dt ON dt.draw_type_id = ad.draw_type_id
LEFT JOIN edge_lab.decision_outcomes o ON o.decision_id = ad.decision_id
GROUP BY a.agent_id, a.code, dt.display_name;

-- Agent memory compartment summary
CREATE VIEW edge_lab.agent_memory_summary AS
SELECT
    a.agent_id,
    a.code AS agent_code,
    (SELECT COUNT(*) FROM edge_lab.memory_identity WHERE agent_id = a.agent_id) AS identity_records,
    (SELECT COUNT(*) FROM edge_lab.memory_hypotheses WHERE agent_id = a.agent_id) AS hypothesis_records,
    (SELECT COUNT(*) FROM edge_lab.memory_experiments WHERE agent_id = a.agent_id) AS experiment_records,
    (SELECT COUNT(*) FROM edge_lab.memory_successes WHERE agent_id = a.agent_id) AS success_records,
    (SELECT COUNT(*) FROM edge_lab.memory_failures WHERE agent_id = a.agent_id) AS failure_records,
    (SELECT COUNT(*) FROM edge_lab.memory_changes WHERE agent_id = a.agent_id) AS change_records,
    (SELECT COUNT(*) FROM edge_lab.memory_calibration WHERE agent_id = a.agent_id) AS calibration_records,
    (SELECT COUNT(*) FROM edge_lab.memory_risk WHERE agent_id = a.agent_id) AS risk_records
FROM edge_lab.agents a;

-- Collective knowledge summary
CREATE VIEW edge_lab.collective_summary AS
SELECT
    knowledge_type,
    proof_level,
    COUNT(*) AS count,
    COUNT(DISTINCT originating_agent_id) AS contributing_agents,
    AVG(validation_count) AS avg_validations,
    MAX(updated_at) AS last_updated
FROM edge_lab.collective_knowledge
GROUP BY knowledge_type, proof_level
ORDER BY knowledge_type, proof_level;
