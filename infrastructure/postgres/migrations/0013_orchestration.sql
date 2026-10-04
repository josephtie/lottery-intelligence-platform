-- Orchestration: jobs queue, run events, alerts, audit log, rich prediction
-- outcomes, strategy settlements, and the PENDING -> LOCKED -> SCORED|INVALID
-- prediction lifecycle with immutability guards.

-- ---------------------------------------------------------------------------
-- Scheduler: durable job registry + runs + events (PostgreSQL-backed queue).
-- ---------------------------------------------------------------------------

CREATE TABLE ops.jobs (
    job_id UUID PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('COLLECT', 'PIPELINE', 'REPORT', 'BACKUP', 'MAINTENANCE')),
    schedule_cron TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Africa/Abidjan',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    config JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(code)) > 0),
    CHECK (jsonb_typeof(config) = 'object')
);

CREATE TRIGGER jobs_append_only
BEFORE UPDATE OR DELETE ON ops.jobs
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TABLE ops.job_runs (
    job_run_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES ops.jobs(job_id),
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'QUEUED' CHECK (status IN (
        'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'RETRY_REQUIRED', 'DEAD'
    )),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    max_retries INTEGER NOT NULL DEFAULT 3 CHECK (max_retries >= 0),
    next_retry_at TIMESTAMPTZ,
    last_error TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    claimed_by TEXT,
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (jsonb_typeof(details) = 'object'),
    CHECK (status = 'RUNNING' OR started_at IS NULL OR started_at <= COALESCE(finished_at, CURRENT_TIMESTAMP))
);

CREATE INDEX job_runs_claimable_idx
    ON ops.job_runs (status, next_retry_at)
    WHERE status IN ('QUEUED', 'RETRY_REQUIRED');

CREATE TRIGGER job_runs_no_delete
BEFORE DELETE ON ops.job_runs
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TABLE ops.job_events (
    job_event_id UUID PRIMARY KEY,
    job_run_id UUID REFERENCES ops.job_runs(job_run_id),
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(event_type)) > 0),
    CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX job_events_type_idx ON ops.job_events (event_type, occurred_at);

CREATE TRIGGER job_events_append_only
BEFORE UPDATE OR DELETE ON ops.job_events
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

-- ---------------------------------------------------------------------------
-- Operations: alerts + audit trail.
-- ---------------------------------------------------------------------------

CREATE TABLE ops.alerts (
    alert_id UUID PRIMARY KEY,
    code TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    entity_type TEXT,
    entity_id UUID,
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    dedupe_key TEXT NOT NULL,
    raised_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMPTZ,
    CHECK (length(trim(code)) > 0),
    CHECK (jsonb_typeof(details) = 'object')
);

CREATE INDEX alerts_open_idx ON ops.alerts (code, raised_at) WHERE acknowledged_at IS NULL;

-- Alerts may only be acknowledged; content is immutable.
CREATE OR REPLACE FUNCTION ops.guard_alert_update() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.code IS DISTINCT FROM OLD.code
        OR NEW.severity IS DISTINCT FROM OLD.severity
        OR NEW.entity_type IS DISTINCT FROM OLD.entity_type
        OR NEW.entity_id IS DISTINCT FROM OLD.entity_id
        OR NEW.details IS DISTINCT FROM OLD.details
        OR NEW.dedupe_key IS DISTINCT FROM OLD.dedupe_key
        OR NEW.raised_at IS DISTINCT FROM OLD.raised_at THEN
        RAISE EXCEPTION 'alert content is immutable (only acknowledged_at may change)';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER alerts_guard
BEFORE UPDATE ON ops.alerts
FOR EACH ROW EXECUTE FUNCTION ops.guard_alert_update();

