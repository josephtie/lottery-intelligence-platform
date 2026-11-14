-- Aggregated prospective metrics per cohort version x model x draw type.
--
-- Scope: PROSPECTIVE REALIZED only. Coverage rows come from the pre-registered
-- cohort (prediction_coverage); outcomes from settled predictions. Backtest,
-- walk-forward and OOS metrics live in the experiment tables and are never
-- mixed here. All denominators are explicit:
--   eligible_pairs   = coverage rows recorded for the cohort pair
--   settled          = generated predictions with a prediction_outcome
--   settlement_rate  = settled / generated (NULL when generated = 0)
-- Turbo economics are aggregated per variant under the payout-rule version
-- applied at settlement time (the rule is read from each outcome's metrics,
-- never re-evaluated here). A hit is not evidence of profitability.

CREATE VIEW research.prospective_metrics AS
WITH base AS (
    SELECT
        cv.cohort_version_id,
        c.code AS cohort_code,
        cv.version AS cohort_version,
        cv.effective_from,
        mv.code AS model_code,
        dt.display_name AS draw_type,
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
        model_code, draw_type,
        COUNT(*) AS eligible_pairs,
        COUNT(*) FILTER (WHERE coverage_status = 'GENERATED') AS generated,
        COUNT(*) FILTER (WHERE coverage_status = 'MISSING') AS missing,
        COUNT(*) FILTER (WHERE coverage_status = 'FAILED') AS failed,
        COUNT(*) FILTER (WHERE coverage_status = 'INELIGIBLE') AS ineligible,
        COUNT(*) FILTER (
            WHERE coverage_status IN ('MISSING', 'FAILED', 'INELIGIBLE')
        ) AS absent_total,
        COUNT(hit_count) AS settled,
        COUNT(*) FILTER (WHERE prediction_status = 'PENDING') AS pending,
        COUNT(*) FILTER (WHERE prediction_status = 'LOCKED') AS locked,
        COUNT(*) FILTER (WHERE prediction_status = 'INVALID') AS invalid,
        AVG(hit_count)::numeric(10, 4) AS mean_hits,
        SUM((positional_hits ->> 'first_1')::int) AS hits_first_1,
        SUM((positional_hits ->> 'first_2')::int) AS hits_first_2,
        SUM((positional_hits ->> 'first_3')::int) AS hits_first_3,
        SUM((positional_hits ->> 'first_4')::int) AS hits_first_4,
        SUM((positional_hits ->> 'first_5')::int) AS hits_first_5
    FROM base
    GROUP BY cohort_version_id, cohort_code, cohort_version, effective_from,
             model_code, draw_type
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
    COALESCE(t.turbo, '{}'::jsonb) AS turbo
FROM agg a
LEFT JOIN turbo_json t
  ON t.cohort_version_id = a.cohort_version_id
 AND t.model_code = a.model_code
 AND t.draw_type = a.draw_type;
