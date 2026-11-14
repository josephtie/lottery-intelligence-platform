-- Model artifact registry + low-power flag on prospective metrics.
--
-- model_artifacts: immutable registry for serialized trained models. The
-- current cohort models are stateless (parameters recomputed per call) and
-- have no artifact; the table exists so a parametric model entering a future
-- cohort is stored content-addressed and reproducible from day one.

CREATE TABLE research.model_artifacts (
    artifact_id UUID PRIMARY KEY,
    model_version_id UUID NOT NULL REFERENCES research.model_versions(model_version_id),
    kind TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    size_bytes BIGINT CHECK (size_bytes IS NULL OR size_bytes > 0),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (model_version_id, sha256),
    CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (jsonb_typeof(metadata) = 'object'),
    CHECK (length(trim(storage_uri)) > 0)
);

CREATE TRIGGER model_artifacts_append_only
BEFORE UPDATE OR DELETE ON research.model_artifacts
FOR EACH ROW EXECUTE FUNCTION ops.reject_append_only_mutation();

CREATE INDEX model_artifacts_version_idx
    ON research.model_artifacts (model_version_id, created_at DESC);

-- Per-draw-type statistical context: how much history exists and whether the
-- type meets the cohort's 30-draw power threshold. Used to flag low-power
-- cells in prospective metrics (they stay eligible, per the cohort charter,
-- but must be reported distinctly).
CREATE VIEW research.draw_type_power AS
SELECT
    dt.draw_type_id,
    dt.display_name,
    COUNT(d.draw_id) FILTER (WHERE d.status IN ('FROZEN', 'SETTLED')) AS settled_draws,
    MIN(d.scheduled_date) FILTER (WHERE d.status IN ('FROZEN', 'SETTLED')) AS first_draw,
    COUNT(d.draw_id) FILTER (WHERE d.status IN ('FROZEN', 'SETTLED')) >= 30 AS meets_power_threshold
FROM catalog.draw_types dt
LEFT JOIN core.draws d ON d.draw_type_id = dt.draw_type_id
GROUP BY dt.draw_type_id, dt.display_name;

-- Replaces the 0016 view: adds historical_draws + low_power columns so
-- denominators are interpretable (a cell with 2 historical draws cannot carry
-- the same evidentiary weight as one with 1,600).
CREATE OR REPLACE VIEW research.prospective_metrics AS
WITH base AS (
    SELECT
        cv.cohort_version_id,
        c.code AS cohort_code,
        cv.version AS cohort_version,
        cv.effective_from,
        mv.code AS model_code,
        dt.display_name AS draw_type,
        dt.draw_type_id,
        cov.status AS coverage_status,
        cov.reason,
        p.status AS prediction_status,
        o.hit_count,
        o.positional_hits,
        o.metrics AS outcome_metrics
    FROM research.prediction_coverage cov
    JOIN research.prospective_cohort_versions cv
      ON cv.cohort_version_id = cov.cohort_version_id
    JOIN research.prospective_cohorts c ON c.cohort_id = cv.cohort_id
    JOIN research.model_versions mv ON mv.model_version_id = cov.model_version_id
    JOIN catalog.draw_types dt ON dt.draw_type_id = cov.draw_type_id
    LEFT JOIN research.predictions p ON p.prediction_id = cov.prediction_id
    LEFT JOIN research.prediction_outcomes o ON o.prediction_id = p.prediction_id
),
agg AS (
    SELECT
        cohort_version_id, cohort_code, cohort_version, effective_from,
        model_code, draw_type, draw_type_id,
        COUNT(*) AS eligible_pairs,
        COUNT(*) FILTER (WHERE coverage_status = 'GENERATED') AS generated,
        COUNT(*) FILTER (WHERE coverage_status = 'MISSING') AS missing,
        COUNT(*) FILTER (WHERE coverage_status = 'FAILED') AS failed,
        COUNT(*) FILTER (WHERE coverage_status = 'INELIGIBLE') AS ineligible,
        COUNT(*) FILTER (
            WHERE coverage_status IN ('MISSING', 'FAILED', 'INELIGIBLE')
        ) AS absent_total,
        COUNT(*) FILTER (WHERE prediction_status = 'PENDING') AS pending,
        COUNT(*) FILTER (WHERE prediction_status = 'LOCKED') AS locked,
        COUNT(*) FILTER (WHERE prediction_status = 'INVALID') AS invalid,
        COUNT(hit_count) AS settled,
        AVG(hit_count)::numeric(10, 4) AS mean_hits,
        SUM((positional_hits ->> 'first_1')::int) AS hits_first_1,
        SUM((positional_hits ->> 'first_2')::int) AS hits_first_2,
        SUM((positional_hits ->> 'first_3')::int) AS hits_first_3,
        SUM((positional_hits ->> 'first_4')::int) AS hits_first_4,
        SUM((positional_hits ->> 'first_5')::int) AS hits_first_5
    FROM base
    GROUP BY cohort_version_id, cohort_code, cohort_version, effective_from,
             model_code, draw_type, draw_type_id
),
turbo_flat AS (
    SELECT
        b.cohort_version_id, b.model_code, b.draw_type,
        t.variant,
        COUNT(*) AS bets,
        COUNT(*) FILTER (WHERE (t.val ->> 'hit')::boolean) AS hits,
        SUM((t.val ->> 'stake')::numeric) AS stake,
        SUM((t.val ->> 'payout')::numeric) AS payout,
        SUM((t.val ->> 'net')::numeric) AS net
    FROM base b
    CROSS JOIN LATERAL jsonb_each(b.outcome_metrics -> 'turbo') AS t(variant, val)
    WHERE b.outcome_metrics IS NOT NULL
    GROUP BY b.cohort_version_id, b.model_code, b.draw_type, t.variant
),
turbo_json AS (
    SELECT
        cohort_version_id, model_code, draw_type,
        jsonb_object_agg(
            variant,
            jsonb_build_object(
                'bets', bets,
                'hits', hits,
                'stake', stake,
                'payout', payout,
                'net', net,
                'roi', ROUND(net / NULLIF(stake, 0), 6)
            )
        ) AS turbo
    FROM turbo_flat
    GROUP BY cohort_version_id, model_code, draw_type
)
SELECT
    a.cohort_code,
    a.cohort_version,
    a.cohort_version_id,
    a.effective_from,
    a.model_code,
    a.draw_type,
    a.eligible_pairs,
    a.generated,
    a.missing,
    a.failed,
    a.ineligible,
    a.absent_total,
    a.pending,
    a.locked,
    a.invalid,
    a.settled,
    ROUND(a.settled::numeric / NULLIF(a.generated, 0), 6) AS settlement_rate,
    a.mean_hits,
    COALESCE(a.hits_first_1, 0) AS hits_first_1,
    COALESCE(a.hits_first_2, 0) AS hits_first_2,
    COALESCE(a.hits_first_3, 0) AS hits_first_3,
    COALESCE(a.hits_first_4, 0) AS hits_first_4,
    COALESCE(a.hits_first_5, 0) AS hits_first_5,
    COALESCE(t.turbo, '{}'::jsonb) AS turbo,
    p.settled_draws AS historical_draws,
    NOT COALESCE(p.meets_power_threshold, false) AS low_power
FROM agg a
LEFT JOIN turbo_json t
  ON t.cohort_version_id = a.cohort_version_id
 AND t.model_code = a.model_code
 AND t.draw_type = a.draw_type
LEFT JOIN research.draw_type_power p ON p.draw_type_id = a.draw_type_id;