CREATE TRIGGER alerts_no_delete
BEFORE DELETE ON ops.alerts
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TABLE ops.audit_events (
    audit_event_id UUID PRIMARY KEY,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID,
    previous_value JSONB,
    attempted_value JSONB,
    outcome TEXT NOT NULL CHECK (outcome IN ('ALLOWED', 'REJECTED')),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX audit_events_entity_idx ON ops.audit_events (entity_type, entity_id, occurred_at);

CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON ops.audit_events
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

-- ---------------------------------------------------------------------------
-- Predictions: richer payload, LOCKED lifecycle, immutability guard.
-- ---------------------------------------------------------------------------

ALTER TABLE research.predictions DROP CONSTRAINT predictions_status_check;
ALTER TABLE research.predictions
    ADD CONSTRAINT predictions_status_check
    CHECK (status IN ('PENDING', 'LOCKED', 'SCORED', 'INVALID'));

ALTER TABLE research.predictions
    ADD COLUMN dataset_version_id UUID REFERENCES datasets.dataset_versions(dataset_version_id),
    ADD COLUMN feature_set_version TEXT,
    ADD COLUMN parameters JSONB NOT NULL DEFAULT '{}'::JSONB,
    ADD COLUMN candidates JSONB,
    ADD COLUMN scores JSONB,
    ADD COLUMN stake NUMERIC,
    ADD COLUMN target_draw_id UUID REFERENCES core.draws(draw_id),
    ADD COLUMN locked_at TIMESTAMPTZ;

ALTER TABLE research.predictions
    ADD CONSTRAINT predictions_stake_nonnegative CHECK (stake IS NULL OR stake >= 0);

-- Prediction lifecycle guard:
--   * content fields are immutable once the row exists (corrections create a
--     new prediction, never edit history);
--   * allowed transitions: PENDING -> PENDING/LOCKED/SCORED/INVALID,
--     LOCKED -> LOCKED/SCORED/INVALID, SCORED -> SCORED, INVALID -> INVALID.
CREATE OR REPLACE FUNCTION research.guard_prediction_update() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.predicted_numbers IS DISTINCT FROM OLD.predicted_numbers
        OR NEW.model_version_id IS DISTINCT FROM OLD.model_version_id
        OR NEW.strategy_version_id IS DISTINCT FROM OLD.strategy_version_id
        OR NEW.draw_type_id IS DISTINCT FROM OLD.draw_type_id
        OR NEW.scheduled_date IS DISTINCT FROM OLD.scheduled_date
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
        OR NEW.dataset_version_id IS DISTINCT FROM OLD.dataset_version_id
        OR NEW.feature_set_version IS DISTINCT FROM OLD.feature_set_version
        OR NEW.parameters IS DISTINCT FROM OLD.parameters
        OR NEW.candidates IS DISTINCT FROM OLD.candidates
        OR NEW.scores IS DISTINCT FROM OLD.scores
        OR NEW.stake IS DISTINCT FROM OLD.stake
        OR NEW.target_draw_id IS DISTINCT FROM OLD.target_draw_id THEN
        RAISE EXCEPTION 'IMMUTABLE_PREDICTION_VIOLATION';
    END IF;
    IF NOT (
        (OLD.status = 'PENDING' AND NEW.status IN ('PENDING', 'LOCKED', 'SCORED', 'INVALID'))
        OR (OLD.status = 'LOCKED' AND NEW.status IN ('LOCKED', 'SCORED', 'INVALID'))
        OR (OLD.status = 'SCORED' AND NEW.status = 'SCORED')
        OR (OLD.status = 'INVALID' AND NEW.status = 'INVALID')
    ) THEN
        RAISE EXCEPTION 'invalid prediction status transition: % -> %', OLD.status, NEW.status;
    END IF;
    IF OLD.status = 'LOCKED' AND NEW.locked_at IS DISTINCT FROM OLD.locked_at THEN
        RAISE EXCEPTION 'IMMUTABLE_PREDICTION_VIOLATION';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER predictions_update_guard
BEFORE UPDATE ON research.predictions
FOR EACH ROW EXECUTE FUNCTION research.guard_prediction_update();

-- ---------------------------------------------------------------------------
-- Settlement records.
-- ---------------------------------------------------------------------------

CREATE TABLE research.prediction_outcomes (
    outcome_id UUID PRIMARY KEY,
    prediction_id UUID NOT NULL UNIQUE REFERENCES research.predictions(prediction_id),
    draw_id UUID NOT NULL REFERENCES core.draws(draw_id),
    draw_version_id UUID NOT NULL REFERENCES core.draw_versions(draw_version_id),
    predicted_numbers INTEGER[] NOT NULL,
    winning_numbers INTEGER[] NOT NULL,
    hit_count INTEGER NOT NULL CHECK (hit_count >= 0),
    positional_hits JSONB NOT NULL DEFAULT '{}'::JSONB,
    metrics JSONB NOT NULL DEFAULT '{}'::JSONB,
    settled_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (jsonb_typeof(positional_hits) = 'object'),
    CHECK (jsonb_typeof(metrics) = 'object')
);

CREATE TRIGGER prediction_outcomes_append_only
BEFORE UPDATE OR DELETE ON research.prediction_outcomes
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TABLE research.strategy_settlements (
    settlement_id UUID PRIMARY KEY,
    strategy_version_id UUID NOT NULL REFERENCES research.strategy_versions(strategy_version_id),
    draw_id UUID NOT NULL REFERENCES core.draws(draw_id),
    draw_version_id UUID NOT NULL REFERENCES core.draw_versions(draw_version_id),
    prediction_id UUID REFERENCES research.predictions(prediction_id),
    scope TEXT NOT NULL CHECK (scope IN (
        'IN_SAMPLE', 'VALIDATION', 'WALK_FORWARD', 'OUT_OF_SAMPLE', 'PROSPECTIVE', 'REALIZED'
    )),
    variant TEXT NOT NULL,
    total_stake NUMERIC NOT NULL CHECK (total_stake >= 0),
    total_payout NUMERIC NOT NULL CHECK (total_payout >= 0),
    net_profit NUMERIC NOT NULL,
    roi NUMERIC,
    metrics JSONB NOT NULL DEFAULT '{}'::JSONB,
    settled_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(variant)) > 0),
    CHECK (jsonb_typeof(metrics) = 'object'),
    UNIQUE (strategy_version_id, draw_id, variant, scope)
);

