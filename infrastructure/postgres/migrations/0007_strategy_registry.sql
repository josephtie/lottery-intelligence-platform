CREATE TABLE research.strategies (
    strategy_id UUID PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'RETIRED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(code)) > 0),
    CHECK (length(trim(display_name)) > 0)
);

CREATE TABLE research.strategy_versions (
    strategy_version_id UUID PRIMARY KEY,
    strategy_id UUID NOT NULL REFERENCES research.strategies(strategy_id),
    version INTEGER NOT NULL CHECK (version > 0),
    game_version_id UUID NOT NULL,
    game_id UUID NOT NULL,
    payout_rule_version_id UUID NOT NULL REFERENCES catalog.payout_rule_versions(payout_rule_version_id),
    dataset_version_id UUID REFERENCES datasets.dataset_versions(dataset_version_id),
    experiment_id UUID REFERENCES research.experiments(experiment_id),
    code_version TEXT NOT NULL,
    definition JSONB NOT NULL,
    definition_sha256 CHAR(64) NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
        'DRAFT', 'BACKTESTED', 'OOS_EVALUATED', 'PROSPECTIVE', 'REJECTED', 'RETIRED'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (strategy_id, version),
    UNIQUE (strategy_id, definition_sha256),
    FOREIGN KEY (game_version_id, game_id)
        REFERENCES catalog.game_versions(game_version_id, game_id),
    CHECK (length(trim(code_version)) > 0),
    CHECK (definition_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (jsonb_typeof(definition) = 'object')
);

CREATE TABLE research.economic_evaluations (
    economic_evaluation_id UUID PRIMARY KEY,
    strategy_version_id UUID NOT NULL REFERENCES research.strategy_versions(strategy_version_id),
    evaluation_window_id UUID NOT NULL REFERENCES research.evaluation_windows(evaluation_window_id),
    draw_type_id UUID NOT NULL REFERENCES catalog.draw_types(draw_type_id),
    scope TEXT NOT NULL CHECK (scope IN ('VALIDATION', 'OUT_OF_SAMPLE', 'PROSPECTIVE')),
    draws_evaluated INTEGER NOT NULL CHECK (draws_evaluated >= 0),
    stake_total NUMERIC(20, 4) NOT NULL CHECK (stake_total >= 0),
    payout_total NUMERIC(20, 4) NOT NULL CHECK (payout_total >= 0),
    net_result NUMERIC(20, 4) NOT NULL,
    roi DOUBLE PRECISION,
    max_drawdown NUMERIC(20, 4) NOT NULL CHECK (max_drawdown >= 0),
    longest_losing_streak INTEGER NOT NULL CHECK (longest_losing_streak >= 0),
    hit_count INTEGER NOT NULL CHECK (hit_count >= 0),
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (strategy_version_id, evaluation_window_id, scope, draw_type_id),
    CHECK (hit_count <= draws_evaluated),
    CHECK (jsonb_typeof(details) = 'object')
);

CREATE TABLE research.strategy_version_status_events (
    status_event_id UUID PRIMARY KEY,
    strategy_version_id UUID NOT NULL REFERENCES research.strategy_versions(strategy_version_id),
    previous_status TEXT,
    new_status TEXT NOT NULL,
    reason TEXT,
    evidence JSONB NOT NULL DEFAULT '{}'::JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(new_status)) > 0),
    CHECK (jsonb_typeof(evidence) = 'object')
);

CREATE INDEX strategy_versions_strategy_idx
    ON research.strategy_versions (strategy_id, version);
CREATE INDEX economic_evaluations_strategy_idx
    ON research.economic_evaluations (strategy_version_id, evaluation_window_id);
CREATE INDEX strategy_status_events_idx
    ON research.strategy_version_status_events (strategy_version_id, occurred_at);

CREATE TRIGGER strategies_no_delete
BEFORE DELETE ON research.strategies
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER strategy_versions_no_delete
BEFORE DELETE ON research.strategy_versions
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER strategy_status_events_append_only
BEFORE UPDATE OR DELETE ON research.strategy_version_status_events
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER economic_evaluations_append_only
BEFORE UPDATE OR DELETE ON research.economic_evaluations
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();
