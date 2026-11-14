-- Fix: target_draw_id and locked_at are assigned at lock time. The original
-- guard treated target_draw_id as immutable content, which made the
-- PENDING -> LOCKED transition itself impossible.
-- These fields may be set while the prediction is PENDING and are frozen
-- once it leaves that state.

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
        OR NEW.stake IS DISTINCT FROM OLD.stake THEN
        RAISE EXCEPTION 'IMMUTABLE_PREDICTION_VIOLATION';
    END IF;
    -- target_draw_id and locked_at are assigned at lock time, then frozen.
    IF OLD.status <> 'PENDING' AND (
        NEW.target_draw_id IS DISTINCT FROM OLD.target_draw_id
        OR NEW.locked_at IS DISTINCT FROM OLD.locked_at
    ) THEN
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
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