CREATE TRIGGER strategy_settlements_append_only
BEFORE UPDATE OR DELETE ON research.strategy_settlements
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

-- ---------------------------------------------------------------------------
-- Orchestrator health screen.
-- ---------------------------------------------------------------------------

CREATE VIEW ops.orchestrator_health AS
SELECT
    (SELECT MAX(occurred_at) FROM ops.job_events WHERE event_type = 'DRAW_DETECTED') AS last_draw_detected_at,
    (SELECT MAX(occurred_at) FROM ops.job_events WHERE event_type = 'DRAW_VALIDATED') AS last_draw_validated_at,
    (SELECT MAX(occurred_at) FROM ops.job_events WHERE event_type = 'DRAW_FROZEN') AS last_draw_frozen_at,
    (SELECT MAX(settled_at) FROM research.prediction_outcomes) AS last_prediction_settled_at,
    (SELECT COUNT(*) FROM ops.job_runs WHERE status = 'FAILED') AS failed_runs,
    (SELECT COUNT(*) FROM ops.job_runs WHERE status = 'DEAD') AS dead_runs,
    (SELECT COUNT(*) FROM ops.job_runs WHERE status IN ('QUEUED', 'RETRY_REQUIRED')) AS pending_runs,
    (SELECT COUNT(*) FROM ops.job_runs WHERE status = 'RETRY_REQUIRED') AS retrying_runs,
    (SELECT COUNT(*) FROM ops.alerts WHERE acknowledged_at IS NULL) AS open_alerts,
    (SELECT MAX(created_at) FROM ingestion.raw_objects) AS last_raw_object_at;
