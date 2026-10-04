-- Prospective cohort: a versioned manifest of the models/draw types under
-- prospective evaluation, plus a per-(draw, model) coverage ledger so missing
-- predictions are explicit, never silently absent.

CREATE TABLE research.prospective_cohorts (
    cohort_id UUID PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(code)) > 0)
);

CREATE TRIGGER prospective_cohorts_append_only
BEFORE UPDATE OR DELETE ON research.prospective_cohorts
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TABLE research.prospective_cohort_versions (
    cohort_version_id UUID PRIMARY KEY,
    cohort_id UUID NOT NULL REFERENCES research.prospective_cohorts(cohort_id),
    version INTEGER NOT NULL CHECK (version > 0),
    definition JSONB NOT NULL,
    definition_sha256 CHAR(64) NOT NULL,
    effective_from DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (cohort_id, version),
    UNIQUE (cohort_id, definition_sha256),
    CHECK (definition_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (jsonb_typeof(definition) = 'object')
);

CREATE TRIGGER prospective_cohort_versions_append_only
BEFORE UPDATE OR DELETE ON research.prospective_cohort_versions
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TABLE research.prospective_cohort_members (
    cohort_member_id UUID PRIMARY KEY,
    cohort_version_id UUID NOT NULL REFERENCES research.prospective_cohort_versions(cohort_version_id),
    model_version_id UUID NOT NULL REFERENCES research.model_versions(model_version_id),
    draw_type_id UUID REFERENCES catalog.draw_types(draw_type_id),
    parameters JSONB NOT NULL DEFAULT '{}'::JSONB,
    seed BIGINT,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'SUSPENDED', 'RETIRED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (cohort_version_id, model_version_id, draw_type_id),
    CHECK (jsonb_typeof(parameters) = 'object')
);

CREATE TRIGGER prospective_cohort_members_append_only
BEFORE UPDATE OR DELETE ON research.prospective_cohort_members
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

-- Coverage ledger: one row per (draw, model, cohort_version) evaluated by the
-- generator. MISSING/FAILED rows make absent predictions explicit and auditable.
CREATE TABLE research.prediction_coverage (
    coverage_id UUID PRIMARY KEY,
    draw_type_id UUID NOT NULL REFERENCES catalog.draw_types(draw_type_id),
    scheduled_date DATE NOT NULL,
    draw_id UUID REFERENCES core.draws(draw_id),
    model_version_id UUID NOT NULL REFERENCES research.model_versions(model_version_id),
    cohort_version_id UUID NOT NULL REFERENCES research.prospective_cohort_versions(cohort_version_id),
    status TEXT NOT NULL CHECK (status IN ('GENERATED', 'MISSING', 'FAILED', 'INELIGIBLE')),
    reason TEXT,
    prediction_id UUID REFERENCES research.predictions(prediction_id),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (draw_type_id, scheduled_date, model_version_id, cohort_version_id)
);

-- Coverage is state, not ledger: a MISSING cell may become GENERATED on retry.
CREATE OR REPLACE FUNCTION research.guard_coverage_update() RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status = 'GENERATED' AND NEW.status <> 'GENERATED' THEN
        RAISE EXCEPTION 'generated coverage cannot revert';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER prediction_coverage_guard
BEFORE UPDATE ON research.prediction_coverage
FOR EACH ROW EXECUTE FUNCTION research.guard_coverage_update();

CREATE TRIGGER prediction_coverage_no_delete
BEFORE DELETE ON research.prediction_coverage
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

-- Prospective performance: per-model realized metrics on settled predictions.
CREATE VIEW research.prospective_performance AS
SELECT
    mv.code AS model_code,
    p.scheduled_date,
    d.draw_id,
    dt.display_name AS draw_type,
    o.hit_count,
    o.positional_hits,
    o.metrics->'turbo' AS turbo,
    o.settled_at
FROM research.prediction_outcomes o
JOIN research.predictions p ON p.prediction_id = o.prediction_id
JOIN research.model_versions mv ON mv.model_version_id = p.model_version_id
JOIN core.draws d ON d.draw_id = o.draw_id
JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id;
