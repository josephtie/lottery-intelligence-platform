-- Purge the v1 calibration metrics recorded with normalized selection
-- fractions instead of inclusion probabilities. The experiments and runs are
-- kept as historical evidence and marked CANCELLED so the metrics cannot be
-- confused with the corrected v2 evaluation (details.calibration_version = 'v2').

ALTER TABLE research.experiment_metrics DISABLE TRIGGER experiment_metrics_append_only;
DELETE FROM research.experiment_metrics
WHERE details->>'metric_kind' = 'calibration'
  AND NOT (details ? 'calibration_version');
ALTER TABLE research.experiment_metrics ENABLE TRIGGER experiment_metrics_append_only;

UPDATE research.experiments e
SET status = 'CANCELLED', completed_at = CURRENT_TIMESTAMP
WHERE e.configuration->>'analysis' = 'probability_calibration'
  AND e.status = 'COMPLETED'
  AND NOT EXISTS (
      SELECT 1 FROM research.experiment_metrics m
      WHERE m.experiment_id = e.experiment_id
  );
