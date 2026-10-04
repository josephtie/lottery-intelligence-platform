CREATE SCHEMA research;

CREATE TABLE research.hypotheses (
    hypothesis_id UUID PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    statement TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN', 'TESTING', 'SUPPORTED', 'REJECTED', 'INCONCLUSIVE', 'RETIRED'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(code)) > 0),
    CHECK (length(trim(title)) > 0),
    CHECK (length(trim(statement)) > 0)
);

CREATE TABLE research.feature_versions (
    feature_version_id UUID PRIMARY KEY,
    code TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    definition JSONB NOT NULL,
    definition_sha256 CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (code, version),
    UNIQUE (code, definition_sha256),
    CHECK (length(trim(code)) > 0),
    CHECK (definition_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (jsonb_typeof(definition) = 'object')
);

CREATE TABLE research.experiments (
    experiment_id UUID PRIMARY KEY,
    hypothesis_id UUID NOT NULL REFERENCES research.hypotheses(hypothesis_id),
    dataset_version_id UUID NOT NULL REFERENCES datasets.dataset_versions(dataset_version_id),
    feature_version_id UUID REFERENCES research.feature_versions(feature_version_id),
    model_version TEXT,
    strategy_version TEXT,
    code_version TEXT NOT NULL,
    configuration JSONB NOT NULL DEFAULT '{}'::JSONB,
    configuration_sha256 CHAR(64) NOT NULL,
    random_seed BIGINT,
    status TEXT NOT NULL DEFAULT 'DESIGNED' CHECK (status IN (
        'DESIGNED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    CHECK (length(trim(code_version)) > 0),
    CHECK (configuration_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (jsonb_typeof(configuration) = 'object'),
    CHECK (completed_at IS NULL OR completed_at >= created_at)
);

CREATE TABLE research.experiment_runs (
    experiment_run_id UUID PRIMARY KEY,
    experiment_id UUID NOT NULL REFERENCES research.experiments(experiment_id),
    run_number INTEGER NOT NULL CHECK (run_number > 0),
    scope TEXT NOT NULL CHECK (scope IN (
        'TRAIN', 'VALIDATION', 'OUT_OF_SAMPLE', 'PROSPECTIVE', 'GLOBAL'
    )),
    cutoff_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'RUNNING' CHECK (status IN (
        'RUNNING', 'COMPLETED', 'FAILED'
    )),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    UNIQUE (experiment_id, run_number),
    CHECK (finished_at IS NULL OR finished_at >= started_at),
    CHECK (jsonb_typeof(details) = 'object')
);

CREATE TABLE research.experiment_metrics (
    experiment_metric_id UUID PRIMARY KEY,
    experiment_id UUID NOT NULL REFERENCES research.experiments(experiment_id),
    experiment_run_id UUID REFERENCES research.experiment_runs(experiment_run_id),
    metric_name TEXT NOT NULL,
    metric_scope TEXT NOT NULL CHECK (metric_scope IN (
        'TRAIN', 'VALIDATION', 'OUT_OF_SAMPLE', 'PROSPECTIVE', 'GLOBAL'
    )),
    metric_value DOUBLE PRECISION,
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(metric_name)) > 0),
    CHECK (jsonb_typeof(details) = 'object')
);

CREATE TABLE research.findings (
    finding_id UUID PRIMARY KEY,
    hypothesis_id UUID NOT NULL REFERENCES research.hypotheses(hypothesis_id),
    experiment_id UUID REFERENCES research.experiments(experiment_id),
    conclusion TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('SUPPORTED', 'REJECTED', 'INCONCLUSIVE')),
    evidence JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(conclusion)) > 0),
    CHECK (jsonb_typeof(evidence) = 'object')
);

CREATE INDEX experiments_hypothesis_idx
    ON research.experiments (hypothesis_id, created_at);
CREATE INDEX experiments_dataset_version_idx
    ON research.experiments (dataset_version_id);
CREATE INDEX experiment_runs_experiment_idx
    ON research.experiment_runs (experiment_id, run_number);
CREATE INDEX experiment_metrics_experiment_idx
    ON research.experiment_metrics (experiment_id, metric_name, metric_scope);
CREATE INDEX findings_hypothesis_idx
    ON research.findings (hypothesis_id, created_at);

CREATE TRIGGER hypotheses_no_delete
BEFORE DELETE ON research.hypotheses
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER experiments_no_delete
BEFORE DELETE ON research.experiments
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER experiment_runs_no_delete
BEFORE DELETE ON research.experiment_runs
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER feature_versions_append_only
BEFORE UPDATE OR DELETE ON research.feature_versions
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER experiment_metrics_append_only
BEFORE UPDATE OR DELETE ON research.experiment_metrics
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER findings_append_only
BEFORE UPDATE OR DELETE ON research.findings
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();
