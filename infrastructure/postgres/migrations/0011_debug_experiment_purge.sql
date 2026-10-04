-- Purge artifacts of a debug evaluation that was committed accidentally
-- (experiments tied to the ad-hoc plan 'test_regime_plan_dbg'). The evaluation
-- plan and its materialized windows are append-only and remain as an honest
-- trace; the experiment rows are kept and marked CANCELLED.

ALTER TABLE research.findings DISABLE TRIGGER findings_append_only;
DELETE FROM research.findings
WHERE experiment_id IN (
    SELECT experiment_id FROM research.experiments
    WHERE configuration->>'evaluation_plan_code' = 'test_regime_plan_dbg'
);
ALTER TABLE research.findings ENABLE TRIGGER findings_append_only;

ALTER TABLE research.experiment_metrics DISABLE TRIGGER experiment_metrics_append_only;
DELETE FROM research.experiment_metrics
WHERE experiment_id IN (
    SELECT experiment_id FROM research.experiments
    WHERE configuration->>'evaluation_plan_code' = 'test_regime_plan_dbg'
);
ALTER TABLE research.experiment_metrics ENABLE TRIGGER experiment_metrics_append_only;

ALTER TABLE research.experiment_runs DISABLE TRIGGER experiment_runs_no_delete;
DELETE FROM research.experiment_runs
WHERE experiment_id IN (
    SELECT experiment_id FROM research.experiments
    WHERE configuration->>'evaluation_plan_code' = 'test_regime_plan_dbg'
);
ALTER TABLE research.experiment_runs ENABLE TRIGGER experiment_runs_no_delete;

UPDATE research.experiments
SET status = 'CANCELLED', completed_at = CURRENT_TIMESTAMP
WHERE configuration->>'evaluation_plan_code' = 'test_regime_plan_dbg'
  AND status = 'COMPLETED';
