CREATE TABLE research.evaluation_plans (
    evaluation_plan_id UUID PRIMARY KEY,
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

CREATE TABLE research.evaluation_windows (
    evaluation_window_id UUID PRIMARY KEY,
    evaluation_plan_id UUID NOT NULL REFERENCES research.evaluation_plans(evaluation_plan_id),
    dataset_version_id UUID NOT NULL REFERENCES datasets.dataset_versions(dataset_version_id),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    train_start DATE NOT NULL,
    train_end DATE NOT NULL,
    validation_start DATE,
    validation_end DATE,
    test_start DATE NOT NULL,
    test_end DATE NOT NULL,
    member_count INTEGER NOT NULL CHECK (member_count >= 0),
    test_member_count INTEGER NOT NULL CHECK (test_member_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (evaluation_plan_id, dataset_version_id, ordinal),
    CHECK (train_end >= train_start),
    CHECK (validation_start IS NULL OR validation_start > train_end),
    CHECK ((validation_start IS NULL) = (validation_end IS NULL)),
    CHECK (validation_end IS NULL OR validation_end >= validation_start),
    CHECK (test_start > train_end),
    CHECK (validation_end IS NULL OR test_start > validation_end),
    CHECK (test_end >= test_start)
);

ALTER TABLE research.experiment_runs
    ADD COLUMN evaluation_window_id UUID REFERENCES research.evaluation_windows(evaluation_window_id);

CREATE INDEX experiment_runs_window_idx
    ON research.experiment_runs (evaluation_window_id);
CREATE INDEX evaluation_windows_plan_idx
    ON research.evaluation_windows (evaluation_plan_id, dataset_version_id, ordinal);

CREATE TRIGGER evaluation_plans_append_only
BEFORE UPDATE OR DELETE ON research.evaluation_plans
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER evaluation_windows_append_only
BEFORE UPDATE OR DELETE ON research.evaluation_windows
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();
