CREATE TABLE research.predictions (
    prediction_id UUID PRIMARY KEY,
    model_version_id UUID NOT NULL REFERENCES research.model_versions(model_version_id),
    strategy_version_id UUID REFERENCES research.strategy_versions(strategy_version_id),
    draw_type_id UUID NOT NULL REFERENCES catalog.draw_types(draw_type_id),
    scheduled_date DATE NOT NULL,
    predicted_numbers INTEGER[] NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'SCORED', 'INVALID')),
    CHECK (cardinality(predicted_numbers) > 0),
    UNIQUE (model_version_id, draw_type_id, scheduled_date, predicted_numbers)
);

CREATE INDEX predictions_draw_lookup_idx
    ON research.predictions (draw_type_id, scheduled_date, status);

CREATE TABLE research.prediction_scores (
    prediction_score_id UUID PRIMARY KEY,
    prediction_id UUID NOT NULL UNIQUE REFERENCES research.predictions(prediction_id),
    draw_version_id UUID NOT NULL REFERENCES core.draw_versions(draw_version_id),
    hits INTEGER NOT NULL CHECK (hits >= 0),
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (jsonb_typeof(details) = 'object')
);

CREATE TRIGGER predictions_no_delete
BEFORE DELETE ON research.predictions
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE TRIGGER prediction_scores_append_only
BEFORE UPDATE OR DELETE ON research.prediction_scores
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();
