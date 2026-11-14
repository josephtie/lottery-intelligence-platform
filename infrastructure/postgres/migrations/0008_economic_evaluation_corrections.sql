ALTER TABLE research.economic_evaluations
    ADD COLUMN evaluator_version TEXT NOT NULL DEFAULT 'v1';

ALTER TABLE research.economic_evaluations
    DROP CONSTRAINT economic_evaluations_strategy_version_id_evaluation_window__key;

ALTER TABLE research.economic_evaluations
    ADD CONSTRAINT economic_evaluations_unique_result
    UNIQUE (strategy_version_id, evaluation_window_id, scope, draw_type_id, evaluator_version);

ALTER TABLE research.economic_evaluations DISABLE TRIGGER economic_evaluations_append_only;
DELETE FROM research.economic_evaluations WHERE evaluator_version = 'v1';
ALTER TABLE research.economic_evaluations ENABLE TRIGGER economic_evaluations_append_only;
