CREATE TABLE research.model_versions (
    model_version_id UUID PRIMARY KEY,
    code TEXT NOT NULL,
    family TEXT NOT NULL CHECK (family IN (
        'BASELINE', 'BENCHMARK', 'STATISTICAL_TEST', 'PREDICTIVE',
        'STRATEGY', 'ENSEMBLE', 'OTHER'
    )),
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

ALTER TABLE research.experiments
    ADD COLUMN model_version_id UUID REFERENCES research.model_versions(model_version_id);

CREATE INDEX model_versions_family_idx
    ON research.model_versions (family, code);
CREATE INDEX experiments_model_version_idx
    ON research.experiments (model_version_id);

CREATE TRIGGER model_versions_append_only
BEFORE UPDATE OR DELETE ON research.model_versions
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();
